"""选定科学结果的只读导出快照、完整精度CSV/JSON与原子目录发布。"""

from concurrent.futures import CancelledError
from dataclasses import dataclass, field, replace
import csv
import hashlib
import json
from pathlib import Path, PurePosixPath, PureWindowsPath
import shutil
import tempfile
from threading import Event
from typing import Callable
from uuid import UUID

from ai_physics_tracker.application.adopted_measurement import AdoptedMeasurementSnapshot
from ai_physics_tracker.application.pendulum_analysis import (
    ANALYSIS_KIND, COLUMNS as ANALYSIS_COLUMNS, analysis_signature,
    load_analysis_result, resolved_analysis_config, reconstruction_input_from_payload,
)
from ai_physics_tracker.application.pendulum_fit import FIT_KIND, load_fit_result
from ai_physics_tracker.application.project_session import ProjectSession, ProjectSessionError
from ai_physics_tracker.application.teacher_models import teacher_model_availability
from ai_physics_tracker.domain.pendulum import ROLE_ORDER
from ai_physics_tracker.domain.scientific_result import ScientificResult
from ai_physics_tracker.domain.pendulum_reconstruction import reconstruct_pendulum
from ai_physics_tracker.domain.types import canonical_json_digest, utc_now
from ai_physics_tracker.infrastructure.project_repository import ProjectRepository
from ai_physics_tracker.infrastructure.scientific_payload import read_scientific_payload


@dataclass(frozen=True)
class ScientificExport:
    """后台验证后的单个历史身份；不拼接另一轮测量或当前候选。"""

    record: ScientificResult
    payload: dict
    current: bool
    reason: str | None
    project_name: str
    source_run: dict = field(default_factory=dict)


def _check_cancel(cancel: Event) -> None:
    if cancel.is_set():
        raise CancelledError()


def prepare_scientific_export(session: ProjectSession, result_id: UUID, *,
                              allow_historical: bool = False) -> ScientificExport:
    """worker读取并校验选定结果；默认拒绝不再匹配当前输入的历史产物。"""
    record = next((r for r in session.project.scientific_results if r.result_id == result_id), None)
    if record is None or record.kind not in (ANALYSIS_KIND, FIT_KIND):
        raise ProjectSessionError("Select a saved kinematics or ODE fit result")
    loader = load_analysis_result if record.kind == ANALYSIS_KIND else load_fit_result
    payload, current, reason = loader(session, record)
    if record.kind == ANALYSIS_KIND:
        # load_analysis_result把输入变化与旧配置都投影成stale；历史导出仍必须
        # 验证自身冻结配置，不能用Allow historical绕过损坏的身份。
        derivative = payload["config"]["angular"]["derivative"]
        expected = resolved_analysis_config(record.extra_fields["end_frame_index"],
            sg_window=derivative["window_frames"], sg_polyorder=derivative["polyorder"])
        measurement = payload["measurement"]
        digest = canonical_json_digest(measurement)
        snapshot = AdoptedMeasurementSnapshot(record.experiment_id, UUID(measurement["active_run_id"]), measurement, digest)
        if (payload["config"] != expected or record.extra_fields["config"] != expected
                or record.payload.columns != ANALYSIS_COLUMNS
                or record.extra_fields["measurement_digest"] != digest
                or analysis_signature(snapshot, record.extra_fields["end_frame_index"],
                    sg_window=derivative["window_frames"], sg_polyorder=derivative["polyorder"]) != record.input_digest):
            raise ProjectSessionError("Saved analysis identity/configuration is invalid")
    if not current and not allow_historical:
        raise ProjectSessionError(f"Result is stale: {reason}. Recompute, or explicitly allow historical export.")
    frames = payload["measurement"]["frames"]
    rows = payload["rows"]
    if (len(rows) != len(frames) or not rows
            or [r["frame_index"] for r in rows] != [r["frame_index"] for r in frames]):
        raise ProjectSessionError("Saved result rows do not match their frozen source frames")
    run = next((r for r in session.tracking_runs()
                if str(r.run_id) == payload["measurement"]["active_run_id"]), None)
    source_run = {}
    if run is not None:
        if (run.extra_fields.get("input_digest") != payload["measurement"]["candidate_input_digest"]
                or run.extra_fields.get("prediction_sha256") != payload["measurement"]["prediction_sha256"]):
            raise ProjectSessionError("Source run identity no longer matches the frozen measurement")
        source_run = {"run_id": str(run.run_id), "engine": run.engine, "engine_version": run.engine_version,
                      "created_at": run.created_at.isoformat(), "config": run.config,
                      "model_snapshot": run.model_snapshot, "input_digest": run.extra_fields["input_digest"]}
        source_run["model_id"] = run.config.get("model_id")
        source_run["model_metadata_scope"] = "Original run id/checkpoint/config; editable current model references are not substituted."
    return ScientificExport(record, payload, current, reason, session.project.name, source_run)


