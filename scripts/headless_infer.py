#!/usr/bin/env python
"""Headless 推理驱动：走与 GUI 完全一致的应用层路径（无 Qt）。

用途：后台/CI 场景对已保存项目发起一次推理（prepare → spawn worker →
candidate 提交 → 保存）。产物语义与 GUI 相同：completed candidate run，
不自动激活、不改观测。

用法：
    python scripts/headless_infer.py --project <项目目录> \
        --training-run <train run id> [--min-confidence 0.6] [--timeout-min 30]
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from uuid import UUID

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))

from ai_physics_tracker.application.project_session import ProjectSession
from ai_physics_tracker.application.tracking_job import (
    TrackingJobRunner,
    prepare_tracking_candidate,
    prepare_tracking_request,
    run_tracking_worker,
)
from ai_physics_tracker.application.tracking_types import InferenceParams, TaskResult
from ai_physics_tracker.domain.tracking_run import mark_run_running
from ai_physics_tracker.infrastructure.dlc_adapter import DLCAdapter
from ai_physics_tracker.infrastructure.project_repository import ProjectRepository
from ai_physics_tracker.infrastructure.task_runner import BackgroundTaskRunner


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True)
    parser.add_argument("--training-run", required=True,
                        help="产生模型的 completed train run id")
    parser.add_argument("--min-confidence", type=float, default=0.6)
    parser.add_argument("--timeout-min", type=float, default=30.0)
    args = parser.parse_args()

    root = Path(args.project).resolve()
    session = ProjectSession.load(ProjectRepository(), root)

    # 时序授权：与 GUI 相同的真实探测路径（ffprobe），失败则拒绝
    from ai_physics_tracker.infrastructure.ffprobe_timing import FFprobeTimingProbe
    video = session.project.videos[0]
    report = FFprobeTimingProbe().probe(session.video_path(video))
    session.confirm_video_timing(video.video_id, report)
    print(f"timing: {report.status} fps={report.fps_measured} frames={report.frame_count}")

    track = session.tracks[0]
    training_run_id = UUID(args.training_run)
    request = prepare_tracking_request(
        session, track.track_id, InferenceParams(min_confidence=args.min_confidence),
        training_run_id=training_run_id)
    print(f"prepared infer run {request.run.run_id} (model from train {str(training_run_id)[:8]})")

    session.record_tracking_run(request.run)
    session.update_tracking_run(mark_run_running(request.run))

    handle = BackgroundTaskRunner().start_task(
        request.run.run_id, run_tracking_worker, request, DLCAdapter())

    deadline = time.monotonic() + args.timeout_min * 60
    result_path = None
    while handle.is_alive() and time.monotonic() < deadline:
        for message in handle.poll_messages(limit=200):
            text = getattr(message, "message", "") or ""
            if text:
                print(f"  [{getattr(message, 'level', 'INFO')}] {text[:120]}")
            if isinstance(message, TaskResult) and not message.success:
                print(f"FAILED: {message.error}", file=sys.stderr)
                return 1
            if (isinstance(message, TaskResult) and message.success
                    and isinstance(message.payload, dict)
                    and message.payload.get("result_path")):
                result_path = root / message.payload["result_path"]
    handle.join(timeout_s=5.0)
    if handle.is_alive():
        handle.cancel(timeout_s=5.0)
        print("worker timed out; cancelled", file=sys.stderr)
        return 1
    for message in handle.poll_messages(limit=500):
        if isinstance(message, TaskResult) and not message.success:
            print(f"FAILED: {message.error}", file=sys.stderr)
            return 1
        if (isinstance(message, TaskResult) and message.success
                and isinstance(message.payload, dict)
                and message.payload.get("result_path")):
            result_path = root / message.payload["result_path"]
    if result_path is None:
        print("worker exited without a result", file=sys.stderr)
        return 1

    candidate = prepare_tracking_candidate(session.project, request, result_path)
    if not session.apply_tracking_candidate(candidate):
        print("candidate no longer matches the active project", file=sys.stderr)
        return 1
    session.save()
    completed = next(r for r in session.tracking_runs() if r.run_id == request.run.run_id)
    print(f"completed run {completed.run_id} status={completed.status} "
          f"import={completed.extra_fields.get('import_summary')}")
    print("saved project (candidate run recorded; nothing activated)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
