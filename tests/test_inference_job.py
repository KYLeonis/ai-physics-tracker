"""推理准备、worker 与落盘结果读取边界测试。"""

from dataclasses import replace
import hashlib
from pathlib import Path
from queue import Queue
from threading import Event

import pytest

from ai_physics_tracker.application.inference_job import (
    _inference_process_worker,
    prepare_inference,
    read_inference_result,
)
from ai_physics_tracker.application.project_session import ProjectSession, ProjectSessionError
from ai_physics_tracker.application.video import VideoStreamInfo
from ai_physics_tracker.domain.tracking_run import (
    create_tracking_run,
    mark_run_completed,
    mark_run_running,
)
from ai_physics_tracker.infrastructure.engine_adapter import InferenceParams
from ai_physics_tracker.infrastructure.mock_engine_adapter import MockEngineAdapter
from ai_physics_tracker.infrastructure.project_repository import ProjectRepository
from ai_physics_tracker.infrastructure.task_runner import TaskProgress


def session_and_model(tmp_path):
    session = ProjectSession.start(ProjectRepository())
    media = tmp_path / "sample.mp4"
    media.touch()
    video, _ = session.register_external_video(media, VideoStreamInfo(
        width_px=100, height_px=100, fps_container=30.0, frame_count=12,
        container_format="mp4", timing_status="cfr"))
    track = session.add_track(video.video_id)
    session.mark_point(track.track_id, 0, 90, 90)
    session.save_as(tmp_path / "project")
    folder = session.project_root / "models"
    folder.mkdir(exist_ok=True)
    (folder / "config.yaml").write_text("bodyparts: [target]\n", encoding="utf-8")
    (folder / "snapshot-1.pt").write_bytes(b"mock weights")
    trained = mark_run_completed(create_tracking_run(video.video_id, track.track_id, "train",
        config={"shuffle": 1, "trainingsetindex": 0}, model_snapshot="models/snapshot-1.pt"))
    trained = replace(trained, extra_fields={"config_path": "models/config.yaml",
        "model_sha256": hashlib.sha256(b"mock weights").hexdigest()})
    session.record_tracking_run(trained)
    return session, trained


class FailingAdapter(MockEngineAdapter):
    def infer(self, run_id, queue, cancel_event, request):
        raise ValueError("broken prediction file")


def test_worker_result_imports_and_persists_with_real_progress(tmp_path):
    session, trained = session_and_model(tmp_path)
    run, request = prepare_inference(session, trained.run_id, InferenceParams(0.5))
    session.update_tracking_run(mark_run_running(run))
    queue = Queue()
    payload = _inference_process_worker(
        run.run_id, queue, Event(), request, MockEngineAdapter()
    )
    points, result = read_inference_result(request, session.project_root, run, payload)
    session.import_engine_points(points, result)
    result = session.tracking_runs()[-1]

    assert result.status == "completed"
    assert result.extra_fields["import_summary"] == {
        "row_count": 12, "missing_count": 0, "low_confidence_count": 0, "inserted": 11, "skipped": 1}
    steps = []
    while not queue.empty():
        message = queue.get()
        if isinstance(message, TaskProgress):
            steps.append(message.step)
    assert steps == list(range(13))
    assert session.effective_point(trained.track_id, 0).source == "manual"
    assert len(session.effective_points(trained.track_id)) == 12
    assert len(session.manual_points(trained.track_id)) == 1
    session.save()
    reopened = ProjectSession.load(ProjectRepository(), session.project_root)
    assert reopened.project.observations == session.project.observations
    assert reopened.tracking_runs()[-1] == result
    assert (reopened.project_root / result.extra_fields["prediction_path"]).is_file()


def test_worker_failure_never_imports_partial_points(tmp_path):
    session, trained = session_and_model(tmp_path)
    previous = session.project.observations
    run, request = prepare_inference(session, trained.run_id, InferenceParams(0.5))

    with pytest.raises(ValueError, match="broken prediction file"):
        _inference_process_worker(run.run_id, Queue(), Event(), request, FailingAdapter())

    assert session.project.observations == previous


def test_model_file_info_detects_replacement_before_prepare(tmp_path):
    session, trained = session_and_model(tmp_path)
    path = session.project_root / "models/snapshot-1.pt"
    stat = path.stat()
    session.update_tracking_run(replace(trained, extra_fields={**trained.extra_fields,
        "model_file_info": [stat.st_size, stat.st_mtime_ns]}))
    path.write_bytes(b"replaced model")
    with pytest.raises(ProjectSessionError, match="model file has changed"):
        prepare_inference(session, trained.run_id, InferenceParams(0.5))
    assert len(session.tracking_runs()) == 1