def export_rows(snapshot: ScientificExport) -> tuple[list[str], list[dict], dict]:
    """CSV扁平化；float由csv原样repr写出，嵌套QC数组以JSON单元格保存。"""
    columns = [c.name for c in snapshot.record.payload.columns if c.name != "points_by_role"]
    units = {c.name: c.unit for c in snapshot.record.payload.columns if c.name != "points_by_role"}
    point_fields = ("pixel_x", "pixel_y", "confidence", "source", "source_detail", "visibility", "quality_flags")
    for role in ROLE_ORDER:
        for field in point_fields:
            name = f"{role}_{field}"
            columns.append(name)
            units[name] = "px" if field in ("pixel_x", "pixel_y") else None
        columns.append(f"{role}_missing_reason")
        units[f"{role}_missing_reason"] = None
    measurement = snapshot.payload["measurement"]
    frozen = {r["frame_index"]: r for r in measurement["frames"]}
    auxiliary = {}
    if "auxiliary_qc_reasons" not in columns:
        columns.append("auxiliary_qc_reasons")
        units["auxiliary_qc_reasons"] = None
        reconstruction = reconstruct_pendulum(reconstruction_input_from_payload(measurement, canonical_json_digest(measurement)))
        auxiliary = {r.frame_index: list(r.auxiliary_qc_reasons) for r in reconstruction.frames}
    rows = []
    for row in snapshot.payload["rows"]:
        flat = {name: row.get(name) for name in columns}
        for role in ROLE_ORDER:
            point = frozen[row["frame_index"]]["points_by_role"][role]
            for field in point_fields:
                flat[f"{role}_{field}"] = point.get(field) if point else None
            flat[f"{role}_missing_reason"] = frozen[row["frame_index"]]["missing_reasons_by_role"][role]
        if auxiliary:
            flat["auxiliary_qc_reasons"] = auxiliary[row["frame_index"]]
        rows.append(flat)
    return columns, rows, units


def _json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def write_export_files(snapshot: ScientificExport, folder: Path, cancel: Event) -> None:
    """只写任务拥有的暂存目录；所有文件完成后由调用方发布。"""
    _check_cancel(cancel)
    columns, rows, units = export_rows(snapshot)
    with (folder / "observations.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            _check_cancel(cancel)
            writer.writerow({key: json.dumps(value, ensure_ascii=False, allow_nan=False)
                             if isinstance(value, (list, dict)) else value for key, value in row.items()})
    _json(folder / "result.json", snapshot.payload)
    provenance = {
        "contract": "publication-scientific-export-v1", "exported_at": utc_now().isoformat(),
        "project_name": snapshot.project_name, "result_id": str(snapshot.record.result_id),
        "experiment_id": str(snapshot.record.experiment_id), "result_created_at": snapshot.record.created_at.isoformat(),
        "kind": snapshot.record.kind, "core_version": snapshot.record.core_version,
        "execution_status": snapshot.record.execution_status,
        "current_at_export": snapshot.current, "historical_reason": snapshot.reason,
        "input_digest": snapshot.record.input_digest, "source_payload_sha256": snapshot.record.payload.sha256,
        "columns": columns, "units": units,
        "precision": "Full stored IEEE-754 values; display rounding is not applied. Blank CSV cells mean missing values.",
        "energy": "Reference energy is a proxy in s^-2, not joules or a fitted raw physical energy.",
        "measurement": {k: v for k, v in snapshot.payload["measurement"].items() if k != "frames"},
        "source_run": snapshot.source_run,
        "timing_basis": "Source frame / frozen fps_nominal; release-relative time subtracts the frozen release time. Legacy payloads do not freeze session timing approval; recorded point source_detail is retained.",
        "parameter_units": {"alpha1_s_inv": "s^-1", "alpha2_rad_inv": "rad^-1", "omega2_s_inv2": "s^-2"},
        "config": snapshot.payload["config"],
        "scope": "One saved result and its frozen adopted measurement; candidate previews are excluded.",
    }
    _json(folder / "provenance.json", provenance)


def publish_scientific_export(snapshot: ScientificExport, destination: Path, cancel: Event,
                               render: Callable[[ScientificExport, Path, Event], None] | None = None) -> Path:
    """新目录事务；不覆盖既有目录，取消/失败只清理本次暂存。"""
    destination = _new_destination(destination)
    staging = Path(tempfile.mkdtemp(prefix=".scientific-export-", dir=destination.parent))
    try:
        write_export_files(snapshot, staging, cancel)
        if render is not None:
            render(snapshot, staging, cancel)
        _check_cancel(cancel)
        files = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in staging.iterdir() if p.is_file()}
        _json(staging / "files.json", {"sha256": files})
        _check_cancel(cancel)
        if destination.exists():
            raise FileExistsError("Export destination appeared during preparation")
        staging.rename(destination)
        return destination
    finally:
        if staging.exists():
            shutil.rmtree(staging)


