"""P1.4 联合推理请求与 candidate 结果的 Qt-free 验证边界。"""

from dataclasses import dataclass, replace
from pathlib import Path
from uuid import UUID, uuid4

from ai_physics_tracker.application.project_session import ProjectSession, ProjectSessionError
from ai_physics_tracker.application.teacher_models import (
    model_effective_state, resolve_pose_cfg_path,
)
from ai_physics_tracker.application.tracking_types import InferenceParams
from ai_physics_tracker.domain.pendulum import ROLE_ORDER
from ai_physics_tracker.domain.tracking_run import (
    TrackingRun, create_tracking_run, mark_run_completed,
)
from ai_physics_tracker.domain.types import canonical_json_digest
from ai_physics_tracker.infrastructure.dlc_predictions import read_joint_raw_predictions
from ai_physics_tracker.infrastructure.hashing import file_sha256

RESULT_SECTION = "experiment_inference"


@dataclass(frozen=True)
class ExperimentInferenceRequest:
    run_id: str
    experiment_id: str
    video_id: str
    model_id: str
    video_path: str
    video_sha256: str
    config_path: str
    config_sha256: str
    checkpoint_path: str
    checkpoint_sha256: str
    pose_cfg_path: str
    pose_cfg_sha256: str
    frame_count: int
    fps_nominal: float
    role_bindings: tuple[tuple[str, str], ...]
    bodypart_mapping: tuple[tuple[str, str], ...]
    model_manifest_hash: str
    input_digest: str
    expected_runtime_versions: dict[str, str]
    expected_device: str
    min_confidence: float
    batch_size: int

    def to_payload(self) -> dict[str, object]:
        return {
            **self.__dict__,
            "role_bindings": [list(pair) for pair in self.role_bindings],
            "bodypart_mapping": [list(pair) for pair in self.bodypart_mapping],
        }


def _capture_input(
    session: ProjectSession, experiment_id: UUID, model_id: UUID,
) -> tuple[dict[str, object], object, object, Path, Path, Path, Path]:
    root = session.project_root
    if root is None:
        raise ProjectSessionError("Save the project before joint inference")
    root = root.resolve()
    experiment = session.pendulum_experiment(experiment_id)
    model = next((item for item in session.project.model_references
                  if item.model_id == model_id), None)
    if model is None:
        raise ProjectSessionError(f"unknown model_id: {model_id}")
    state, reason = model_effective_state(root, model)
    if state != "compatible":
        raise ProjectSessionError(f"Model is not compatible: {state}; {reason or 'run self-test'}")
    runtime = (model.self_test_evidence or {}).get("runtime")
    if not isinstance(runtime, dict):
        raise ProjectSessionError("Compatible model has no runtime self-test evidence")
    versions = runtime.get("versions")
    if (not isinstance(versions, dict) or not versions.get("deeplabcut")
            or not versions.get("torch") or not runtime.get("device")):
        raise ProjectSessionError("Compatible model runtime evidence is incomplete")
    video = next((item for item in session.project.videos
                  if item.video_id == experiment.video_id), None)
    timeline = next((item for item in session.project.timelines
                     if item.video_id == experiment.video_id), None)
    if video is None or timeline is None or not session.can_measure(experiment.video_id):
        raise ProjectSessionError("Experiment video timing is unavailable or unconfirmed")
    video_path = session.video_path(video)
    if video_path is None or not video_path.is_file():
        raise ProjectSessionError("Experiment video file is unavailable")
    pose_cfg = resolve_pose_cfg_path(root, model)
    if pose_cfg is None or not pose_cfg.is_file():
        raise ProjectSessionError("Model pose configuration is unavailable")
    config = (root / model.config_path).resolve()
    checkpoint = (root / model.checkpoint_path).resolve()
    if any(not path.is_file() or not path.is_relative_to(root)
           for path in (config, checkpoint, pose_cfg.resolve())):
        raise ProjectSessionError("Model files are missing or outside the project")
    bindings = tuple((role, str(track_id))
                     for role, track_id in experiment.roles.by_role().items())
    captured: dict[str, object] = {
        "experiment_id": str(experiment_id),
        "video_id": str(video.video_id),
        "video_sha256": file_sha256(video_path),
        "frame_count": video.frame_count,
        "width_px": video.width_px,
        "height_px": video.height_px,
        "fps_nominal": timeline.fps_nominal,
        "timing_detail": session.measurement_timing_detail(video.video_id),
        "role_bindings": [list(pair) for pair in bindings],
        "model_id": str(model_id),
        "model_manifest_hash": model.manifest_hash,
        "bodypart_mapping": [list(pair) for pair in model.bodypart_mapping],
        "pose_cfg_sha256": file_sha256(pose_cfg),
        "runtime_versions": {
            "deeplabcut": str(versions["deeplabcut"]),
            "torch": str(versions["torch"]),
        },
        "runtime_device": str(runtime["device"]),
    }
    return captured, experiment, model, video_path, config, checkpoint, pose_cfg


