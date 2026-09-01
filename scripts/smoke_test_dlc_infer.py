"""真实 CPU 训练→推理→导入→保存重开冒烟；全部产物保留以便核查。"""

import argparse
from dataclasses import replace
from pathlib import Path
import tempfile
import time

from smoke_test_dlc_train import create_synthetic_video
from ai_physics_tracker.application.project_session import ProjectSession
from ai_physics_tracker.application.tracking_job import (
    TrackingJobRunner,
    prepare_tracking_candidate,
    prepare_tracking_request,
)
from ai_physics_tracker.domain.tracking_run import mark_run_running
from ai_physics_tracker.infrastructure.engine_adapter import TrainingParams, InferenceParams
from ai_physics_tracker.infrastructure.opencv_video_reader import OpenCVVideoReader
from ai_physics_tracker.infrastructure.project_repository import ProjectRepository
from ai_physics_tracker.infrastructure.task_runner import TaskProgress, TaskLog, TaskResult


def wait_for_run(session, request, handle, log_path, timeout_s=300):
    """持续排空队列；超时必须回收 worker，不能留下后台训练进程。"""
    started = time.monotonic()
    progress = []
    result_path = None
    try:
        with log_path.open("w", encoding="utf-8") as log:
            while True:
                messages = handle.poll_messages(limit=200)
                if not handle.is_alive():
                    messages += handle.poll_messages(limit=200)
                for message in messages:
                    if isinstance(message, TaskProgress):
                        progress.append(message.step)
                        print(f"Progress: {message.step}/{message.total_steps}", flush=True)
                    elif isinstance(message, TaskLog):
                        log.write(message.message + "\n")
                    elif isinstance(message, TaskResult):
                        if not message.success:
                            raise RuntimeError(message.error or "Smoke task failed")
                        if message.payload and message.payload.get("result_path"):
                            result_path = session.project_root / message.payload["result_path"]
                if not handle.is_alive():
                    break
                if time.monotonic() - started > timeout_s:
                    raise TimeoutError("Smoke task exceeded timeout")
                handle.join(timeout_s=0.1)
    finally:
        if handle.is_alive():
            handle.cancel(timeout_s=1.0)
    if result_path is None:
        raise RuntimeError("Smoke task produced no importable result")
    candidate = prepare_tracking_candidate(session.project, request, result_path)
    if not session.apply_tracking_candidate(candidate):
        raise RuntimeError("Smoke task result no longer matches the active project")
    result = next(r for r in session.tracking_runs() if r.run_id == request.run.run_id)
    if result.status != "completed":
        raise RuntimeError(f"{result.task_type} failed: {result.error_message}")
    return result, progress


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="不存在的输出目录；默认新建临时目录并保留")
    args = parser.parse_args()
    if args.output is None:
        root = Path(tempfile.mkdtemp(prefix="physics_inference_smoke_"))
    else:
        root = args.output.resolve()
        root.mkdir(parents=True, exist_ok=False)
    print(f"Artifacts retained at: {root}", flush=True)
    media = root / "synthetic_pendulum.mp4"
    create_synthetic_video(media)
    repository = ProjectRepository()
    session = ProjectSession.start(repository, "Inference smoke")
    reader = OpenCVVideoReader()
    try:
        info = reader.open(media)
        # 本脚本刚生成的恒定帧率合成媒体；不对任意用户视频授予此权限。
        video, _ = session.register_external_video(media, replace(info, timing_status="cfr"))
        track = session.add_track(video.video_id, "Bob")
        for frame_index in range(0, 10, 2):
            session.mark_point(track.track_id, frame_index, 30 + 4 * frame_index, 50)
        session.save_as(root / "project")
        train_request = prepare_tracking_request(
            session,
            track.track_id,
            TrainingParams(epochs=1, batch_size=1, device="cpu"),
        )
    finally:
        reader.close()
    session.record_tracking_run(train_request.run)
    session.update_tracking_run(mark_run_running(train_request.run))
    handle = TrackingJobRunner().start(train_request)
    trained, _ = wait_for_run(session, train_request, handle, root / "training.log")
    assert (session.project_root / trained.model_snapshot).is_file()
    session.save()
    print(f"Training snapshot: {trained.model_snapshot}", flush=True)
    infer_request = prepare_tracking_request(
        session,
        track.track_id,
        InferenceParams(min_confidence=0.0, device="cpu", batch_size=2),
        training_run_id=trained.run_id,
    )
    session.record_tracking_run(infer_request.run)
    session.update_tracking_run(mark_run_running(infer_request.run))
    handle = TrackingJobRunner().start(infer_request)
    completed, progress = wait_for_run(
        session, infer_request, handle, root / "inference.log"
    )
    assert any(0 < step < 10 for step in progress) and max(progress) == 10
    assert completed.extra_fields["import_summary"]["inserted"] == 5
    assert len(session.effective_points(track.track_id)) == 10
    session.compute_kinematics(track.track_id)
    session.save()
    reopened = ProjectSession.load(repository, session.project_root)
    assert reopened.project.observations == session.project.observations
    assert reopened.tracking_runs()[-1] == completed
    assert (reopened.project_root / completed.extra_fields["prediction_path"]).is_file()
    print(f"PASSED: {completed.extra_fields['import_summary']}", flush=True)
    print("Pipeline smoke only; one training epoch is not a tracking accuracy benchmark.", flush=True)


if __name__ == "__main__":
    main()
