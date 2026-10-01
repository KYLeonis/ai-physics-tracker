"""只读归档θ输入，调用产品core重拟合；expected/golden/科研原件均不改写。"""

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import asdict
import csv
import gzip
from hashlib import sha256
import json
from math import degrees, isfinite, radians
import multiprocessing
import os
from pathlib import Path
import sys
from time import perf_counter

import numpy as np
import scipy

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from ai_physics_tracker.domain.angular_analysis import AngularSeries, LEGACY
from ai_physics_tracker.domain.pendulum_ode import (
    InitialCondition, M0, M1, ObjectiveRequest, PendulumParameters, evaluate_trajectory,
    fit_valid_indices,
)
from ai_physics_tracker.domain.pendulum_fit import fit_pendulum

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "publication/evidence"
TOLERANCES = {
    "alpha1_s_inv": (1e-5, 1e-3), "alpha2_rad_inv": (1e-5, 1e-3),
    "omega2_s_inv2": (1e-4, 1e-5), "rmse_deg": (1e-3, 1e-3), "optimizer_cost": (1e-7, 1e-3),
}


def read_request(video_id: str, prov_root: Path | None) -> tuple[ObjectiveRequest, str]:
    """解析边界校验hash、bool与rad单位；不是原四点重建或训练验证。"""
    manifest = json.loads((EVIDENCE / "source-map.json").read_text(encoding="utf-8"))
    source = next(s for s in manifest["sources"] if s["id"] == f"trajectory-{video_id}")
    if prov_root is None:
        local = next(s for s in manifest["local_files"] if s["path"].endswith(f"{video_id}-effective.csv.gz"))
        path, expected_sha = EVIDENCE / local["path"], local["sha256"]
    else:
        path, expected_sha = prov_root / source["path"], source["sha256"]
    digest = sha256(path.read_bytes()).hexdigest()
    if digest != expected_sha:
        raise ValueError(f"archived input hash mismatch: {video_id}")
    with gzip.open(path, "rt", encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    metadata = json.loads((EVIDENCE / "golden/inputs24.json").read_text(encoding="utf-8"))
    item = next(row for row in metadata if row["video_id"] == video_id)
    if any(row["geometry_valid"] not in ("True", "False") for row in rows):
        raise ValueError("archived QC flags are not true booleans")
    angles = [radians(float(row["theta_observed_deg"])) for row in rows]
    qc = tuple(row["geometry_valid"] == "True" for row in rows)
    weights = [float(row["marker_likelihood"]) for row in rows]
    series = AngularSeries(digest, tuple(int(row["frame_index_0based"]) for row in rows),
        tuple(float(row["time_s"]) for row in rows),
        tuple(value if isfinite(value) else None for value in angles), qc, item["fps"])
    request = ObjectiveRequest(series,
        tuple(float(np.clip(w, .05, 1.)) if isfinite(w) else None for w in weights),
        InitialCondition(item["theta0_rad"], item["omega0_rad_s"], "archived_toml"),
        item["release_frame"], series.frame_indices[-1], item["length_m"], profile_id=LEGACY)
    return request, digest


def regression_case(video_id: str, prov_root: Path | None) -> list[dict]:
    """同视频顺序M0→M1 warm；不同视频可独立并行。"""
    started = perf_counter()
    request, source_sha = read_request(video_id, prov_root)
    with (EVIDENCE / "golden/formal-fit48.csv").open(encoding="utf-8-sig", newline="") as stream:
        expected = {row["model"]: row for row in csv.DictReader(stream) if row["video_id"] == video_id}
    m0 = fit_pendulum(request, M0)
    fits = (m0, fit_pendulum(request, M1, warm_start=m0))
    report = []
    for fit in fits:
        actual = {} if fit.parameters is None else asdict(fit.parameters)
        if fit.trajectory is not None:
            actual["rmse_deg"] = degrees(fit.trajectory.rmse_rad)
        if fit.selected_start_index is not None:
            actual["optimizer_cost"] = fit.starts[fit.selected_start_index].cost_rad2
        differences = {}
        for field, (atol, rtol) in TOLERANCES.items():
            reference = float(expected[fit.model][field])
            value = actual.get(field)
            error = None if value is None else abs(value-reference)
            differences[field] = {"expected": reference, "actual": value, "absolute_error": error,
                                  "tolerance": atol+rtol*abs(reference),
                                  "passed": value is not None and error <= atol+rtol*abs(reference)}
        source = next(s for s in json.loads((EVIDENCE / "source-map.json").read_text(encoding="utf-8"))["sources"]
                      if s["id"] == f"trajectory-{video_id}")
        path = prov_root/source["path"] if prov_root is not None else EVIDENCE/f"golden/{video_id}-effective.csv.gz"
        with gzip.open(path, "rt", encoding="utf-8-sig", newline="") as stream:
            archived = [radians(float(row[f"theta_predicted_deg__{fit.model}"])) for row in csv.DictReader(stream)]
        # E2固定归档参数验证forward；重新拟合后的预测差仅作E3诊断。
        reference = expected[fit.model]
        fixed = evaluate_trajectory(request, fit.model, PendulumParameters(
            float(reference["alpha1_s_inv"]), float(reference["omega2_s_inv2"]),
            float(reference["alpha2_rad_inv"])))
        e2_error = None if fixed.status != "success" else float(np.max(
            np.abs(np.asarray(fixed.prediction.theta_rad)-archived)))
        e2_rmse_error = None if fixed.status != "success" else abs(degrees(fixed.rmse_rad)-float(reference["rmse_deg"]))
        refit_error = None if fit.trajectory is None else float(np.max(
            np.abs(np.asarray(fit.trajectory.prediction.theta_rad)-archived)))
        identity = {
            "release_frame_used_0based": request.release_frame_index,
            "frame_count_post_release": len(request.series.frame_indices),
            "frame_count_geometry_valid": len(fit_valid_indices(request)),
            "optimization_point_count": len(fit.sample_frames),
        }
        identity_checks = {key: {"expected": int(reference[key]), "actual": value,
                                "passed": value == int(reference[key])} for key, value in identity.items()}
        selected = None if fit.selected_start_index is None else fit.starts[fit.selected_start_index]
        report.append({"video_id": video_id, "model": fit.model, "status": fit.status, "reason": fit.reason,
            "source_sha256": source_sha, "input_digest": fit.input_digest,
            "comparability_digest": fit.comparability_digest, "differences": differences,
            "identity_checks": identity_checks,
            "archived_diagnostics": {key: reference[key] for key in (
                "fit_status", "optimizer_nfev", "jacobian_rank", "jacobian_condition_number")},
            "selected_diagnostics": None if selected is None else {
                "nfev": selected.nfev, "jacobian_rank": selected.jacobian_rank,
                "jacobian_condition": selected.jacobian_condition},
            "refit_prediction_max_abs_rad": refit_error,
            "e2_prediction_max_abs_rad": e2_error, "e2_rmse_abs_deg": e2_rmse_error,
            "e2_passed": e2_error is not None and e2_error <= 1e-5 and e2_rmse_error <= 1e-4,
            "e3_passed": fit.status == reference["fit_status"] == "success"
                and all(row["passed"] for row in differences.values())
                and all(row["passed"] for row in identity_checks.values()),
            "warnings": fit.warnings, "starts": [asdict(start) for start in fit.starts],
            "seed": {k: v for k, v in asdict(fit.seed).items() if k != "source_frames"},
            "seed_frame_count": len(fit.seed.source_frames), "sample_count": len(fit.sample_frames),
            "sample_digest": sha256(json.dumps([fit.sample_frames, fit.sample_time_s]).encode()).hexdigest(),
            "config": fit.config, "elapsed_case_s": perf_counter()-started})
    return report


def write_report(path: Path, rows: list[dict], requested: list[str], errors: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"contract": "publication-fit-regression-v1", "scope": "legacy effective-release refit",
        "numpy_version": np.__version__, "scipy_version": scipy.__version__, "python_version": sys.version,
        "requested_videos": requested, "completed_fit_count": len(rows), "errors": errors,
        "e2_pass_count": sum(row["e2_passed"] for row in rows),
        "e3_pass_count": sum(row["e3_passed"] for row in rows), "results": sorted(rows, key=lambda r: (r["video_id"], r["model"])),
        "complete": len(rows) == 2*len(requested) and not errors}
    temporary = path.with_suffix(path.suffix+".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False)+"\n", encoding="utf-8")
    os.replace(temporary, path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prov-root", type=Path)
    parser.add_argument("--video-id", action="append")
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.workers < 1:
        parser.error("workers must be positive")
    protected = (EVIDENCE/"golden", ROOT/"publication/profiles")
    if any(args.output.resolve().is_relative_to(p.resolve()) for p in protected) or (
            args.output.resolve() == (EVIDENCE/"source-map.json").resolve()) or (
            args.prov_root is not None and args.output.resolve().is_relative_to(args.prov_root.resolve())):
        parser.error("output must not overwrite frozen inputs/profiles or external research assets")
    videos = args.video_id or ([r["video_id"] for r in json.loads((EVIDENCE/"golden/inputs24.json").read_text(encoding="utf-8"))]
                               if args.prov_root is not None else ["P011", "P014"])
    rows, errors = [], {}
    with ProcessPoolExecutor(max_workers=args.workers, mp_context=multiprocessing.get_context("spawn")) as executor:
        jobs = {executor.submit(regression_case, video, args.prov_root): video for video in videos}
        for job in as_completed(jobs):
            video = jobs[job]
            try:
                result = job.result()
                rows.extend(result)
                print(json.dumps({"video_id": video, "e3_passed": [r["e3_passed"] for r in result],
                                  "elapsed_s": round(result[-1]["elapsed_case_s"], 1)}), flush=True)
            except (OSError, ValueError, KeyError, RuntimeError, StopIteration) as error:
                errors[video] = str(error)
                print(json.dumps({"video_id": video, "error": str(error)}), flush=True)
            write_report(args.output, rows, videos, errors)
    return 0 if not errors and len(rows) == 2*len(videos) and all(r["e2_passed"] and r["e3_passed"] for r in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
