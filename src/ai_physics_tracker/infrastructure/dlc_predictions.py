"""DLC 预测结果解析器，负责在基础设施边界校验外部数据。"""

from __future__ import annotations

import csv
import os
from dataclasses import dataclass
from math import isfinite, isnan
from numbers import Integral
from pathlib import Path
from typing import Any, Mapping
from uuid import UUID, uuid4

from ai_physics_tracker.domain.timeline import Timeline, frame_to_time
from ai_physics_tracker.domain.track import TrackPoint
from ai_physics_tracker.domain.types import utc_now

_REQUIRED_COORDS = frozenset({"x", "y", "likelihood"})
_PATH_SUFFIXES = frozenset({".h5", ".hdf5"})


@dataclass(frozen=True)
class ParsedPredictions:
    """一次预测结果的点与导入统计。"""

    points: tuple[TrackPoint, ...]
    row_count: int
    missing_count: int
    low_confidence_count: int

    def __post_init__(self) -> None:
        counts = (self.row_count, self.missing_count, self.low_confidence_count)
        if any(isinstance(value, bool) or not isinstance(value, int) or value < 0 for value in counts):
            raise ValueError("prediction counts must be non-negative integers")
        if self.row_count != len(self.points) + self.missing_count + self.low_confidence_count:
            raise ValueError("prediction counts do not add up to row_count")


@dataclass(frozen=True)
class _PredictionRow:
    frame_index: int
    pixel_x: float
    pixel_y: float
    likelihood: float


def parse_predictions(
    prediction_data: Any,
    track_id: UUID,
    timeline: Timeline,
    source_detail: str,
    bodypart: str = "target",
    min_confidence: float = 0.0,
    *,
    frame_count: int | None = None,
) -> ParsedPredictions:
    """解析 DLC DataFrame、HDF5、CSV 或字典记录为 TrackPoint。

    外部结果先整体校验，任何非法帧号、列结构或数值都会拒绝整批；NaN
    只表示缺测，低于阈值的有限 likelihood 计为低置信度且不生成点。
    """

    threshold = _validate_threshold(min_confidence)
    expected_frame_count = _validate_frame_count(frame_count)
    if not isinstance(bodypart, str) or not bodypart:
        raise ValueError("bodypart must be a non-empty string")
    if not isinstance(source_detail, str) or not source_detail.strip():
        raise ValueError("source_detail must identify the inference run")

    rows = _load_rows(prediction_data, bodypart)
    _validate_rows(rows, expected_frame_count)

    now = utc_now()
    points: list[TrackPoint] = []
    missing_count = 0
    low_confidence_count = 0
    for row in rows:
        if isnan(row.pixel_x) or isnan(row.pixel_y) or isnan(row.likelihood):
            missing_count += 1
            continue
        if row.likelihood < threshold:
            low_confidence_count += 1
            continue
        points.append(
            TrackPoint(
                point_id=uuid4(),
                track_id=track_id,
                frame_index=row.frame_index,
                time_s=frame_to_time(row.frame_index, timeline),
                pixel_x=row.pixel_x,
                pixel_y=row.pixel_y,
                source="dlc",
                visibility="unknown",
                status="active",
                created_at=now,
                modified_at=now,
                source_detail=source_detail,
                confidence=row.likelihood,
            )
        )

    return ParsedPredictions(
        points=tuple(points),
        row_count=len(rows),
        missing_count=missing_count,
        low_confidence_count=low_confidence_count,
    )


def _validate_threshold(value: float) -> float:
    if isinstance(value, bool):
        raise ValueError("min_confidence must be finite and in [0, 1]")
    try:
        threshold = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("min_confidence must be finite and in [0, 1]") from exc
    if not isfinite(threshold) or not 0 <= threshold <= 1:
        raise ValueError("min_confidence must be finite and in [0, 1]")
    return threshold


def _validate_frame_count(value: int | None) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, Integral) or value <= 0:
        raise ValueError("frame_count must be a positive integer")
    return int(value)


