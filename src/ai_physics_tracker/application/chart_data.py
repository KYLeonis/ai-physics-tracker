"""Qt-free 的图表数据适配器。

该模块只读取 :class:`Project` 快照，把稀疏的 ``DerivedData`` 转成 GUI
可以直接绘制的不可变序列；不负责计算、持久化或补齐缺测帧。
"""

from collections.abc import Mapping
from dataclasses import dataclass
from math import isfinite
from numbers import Integral
from typing import Literal
from uuid import UUID

from ai_physics_tracker.domain.derived import DerivedData
from ai_physics_tracker.domain.project import Project
from ai_physics_tracker.domain.timeline import Timeline, frame_to_time
from ai_physics_tracker.domain.track import Track

ChartKind = Literal["x_t", "y_t", "v_t", "a_t", "xy"]


@dataclass(frozen=True)
class ChartSeries:
    """一条可绘制曲线；``frames`` 保留了每个点对应的源帧号。"""

    track_id: UUID
    name: str
    color: str
    component: str
    frames: tuple[int, ...]
    x_values: tuple[float, ...]
    y_values: tuple[float, ...]
    connect: tuple[bool, ...]
    unit: str
    status: str
    pipeline_summary: str


@dataclass(frozen=True)
class ChartData:
    """一个图表标签页的数据和面向用户的状态消息。"""

    title: str
    x_label: str
    y_label: str
    x_unit: str
    y_unit: str
    series: tuple[ChartSeries, ...]
    messages: tuple[str, ...]
    pixel_coordinates: bool


_CHART_LABELS: dict[str, tuple[str, str, str]] = {
    "x_t": ("x(t)", "Time", "x"),
    "y_t": ("y(t)", "Time", "y"),
    "v_t": ("v(t)", "Time", "Velocity"),
    "a_t": ("a(t)", "Time", "Acceleration"),
    "xy": ("x-y", "x", "y"),
}


