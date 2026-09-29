"""P1.4 S1：联合候选与当前实验、模型和原始 artifact 身份绑定。"""

import csv
from dataclasses import replace
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from ai_physics_tracker.application.experiment_inference_job import (
    RESULT_SECTION, prepare_experiment_inference, verify_experiment_inference_result,
)
from ai_physics_tracker.application.experiment_review import (
    build_experiment_review_queue, frame_diagnostic,
)
from ai_physics_tracker.application.adopted_measurement import (
    assert_adopted_measurement_current, build_adopted_measurement,
)
from ai_physics_tracker.application.project_session import ProjectSession, ProjectSessionError
from ai_physics_tracker.application.tracking_types import InferenceParams
from ai_physics_tracker.application.video import VideoStreamInfo
from ai_physics_tracker.domain.pendulum import ROLE_ORDER, PendulumRoles, PhysicalParameters
from ai_physics_tracker.domain.project import create_project
from ai_physics_tracker.domain.teacher_model import (
    ModelManifestEntry, TeacherModelReference, build_manifest_hash,
)
from ai_physics_tracker.domain.types import utc_now
from ai_physics_tracker.infrastructure.hashing import file_sha256
from ai_physics_tracker.infrastructure.dlc_predictions import JointRawPredictions, RawPrediction
from ai_physics_tracker.infrastructure.project_repository import ProjectRepository
from ai_physics_tracker.domain.track_store import TrackStore


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


def test_joint_review_merges_roles_and_reports_geometry_without_pivot_cutoff():
    rows = {
        role: tuple(RawPrediction(index, float(index), float(index + 1),
                                  0.2 if role == "tip" and index == 2 else 0.9)
                    for index in range(5))
        for role in ROLE_ORDER
    }
    rows["pivot"] = tuple(
        RawPrediction(index, float("nan"), float("nan"), float("nan"))
        if index == 2 else row
        for index, row in enumerate(rows["pivot"])
    )
    raw = JointRawPredictions(tuple(rows.items()), 5, 4, (("pivot", 1),))
    diagnostic = frame_diagnostic(
        raw, 2, confidence_threshold=0.6, fixed_pivot_px=(0.0, 0.0),
    )
    assert diagnostic.predictions["pivot"] is None
    assert diagnostic.role_reasons["pivot"] == ("missing",)
    assert diagnostic.role_reasons["tip"] == ("low_confidence",)
    assert not diagnostic.complete
    assert diagnostic.pivot_offset_px is None
    queue = build_experiment_review_queue(
        raw, fps_nominal=10.0, confidence_threshold=0.6,
        fixed_pivot_px=(0.0, 0.0), top_n=2,
    )
    assert sum(item.frame_index == 2 for item in queue) == 1


def test_joint_review_correct_is_run_scoped_manual_and_undoable(
    tmp_path, synthetic_video_path,
):
    session, experiment, run, request = _prepared(tmp_path, synthetic_video_path)
    job_dir = session.project_root / "data" / "engines" / str(run.run_id)
    completed = verify_experiment_inference_result(
        session, run, request, _result(job_dir, request), job_dir,
    )
    session.update_tracking_run(completed)
    before_revision = experiment.measurement_revision
    queue = session.create_experiment_review_queue(run.run_id, top_n=2)
    assert queue
    frame = queue[0].frame_index
    assert session.project.observations == ()
    assert session.pendulum_experiment(experiment.experiment_id).active_infer_run_id is None
    assert session.review_experiment_frame(run.run_id, frame, "accepted") is None
    assert session.project.observations == ()
    point = session.review_experiment_frame(
        run.run_id, frame, "corrected", role="tip", pixel_x=6.0, pixel_y=7.0,
    )
    assert point is not None and point.track_id == experiment.roles.tip
    assert point.confidence is None and point.source == "manual"
    assert session.effective_point(experiment.roles.tip, frame) == point
    assert session.pendulum_experiment(experiment.experiment_id).measurement_revision == before_revision + 1
    assert session.get_experiment_review(run.run_id)[1][frame]["disposition"] == "corrected"
    assert session.undo()
    assert session.project.observations == ()
    assert session.get_experiment_review(run.run_id)[1][frame]["disposition"] == "accepted"
    assert session.redo()
    assert session.effective_point(experiment.roles.tip, frame) == point
    session.delete_active_manual_point(experiment.roles.tip, frame)
    assert frame not in session.get_experiment_review(run.run_id)[1]
    assert session.undo()
    assert session.effective_point(experiment.roles.tip, frame) == point
    session.save()
    reopened = ProjectSession.load(ProjectRepository(), session.project_root)
    assert reopened.get_experiment_review(run.run_id)[1][frame]["disposition"] == "corrected"
    assert reopened.effective_point(experiment.roles.tip, frame) == point