def _load_rows(prediction_data: Any, bodypart: str) -> list[_PredictionRow]:
    if hasattr(prediction_data, "columns") and hasattr(prediction_data, "iterrows"):
        return _load_dataframe(prediction_data, bodypart)

    if isinstance(prediction_data, (list, tuple)):
        return _load_records(prediction_data)

    if isinstance(prediction_data, (str, os.PathLike)):
        path = Path(prediction_data)
        suffix = path.suffix.lower()
        if suffix == ".csv":
            return _load_csv(path, bodypart)
        if suffix in _PATH_SUFFIXES:
            return _load_hdf(path, bodypart)
        raise ValueError(f"unsupported prediction file type: {path.suffix or '<none>'}")

    raise ValueError("prediction data must be a DataFrame, CSV/HDF5 path, or record sequence")


def _load_hdf(path: Path, bodypart: str) -> list[_PredictionRow]:
    try:
        import pandas as pd
    except ImportError as exc:
        raise ValueError("pandas is required to read HDF5 predictions") from exc

    try:
        dataframe = pd.read_hdf(path, key="df_with_missing")
    except Exception as exc:
        raise ValueError(f"failed to read HDF5 predictions: {path}") from exc
    return _load_dataframe(dataframe, bodypart)


def _load_dataframe(dataframe: Any, bodypart: str) -> list[_PredictionRow]:
    try:
        columns = list(dataframe.columns)
    except Exception as exc:
        raise ValueError("prediction DataFrame has no readable columns") from exc
    selected = _select_columns(columns, bodypart)

    try:
        iterator = dataframe.iterrows()
    except Exception as exc:
        raise ValueError("prediction DataFrame cannot be iterated") from exc

    rows: list[_PredictionRow] = []
    for frame_value, row in iterator:
        frame_index = _parse_frame(frame_value, source="DataFrame")
        values: dict[str, Any] = {}
        for coord, column in selected.items():
            try:
                values[coord] = row[column]
            except (KeyError, IndexError, TypeError) as exc:
                raise ValueError(f"DataFrame row {frame_index} is missing {coord}") from exc
        rows.append(
            _PredictionRow(
                frame_index=frame_index,
                pixel_x=_parse_number(values["x"], "pixel_x"),
                pixel_y=_parse_number(values["y"], "pixel_y"),
                likelihood=_parse_number(values["likelihood"], "likelihood"),
            )
        )
    return rows


def _load_records(records: list[Any] | tuple[Any, ...]) -> list[_PredictionRow]:
    rows: list[_PredictionRow] = []
    for position, item in enumerate(records):
        if not isinstance(item, Mapping):
            raise ValueError(f"prediction record {position} must be a mapping")
        frame_value = _record_value(item, "frame_index", "frame", "frame_index")
        x_value = _record_value(item, "pixel_x", "x", "pixel_x")
        y_value = _record_value(item, "pixel_y", "y", "pixel_y")
        likelihood_value = _record_value(item, "likelihood", "confidence", "likelihood")
        rows.append(
            _PredictionRow(
                frame_index=_parse_frame(frame_value, source="record"),
                pixel_x=_parse_number(x_value, "pixel_x"),
                pixel_y=_parse_number(y_value, "pixel_y"),
                likelihood=_parse_number(likelihood_value, "likelihood"),
            )
        )
    return rows


def _record_value(record: Mapping[str, Any], first: str, second: str, label: str) -> Any:
    present = [key for key in (first, second) if key in record]
    if len(present) != 1 or record[present[0]] is None:
        raise ValueError(f"record must contain exactly one non-empty {label} field")
    return record[present[0]]


