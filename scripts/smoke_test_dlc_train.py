"""真实 DeepLabCut 3.x 训练冒烟测试脚本。"""

import os
from pathlib import Path
import shutil
import sys
import tempfile
from uuid import uuid4

import cv2
import numpy as np

# 确保项目源码在 sys.path
repo_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(repo_root / "src"))

from ai_physics_tracker.domain.track import TrackPoint
from ai_physics_tracker.domain.types import utc_now
from ai_physics_tracker.infrastructure.dlc_adapter import DLCAdapter
from ai_physics_tracker.infrastructure.engine_adapter import TrainingParams
from ai_physics_tracker.infrastructure.opencv_video_reader import OpenCVVideoReader


def create_synthetic_video(video_path: Path, frame_count: int = 10) -> None:
    """生成恒定帧率移动圆点，供训练/推理冒烟共用。"""
    writer = cv2.VideoWriter(str(video_path), cv2.VideoWriter_fourcc(*"mp4v"),
                             30.0, (100, 100))
    if not writer.isOpened():
        raise RuntimeError("Cannot create synthetic video")
    try:
        for frame_index in range(frame_count):
            img = np.zeros((100, 100, 3), dtype=np.uint8)
            cv2.circle(img, (30 + frame_index * 4, 50), 5, (255, 255, 255), -1)
            writer.write(img)
    finally:
        writer.release()


def main() -> None:
    print("=== DeepLabCut 3.x Real Smoke Test ===")
    tmp_dir = Path(tempfile.mkdtemp(prefix="dlc_smoke_"))
    print(f"Working directory: {tmp_dir}")

    try:
        # 1. 创建合成视频（10 帧，100x100）
        video_path = tmp_dir / "synthetic_pendulum.mp4"
        create_synthetic_video(video_path)
        print(f"Created synthetic video: {video_path}")

        adapter = DLCAdapter()
        print(f"DeepLabCut version: {adapter.engine_version()}")

        # 2. 创建 DLC 项目
        config_path = adapter.create_project(
            project_name="smoke_test_project",
            experimenter="AIPhysicsTracker",
            video_path=video_path,
            working_dir=tmp_dir,
            bodyparts=["target"],
        )
        print(f"Created DLC config: {config_path}")

        # 3. 构造 5 个人工标注点并导出
        now = utc_now()
        track_id = uuid4()
        points = []
        for i in range(5):
            points.append(
                TrackPoint(
                    point_id=uuid4(),
                    track_id=track_id,
                    frame_index=i * 2,
                    time_s=(i * 2) / 30.0,
                    pixel_x=float(30 + (i * 2) * 4),
                    pixel_y=50.0,
                    source="manual",
                    visibility="visible",
                    status="active",
                    created_at=now,
                    modified_at=now,
                )
            )

        video_reader = OpenCVVideoReader()
        video_reader.open(video_path)
        exported_count = adapter.export_annotations(
            tuple(points),
            video_reader,
            config_path,
            scorer="AIPhysicsTracker",
            bodyparts=["target"],
        )
        video_reader.close()
        print(f"Exported {exported_count} frames to DLC labeled-data")

        # 4. 创建训练数据集（包含显式 fixed split: 3 train, 2 test）
        print("Creating training dataset with fixed split...")
        adapter.create_training_dataset(
            config_path,
            num_shuffles=1,
            train_indices=[0, 1, 2],
            test_indices=[3, 4],
        )
        print("Training dataset created successfully with fixed split")

        # 5. 执行 1 epoch 真实训练（CPU 模式冒烟）
        from multiprocessing import Event, Queue

        queue = Queue()
        cancel_event = Event()
        params = TrainingParams(epochs=1, batch_size=1, device="cpu")

        print("Starting 1 epoch real training...")
        outcome = adapter.train(
            run_id=uuid4(),
            queue=queue,
            cancel_event=cancel_event,
            config_path=config_path,
            params=params,
        )

        print(f"Training outcome: status={outcome.status}, snapshot={outcome.snapshot_path}")
        if outcome.status != "completed":
            print(f"Smoke test failed! Error: {outcome.error_message}", file=sys.stderr)
            sys.exit(1)

        # 6. Resume/fine-tune（ADR-0015）：从第一阶段 snapshot 继续训练 1 epoch。
        # 使用全新的 DLC 项目目录（与产品 per-run 语义一致），验证 snapshot_path
        # 能跨项目加载权重并产出新 snapshot。
        print("Starting resume stage (1 epoch from previous snapshot)...")
        resume_config = adapter.create_project(
            project_name="smoke_test_project_resume",
            experimenter="AIPhysicsTracker",
            video_path=video_path,
            working_dir=tmp_dir / "resume_run",
            bodyparts=["target"],
        )
        video_reader = OpenCVVideoReader()
        video_reader.open(video_path)
        adapter.export_annotations(
            tuple(points), video_reader, resume_config,
            scorer="AIPhysicsTracker", bodyparts=["target"],
        )
        video_reader.close()
        adapter.create_training_dataset(
            resume_config, num_shuffles=1, train_indices=[0, 1, 2], test_indices=[3, 4],
        )
        resume_outcome = adapter.train(
            run_id=uuid4(),
            queue=queue,
            cancel_event=Event(),
            config_path=resume_config,
            params=params,
            snapshot_path=Path(outcome.snapshot_path),
        )
        print(f"Resume outcome: status={resume_outcome.status}, "
              f"snapshot={resume_outcome.snapshot_path}")
        if resume_outcome.status != "completed":
            print(f"Resume stage failed! Error: {resume_outcome.error_message}",
                  file=sys.stderr)
            sys.exit(1)
        if Path(resume_outcome.snapshot_path).resolve() == Path(outcome.snapshot_path).resolve():
            print("Resume must produce a NEW snapshot, not overwrite the parent",
                  file=sys.stderr)
            sys.exit(1)

        print("=== Real DLC 3.x Smoke Test PASSED! (restart + resume) ===")
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


if __name__ == "__main__":
    main()
