"""推理编排的真实 spawn 生命周期与原子提交边界。"""

from concurrent.futures import CancelledError
from dataclasses import replace
import hashlib
import os
from pathlib import Path
from queue import Queue
from threading import Event
import time
from uuid import uuid4

import pytest

from ai_physics_tracker.application.inference_job import InferenceCoordinator, _inference_process_worker
from ai_physics_tracker.application.project_session import ProjectSession, ProjectSessionError
from ai_physics_tracker.application.video import VideoStreamInfo
from ai_physics_tracker.application.video_timing import TimingReport
from ai_physics_tracker.domain.tracking_run import create_tracking_run, mark_run_completed
from ai_physics_tracker.infrastructure.engine_adapter import InferenceParams
from ai_physics_tracker.infrastructure.mock_engine_adapter import MockEngineAdapter
from ai_physics_tracker.infrastructure.project_repository import ProjectRepository
from ai_physics_tracker.infrastructure.task_runner import TaskResult, TaskProgress


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


def poll_finished(coordinator, session, run, handle):
    messages = []
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        messages.extend(coordinator.poll_messages(session, run.run_id))
        if not handle.is_alive():
            messages.extend(coordinator.poll_messages(session, run.run_id))
            break
        handle.join(timeout_s=0.01)
    else:
        coordinator.cancel_all(session)
        pytest.fail("Inference did not terminate")
    return messages


class WaitingAdapter(MockEngineAdapter):
    def infer(self, run_id, queue, cancel_event, request):
        queue.put(TaskProgress(run_id, 0, request.frame_count))
        cancel_event.wait(10)
        raise CancelledError("Cancelled at test barrier")


class CrashingAdapter(MockEngineAdapter):
    def infer(self, run_id, queue, cancel_event, request):
        os._exit(23)


class FailingAdapter(MockEngineAdapter):
    def infer(self, run_id, queue, cancel_event, request):
        raise ValueError("broken prediction file")


class ImmediateHandle:
    def __init__(self, messages):
        self.messages = messages
        self.exitcode = 0

    def poll_messages(self):
        messages, self.messages = self.messages, []
        return messages

    def is_alive(self):
        return False

    def join(self, timeout_s=None):
        pass

    def cancel(self, timeout_s=0):
        pass


class ImmediateRunner:
    def start_task(self, run_id, target, *args):
        payload = target(run_id, Queue(), Event(), *args)
        # 重复的结果消息不能触发二次导入。
        return ImmediateHandle([TaskResult(run_id, True, payload), TaskResult(run_id, True, payload)])


def test_spawn_inference_imports_and_persists_with_real_progress(tmp_path):
    session, trained = session_and_model(tmp_path)
    coordinator = InferenceCoordinator()
    run = coordinator.prepare_inference(session, trained.run_id, InferenceParams(0.5), adapter=MockEngineAdapter())
    handle = coordinator.start_inference(session, run.run_id)
    messages = poll_finished(coordinator, session, run, handle)
    result = session.tracking_runs()[-1]
    assert result.status == "completed"
    assert result.extra_fields["import_summary"] == {
        "row_count": 12, "missing_count": 0, "low_confidence_count": 0, "inserted": 11, "skipped": 1}
    steps = [m.step for m in messages if isinstance(m, TaskProgress)]
    assert steps == list(range(13))
    assert session.effective_point(trained.track_id, 0).source == "manual"
    assert len(session.effective_points(trained.track_id)) == 12
    assert len(session.manual_points(trained.track_id)) == 1
    session.save()
    reopened = ProjectSession.load(ProjectRepository(), session.project_root)
    assert reopened.project.observations == session.project.observations
    assert reopened.tracking_runs()[-1] == result
    assert (reopened.project_root / result.extra_fields["prediction_path"]).is_file()


@pytest.mark.parametrize("adapter,status", [(FailingAdapter(), "failed"), (CrashingAdapter(), "failed")])
def test_spawn_failure_never_imports_partial_points(tmp_path, adapter, status):
    session, trained = session_and_model(tmp_path)
    previous = session.project.observations
    coordinator = InferenceCoordinator()
    run = coordinator.prepare_inference(session, trained.run_id, InferenceParams(0.5), adapter=adapter)
    handle = coordinator.start_inference(session, run.run_id)
    poll_finished(coordinator, session, run, handle)
    assert session.tracking_runs()[-1].status == status
    assert session.project.observations == previous
    assert not handle.is_alive()


def test_cancel_reaps_process_and_preserves_points(tmp_path):
    session, trained = session_and_model(tmp_path)
    previous = session.project.observations
    coordinator = InferenceCoordinator()
    run = coordinator.prepare_inference(session, trained.run_id, InferenceParams(0.5), adapter=WaitingAdapter())
    handle = coordinator.start_inference(session, run.run_id)
    coordinator.cancel_all(session)
    assert not handle.is_alive()
    assert session.tracking_runs()[-1].status == "cancelled"
    assert coordinator.poll_messages(session, run.run_id) == []
    assert session.project.observations == previous