def build_chart_data(
    project: Project,
    video_id: UUID,
    track_ids: tuple[UUID, ...],
    kind: ChartKind,
    *,
    smoothed: bool = False,
) -> ChartData:
    """从当前视频的派生结果构造一份只读图表快照。

    时间图的横坐标始终由源帧号和该视频的 ``Timeline`` 计算；缺帧只会让
    ``connect`` 断开，不会生成 NaN 或插值点。位置图使用世界坐标（有 active
    标定）或像素坐标（无标定），而 velocity/acceleration 始终使用两列分量。
    """

    labels = _CHART_LABELS.get(kind)
    if labels is None:
        return ChartData(
            title="Chart",
            x_label="Time",
            y_label="Value",
            x_unit="s",
            y_unit="",
            series=(),
            messages=(f"不支持图表类型 {kind!r}",),
            pixel_coordinates=False,
        )

    title, x_label, y_label = labels
    video = next((item for item in project.videos if item.video_id == video_id), None)
    timeline = next(
        (item for item in project.timelines if item.video_id == video_id), None
    )
    if video is None:
        return ChartData(
            title=title,
            x_label=x_label,
            y_label=y_label,
            x_unit="s" if kind != "xy" else "",
            y_unit="",
            series=(),
            messages=(f"未找到视频 {video_id}，暂无图表数据",),
            pixel_coordinates=False,
        )
    if timeline is None:
        return ChartData(
            title=title,
            x_label=x_label,
            y_label=y_label,
            x_unit="s" if kind != "xy" else "",
            y_unit="",
            series=(),
            messages=(f"视频 {video_id} 缺少 Timeline，暂无图表数据",),
            pixel_coordinates=False,
        )

    active_calibration = _active_calibration(project, video_id)
    pixel_coordinates = active_calibration is None
    position_unit = active_calibration.unit if active_calibration is not None else "px"
    source_kind = _source_kind(kind, smoothed)
    expected_unit = _derived_unit(position_unit, source_kind)
    x_unit = "s" if kind != "xy" else expected_unit
    y_unit = expected_unit
    messages: list[str] = []
    if pixel_coordinates:
        messages.append("当前视频未标定（未设置标定），使用像素坐标（px；y 轴向下）")

    tracks_by_id = {track.track_id: track for track in project.tracks}
    series: list[ChartSeries] = []
    seen_track_ids: set[UUID] = set()
    if not track_ids:
        messages.append("未选择轨迹，暂无图表数据")

    for track_id in track_ids:
        if track_id in seen_track_ids:
            continue
        seen_track_ids.add(track_id)
        track = tracks_by_id.get(track_id)
        if track is None:
            messages.append(f"未找到轨迹 {track_id}，已忽略")
            continue
        if track.video_id != video_id:
            messages.append(f"轨迹 {track.name!r} 不属于当前视频，已忽略")
            continue

        derived = _last_derived(project.derived, track_id, source_kind)
        if derived is None:
            messages.append(
                f"轨迹 {track.name!r} 缺少 {source_kind} 派生数据，暂无图表数据"
            )
            continue
        if derived.status == "stale":
            messages.append(
                f"轨迹 {track.name!r} 的 {source_kind} 派生数据为 stale，曲线可能已过期"
            )
        elif derived.status != "valid":
            messages.append(
                f"轨迹 {track.name!r} 的 {source_kind} 状态无效，已忽略"
            )
            continue

        expected_calibration = active_calibration.calibration_id if active_calibration else None
        context_mismatch = derived.calibration_ref != expected_calibration
        if context_mismatch:
            messages.append(f"轨迹 {track.name!r} 使用的标定不是当前标定，按 stale 显示，请重新计算")

        if derived.unit != expected_unit:
            messages.append(
                f"轨迹 {track.name!r} 的单位 {derived.unit!r} 与当前图表期望单位 "
                f"{expected_unit!r} 不兼容，已忽略"
            )
            continue

        prepared = _prepare_derived_rows(derived, track, timeline, messages)
        if prepared is None:
            continue
        frames, values = prepared
        if not frames:
            if source_kind in {"velocity", "acceleration"}:
                messages.append(
                    f"轨迹 {track.name!r} 的 {source_kind} 连续点不足，暂无可显示数据"
                )
            else:
                messages.append(
                    f"轨迹 {track.name!r} 在当前 working_zone 内无有效数据"
                )
            continue

        x_values, components = _chart_values(kind, frames, values, timeline)
        connect = _connect_flags(frames)
        pipeline_summary = _pipeline_summary(derived)
        for component, y_values in components:
            series.append(
                ChartSeries(
                    track_id=track.track_id,
                    name=track.name,
                    color=track.color,
                    component=component,
                    frames=frames,
                    x_values=x_values,
                    y_values=y_values,
                    connect=connect,
                    unit=derived.unit,
                    status="stale" if context_mismatch else derived.status,
                    pipeline_summary=pipeline_summary,
                )
            )

    return ChartData(
        title=title,
        x_label=x_label,
        y_label=y_label,
        x_unit=x_unit,
        y_unit=y_unit,
        series=tuple(series),
        messages=tuple(messages),
        pixel_coordinates=pixel_coordinates,
    )


def _source_kind(kind: ChartKind, smoothed: bool) -> str:
    if kind in {"x_t", "y_t", "xy"}:
        return "smoothed_position" if smoothed else "world_position"
    if kind == "v_t":
        return "velocity"
    return "acceleration"


def _derived_unit(position_unit: str, source_kind: str) -> str:
    if source_kind == "velocity":
        return f"{position_unit}/s"
    if source_kind == "acceleration":
        return f"{position_unit}/s²"
    return position_unit


def _active_calibration(project: Project, video_id: UUID):
    calibration_id = project.active_calibration_by_video.get(video_id)
    if calibration_id is None:
        return None
    return next(
        (
            calibration
            for calibration in project.calibrations
            if calibration.calibration_id == calibration_id
            and calibration.video_id == video_id
        ),
        None,
    )


def _last_derived(
    derived_items: tuple[DerivedData, ...], track_id: UUID, kind: str
) -> DerivedData | None:
    """按 project.derived 的持久化顺序取同轨迹同 kind 的最后一条。"""

    matches = [
        item
        for item in derived_items
        if item.track_id == track_id and item.kind == kind
    ]
    return matches[-1] if matches else None


