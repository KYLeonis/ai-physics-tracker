"""P1.2-S6 真实 DeepLabCut 3.x 四 bodypart dataset 冒烟测试。

验证链（计划 §6 Real DLC verification）：
1. 合成短视频（4 个不同位置的标记点）；
2. DLCAdapter.create_project 以规范四 bodypart 建 config；
3. export_experiment_annotations 导出 ExperimentExportRow（一帧一行八坐标）；
4. deeplabcut.create_training_dataset 以显式共同 split 读取；
5. 解析生成的训练 CSV/HDF，断言四 bodyparts 与行结构；
此处不训练、不声称任何模型精度。
"""

import os
from pathlib import Path
import shutil
import sys
import tempfile

import cv2
import numpy as np

repo_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(repo_root / "src"))

from ai_physics_tracker.application.experiment_export import ExperimentExportRow
from ai_physics_tracker.domain.pendulum import ROLE_ORDER
from ai_physics_tracker.infrastructure.dlc_adapter import DLCAdapter
from ai_physics_tracker.infrastructure.opencv_video_reader import OpenCVVideoReader

FRAME_COUNT = 12
# 每帧四点位置随帧移动，保证坐标非退化
FRAME_MARKS = {
    frame: tuple(
        (float(20 + frame * 2 + role * 6), float(25.0 + role * 15))
        for role in range(4)
    )
    for frame in range(FRAME_COUNT)
}


def create_synthetic_video(video_path: Path) -> None:
    """生成含四个可见标记的 CFR 短视频（每 role 一个圆点）。"""

    writer = cv2.VideoWriter(
        str(video_path), cv2.VideoWriter_fourcc(*"mp4v"), 30.0, (120, 100)
    )
    if not writer.isOpened():
        raise RuntimeError("Cannot create synthetic video")
    try:
        for frame_index in range(FRAME_COUNT):
            img = np.zeros((100, 120, 3), dtype=np.uint8)
            for role, (x, y) in enumerate(FRAME_MARKS[frame_index]):
                color = (60 * (role + 1), 255 - 60 * role, 128)
                cv2.circle(img, (int(x), int(y)), 4, color, -1)
            writer.write(img)
    finally:
        writer.release()


def main() -> int:
    print("=== P1.2-S6 four-bodypart DLC dataset smoke ===")
    tmp_dir = Path(tempfile.mkdtemp(prefix="p12_dlc_smoke_"))
    print(f"Working directory: {tmp_dir}")
    try:
        video_path = tmp_dir / "synthetic_pendulum4.mp4"
        create_synthetic_video(video_path)
        print(f"Synthetic video: {video_path} ({FRAME_COUNT} frames)")

        adapter = DLCAdapter()
        print(f"DeepLabCut version: {adapter.engine_version()}")

        config_path = adapter.create_project(
            project_name="p12_smoke",
            experimenter="AIPhysicsTracker",
            video_path=video_path,
            working_dir=tmp_dir,
            bodyparts=list(ROLE_ORDER),
        )
        print(f"Created DLC config with bodyparts {list(ROLE_ORDER)}")

        # 导出行：帧 1,4,7,10（train）与 2,5,8（fixed-check/test）
        train_frames = (1, 4, 7, 10)
        test_frames = (2, 5, 8)
        rows = tuple(
            ExperimentExportRow(frame_index=frame, coordinates=FRAME_MARKS[frame])
            for frame in sorted(train_frames + test_frames)
        )
        reader = OpenCVVideoReader()
        reader.open(video_path)
        try:
            exported = adapter.export_experiment_annotations(
                rows, reader, config_path, scorer="AIPhysicsTracker"
            )
        finally:
            reader.close()
        print(f"Exported {exported} rows (one PNG + one 8-coordinate row each)")
        assert exported == len(rows), "row count mismatch"

        train_indices, test_indices = (
            tuple(range(len(train_frames))),
            tuple(range(len(train_frames), len(rows))),
        )
        print(
            f"Creating training dataset with shared split: "
            f"train={list(train_indices)} test={list(test_indices)}"
        )
        adapter.create_training_dataset(
            config_path,
            num_shuffles=1,
            train_indices=list(train_indices),
            test_indices=list(test_indices),
        )
        print("create_training_dataset OK — DLC accepted the four-bodypart data")

        # 独立解析生成的 CSV：断言结构而非信任 DLC 静默成功
        csv_candidates = list(
            (tmp_dir / "p12_smoke" / "labeled-data" / "synthetic_pendulum4").glob(
                "CollectedData_*.csv"
            )
        )
        assert csv_candidates, "CollectedData CSV not found after dataset creation"
        import csv as csv_module

        with open(csv_candidates[0], encoding="utf-8") as handle:
            table = list(csv_module.reader(handle))
        assert table[1][1:3] == ["tip", "tip"], table[1]
        assert table[1][3:5] == ["body_top", "body_top"], table[1]
        assert table[1][5:7] == ["body_bottom", "body_bottom"], table[1]
        assert table[1][7:9] == ["pivot", "pivot"], table[1]
        data_rows = [row for row in table[3:] if row]
        assert len(data_rows) == len(rows), (
            f"expected {len(rows)} data rows, got {len(data_rows)}"
        )
        for row in data_rows:
            filled = row[1:]
            assert len(filled) == 8 and all(value != "" for value in filled), (
                f"incomplete coordinate row: {row}"
            )
        print(
            "Parsed generated CSV: 4 canonical bodyparts, "
            f"{len(data_rows)} complete 8-coordinate rows"
        )
        print("=== P1.2-S6 smoke PASS ===")
        return 0
    except Exception as error:
        print(f"SMOKE FAILED: {error}", file=sys.stderr)
        import traceback

        traceback.print_exc()
        return 1
    finally:
        keep = os.environ.get("P12_SMOKE_KEEP")
        if keep:
            print(f"Keeping working directory: {tmp_dir}")
        else:
            shutil.rmtree(tmp_dir, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