def test_joint_review_rejects_tampered_candidate_without_manual_write(
    tmp_path, synthetic_video_path,
):
    session, experiment, run, request = _prepared(tmp_path, synthetic_video_path)
    job_dir = session.project_root / "data" / "engines" / str(run.run_id)
    completed = verify_experiment_inference_result(
        session, run, request, _result(job_dir, request), job_dir,
    )
    session.update_tracking_run(completed)
    frame = session.create_experiment_review_queue(run.run_id, top_n=1)[0].frame_index
    (job_dir / "predictions.csv").write_text("changed", encoding="utf-8")
    before = session.project
    with pytest.raises(ProjectSessionError, match="candidate changed"):
        session.review_experiment_frame(
            run.run_id, frame, "corrected", role="tip", pixel_x=1.0, pixel_y=2.0,
        )
    assert session.project == before


def test_joint_activation_replace_clear_and_history_are_four_role_atomic(
    tmp_path, synthetic_video_path,
):
    session, experiment, run, request = _prepared(tmp_path, synthetic_video_path)
    folder = session.project_root / "data" / "engines" / str(run.run_id)
    session.update_tracking_run(verify_experiment_inference_result(
        session, run, request, _result(folder, request), folder,
    ))
    frame = session.create_experiment_review_queue(run.run_id, top_n=1)[0].frame_index
    manual = session.review_experiment_frame(
        run.run_id, frame, "corrected", role="tip", pixel_x=6.0, pixel_y=7.0,
    )
    candidate_only = session.project
    first = session.activate_experiment_candidate(experiment.experiment_id, run.run_id)
    assert first.action == "activate" and first.to_run_id == run.run_id
    assert len(first.role_counts) == 4
    assert session.effective_point(experiment.roles.tip, frame) == manual
    assert {point.source_detail for point in session.project.observations
            if point.source != "manual"} == {run.source_detail}
    assert session.pendulum_experiment(experiment.experiment_id).active_infer_run_id == run.run_id
    assert session.undo()
    assert session.project == candidate_only
    assert session.redo()
    assert session.pendulum_experiment(experiment.experiment_id).active_infer_run_id == run.run_id

    replacement, replacement_request = prepare_experiment_inference(
        session, experiment.experiment_id, UUID(request.model_id),
        InferenceParams(min_confidence=0.0, device="cpu"),
    )
    replacement_folder = session.project_root / "data" / "engines" / str(replacement.run_id)
    session.update_tracking_run(verify_experiment_inference_result(
        session, replacement, replacement_request,
        _result(replacement_folder, replacement_request), replacement_folder,
    ))
    second = session.replace_experiment_candidate(experiment.experiment_id, replacement.run_id)
    assert second.from_run_id == run.run_id and second.to_run_id == replacement.run_id
    assert session.effective_point(experiment.roles.tip, frame) == manual
    assert {point.source_detail for point in session.project.observations
            if point.source != "manual"} == {replacement.source_detail}
    cleared = session.clear_experiment_candidate(experiment.experiment_id)
    assert cleared.action == "clear"
    assert session.pendulum_experiment(experiment.experiment_id).active_infer_run_id is None
    assert [point for point in session.project.observations if point.source != "manual"] == []
    assert session.effective_point(experiment.roles.tip, frame) == manual
    assert session.undo()
    assert session.pendulum_experiment(experiment.experiment_id).active_infer_run_id == replacement.run_id
    session.save()
    reopened = ProjectSession.load(ProjectRepository(), session.project_root)
    assert reopened.pendulum_experiment(experiment.experiment_id).active_infer_run_id == replacement.run_id
    assert reopened.effective_point(experiment.roles.tip, frame) == manual