def _prepare_derived_rows(
    derived: DerivedData,
    track: Track,
    timeline: Timeline,
    messages: list[str],
) -> tuple[tuple[int, ...], tuple[tuple[float, float], ...]] | None:
    """校验并按 working_zone 筛选一条派生数据，不改动原始对象。"""

    if derived.values is None:
        if derived.payload_ref is not None:
            detail = f"外置派生数据 payload_ref={derived.payload_ref!r} 暂不支持读取"
        else:
            detail = "派生数据 values=None，暂无可读取的内嵌值"
        messages.append(f"轨迹 {track.name!r} 的 {derived.kind} {detail}")
        return None

    try:
        raw_frames = tuple(derived.frames)
        raw_values = tuple(derived.values)
    except (TypeError, ValueError):
        messages.append(f"轨迹 {track.name!r} 的 {derived.kind} 数据结构无法读取")
        return None

    if len(raw_frames) != len(raw_values):
        messages.append(
            f"轨迹 {track.name!r} 的 {derived.kind} frames/values 长度不一致，已忽略"
        )
        return None

    frames: list[int] = []
    values: list[tuple[float, float]] = []
    previous_frame: int | None = None
    for raw_frame, raw_value in zip(raw_frames, raw_values):
        if isinstance(raw_frame, bool) or not isinstance(raw_frame, Integral):
            messages.append(
                f"轨迹 {track.name!r} 的 {derived.kind} 含非法帧号，已忽略"
            )
            return None
        frame = int(raw_frame)
        if frame < 0 or (previous_frame is not None and frame <= previous_frame):
            messages.append(
                f"轨迹 {track.name!r} 的 {derived.kind} 帧顺序非法，已忽略"
            )
            return None
        previous_frame = frame

        if isinstance(raw_value, (str, bytes)):
            messages.append(
                f"轨迹 {track.name!r} 的 {derived.kind} 值不是二维数值，已忽略"
            )
            return None
        try:
            row = tuple(raw_value)
        except (TypeError, ValueError):
            messages.append(
                f"轨迹 {track.name!r} 的 {derived.kind} 值不是二维数值，已忽略"
            )
            return None
        if len(row) != 2:
            messages.append(
                f"轨迹 {track.name!r} 的 {derived.kind} 值形状不是 2 列，已忽略"
            )
            return None
        try:
            first, second = float(row[0]), float(row[1])
        except (TypeError, ValueError, OverflowError):
            messages.append(
                f"轨迹 {track.name!r} 的 {derived.kind} 含非数值，已忽略"
            )
            return None
        if not isfinite(first) or not isfinite(second):
            messages.append(
                f"轨迹 {track.name!r} 的 {derived.kind} 含非有限值，已忽略"
            )
            return None
        if timeline.working_zone[0] <= frame <= timeline.working_zone[1]:
            frames.append(frame)
            values.append((first, second))

    return tuple(frames), tuple(values)


def _chart_values(
    kind: ChartKind,
    frames: tuple[int, ...],
    values: tuple[tuple[float, float], ...],
    timeline: Timeline,
) -> tuple[tuple[float, ...], tuple[tuple[str, tuple[float, ...]], ...]]:
    if kind == "xy":
        return (
            tuple(value[0] for value in values),
            (("xy", tuple(value[1] for value in values)),),
        )

    x_values = tuple(frame_to_time(frame, timeline) for frame in frames)
    if kind == "x_t":
        components = (("x", tuple(value[0] for value in values)),)
    elif kind == "y_t":
        components = (("y", tuple(value[1] for value in values)),)
    elif kind == "v_t":
        components = (
            ("vx", tuple(value[0] for value in values)),
            ("vy", tuple(value[1] for value in values)),
        )
    else:
        components = (
            ("ax", tuple(value[0] for value in values)),
            ("ay", tuple(value[1] for value in values)),
        )
    return x_values, components


def _connect_flags(frames: tuple[int, ...]) -> tuple[bool, ...]:
    if not frames:
        return ()
    return tuple(
        next_frame == frame + 1
        for frame, next_frame in zip(frames, frames[1:])
    ) + (False,)


def _pipeline_summary(derived: DerivedData) -> str:
    """提取 SG 的实际参数，供图例/状态栏简短显示。"""

    step_names: list[str] = []
    window_length: object | None = None
    polyorder: object | None = None
    for step in derived.pipeline:
        if not isinstance(step, Mapping):
            continue
        step_name = step.get("step")
        if isinstance(step_name, str) and step_name:
            step_names.append(step_name)
        if step_name != "savitzky_golay":
            continue
        params = step.get("params")
        if not isinstance(params, Mapping):
            continue
        if "window_length" in params:
            window_length = params["window_length"]
        elif "window" in params:
            window_length = params["window"]
        if "polyorder" in params:
            polyorder = params["polyorder"]

    if window_length is not None or polyorder is not None:
        return (
            "Savitzky-Golay "
            f"window={window_length!r}, polyorder={polyorder!r}"
        )
    if step_names:
        if step_names == ["calibration_transform"]:
            return "calibration"
        return " → ".join(step_names)
    return "raw"


__all__ = ["ChartData", "ChartKind", "ChartSeries", "build_chart_data"]