def prepare_experiment_inference(
    session: ProjectSession, experiment_id: UUID, model_id: UUID,
    params: InferenceParams, *, run_id: UUID | None = None,
) -> tuple[TrackingRun, ExperimentInferenceRequest]:
    """登记唯一四成员 pending run；candidate 尚不接触 observations。"""

    captured, experiment, model, video, config, checkpoint, pose_cfg = _capture_input(
        session, experiment_id, model_id
    )
    members = experiment.roles.track_ids()
    if any(run.status in {"pending", "running"}
           and any(member in run.member_track_ids for member in members)
           for run in session.tracking_runs()):
        raise ProjectSessionError("This experiment already has an active engine task")
    resolved_id = run_id or uuid4()
    request = ExperimentInferenceRequest(
        run_id=str(resolved_id), experiment_id=str(experiment_id),
        video_id=str(experiment.video_id), model_id=str(model_id),
        video_path=str(video), video_sha256=str(captured["video_sha256"]),
        config_path=str(config), config_sha256=file_sha256(config),
        checkpoint_path=str(checkpoint), checkpoint_sha256=file_sha256(checkpoint),
        pose_cfg_path=str(pose_cfg), pose_cfg_sha256=str(captured["pose_cfg_sha256"]),
        frame_count=int(captured["frame_count"]), fps_nominal=float(captured["fps_nominal"]),
        role_bindings=tuple((str(role), str(track)) for role, track in captured["role_bindings"]),
        bodypart_mapping=model.bodypart_mapping,
        model_manifest_hash=model.manifest_hash,
        input_digest=canonical_json_digest(captured),
        expected_runtime_versions=dict(captured["runtime_versions"]),
        expected_device=str(captured["runtime_device"]),
        min_confidence=float(params.min_confidence), batch_size=params.batch_size,
    )
    run = create_tracking_run(
        video_id=experiment.video_id, member_track_ids=members, task_type="infer",
        engine_version=model.engine_version or "3.0.1",
        experiment_id=experiment_id, role_bindings=experiment.roles,
        config={"request_kind": "experiment-joint-inference-v1",
                "model_id": str(model_id), "input_digest": request.input_digest,
                "min_confidence": request.min_confidence,
                "requested_device": params.device, "device": request.expected_device,
                "batch_size": request.batch_size,
                "bodypart_mapping": [list(pair) for pair in request.bodypart_mapping]},
        model_snapshot=model.checkpoint_path, run_id=resolved_id,
    )
    session.record_tracking_run(run)
    return run, request