@pytest.mark.parametrize("change", ["root", "media", "timing", "config", "snapshot"])
def test_changed_context_rejects_completed_result(tmp_path, change):
    session, trained = session_and_model(tmp_path)
    coordinator = InferenceCoordinator(ImmediateRunner())
    run = coordinator.prepare_inference(session, trained.run_id, InferenceParams(0.5), adapter=MockEngineAdapter())
    coordinator.start_inference(session, run.run_id)
    if change == "root":
        session.save_as(tmp_path / "copied")
    elif change == "media":
        (tmp_path / "sample.mp4").write_bytes(b"changed media")
    elif change == "timing":
        session.relink(trained.video_id, tmp_path / "sample.mp4")
    else:
        path = "models/config.yaml" if change == "config" else "models/snapshot-1.pt"
        with (session.project_root / path).open("ab") as stream:
            stream.write(b"changed")
    before = session.project.observations
    messages = coordinator.poll_messages(session, run.run_id)
    assert session.tracking_runs()[-1].status == "failed"
    assert session.project.observations == before
    results = [message for message in messages if isinstance(message, TaskResult)]
    assert len(results) == 1 and not results[0].success


def test_manual_edits_and_duplicate_result_preserve_first_wins(tmp_path):
    session, trained = session_and_model(tmp_path)
    coordinator = InferenceCoordinator(ImmediateRunner())
    run = coordinator.prepare_inference(session, trained.run_id, InferenceParams(0.5), adapter=MockEngineAdapter())
    coordinator.start_inference(session, run.run_id)
    manual = session.mark_point(trained.track_id, 5, 99, 99)
    coordinator.poll_messages(session, run.run_id)
    assert session.tracking_runs()[-1].status == "completed"
    assert session.effective_point(trained.track_id, 5) == manual
    assert session.tracking_runs()[-1].extra_fields["import_summary"]["inserted"] == 10
    assert len(session.project.observations) == 12


def test_tampered_artifact_and_foreign_session_do_not_import(tmp_path):
    session, trained = session_and_model(tmp_path)
    coordinator = InferenceCoordinator(ImmediateRunner())
    run = coordinator.prepare_inference(session, trained.run_id, InferenceParams(0.5), adapter=MockEngineAdapter())
    coordinator.start_inference(session, run.run_id)
    (session.project_root / "data" / "engines" / str(run.run_id) / "observations.json").write_text("[]", encoding="utf-8")
    coordinator.poll_messages(session, run.run_id)
    assert session.tracking_runs()[-1].status == "failed"
    assert len(session.project.observations) == 1
    run2 = coordinator.prepare_inference(session, trained.run_id, InferenceParams(0.5), adapter=MockEngineAdapter())
    coordinator.start_inference(session, run2.run_id)
    foreign = session.detached()
    with pytest.raises(ProjectSessionError, match="different session"):
        coordinator.poll_messages(foreign, run2.run_id)
    assert session.tracking_runs()[-1].status == "cancelled"
    assert len(foreign.project.observations) == 1


def test_model_file_info_detects_replacement_before_prepare(tmp_path):
    session, trained = session_and_model(tmp_path)
    path = session.project_root / "models/snapshot-1.pt"
    stat = path.stat()
    session.update_tracking_run(replace(trained, extra_fields={**trained.extra_fields,
        "model_file_info": [stat.st_size, stat.st_mtime_ns]}))
    path.write_bytes(b"replaced model")
    with pytest.raises(ProjectSessionError, match="model file has changed"):
        InferenceCoordinator().prepare_inference(session, trained.run_id, InferenceParams(0.5), adapter=MockEngineAdapter())
    assert len(session.tracking_runs()) == 1


def test_spawn_start_failure_marks_run_failed(tmp_path):
    class BrokenRunner:
        def start_task(self, *args):
            raise OSError("spawn unavailable")
    session, trained = session_and_model(tmp_path)
    coordinator = InferenceCoordinator(BrokenRunner())
    run = coordinator.prepare_inference(session, trained.run_id, InferenceParams(0.5), adapter=MockEngineAdapter())
    with pytest.raises(ProjectSessionError, match="spawn unavailable"):
        coordinator.start_inference(session, run.run_id)
    assert session.tracking_runs()[-1].status == "failed"


def test_equivalent_media_locator_does_not_invalidate_inference(tmp_path):
    session, trained = session_and_model(tmp_path)
    session.relink(trained.video_id, tmp_path / "project" / ".." / "sample.mp4")
    session.confirm_video_timing(trained.video_id, TimingReport("cfr", "verified synthetic media"))
    coordinator = InferenceCoordinator(ImmediateRunner())
    run = coordinator.prepare_inference(session, trained.run_id, InferenceParams(0.5), adapter=MockEngineAdapter())
    coordinator.start_inference(session, run.run_id)
    coordinator.poll_messages(session, run.run_id)
    assert session.tracking_runs()[-1].status == "completed"


