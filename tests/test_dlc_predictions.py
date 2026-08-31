"""DLC 预测结果解析边界测试。"""

import csv
from pathlib import Path
from unittest.mock import MagicMock
from uuid import uuid4

import numpy as np
import pytest

from ai_physics_tracker.domain.timeline import Timeline
from ai_physics_tracker.infrastructure.dlc_predictions import (
    ParsedPredictions,
    parse_predictions,
)


def _timeline(frame_count: int = 4) -> Timeline:
    return Timeline(uuid4(), 20.0, (0, frame_count - 1))


def _parse(records: list[dict], **kwargs: object) -> ParsedPredictions:
    frame_count = kwargs.get("frame_count", 4)
    timeline_frame_count = frame_count if isinstance(frame_count, int) and frame_count > 0 else 4
    return parse_predictions(
        records,
        uuid4(),
        _timeline(timeline_frame_count),
        "dlc:run-1",
        **kwargs,
    )


def test_records_return_points_and_separate_missing_and_low_counts() -> None:
    result = _parse(
        [
            {"frame_index": 0, "pixel_x": 10, "pixel_y": 20, "confidence": 0.5},
            {"frame": 1, "x": 11, "y": 21, "likelihood": 0.49},
            {"frame_index": 2, "x": np.nan, "y": 22, "likelihood": 0.9},
            {"frame_index": 3, "x": 13, "y": 23, "likelihood": np.nan},
        ],
        min_confidence=0.5,
        frame_count=4,
    )

    assert result.row_count == 4
    assert result.missing_count == 2
    assert result.low_confidence_count == 1
    assert len(result.points) == 1
    point = result.points[0]
    assert point.frame_index == 0
    assert point.time_s == 0.0
    assert point.pixel_x == 10.0
    assert point.pixel_y == 20.0
    assert point.source == "dlc"
    assert point.source_detail == "dlc:run-1"
    assert point.confidence == 0.5
    assert point.visibility == "unknown"


@pytest.mark.parametrize("threshold", [-0.01, 1.01, float("nan"), float("inf")])
def test_threshold_must_be_finite_and_in_range(threshold: float) -> None:
    with pytest.raises(ValueError, match="min_confidence"):
        _parse(
            [{"frame": 0, "x": 1, "y": 2, "likelihood": 1}],
            min_confidence=threshold,
            frame_count=1,
        )


@pytest.mark.parametrize("frame_value", [True, 1.0, -1])
def test_record_frame_must_be_non_negative_integer(frame_value: object) -> None:
    with pytest.raises(ValueError, match="frame"):
        _parse(
            [{"frame": frame_value, "x": 1, "y": 2, "likelihood": 1}],
            frame_count=None,
        )


def test_duplicate_and_incomplete_frames_are_rejected_without_renumbering() -> None:
    with pytest.raises(ValueError, match="duplicate"):
        _parse(
            [
                {"frame": 0, "x": 1, "y": 2, "likelihood": 1},
                {"frame": 0, "x": 3, "y": 4, "likelihood": 1},
            ],
            frame_count=None,
        )
    with pytest.raises(ValueError, match="cover"):
        _parse(
            [
                {"frame": 1, "x": 1, "y": 2, "likelihood": 1},
                {"frame": 2, "x": 3, "y": 4, "likelihood": 1},
            ],
            frame_count=2,
        )


def test_sparse_frames_are_allowed_without_frame_count() -> None:
    result = _parse(
        [{"frame": 7, "x": 1, "y": 2, "likelihood": 1}],
        frame_count=None,
    )
    assert [point.frame_index for point in result.points] == [7]


def test_invalid_confidence_is_not_hidden_by_nan_coordinates() -> None:
    with pytest.raises(ValueError, match="likelihood"):
        _parse(
            [
                {"frame": 0, "x": np.nan, "y": 2, "likelihood": 1.5},
                {"frame": 1, "x": 3, "y": 4, "likelihood": 0.9},
            ],
            frame_count=None,
        )