def verify_experiment_inference_result(
    session: ProjectSession, run: TrackingRun, request: ExperimentInferenceRequest,
    result: dict[str, object], job_dir: Path,
) -> TrackingRun:
    """协议级 read_result 后再验领域身份和 raw artifact，返回未激活的 run。"""

    if run.run_id != UUID(request.run_id) or run.status not in {"pending", "running"}:
        raise ProjectSessionError("Joint inference run identity or lifecycle changed")
    if (run.config.get("input_digest") != request.input_digest
            or run.config.get("min_confidence") != request.min_confidence
            or run.config.get("device") != request.expected_device
            or run.config.get("batch_size") != request.batch_size
            or run.config.get("bodypart_mapping") !=
            [list(pair) for pair in request.bodypart_mapping]):
        raise ProjectSessionError("Joint inference run configuration changed")
    if not any(item.run_id == run.run_id for item in session.tracking_runs()):
        raise ProjectSessionError("Joint inference run is no longer registered")
    captured, experiment, model, video, config, checkpoint, pose_cfg = _capture_input(
        session, UUID(request.experiment_id), UUID(request.model_id)
    )
    if (canonical_json_digest(captured) != request.input_digest
            or file_sha256(config) != request.config_sha256
            or file_sha256(checkpoint) != request.checkpoint_sha256
            or file_sha256(pose_cfg) != request.pose_cfg_sha256
            or str(video) != request.video_path
            or experiment.roles != run.role_bindings
            or model.bodypart_mapping != request.bodypart_mapping):
        raise ProjectSessionError("Joint inference inputs changed; candidate is stale")
    section = result.get(RESULT_SECTION)
    if not isinstance(section, dict):
        raise ProjectSessionError("Joint inference result section is missing")
    if (section.get("input_digest") != request.input_digest
            or section.get("video_sha256") != request.video_sha256
            or section.get("model_manifest_hash") != request.model_manifest_hash
            or section.get("bodypart_mapping") != [list(pair) for pair in request.bodypart_mapping]
            or section.get("frame_count") != request.frame_count
            or section.get("versions") != request.expected_runtime_versions
            or result.get("actual_device") != request.expected_device):
        raise ProjectSessionError("Joint inference result identity does not match request")
    relative = section.get("prediction_path")
    if not isinstance(relative, str) or not relative:
        raise ProjectSessionError("Joint inference prediction artifact is missing")
    folder = Path(job_dir).resolve()
    artifact = (folder / relative).resolve()
    if not artifact.is_relative_to(folder) or not artifact.is_file():
        raise ProjectSessionError("Joint inference artifact escapes its job directory")
    outputs = result.get("outputs")
    declared = next((item for item in outputs if isinstance(item, dict)
                     and item.get("path") == relative), None) if isinstance(outputs, list) else None
    if (declared is None or declared.get("size") != artifact.stat().st_size
            or declared.get("sha256") != file_sha256(artifact)):
        raise ProjectSessionError("Joint inference artifact hash is unverified")
    try:
        parsed = read_joint_raw_predictions(
            artifact, request.bodypart_mapping, frame_count=request.frame_count,
            expected_scorer=str(section["scorer"]),
        )
    except (ValueError, KeyError) as error:
        raise ProjectSessionError(f"Joint inference artifact is invalid: {error}") from error
    if (section.get("complete_count") != parsed.complete_count
            or section.get("missing_by_role") != dict(parsed.missing_by_role)):
        raise ProjectSessionError("Joint inference summary disagrees with raw artifact")
    project_root = session.project_root.resolve()
    if not artifact.is_relative_to(project_root):
        raise ProjectSessionError("Joint inference artifact is outside the project")
    completed = mark_run_completed(run)
    return replace(
        completed,
        engine_version=str(section.get("engine_version") or run.engine_version),
        extra_fields={
            **run.extra_fields,
            "prediction_path": artifact.relative_to(project_root).as_posix(),
            "prediction_sha256": declared["sha256"],
            "model_id": request.model_id,
            "input_digest": request.input_digest,
            "video_sha256": request.video_sha256,
            "verified_min_confidence": request.min_confidence,
            "scorer": section["scorer"],
            "complete_count": parsed.complete_count,
            "missing_by_role": dict(parsed.missing_by_role),
            "runtime_identity": {key: result.get(key) for key in
                                 ("python", "executable", "platform", "machine", "actual_device")},
        },
    )