@pytest.mark.parametrize("digest", [None, "", "invalid", "0" * 63])
def test_legacy_hash_is_not_an_inference_requirement(tmp_path, digest):
    session, trained = session_and_model(tmp_path)
    extras = dict(trained.extra_fields)
    extras["model_sha256"] = digest
    session.update_tracking_run(replace(trained, extra_fields=extras))
    run = InferenceCoordinator().prepare_inference(session, trained.run_id, InferenceParams(0.5), adapter=MockEngineAdapter())
    assert run.status == "pending"
    assert session.tracking_runs()[0].extra_fields["model_sha256"] == digest


def test_ai_preparation_does_not_rescan_legacy_video_hash(tmp_path):
    session, trained = session_and_model(tmp_path)
    session._project = replace(session.project, videos=tuple(
        replace(video, sha256=hashlib.sha256(b"").hexdigest()) for video in session.project.videos))
    (tmp_path / "sample.mp4").write_bytes(b"replacement video")
    run = InferenceCoordinator().prepare_inference(session, trained.run_id, InferenceParams(0.5), adapter=MockEngineAdapter())
    assert run.status == "pending"
    assert session.project.videos[0].sha256 == hashlib.sha256(b"").hexdigest()


def test_lightweight_policy_accepts_media_with_unchanged_stat(tmp_path):
    session, trained = session_and_model(tmp_path)
    media = tmp_path / "sample.mp4"
    media.write_bytes(b"original")
    coordinator = InferenceCoordinator(ImmediateRunner())
    run = coordinator.prepare_inference(session, trained.run_id, InferenceParams(0.5), adapter=MockEngineAdapter())
    coordinator.start_inference(session, run.run_id)
    stamp = media.stat()
    media.write_bytes(b"replaced")
    os.utime(media, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
    messages = coordinator.poll_messages(session, run.run_id)
    assert session.tracking_runs()[-1].status == "completed"
    assert [message for message in messages if isinstance(message, TaskResult)][0].success
    assert len(session.project.observations) == 12


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
    coordinator = InferenceCoordinator(ImmediateRunner())
    run = coordinator.prepare_inference(session, trained.run_id, InferenceParams(0.5),
        adapter=MockEngineAdapter(), config_path=config)
    assert run.model_snapshot is None
    assert "config_path" not in run.extra_fields
    coordinator.start_inference(session, run.run_id)
    coordinator.poll_messages(session, run.run_id)
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
    coordinator = InferenceCoordinator()
    run = coordinator.prepare_inference(session, trained.run_id, InferenceParams(0.5),
        adapter=MockEngineAdapter(default_confidence=0.4))
    handle = coordinator.start_inference(session, run.run_id)
    poll_finished(coordinator, session, run, handle)
    assert session.tracking_runs()[-1].status == "completed"
    assert session.tracking_runs()[-1].extra_fields["import_summary"]["low_confidence_count"] == 12
    assert len(session.project.observations) == 1


def test_cancelled_legacy_run_has_no_uncreated_archive_references(tmp_path):
    session, trained = session_and_model(tmp_path)
    external = tmp_path / "external.yaml"
    external.write_text("external config", encoding="utf-8")
    coordinator = InferenceCoordinator()
    run = coordinator.prepare_inference(session, trained.run_id, InferenceParams(0.5),
        adapter=MockEngineAdapter(), config_path=external)
    coordinator.cancel_inference(session, run.run_id)
    session.save()
    cancelled = ProjectSession.load(ProjectRepository(), session.project_root).tracking_runs()[-1]
    assert cancelled.status == "cancelled"
    assert cancelled.model_snapshot is None
    assert "config_path" not in cancelled.extra_fields
    assert cancelled.config["training_run_id"] == str(trained.run_id)


def test_lightweight_policy_accepts_config_with_unchanged_stat(tmp_path):
    session, trained = session_and_model(tmp_path)
    config = session.project_root / "models/config.yaml"
    coordinator = InferenceCoordinator(ImmediateRunner())
    run = coordinator.prepare_inference(session, trained.run_id, InferenceParams(0.5), adapter=MockEngineAdapter())
    coordinator.start_inference(session, run.run_id)
    previous = config.stat()
    config.write_bytes(b"x" * previous.st_size)
    os.utime(config, ns=(previous.st_atime_ns, previous.st_mtime_ns))
    coordinator.poll_messages(session, run.run_id)
    assert session.tracking_runs()[-1].status == "completed"
    assert len(session.project.observations) == 12