def _new_destination(destination: Path) -> Path:
    destination = destination.absolute()
    if (destination.exists() or destination.is_symlink()):
        raise FileExistsError("Choose a NEW output directory; existing files are never overwritten")
    if (not destination.parent.is_dir() or PureWindowsPath(destination.name).is_reserved()
            or destination.name.endswith((".", " ")) or any(c in '<>:"\\|?*' for c in destination.name)):
        raise ValueError("Choose an existing parent and a Windows-safe directory name")
    return destination


def _file_digest(path: Path, cancel: Event) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            _check_cancel(cancel)
            digest.update(block)
    return digest.hexdigest()


def save_portable_copy(session: ProjectSession, destination: Path, cancel: Event) -> Path:
    """复用Save As保存完整项目，再托管外部视频；原会话和原工程保持不变。"""
    if session.project_root is None:
        raise ProjectSessionError("Save the project before making a portable copy")
    destination = _new_destination(destination)
    root = session.project_root.resolve()
    if destination.resolve() == root or destination.resolve().is_relative_to(root):
        raise ValueError("Portable copy must be outside the source project")
    owner = Path(tempfile.mkdtemp(prefix=".portable-project-", dir=destination.parent))
    stage = owner / "project"
    try:
        _check_cancel(cancel)
        # 既有Save As事务复制科学payload、模型manifest与engine历史；复制阶段
        # 沿用仓储的不可中断边界，取消在其后拒绝发布，不会生成半成品目标。
        candidate = session.detached()
        candidate.save_as(stage)
        for model in candidate.project.model_references:
            _check_cancel(cancel)
            state, reason = teacher_model_availability(stage, model)
            if state == "unavailable":
                raise ProjectSessionError(f"Portable model files are unavailable: {reason}")
        for result in candidate.project.scientific_results:
            _check_cancel(cancel)
            if result.payload is not None:
                read_scientific_payload(stage, result.payload)
        videos = []
        for video in session.project.videos:
            _check_cancel(cancel)
            source = session.video_path(video)
            if source is None or not source.is_file():
                raise ProjectSessionError(f"Relink missing video before portable copy: {video.display_name}")
            expected_sha = video.sha256 or _file_digest(source, cancel)
            if video.file_path is None or not (stage / video.file_path).is_file():
                relative = PurePosixPath(f"videos/{video.video_id}{source.suffix.lower()}")
                target = stage / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                with source.open("rb") as incoming, target.open("xb") as outgoing:
                    while block := incoming.read(1024 * 1024):
                        _check_cancel(cancel)
                        outgoing.write(block)
                video = replace(video, file_path=relative)
            if _file_digest(stage / video.file_path, cancel) != expected_sha:
                raise ProjectSessionError(f"Video content changed during portable copy: {video.display_name}")
            videos.append(video)
        ProjectRepository().save(stage, replace(candidate.project, videos=tuple(videos)))
        _check_cancel(cancel)
        if destination.exists():
            raise FileExistsError("Portable destination appeared during preparation")
        stage.rename(destination)
        return destination
    finally:
        if owner.exists():
            shutil.rmtree(owner)