def _load_csv(path: Path, bodypart: str) -> list[_PredictionRow]:
    try:
        with path.open("r", newline="", encoding="utf-8") as stream:
            csv_rows = list(csv.reader(stream))
    except OSError as exc:
        raise ValueError(f"failed to read prediction CSV: {path}") from exc

    if len(csv_rows) < 3:
        raise ValueError("prediction CSV must contain three header rows")
    headers = csv_rows[:3]
    width = len(headers[0])
    if width < 4 or any(len(row) != width for row in headers):
        raise ValueError("prediction CSV headers have inconsistent columns")
    if [row[0] for row in headers] != ["scorer", "bodyparts", "coords"]:
        raise ValueError("prediction CSV must use scorer/bodyparts/coords headers")

    columns = list(zip(headers[0][1:], headers[1][1:], headers[2][1:]))
    selected = _select_columns(columns, bodypart)
    # 列结构校验已保证标签唯一，直接定位列，无需在 CI 中引入表格依赖。
    selected_positions = {
        coord: next(index + 1 for index, column in enumerate(columns) if column == label)
        for coord, label in selected.items()
    }

    parsed: list[_PredictionRow] = []
    for position, data_row in enumerate(csv_rows[3:], start=4):
        if len(data_row) != width:
            raise ValueError(f"prediction CSV row {position} has inconsistent columns")
        frame_index = _parse_frame(data_row[0], source="CSV")
        parsed.append(
            _PredictionRow(
                frame_index=frame_index,
                pixel_x=_parse_number(data_row[selected_positions["x"]], "pixel_x"),
                pixel_y=_parse_number(data_row[selected_positions["y"]], "pixel_y"),
                likelihood=_parse_number(
                    data_row[selected_positions["likelihood"]], "likelihood"
                ),
            )
        )
    return parsed


def _select_columns(columns: list[Any], bodypart: str) -> dict[str, Any]:
    groups: dict[tuple[Any, Any], dict[str, Any]] = {}
    for column in columns:
        if not isinstance(column, tuple) or len(column) != 3:
            raise ValueError("prediction columns must have exactly three levels")
        scorer, column_bodypart, coord = column
        if not all(isinstance(value, str) and value for value in (scorer, column_bodypart, coord)):
            raise ValueError("prediction column labels must be non-empty strings")
        if coord not in _REQUIRED_COORDS:
            raise ValueError("prediction coords must be exactly x, y, and likelihood")
        key = (scorer, column_bodypart)
        group = groups.setdefault(key, {})
        if coord in group:
            raise ValueError(f"duplicate prediction column: {column}")
        group[coord] = column

    matching = [(key, group) for key, group in groups.items() if key[1] == bodypart]
    if len(matching) != 1:
        raise ValueError("prediction bodypart/scorer match is missing or ambiguous")
    _, selected = matching[0]
    if set(selected) != _REQUIRED_COORDS:
        raise ValueError("prediction bodypart must contain x, y, and likelihood")
    for key, group in groups.items():
        if set(group) != _REQUIRED_COORDS:
            raise ValueError(f"prediction bodypart {key[1]!r} must contain x, y, and likelihood")
    return selected


def _parse_frame(value: Any, *, source: str) -> int:
    if source == "CSV":
        if not isinstance(value, str) or not value.strip():
            raise ValueError("CSV frame index must be an integer string")
        try:
            frame_index = int(value.strip(), 10)
        except (TypeError, ValueError) as exc:
            raise ValueError("CSV frame index must be an integer string") from exc
    else:
        if isinstance(value, bool) or not isinstance(value, Integral):
            raise ValueError(f"{source} frame index must be an integer")
        frame_index = int(value)
    if frame_index < 0:
        raise ValueError("frame_index must be non-negative")
    return frame_index


def _parse_number(value: Any, label: str) -> float:
    if value is None or isinstance(value, bool):
        raise ValueError(f"{label} must be numeric")
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{label} must be numeric") from exc
    return number


def _validate_rows(rows: list[_PredictionRow], frame_count: int | None) -> None:
    seen_frames: set[int] = set()
    for row in rows:
        if row.frame_index in seen_frames:
            raise ValueError(f"duplicate frame_index: {row.frame_index}")
        seen_frames.add(row.frame_index)
        for label, value in (("pixel_x", row.pixel_x), ("pixel_y", row.pixel_y)):
            if isnan(value):
                continue
            if not isfinite(value):
                raise ValueError(f"{label} must be finite or NaN")
        if isnan(row.likelihood):
            continue
        if not isfinite(row.likelihood) or not 0 <= row.likelihood <= 1:
            raise ValueError("likelihood must be finite, NaN, or in [0, 1]")

    if frame_count is not None and seen_frames != set(range(frame_count)):
        raise ValueError("prediction frames must cover every source frame from 0 to frame_count - 1")