def test_joint_activation_failure_on_third_role_keeps_original_snapshot(
    tmp_path, synthetic_video_path, monkeypatch,
):
    session, experiment, run, request = _prepared(tmp_path, synthetic_video_path)
    folder = session.project_root / "data" / "engines" / str(run.run_id)
    session.update_tracking_run(verify_experiment_inference_result(
        session, run, request, _result(folder, request), folder,
    ))
    before = session.project
    original = TrackStore.replace_track_engine_points

    def fail_on_body_bottom(store, track_id, points):
        if track_id == experiment.roles.body_bottom:
            raise ValueError("injected third-role failure")
        return original(store, track_id, points)

    monkeypatch.setattr(TrackStore, "replace_track_engine_points", fail_on_body_bottom)
    with pytest.raises(ProjectSessionError, match="third-role failure"):
        session.activate_experiment_candidate(experiment.experiment_id, run.run_id)
    assert session.project == before
    assert session.project.observations == ()


def test_adopted_measurement_keeps_absolute_frames_fixed_pivot_and_sources(
    tmp_path, synthetic_video_path,
):
    session, experiment, run, request = _prepared(tmp_path, synthetic_video_path)
    folder = session.project_root / "data" / "engines" / str(run.run_id)
    session.update_tracking_run(verify_experiment_inference_result(
        session, run, request, _result(folder, request), folder,
    ))
    session.set_fixed_pivot(experiment.experiment_id, (10.0, 11.0))
    session.set_release_frame(experiment.experiment_id, 3)
    session.set_physical(experiment.experiment_id, PhysicalParameters(
        length_m=1.2, g_m_s2=9.8, length_source="measured", g_source="assumed",
    ))
    session.add_calibration(
        experiment.video_id, (0.0, 0.0), (10.0, 0.0), 2.0, "cm",
    )
    frame = session.create_experiment_review_queue(run.run_id, top_n=1)[0].frame_index
    manual = session.review_experiment_frame(
        run.run_id, frame, "corrected", role="tip", pixel_x=6.0, pixel_y=7.0,
    )
    session.activate_experiment_candidate(experiment.experiment_id, run.run_id)
    snapshot = build_adopted_measurement(session, experiment.experiment_id)
    payload = snapshot.payload
    assert len(payload["frames"]) == request.frame_count
    assert [row["frame_index"] for row in payload["frames"]] == list(range(request.frame_count))
    assert payload["frames"][3]["time_release_relative_s"] == pytest.approx(0.0)
    assert payload["frames"][0]["time_release_relative_s"] == pytest.approx(-0.3)
    assert payload["geometry"]["fixed_pivot_px"] == [10.0, 11.0]
    assert payload["calibration"]["unit"] == "cm"
    assert payload["calibration"]["height_px"] == 48
    assert payload["physical"]["length_m"] == 1.2
    assert payload["frames"][frame]["points_by_role"]["tip"]["point_id"] == str(manual.point_id)
    assert payload["frames"][frame]["points_by_role"]["tip"]["confidence"] is None
    assert payload["frames"][frame]["points_by_role"]["pivot"]["source"] == "dlc"
    assert "theta" not in str(payload).lower()
    assert_adopted_measurement_current(session, snapshot)
    session.set_fixed_pivot(experiment.experiment_id, (12.0, 11.0))
    with pytest.raises(ProjectSessionError, match="stale"):
        assert_adopted_measurement_current(session, snapshot)
    Path(request.video_path).write_bytes(b"changed after adoption")
    with pytest.raises(ProjectSessionError, match="video changed"):
        build_adopted_measurement(session, experiment.experiment_id)
