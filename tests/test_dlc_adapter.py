"""DLC 引擎适配器、数据转换与 Mock 适配器测试。"""

import csv
from pathlib import Path
from unittest.mock import MagicMock
from uuid import uuid4

import numpy as np
import pytest

from ai_physics_tracker.application.video import DecodedFrame
from ai_physics_tracker.domain.timeline import Timeline
from ai_physics_tracker.domain.track import TrackPoint
from ai_physics_tracker.domain.types import utc_now
from ai_physics_tracker.infrastructure.dlc_adapter import (
    DLCAdapter,
    detect_device,
)
from ai_physics_tracker.infrastructure.engine_adapter import EngineAdapter
from ai_physics_tracker.infrastructure.mock_engine_adapter import MockEngineAdapter
from ai_physics_tracker.infrastructure.opencv_video_reader import OpenCVVideoReader


def test_adapters_satisfy_protocol() -> None:
    dlc = DLCAdapter()
    mock = MockEngineAdapter()
    assert isinstance(dlc, EngineAdapter)
    assert isinstance(mock, EngineAdapter)


def test_dlc_create_project(tmp_path: Path) -> None:
    adapter = DLCAdapter()
    video_file = tmp_path / "test_video.mp4"
    video_file.touch()

    config_path = adapter.create_project(
        project_name="pendulum_exp",
        experimenter="Leonis",
        video_path=video_file,
        working_dir=tmp_path,
        bodyparts=["bob", "pivot"],
    )

    assert config_path.is_file()
    assert config_path.name == "config.yaml"

    content = config_path.read_text(encoding="utf-8")
    assert "Task: pendulum_exp" in content
    assert "scorer: Leonis" in content
    assert "bob" in content
    assert "pivot" in content
    assert "engine: pytorch" in content

    proj_dir = tmp_path / "pendulum_exp"
    assert (proj_dir / "labeled-data" / "test_video").is_dir()
    assert (proj_dir / "training-datasets").is_dir()
    assert (proj_dir / "dlc-models").is_dir()


def test_dlc_export_annotations(tmp_path: Path) -> None:
    adapter = DLCAdapter()
    video_file = tmp_path / "sample.mp4"
    video_file.touch()
    config_path = adapter.create_project(
        project_name="proj",
        experimenter="Tester",
        video_path=video_file,
        working_dir=tmp_path,
        bodyparts=["target"],
    )

    track_id = uuid4()
    now = utc_now()
    # 构造 2 个 active manual 点和 1 个 superseded 点
    p1 = TrackPoint(
        point_id=uuid4(),
        track_id=track_id,
        frame_index=5,
        time_s=5 / 30.0,
        pixel_x=100.5,
        pixel_y=200.5,
        source="manual",
        visibility="visible",
        status="active",
        created_at=now,
        modified_at=now,
    )
    p2 = TrackPoint(
        point_id=uuid4(),
        track_id=track_id,
        frame_index=15,
        time_s=15 / 30.0,
        pixel_x=120.0,
        pixel_y=220.0,
        source="manual",
        visibility="visible",
        status="active",
        created_at=now,
        modified_at=now,
    )
    p_superseded = TrackPoint(
        point_id=uuid4(),
        track_id=track_id,
        frame_index=25,
        time_s=25 / 30.0,
        pixel_x=300.0,
        pixel_y=300.0,
        source="manual",
        visibility="visible",
        status="superseded",
        superseded_by=p1.point_id,
        created_at=now,
        modified_at=now,
    )

    # 模拟视频读取器
    mock_reader = MagicMock(spec=OpenCVVideoReader)
    mock_reader.is_open = True
    dummy_pixels = np.zeros((100, 100, 3), dtype=np.uint8)
    mock_reader.read_frame.return_value = DecodedFrame(
        frame_index=5,
        pixels_rgb=dummy_pixels,
    )

    count = adapter.export_annotations(
        track_points=(p1, p2, p_superseded),
        video_reader=mock_reader,
        config_path=config_path,
        scorer="AIPhysicsTracker",
        bodyparts=["target"],
    )

    assert count == 2

    # 验证导出的 CSV 内容
    csv_path = tmp_path / "proj" / "labeled-data" / "sample" / "CollectedData_AIPhysicsTracker.csv"
    assert csv_path.is_file()

    with open(csv_path, encoding="utf-8") as f:
        reader = list(csv.reader(f))

    assert len(reader) == 5  # 3 rows of headers + 2 rows of data
    assert reader[0] == ["scorer", "AIPhysicsTracker", "AIPhysicsTracker"]
    assert reader[1] == ["bodyparts", "target", "target"]
    assert reader[2] == ["coords", "x", "y"]
    assert reader[3][1:] == ["100.50", "200.50"]
    assert reader[4][1:] == ["120.00", "220.00"]

    # 验证 PNG 图像文件已创建
    img1 = tmp_path / "proj" / "labeled-data" / "sample" / "img00005.png"
    img2 = tmp_path / "proj" / "labeled-data" / "sample" / "img00015.png"
    assert img1.is_file()
    assert img2.is_file()


