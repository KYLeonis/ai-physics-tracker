"""Prepare isolated P6.5 projects and rerun the frozen P011 analysis; never train."""

import argparse
from dataclasses import asdict, replace
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import platform
import subprocess
from threading import Event
import tomllib
from uuid import uuid4

from ai_physics_tracker.application.chart_data import build_chart_data
from ai_physics_tracker.application.project_session import ProjectSession
from ai_physics_tracker.application.signal_analysis_job import (
    SignalSelection, prepare_signal_analysis, run_signal_analysis,
)
from ai_physics_tracker.application.video import VideoStreamInfo
from ai_physics_tracker.application.video_timing import TimingReport
from ai_physics_tracker.domain.angular import PendulumReference
from ai_physics_tracker.domain.function_fit import FitParameter, FitSpec
from ai_physics_tracker.domain.project import Project
from ai_physics_tracker.domain.recurrence import RecurrenceSpec
from ai_physics_tracker.infrastructure.ffprobe_timing import FFprobeTimingProbe
from ai_physics_tracker.infrastructure.project_repository import ProjectRepository


REPOSITORY = Path(__file__).resolve().parents[1]
REFERENCE_PROTOCOL_SHA256 = "64ccd90b9afe753bf8edd71be7316a95afe81bcc5b17dbf89e6e822e4353e63e"
FIT = FitSpec("c+A*exp(-beta*t)*cos(Omega*t+phi)", (
    FitParameter("c", 0), FitParameter("A", .5), FitParameter("beta", .05),
    FitParameter("Omega", 6), FitParameter("phi", 0),
))
PERIOD_FORMULAS = (("T", "2*pi/abs(Omega)"),)


def verified_file(path: Path, expected: str) -> str:
    """Reject a missing or changed reference before creating any output."""
    with path.open("rb") as stream:
        actual = hashlib.file_digest(stream, "sha256").hexdigest()
    if actual != expected:
        raise ValueError(f"Frozen reference fingerprint mismatch: {path}")
    return actual


