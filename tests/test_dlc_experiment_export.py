"""P1.2-S5:experiment 四 bodypart DLC 导出的 golden structure 测试。

一帧一次解码、一行八坐标按规范 role 序、bodypart 错位整体拒绝、
foreign labeled-data 守卫、行数=计划行数。
"""

import csv
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np
import pytest

from ai_physics_tracker.application.experiment_export import ExperimentExportRow
from ai_physics_tracker.infrastructure.dlc_adapter import DLCAdapter
from ai_physics_tracker.infrastructure.opencv_video_reader import OpenCVVideoReader


class _FakeDataFrame:
    def to_hdf(self, path: str, key: str, mode: str) -> None:
        Path(path).write_bytes(b"fake hdf5")


def _fake_pandas() -> SimpleNamespace:
    return SimpleNamespace(read_csv=lambda *args, **kwargs: _FakeDataFrame())


def _reader(tmp_path: Path, frame_count: int = 30) -> MagicMock:
    video_file = tmp_path / "pendulum.mp4"
    video_file.touch()
    reader = MagicMock(spec=OpenCVVideoReader)
    reader.info.frame_count = frame_count
    reader.is_open = True
    reader.path = video_file
    pixels = np.zeros((48, 64, 3), dtype=np.uint8)
    reader.read_frame.side_effect = lambda index: SimpleNamespace(
        frame_index=index, pixels_rgb=pixels
    )
    return reader


def _adapter_with_pendulum_config(tmp_path: Path) -> tuple[DLCAdapter, Path]:
    adapter = DLCAdapter()
    video_file = tmp_path / "pendulum.mp4"
    video_file.touch()
    config_path = adapter.create_project(
        project_name="proj",
        experimenter="Tester",
        video_path=video_file,
        working_dir=tmp_path,
        bodyparts=["tip", "body_top", "body_bottom", "pivot"],
    )
    return adapter, config_path


def test_export_writes_full_rows_in_canonical_role_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(sys.modules, "pandas", _fake_pandas())
    adapter, config_path = _adapter_with_pendulum_config(tmp_path)
    reader = _reader(tmp_path)
    rows = (
        ExperimentExportRow(
            frame_index=9,
            coordinates=((1.0, 2.0), (3.0, 4.0), (5.0, 6.0), (7.0, 8.0)),
        ),
        ExperimentExportRow(
            frame_index=5,
            coordinates=((10.0, 20.0), (30.0, 40.0), (50.0, 60.0), (70.0, 80.0)),
        ),
    )

    count = adapter.export_experiment_annotations(
        rows, reader, config_path, scorer="Tester"
    )

    assert count == 2
    csv_path = tmp_path / "proj" / "labeled-data" / "pendulum" / "CollectedData_Tester.csv"
    with open(csv_path, encoding="utf-8") as f:
        table = list(csv.reader(f))
    assert table[0] == ["scorer"] + ["Tester"] * 8
    assert table[1] == [
        "bodyparts", "tip", "tip", "body_top", "body_top",
        "body_bottom", "body_bottom", "pivot", "pivot",
    ]
    assert table[2] == ["coords"] + ["x", "y"] * 4
    # 行按帧升序(5 在 9 前),每行 8 个坐标全填满——首列缺陷的回归
    assert table[3][0].endswith("img00005.png")
    assert table[3][1:] == [
        "10.00", "20.00", "30.00", "40.00", "50.00", "60.00", "70.00", "80.00"
    ]
    assert table[4][1:] == [
        "1.00", "2.00", "3.00", "4.00", "5.00", "6.00", "7.00", "8.00"
    ]
    # 每帧恰一张 PNG(一次解码)
    labeled = tmp_path / "proj" / "labeled-data" / "pendulum"
    assert sorted(p.name for p in labeled.glob("*.png")) == [
        "img00005.png", "img00009.png"
    ]
    assert reader.read_frame.call_count == 2
    assert (labeled / "CollectedData_Tester.h5").is_file()


def test_export_rejects_bodypart_order_mismatch(tmp_path: Path) -> None:
    adapter = DLCAdapter()
    video_file = tmp_path / "pendulum.mp4"
    video_file.touch()
    config_path = adapter.create_project(
        project_name="proj",
        experimenter="Tester",
        video_path=video_file,
        working_dir=tmp_path,
        bodyparts=["tip", "body_top", "body_bottom", "pivot"],
    )
    # 手改 config 的 bodypart 顺序:导出必须整体拒绝(列错位不可察觉)
    text = config_path.read_text(encoding="utf-8")
    text = text.replace(
        "bodyparts:\n  - tip\n  - body_top\n  - body_bottom\n  - pivot",
        "bodyparts:\n  - pivot\n  - body_top\n  - body_bottom\n  - tip",
    )
    assert "  - pivot\n  - body_top" in text  # 确认篡改生效
    config_path.write_text(text, encoding="utf-8")
    reader = _reader(tmp_path)
    rows = (
        ExperimentExportRow(
            frame_index=5,
            coordinates=((1.0, 2.0), (3.0, 4.0), (5.0, 6.0), (7.0, 8.0)),
        ),
    )
    with pytest.raises(RuntimeError, match="do not match the canonical"):
        adapter.export_experiment_annotations(rows, reader, config_path)


def test_export_rejects_duplicate_frames(tmp_path: Path) -> None:
    adapter, config_path = _adapter_with_pendulum_config(tmp_path)
    reader = _reader(tmp_path)
    row = ExperimentExportRow(
        frame_index=5,
        coordinates=((1.0, 2.0), (3.0, 4.0), (5.0, 6.0), (7.0, 8.0)),
    )
    with pytest.raises(RuntimeError, match="Duplicate export row"):
        adapter.export_experiment_annotations(
            (row, ExperimentExportRow(5, row.coordinates)), reader, config_path
        )


def test_export_rejects_foreign_labeled_data(tmp_path: Path) -> None:
    adapter, config_path = _adapter_with_pendulum_config(tmp_path)
    reader = _reader(tmp_path)
    foreign = tmp_path / "proj" / "labeled-data" / "other-video"
    foreign.mkdir(parents=True)
    row = ExperimentExportRow(
        frame_index=5,
        coordinates=((1.0, 2.0), (3.0, 4.0), (5.0, 6.0), (7.0, 8.0)),
    )
    with pytest.raises(RuntimeError, match="another video"):
        adapter.export_experiment_annotations((row,), reader, config_path)