@pytest.mark.parametrize("digest", [None, "", "invalid", "0" * 63])
def test_legacy_hash_is_not_an_inference_requirement(tmp_path, digest):
    session, trained = session_and_model(tmp_path)
    extras = dict(trained.extra_fields)
    extras["model_sha256"] = digest
    session.update_tracking_run(replace(trained, extra_fields=extras))
    run, _request = prepare_inference(session, trained.run_id, InferenceParams(0.5))
    assert run.status == "pending"
    assert session.tracking_runs()[0].extra_fields["model_sha256"] == digest


def test_ai_preparation_does_not_rescan_legacy_video_hash(tmp_path):
    session, trained = session_and_model(tmp_path)
    session._project = replace(session.project, videos=tuple(
        replace(video, sha256=hashlib.sha256(b"").hexdigest()) for video in session.project.videos))
    (tmp_path / "sample.mp4").write_bytes(b"replacement video")
    run, _request = prepare_inference(session, trained.run_id, InferenceParams(0.5))
    assert run.status == "pending"
    assert session.project.videos[0].sha256 == hashlib.sha256(b"").hexdigest()


def test_verified_external_legacy_model_is_archived_without_absolute_new_refs(tmp_path):
    session, trained = session_and_model(tmp_path)
    external = tmp_path / "legacy model"
    external.mkdir()
    snapshot = external / "snapshot-1.pt"
    snapshot.write_bytes(b"mock weights")
    config = external / "config.yaml"
    config.write_text("legacy config", encoding="utf-8")
    trained = replace(trained, model_snapshot=str(snapshot),
        extra_fields={"model_sha256": hashlib.sha256(b"mock weights").hexdigest()})
    session.update_tracking_run(trained)
    run, request = prepare_inference(
        session, trained.run_id, InferenceParams(0.5), config_path=config
    )
    session.update_tracking_run(mark_run_running(run))
    assert run.model_snapshot is None
    assert "config_path" not in run.extra_fields
    payload = _inference_process_worker(
        run.run_id, Queue(), Event(), request, MockEngineAdapter()
    )
    points, completed = read_inference_result(request, session.project_root, run, payload)
    session.import_engine_points(points, completed)
    completed = session.tracking_runs()[-1]
    assert completed.status == "completed"
    assert not Path(completed.model_snapshot).is_absolute()
    assert not Path(completed.extra_fields["config_path"]).is_absolute()
    assert (session.project_root / completed.model_snapshot).read_bytes() == snapshot.read_bytes()
    assert (session.project_root / completed.extra_fields["config_path"]).read_bytes() == config.read_bytes()
    assert session.tracking_runs()[0] == trained
    session.save()
    reopened = ProjectSession.load(ProjectRepository(), session.project_root)
    assert reopened.tracking_runs()[-1] == completed


def test_spawn_retains_explicit_adapter_parameters(tmp_path):
    session, trained = session_and_model(tmp_path)
    run, request = prepare_inference(session, trained.run_id, InferenceParams(0.5))
    session.update_tracking_run(mark_run_running(run))
    payload = _inference_process_worker(
        run.run_id,
        Queue(),
        Event(),
        request,
        MockEngineAdapter(default_confidence=0.4),
    )
    points, completed = read_inference_result(request, session.project_root, run, payload)
    session.import_engine_points(points, completed)
    assert completed.extra_fields["import_summary"]["low_confidence_count"] == 12
    assert len(session.project.observations) == 1


def test_cancelled_external_run_has_no_uncreated_archive_references(tmp_path):
    session, trained = session_and_model(tmp_path)
    external = tmp_path / "external.yaml"
    external.write_text("external config", encoding="utf-8")
    run, request = prepare_inference(
        session, trained.run_id, InferenceParams(0.5), config_path=external
    )
    cancelled = Event()
    cancelled.set()
    payload = _inference_process_worker(
        run.run_id, Queue(), cancelled, request, MockEngineAdapter()
    )
    assert payload == {"status": "cancelled"}
    assert run.model_snapshot is None
    assert "config_path" not in run.extra_fields
    assert run.config["training_run_id"] == str(trained.run_id)
