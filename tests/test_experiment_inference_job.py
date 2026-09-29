"""P1.4 S1：联合候选与当前实验、模型和原始 artifact 身份绑定。"""

import csv
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

import pytest

from ai_physics_tracker.application.experiment_inference_job import (
    RESULT_SECTION, prepare_experiment_inference, verify_experiment_inference_result,
)
from ai_physics_tracker.application.project_session import ProjectSession, ProjectSessionError
from ai_physics_tracker.application.tracking_types import InferenceParams
from ai_physics_tracker.application.video import VideoStreamInfo
from ai_physics_tracker.domain.pendulum import ROLE_ORDER, PendulumRoles
from ai_physics_tracker.domain.project import create_project
from ai_physics_tracker.domain.teacher_model import (
    ModelManifestEntry, TeacherModelReference, build_manifest_hash,
)
from ai_physics_tracker.domain.types import utc_now
from ai_physics_tracker.infrastructure.hashing import file_sha256
from ai_physics_tracker.infrastructure.project_repository import ProjectRepository


def _prepared(tmp_path, synthetic_video_path):
    session = ProjectSession(ProjectRepository(), create_project("joint infer"))
    video, _ = session.register_external_video(synthetic_video_path, VideoStreamInfo(
        width_px=64, height_px=48, fps_container=10.0, frame_count=12,
        container_format="avi", timing_status="cfr",
    ))
    tracks = {role: session.add_track(video.video_id, role) for role in ROLE_ORDER}
    roles = PendulumRoles(*(tracks[role].track_id for role in ROLE_ORDER))
    root = tmp_path / "project"
    session.save_as_publication(root, roles)
    experiment = session.pendulum_experiments()[0]
    model_id = uuid4()
    folder = root / "models" / str(model_id)
    folder.mkdir(parents=True)
    for name, data in (("config.yaml", b"engine: pytorch\n"),
                       ("snapshot-1.pt", b"checkpoint"),
                       ("pytorch_config.yaml", b"pose")):
        (folder / name).write_bytes(data)
    manifest = tuple(ModelManifestEntry(
        f"models/{model_id}/{file.name}", file.stat().st_size, file_sha256(file)
    ) for file in sorted(folder.iterdir()))
    mapping = tuple((role, role) for role in ROLE_ORDER)
    model = TeacherModelReference(
        model_id=model_id, origin="imported", created_at=utc_now(),
        bodypart_mapping=mapping,
        config_path=f"models/{model_id}/config.yaml",
        checkpoint_path=f"models/{model_id}/snapshot-1.pt",
        manifest=manifest, manifest_hash=build_manifest_hash(manifest),
        compatibility_state="compatible",
        self_test_evidence={
            "model_manifest_hash": build_manifest_hash(manifest),
            "bodypart_mapping": [list(pair) for pair in mapping],
            "pose_cfg_sha256": file_sha256(folder / "pytorch_config.yaml"),
            "runtime": {"device": "cpu", "versions": {
                "deeplabcut": "3.0.1", "torch": "2.13.0",
            }},
        },
    )
    session._project = replace(session.project, model_references=(model,))
    run, request = prepare_experiment_inference(
        session, experiment.experiment_id, model_id,
        InferenceParams(min_confidence=0.0, device="cpu"),
    )
    return session, experiment, run, request


def _result(job_dir: Path, request):
    job_dir.mkdir(parents=True, exist_ok=True)
    artifact = job_dir / "predictions.csv"
    with artifact.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(["scorer", *["DLC"] * 12])
        writer.writerow(["bodyparts", *[role for role in ROLE_ORDER for _ in range(3)]])
        writer.writerow(["coords", *[coord for _ in ROLE_ORDER
                                      for coord in ("x", "y", "likelihood")]])
        for frame in range(request.frame_count):
            writer.writerow([frame, *[value for _ in ROLE_ORDER
                                      for value in (1.0, 2.0, 0.9)]])
    return {
        "actual_device": "cpu",
        "outputs": [{"path": artifact.name, "size": artifact.stat().st_size,
                     "sha256": file_sha256(artifact)}],
        RESULT_SECTION: {
            "input_digest": request.input_digest,
            "video_sha256": request.video_sha256,
            "model_manifest_hash": request.model_manifest_hash,
            "bodypart_mapping": [list(pair) for pair in request.bodypart_mapping],
            "frame_count": request.frame_count,
            "prediction_path": artifact.name,
            "scorer": "DLC", "engine_version": "3.0.1",
            "versions": request.expected_runtime_versions,
            "complete_count": request.frame_count,
            "missing_by_role": {role: 0 for role in ROLE_ORDER},
        },
    }


def test_joint_result_is_candidate_and_does_not_activate(tmp_path, synthetic_video_path):
    session, experiment, run, request = _prepared(tmp_path, synthetic_video_path)
    job_dir = session.project_root / "data" / "engines" / str(run.run_id)
    result = _result(job_dir, request)
    completed = verify_experiment_inference_result(session, run, request, result, job_dir)
    assert completed.status == "completed"
    assert completed.member_track_ids == experiment.roles.track_ids()
    assert completed.extra_fields["complete_count"] == request.frame_count
    assert session.pendulum_experiment(experiment.experiment_id).active_infer_run_id is None
    assert session.project.observations == ()


def test_joint_result_rejects_changed_raw_artifact_and_stale_binding(
    tmp_path, synthetic_video_path,
):
    session, experiment, run, request = _prepared(tmp_path, synthetic_video_path)
    job_dir = session.project_root / "data" / "engines" / str(run.run_id)
    result = _result(job_dir, request)
    (job_dir / "predictions.csv").write_text("tampered", encoding="utf-8")
    with pytest.raises(ProjectSessionError, match="hash"):
        verify_experiment_inference_result(session, run, request, result, job_dir)
    result = _result(job_dir, request)
    (Path(request.video_path)).write_bytes(b"changed")
    with pytest.raises(ProjectSessionError):
        verify_experiment_inference_result(session, run, request, result, job_dir)