def test_dlc_import_results_dict_records() -> None:
    adapter = DLCAdapter()
    tid = uuid4()
    vid = uuid4()
    timeline = Timeline(video_id=vid, fps_nominal=30.0, working_zone=(0, 100))

    prediction_records = [
        {"frame_index": 0, "x": 10.0, "y": 20.0, "likelihood": 0.99},
        {"frame_index": 1, "x": 12.0, "y": 22.0, "likelihood": 0.85},
        {"frame_index": 2, "x": 14.0, "y": 24.0, "likelihood": 0.10},  # 低置信度
        {"frame_index": 3, "x": float("nan"), "y": 26.0, "likelihood": 0.90},  # NaN 坐标
    ]

    # min_confidence=0.5 过滤
    points = adapter.import_results(
        prediction_data=prediction_records,
        track_id=tid,
        timeline=timeline,
        source_detail="dlc:run1",
        min_confidence=0.5,
    )

    assert len(points) == 2
    assert points[0].frame_index == 0
    assert points[0].pixel_x == 10.0
    assert points[0].pixel_y == 20.0
    assert points[0].confidence == 0.99
    assert points[0].source == "dlc"
    assert points[0].source_detail == "dlc:run1"
    assert points[0].time_s == 0.0

    assert points[1].frame_index == 1
    assert points[1].pixel_x == 12.0
    assert points[1].confidence == 0.85
    assert points[1].time_s == 1 / 30.0


def test_detect_device() -> None:
    device = detect_device()
    assert device in {"cuda", "mps", "cpu"}


def test_mock_engine_adapter(tmp_path: Path) -> None:
    adapter = MockEngineAdapter(default_confidence=0.92)
    video_file = tmp_path / "vid.mp4"
    video_file.touch()

    config_path = adapter.create_project("p1", "Exp", video_file, tmp_path)
    assert config_path.is_file()

    tid = uuid4()
    vid = uuid4()
    timeline = Timeline(video_id=vid, fps_nominal=25.0, working_zone=(0, 50))
    records = [{"frame": 0, "x": 5.0, "y": 6.0}]
    pts = adapter.import_results(records, tid, timeline, "mock:1")

    assert len(pts) == 1
    assert pts[0].pixel_x == 5.0
    assert pts[0].confidence == 0.92
    assert pts[0].source == "dlc"


def test_dlc_import_results_mock_dataframe() -> None:
    adapter = DLCAdapter()
    tid = uuid4()
    vid = uuid4()
    timeline = Timeline(video_id=vid, fps_nominal=30.0, working_zone=(0, 100))

    # 模拟 Pandas MultiIndex DataFrame
    mock_df = MagicMock()
    col_x = ("AIPhysicsTracker", "target", "x")
    col_y = ("AIPhysicsTracker", "target", "y")
    col_lh = ("AIPhysicsTracker", "target", "likelihood")
    mock_df.columns = [col_x, col_y, col_lh]

    row_0 = {col_x: 50.0, col_y: 60.0, col_lh: 0.95}
    row_1 = {col_x: 55.0, col_y: 65.0, col_lh: 0.20}  # 低于 0.5
    row_2 = {col_x: float("nan"), col_y: 70.0, col_lh: 0.98}

    mock_df.iterrows.return_value = [
        (0, row_0),
        (1, row_1),
        (2, row_2),
    ]

    points = adapter.import_results(
        prediction_data=mock_df,
        track_id=tid,
        timeline=timeline,
        source_detail="dlc:infer:df1",
        bodypart="target",
        min_confidence=0.5,
    )

    assert len(points) == 1
    assert points[0].frame_index == 0
    assert points[0].pixel_x == 50.0
    assert points[0].pixel_y == 60.0
    assert points[0].confidence == 0.95
    assert points[0].source == "dlc"
    assert points[0].source_detail == "dlc:infer:df1"


