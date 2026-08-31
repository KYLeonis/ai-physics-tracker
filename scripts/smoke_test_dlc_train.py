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


def main() -> None:
    print("=== DeepLabCut 3.x Real Smoke Test ===")
    tmp_dir = Path(tempfile.mkdtemp(prefix="dlc_smoke_"))
    print(f"Working directory: {tmp_dir}")

    try:
        # 1. 创建合成视频（10 帧，100x100）
        video_path = tmp_dir / "synthetic_pendulum.mp4"
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        writer = cv2.VideoWriter(str(video_path), fourcc, 30.0, (100, 100))
        for i in range(10):
            img = np.zeros((100, 100, 3), dtype=np.uint8)
            # 绘制一个白色移动圆点
            cx, cy = 30 + i * 4, 50
            cv2.circle(img, (cx, cy), 5, (255, 255, 255), -1)
            writer.write(img)
        writer.release()
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

        # 4. 创建训练数据集
        print("Creating training dataset...")
        adapter.create_training_dataset(config_path, num_shuffles=1)
        print("Training dataset created successfully")

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

        print("=== Real DLC 3.x Smoke Test PASSED! ===")
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


if __name__ == "__main__":
    main()
