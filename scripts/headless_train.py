#!/usr/bin/env python
"""Headless 训练驱动：走与 GUI 完全一致的应用层路径（无 Qt）。

用途：后台对已保存项目发起一次训练（prepare → spawn worker → candidate
提交 → 保存）；配合 --repeat 可重复同配置训练以测量 run-to-run 方差。

用法：
    python scripts/headless_train.py --project <项目目录> [--epochs 50]
        [--repeat 2] [--timeout-min 60]
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
from ai_physics_tracker.application.tracking_types import TaskResult, TrainingParams
from ai_physics_tracker.domain.tracking_run import mark_run_running
from ai_physics_tracker.infrastructure.ffprobe_timing import FFprobeTimingProbe
from ai_physics_tracker.infrastructure.project_repository import ProjectRepository
from ai_physics_tracker.infrastructure.task_runner import BackgroundTaskRunner


def run_once(root: Path, epochs: int, timeout_min: float, label: str) -> float | None:
    from ai_physics_tracker.infrastructure.dlc_adapter import DLCAdapter

    session = ProjectSession.load(ProjectRepository(), root)
    video = session.project.videos[0]
    report = FFprobeTimingProbe().probe(session.video_path(video))
    session.confirm_video_timing(video.video_id, report)
    track = session.tracks[0]
    request = prepare_tracking_request(
        session, track.track_id,
        TrainingParams(epochs=epochs, extra_params={}))
    print(f"[{label}] prepared train run {request.run.run_id}", flush=True)
    session.record_tracking_run(request.run)
    session.update_tracking_run(mark_run_running(request.run))

    handle = BackgroundTaskRunner().start_task(
        request.run.run_id, run_tracking_worker, request, DLCAdapter())
    deadline = time.monotonic() + timeout_min * 60
    result_path = None
    while handle.is_alive() and time.monotonic() < deadline:
        for message in handle.poll_messages(limit=200):
            if isinstance(message, TaskResult) and not message.success:
                print(f"[{label}] FAILED: {message.error}", file=sys.stderr, flush=True)
                return None
            if (isinstance(message, TaskResult) and message.success
                    and isinstance(message.payload, dict)
                    and message.payload.get("result_path")):
                result_path = root / message.payload["result_path"]
    handle.join(timeout_s=5.0)
    for message in handle.poll_messages(limit=500):
        if isinstance(message, TaskResult) and not message.success:
            print(f"[{label}] FAILED: {message.error}", file=sys.stderr, flush=True)
            return None
        if (isinstance(message, TaskResult) and message.success
                and isinstance(message.payload, dict)
                and message.payload.get("result_path")):
            result_path = root / message.payload["result_path"]
    if result_path is None:
        print(f"[{label}] worker exited without a result", file=sys.stderr, flush=True)
        return None

    candidate = prepare_tracking_candidate(session.project, request, result_path)
    if not session.apply_tracking_candidate(candidate):
        print(f"[{label}] candidate no longer matches the active project",
              file=sys.stderr, flush=True)
        return None
    session.save()
    run = next(r for r in session.tracking_runs() if r.run_id == request.run.run_id)
    evaluation = run.extra_fields.get("evaluation") or {}
    val = ((evaluation.get("test") or {}).get("metrics") or {}).get("rmse")
    train = ((evaluation.get("train") or {}).get("metrics") or {}).get("rmse")
    print(f"[{label}] completed {run.run_id} train_RMSE={train} val_RMSE={val}", flush=True)
    return val


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True)
    parser.add_argument("--epochs", type=int, default=50)
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--timeout-min", type=float, default=60.0)
    args = parser.parse_args()

    root = Path(args.project).resolve()
    values = []
    for index in range(args.repeat):
        value = run_once(root, args.epochs, args.timeout_min, f"run{index + 1}")
        if value is None:
            return 1
        values.append(value)
    print(f"val RMSE samples: {values}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