@pytest.mark.parametrize("likelihood", [float("inf"), float("-inf"), -0.1, 1.1])
def test_invalid_likelihood_rejects_the_whole_batch(likelihood: float) -> None:
    with pytest.raises(ValueError, match="likelihood"):
        _parse(
            [
                {"frame": 0, "x": 1, "y": 2, "likelihood": likelihood},
                {"frame": 1, "x": 3, "y": 4, "likelihood": 0.9},
            ],
            frame_count=None,
        )


def test_dataframe_duck_type_accepts_numpy_integer_index() -> None:
    dataframe = MagicMock()
    columns = [
        ("scorer", "target", "x"),
        ("scorer", "target", "y"),
        ("scorer", "target", "likelihood"),
    ]
    dataframe.columns = columns
    dataframe.iterrows.return_value = [
        (np.int64(0), {columns[0]: 1, columns[1]: 2, columns[2]: 0.8}),
    ]

    result = parse_predictions(dataframe, uuid4(), _timeline(1), "run")
    assert result.row_count == 1
    assert result.points[0].frame_index == 0


@pytest.mark.parametrize(
    "columns",
    [
        [
            ("s", "target", "x"),
            ("s", "target", "y"),
        ],
        [
            ("s", "target", "x"),
            ("s", "target", "x"),
            ("s", "target", "y"),
            ("s", "target", "likelihood"),
        ],
        [
            ("s", "target", "x", "extra"),
            ("s", "target", "y", "extra"),
            ("s", "target", "likelihood", "extra"),
        ],
        [
            ("s1", "target", "x"),
            ("s1", "target", "y"),
            ("s1", "target", "likelihood"),
            ("s2", "target", "x"),
            ("s2", "target", "y"),
            ("s2", "target", "likelihood"),
        ],
    ],
)
def test_dataframe_schema_must_have_one_complete_scorer_bodypart(columns: list[tuple]) -> None:
    dataframe = MagicMock()
    dataframe.columns = columns
    dataframe.iterrows.return_value = []
    with pytest.raises(ValueError):
        parse_predictions(dataframe, uuid4(), _timeline(1), "run")


def test_csv_uses_stdlib_and_converts_integer_frame_strings(tmp_path: Path) -> None:
    path = tmp_path / "predictions.csv"
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(["scorer", "DLC", "DLC", "DLC"])
        writer.writerow(["bodyparts", "target", "target", "target"])
        writer.writerow(["coords", "x", "y", "likelihood"])
        writer.writerow(["0", "1.5", "2.5", "0.8"])
        writer.writerow(["1", "3.5", "4.5", "0.2"])

    result = parse_predictions(
        path,
        uuid4(),
        _timeline(2),
        "dlc:csv",
        min_confidence=0.5,
        frame_count=2,
    )
    assert result.row_count == 2
    assert result.low_confidence_count == 1
    assert result.points[0].frame_index == 0
    assert result.points[0].pixel_x == 1.5


def test_csv_rejects_non_integer_frame_strings(tmp_path: Path) -> None:
    path = tmp_path / "bad.csv"
    path.write_text(
        "scorer,s,s,s\nbodyparts,target,target,target\ncoords,x,y,likelihood\n1.0,1,2,0.9\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="integer"):
        parse_predictions(path, uuid4(), _timeline(1), "run")


def test_hdf_path_is_loaded_through_standard_dlc_key(tmp_path: Path) -> None:
    pd = pytest.importorskip("pandas")
    pytest.importorskip("tables")
    columns = pd.MultiIndex.from_tuples(
        [
            ("scorer", "target", "x"),
            ("scorer", "target", "y"),
            ("scorer", "target", "likelihood"),
        ]
    )
    dataframe = pd.DataFrame([[1.0, 2.0, 0.9]], index=np.array([0], dtype=np.int64), columns=columns)
    path = tmp_path / "predictions.h5"
    dataframe.to_hdf(path, key="df_with_missing")

    result = parse_predictions(path, uuid4(), _timeline(1), "dlc:h5", frame_count=1)
    assert result.points[0].confidence == 0.9