def write_json(path: Path, payload: dict) -> None:
    """Create a new evidence file, refusing to overwrite a previous run."""
    with path.open("x", encoding="utf-8") as stream:
        json.dump(payload, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def reference_files(root: Path) -> tuple[dict, dict, dict[Path, str]]:
    """Verify the original protocol and every input it identifies."""
    verified_file(root / "benchmark-protocol.json", REFERENCE_PROTOCOL_SHA256)
    protocol = json.loads((root / "benchmark-protocol.json").read_text(encoding="utf-8"))
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    parameters = Path(manifest["source_parameters"]["path"])
    verified_file(parameters, protocol["source_parameters_sha256"])
    toml = tomllib.loads(parameters.read_text(encoding="utf-8"))
    files = {
        root / "benchmark-protocol.json": REFERENCE_PROTOCOL_SHA256,
        root / "benchmark-project" / "project.json": protocol["project_file_sha256"],
        root / "human-period-reference.json": protocol["human_reference_sha256"],
        Path(manifest["clip"]["path"]): protocol["clip_sha256"],
        Path(manifest["source"]["path"]): manifest["source"]["sha256"],
        parameters: protocol["source_parameters_sha256"],
        parameters.parent / toml["derived"]["video"]["csv_filename"]: protocol["source_dlc_csv_sha256"],
    }
    for path, expected in files.items():
        verified_file(path, expected)
    # Also detect accidental writes to companion metadata during this run.
    for path in (root / "manifest.json", root / "source-frame-map.csv"):
        with path.open("rb") as stream:
            files[path] = hashlib.file_digest(stream, "sha256").hexdigest()
    return protocol, manifest, files


def authorize(session: ProjectSession, report: TimingReport) -> None:
    """Apply the same measured timing and ADR-0024 budget checks as the GUI."""
    video = session.project.videos[0]
    session.confirm_video_timing(video.video_id, report)
    if report.status == "near_cfr":
        session.accept_approximate_timing(video.video_id, report, automatic=True)
    elif report.status != "cfr":
        raise ValueError(f"Timing does not allow analysis: {report.reason}")


def prepare_manual_project(reference: Project, report: TimingReport, destination: Path) -> Project:
    """Create new IDs and calibration, carrying over no labels, runs or results."""
    repository = ProjectRepository()
    session = ProjectSession.start(repository, "P6.5 P011 — manual annotation / new AI")
    source = reference.videos[0]
    info = VideoStreamInfo(source.width_px, source.height_px, source.fps_container,
                           source.frame_count, source.container_format, report.status)
    video, _ = session.register_preview_video(Path(source.original_path), info, sha256=source.sha256)
    authorize(session, report)
    track = session.add_track(video.video_id, "marker_tip — dark dot at block centre")
    calibration = next(c for c in reference.calibrations
                       if c.calibration_id == reference.active_calibration_by_video[source.video_id])
    session.add_calibration(replace(calibration, calibration_id=uuid4(), video_id=video.video_id))
    project = replace(session.project, ui_state={"workflow": {
        "selected_video_id": str(video.video_id), "selected_track_id": str(track.track_id),
    }})
    saved = repository.create_from_project(destination, project)
    if saved.observations or saved.derived or saved.tracking_runs:
        raise ValueError("New AI project must start with no labels, results or training")
    return saved


def run_reference_analysis(reference: Project, report: TimingReport, destination: Path,
                           protocol: dict, human_mean_s: float) -> dict:
    """Recompute through application jobs, then verify actual save and reload."""
    repository = ProjectRepository()
    project = replace(reference, name="P6.5 P011 — archived DLC analysis regression", derived=())
    repository.create_from_project(destination, project)
    session = ProjectSession.load(repository, destination)
    authorize(session, report)
    track = session.tracks[0]
    session.compute_kinematics(track.track_id)
    session.compute_angular(track.track_id, reference=PendulumReference(tuple(protocol["calibration"]["pivot_px"])))
    selection = SignalSelection(track.track_id, "theta", *protocol["interval_frames_inclusive"])
    request = protocol["period_request"]
    recurrence = RecurrenceSpec(request["reference_level_rad"], request["direction"],
                                request["hysteresis"], request["min_separation_s"], wrapped_angle=True)
    for spec, formulas in ((FIT, PERIOD_FORMULAS), (recurrence, ())):
        result = run_signal_analysis(prepare_signal_analysis(session, selection, spec, formulas), Event())
        if result.record is None:
            raise ValueError(f"Analysis failed without publishing a result: {result.fit_outcome}")
        session.apply_analysis_result(result)
    saved = session.save()
    reloaded = ProjectSession.load(repository, destination)
    if saved != reloaded.project:
        raise ValueError("Analysis changed across save and reload")
    charts = {}
    for kind in ("theta_t", "omega_t", "alpha_t", "theta_omega"):
        chart = build_chart_data(reloaded.project, track.video_id, (track.track_id,), kind)
        if not chart.series or any(series.status != "valid" for series in chart.series):
            raise ValueError(f"Chart unavailable after reload: {kind}: {chart.messages}")
        charts[kind] = {"points": [len(series.frames) for series in chart.series],
                        "x_unit": chart.x_unit, "y_unit": chart.y_unit}
    return analysis_summary(reloaded, human_mean_s) | {"save_reload_equal": True, "charts": charts}


def analysis_summary(session: ProjectSession, human_mean_s: float) -> dict:
    """Report the two comparisons separately, preserving every measured interval."""
    track = session.tracks[0]
    fitted = session.saved_derived_data(track.track_id, "function_fit_theta").extra_fields["analysis"]
    recurrence = session.saved_derived_data(track.track_id, "signal_recurrence_theta").extra_fields["analysis"]
    fit_summary = fitted["summary"]
    fit_period = fit_summary["result_formulas"][0]["value"]
    mean_period = recurrence["summary"]["mean_interval_s"]
    if fit_period is None or mean_period is None:
        raise ValueError("A comparison requires both a fit period and measured intervals")
    fit_error = abs(fit_period / human_mean_s - 1)
    recurrence_error = abs(mean_period / human_mean_s - 1)
    return {
        "human_mean_s": human_mean_s,
        "fit_period_s": fit_period, "fit_relative_difference": fit_error,
        "fit_passed": fit_error <= .05, "fit_summary": fit_summary,
        "recurrence_mean_s": mean_period, "recurrence_relative_difference": recurrence_error,
        "recurrence_passed": recurrence_error <= .05, "recurrence_summary": recurrence["summary"],
        "selection": fitted["selection"], "fit_sample_count": len(fitted["samples"]),
        "observations": len(session.project.observations),
        "limitations": ["Archived DLC is not manual ground truth", "Same-video reference is not independent clock calibration",
                        "Conditional SE/local intervals do not include systematic errors or prove model suitability"],
    }


def prepare(reference_root: Path, output: Path) -> dict:
    """Freeze inputs/settings before calculation and prepare both evidence lanes."""
    reference_root, output = reference_root.resolve(), output.resolve()
    if output.exists() or output.is_relative_to(reference_root):
        raise FileExistsError("Use a new output directory outside the frozen reference")
    protocol, manifest, files = reference_files(reference_root)
    reference = ProjectRepository().load(reference_root / "benchmark-project")
    report = FFprobeTimingProbe().probe(Path(manifest["clip"]["path"]))
    # Validate measured timing before creating output, not merely the old report.
    validation = ProjectSession(ProjectRepository(), reference)
    authorize(validation, report)
    human = json.loads((reference_root / "human-period-reference.json").read_text(encoding="utf-8"))
    if human["confirmed_by_user"] is not True or len(human["events"]) < 6:
        raise ValueError("At least five independently reviewed human intervals are required")
    midpoints = [(event["clip_lower_pts_s"] + event["clip_upper_pts_s"]) / 2 for event in human["events"]]
    human_mean_s = (midpoints[-1] - midpoints[0]) / (len(midpoints) - 1)
    output.mkdir(parents=True, exist_ok=False)
    frozen = {
        "source_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPOSITORY, text=True).strip(),
        "preparation_script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "inputs": {str(path): expected for path, expected in files.items()},
        "python": platform.python_version(), "platform": platform.platform(),
        "packages": {name: version(name) for name in ("numpy", "scipy", "PySide6", "torch", "deeplabcut")},
        "timing_report": asdict(report), "original_protocol": protocol,
        "fit": asdict(FIT), "result_formulas": PERIOD_FORMULAS,
        "human_mean_s": human_mean_s, "relative_difference_limit": .05,
        "training": {"maximum_starts": 2, "mode": "restart", "epochs": 50, "batch_size": 8,
                     "device": "auto", "manual_frames": 20, "fixed_validation_frames": 4,
                     "failed_or_cancelled_starts_count": True},
    }
    write_json(output / "protocol.json", frozen)
    manual = prepare_manual_project(reference, report, output / "manual-project")
    summary = run_reference_analysis(reference, report, output / "reference-project", protocol, human_mean_s)
    summary["manual_project_id"] = str(manual.project_id)
    summary["training_starts"] = 0
    for path, expected in files.items():
        verified_file(path, expected)
    summary["original_fingerprints_unchanged"] = True
    write_json(output / "reference-result.json", summary)
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference-root", type=Path, default=REPOSITORY / "experiment/p63-reference")
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    result = prepare(arguments.reference_root, arguments.output)
    print(json.dumps({key: result[key] for key in (
        "fit_period_s", "fit_relative_difference", "fit_passed", "recurrence_mean_s",
        "recurrence_relative_difference", "recurrence_passed", "save_reload_equal", "training_starts",
    )}, indent=2))