def test_dlc_export_annotations_frame_read_failure_fallback(tmp_path: Path) -> None:
    adapter = DLCAdapter()
    video_file = tmp_path / "fail_video.mp4"
    video_file.touch()
    config_path = adapter.create_project("proj_fail", "Tester", video_file, tmp_path)

    point = TrackPoint(
        point_id=uuid4(),
        track_id=uuid4(),
        frame_index=10,
        time_s=10 / 30.0,
        pixel_x=50.0,
        pixel_y=60.0,
        source="manual",
        visibility="visible",
        status="active",
        created_at=utc_now(),
        modified_at=utc_now(),
    )

    # 读取器抛出异常
    mock_reader = MagicMock(spec=OpenCVVideoReader)
    mock_reader.is_open = True
    mock_reader.read_frame.side_effect = RuntimeError("Decode error")

    count = adapter.export_annotations((point,), mock_reader, config_path)
    assert count == 1

    img_path = tmp_path / "proj_fail" / "labeled-data" / "fail_video" / "img00010.png"
    assert img_path.is_file()
    assert img_path.stat().st_size > 0


def test_dlc_export_annotations_multiple_bodyparts(tmp_path: Path) -> None:
    adapter = DLCAdapter()
    video_file = tmp_path / "multi_video.mp4"
    video_file.touch()
    config_path = adapter.create_project("proj_multi", "Tester", video_file, tmp_path, bodyparts=["head", "tail"])

    point = TrackPoint(
        point_id=uuid4(),
        track_id=uuid4(),
        frame_index=1,
        time_s=1 / 30.0,
        pixel_x=10.0,
        pixel_y=20.0,
        source="manual",
        visibility="visible",
        status="active",
        created_at=utc_now(),
        modified_at=utc_now(),
    )

    mock_reader = MagicMock(spec=OpenCVVideoReader)
    mock_reader.is_open = False

    count = adapter.export_annotations((point,), mock_reader, config_path, bodyparts=["head", "tail"])
    assert count == 1

    csv_path = tmp_path / "proj_multi" / "labeled-data" / "multi_video" / "CollectedData_AIPhysicsTracker.csv"
    with open(csv_path, encoding="utf-8") as f:
        rows = list(csv.reader(f))

    assert len(rows) == 4
    assert rows[0] == ["scorer", "AIPhysicsTracker", "AIPhysicsTracker", "AIPhysicsTracker", "AIPhysicsTracker"]
    assert rows[1] == ["bodyparts", "head", "head", "tail", "tail"]
    assert rows[2] == ["coords", "x", "y", "x", "y"]
    assert rows[3] == ["labeled-data/multi_video/img00001.png", "10.00", "20.00", "", ""]


def test_training_params_validation_and_config() -> None:
    from ai_physics_tracker.infrastructure.engine_adapter import TrainingParams

    params = TrainingParams(epochs=20, batch_size=4, device="cpu", display_iters=5, save_iters=10)
    cfg = params.to_config()
    assert cfg["epochs"] == 20
    assert cfg["batch_size"] == 4
    assert cfg["device"] == "cpu"

    restored = TrainingParams.from_config(cfg)
    assert restored.epochs == 20
    assert restored.batch_size == 4

    with pytest.raises(ValueError, match="epochs must be positive"):
        TrainingParams(epochs=0)

    with pytest.raises(ValueError, match="batch_size must be positive"):
        TrainingParams(batch_size=-1)


def test_mock_engine_adapter_train(tmp_path: Path) -> None:
    from multiprocessing import Event, Queue
    from ai_physics_tracker.infrastructure.engine_adapter import TrainingParams

    adapter = MockEngineAdapter(version="3.0.1-test")
    assert adapter.engine_version() == "3.0.1-test"

    video_file = tmp_path / "vid.mp4"
    video_file.touch()
    cfg_path = adapter.create_project("test_train", "User", video_file, tmp_path)

    # 1. Successful training
    q = Queue()
    cancel_evt = Event()
    params = TrainingParams(epochs=3, extra_params={"simulate_delay": 0.0})
    outcome = adapter.train(uuid4(), q, cancel_evt, cfg_path, params)

    assert outcome.status == "completed"
    assert outcome.epochs_completed == 3
    assert outcome.snapshot_path is not None
    assert Path(outcome.snapshot_path).is_file()

    # 2. Cancelled training
    cancel_evt.set()
    outcome_cancelled = adapter.train(uuid4(), q, cancel_evt, cfg_path, params)
    assert outcome_cancelled.status == "cancelled"
    assert outcome_cancelled.epochs_completed == 0

    # 3. Simulated failure
    cancel_evt.clear()
    params_fail = TrainingParams(epochs=3, extra_params={"simulate_failure": "Out of memory"})
    outcome_failed = adapter.train(uuid4(), q, cancel_evt, cfg_path, params_fail)
    assert outcome_failed.status == "failed"
    assert outcome_failed.error_message == "Out of memory"



