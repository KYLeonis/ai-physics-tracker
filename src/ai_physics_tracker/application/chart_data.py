"""Qt-free 的图表数据适配器。

该模块只读取 :class:`Project` 快照，把稀疏的 ``DerivedData`` 转成 GUI
可以直接绘制的不可变序列；不负责计算、持久化或补齐缺测帧。

Phase 6.2（ADR-0019/0020）在既有线性五图之外新增角运动时间图
（theta_t / omega_t / alpha_t，单列 values）与相空间图（theta_omega /
x_vx，两条同配方结果按源帧交集配对）。角度显示单位 rad / degree 只在
显示层转换，持久化数据保持 rad；原始 wrapped θ 跨 ±π 断线，不重新
unwrap、不写回。

职责划分：科学配方 / 时序来源的读取、核对与披露在 ``chart_recipe.py``；
本模块负责图表组装（kind 映射、单位与坐标语义、展示状态、序列构建）。
"""

from dataclasses import dataclass
from math import pi
from typing import Literal
from uuid import UUID

from ai_physics_tracker.application.chart_recipe import (
    ComparisonBasis,
    angular_pipeline_summary,
    calibration_recipe_reject_reason,
    comparison_basis,
    comparison_mismatch_reason,
    fps_mismatch_reason,
    has_approximate_timing,
    pair_recipe_reject_reason,
    pair_timing_reject_reason,
    pipeline_summary,
    prepare_derived_rows,
    reference_reject_reason,
    smoothing_readable_reject_reason,
    timing_identity_reject_reason,
    unreadable_step_reason,
    zone_mismatch,
)
from ai_physics_tracker.domain.calibration import Calibration
from ai_physics_tracker.domain.derived import ANGULAR_KINDS, DerivedData
from ai_physics_tracker.domain.project import Project
from ai_physics_tracker.domain.timeline import Timeline, frame_to_time
from ai_physics_tracker.domain.track import Track

ChartKind = Literal[
    "x_t",
    "y_t",
    "v_t",
    "a_t",
    "xy",
    "theta_t",
    "omega_t",
    "alpha_t",
    "theta_omega",
    "x_vx",
]

ANGLE_UNIT_RAD = "rad"
ANGLE_UNIT_DEGREE = "degree"
_ANGLE_UNITS = (ANGLE_UNIT_RAD, ANGLE_UNIT_DEGREE)
_DEGREES_PER_RADIAN = 180.0 / pi

# 时间图 kind（横轴为绝对源帧时间）；xy 与相空间的横轴是数据本身。
_TIME_CHART_KINDS = frozenset(
    {"x_t", "y_t", "v_t", "a_t", "theta_t", "omega_t", "alpha_t"}
)
_ANGULAR_CHART_KINDS = frozenset({"theta_t", "omega_t", "alpha_t", "theta_omega"})
_ANGULAR_SOURCE_KINDS = frozenset(ANGULAR_KINDS)

# 导数类 kind：短于滤波窗时无输出，与"区间内无数据"的原因区分。
_DERIVATIVE_SOURCE_KINDS = frozenset(
    {"velocity", "acceleration", "angular_velocity", "angular_acceleration"}
)

# 各角运动 kind 的存储单位（ADR-0019：计算一律 rad 系）与 degree 显示单位。
_ANGULAR_STORED_UNITS = {
    "angular_position": "rad",
    "smoothed_angular_position": "rad",
    "angular_velocity": "rad/s",
    "angular_acceleration": "rad/s²",
}
_ANGULAR_DEGREE_UNITS = {
    "angular_position": "°",
    "smoothed_angular_position": "°",
    "angular_velocity": "°/s",
    "angular_acceleration": "°/s²",
}
_ANGULAR_COMPONENTS = {
    "angular_position": "theta",
    "smoothed_angular_position": "theta",
    "angular_velocity": "omega",
    "angular_acceleration": "alpha",
}

# 相空间 kind → (主量 kind, 一阶导量 kind)；主量恒为同配方平滑结果。
_PHASE_PAIRS = {
    "theta_omega": ("smoothed_angular_position", "angular_velocity"),
    "x_vx": ("smoothed_position", "velocity"),
}


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
    "theta_t": ("θ(t)", "Time", "θ"),
    "omega_t": ("ω(t)", "Time", "ω"),
    "alpha_t": ("α(t)", "Time", "α"),
    "theta_omega": ("θ–ω", "θ", "ω"),
    "x_vx": ("x–vx", "x", "vx"),
}


def build_chart_data(
    project: Project,
    video_id: UUID,
    track_ids: tuple[UUID, ...],
    kind: ChartKind,
    *,
    smoothed: bool = False,
    angle_unit: str = ANGLE_UNIT_RAD,
) -> ChartData:
    """从当前视频的派生结果构造一份只读图表快照。

    时间图的横坐标始终由源帧号和该视频的 ``Timeline`` 计算；缺帧只会让
    ``connect`` 断开，不会生成 NaN 或插值点。位置图使用世界坐标（有 active
    标定）或像素坐标（无标定），而 velocity/acceleration 始终使用两列分量。

    角运动图（theta_t/omega_t/alpha_t/theta_omega）消费单列 values；
    ``angle_unit`` 只切换显示单位（rad 或 degree），持久化数据不被改写。
    相空间图（theta_omega/x_vx）按源帧交集配对同配方的两条结果，
    ``smoothed`` 对相空间无意义（主量恒为平滑结果），被忽略。
    """

    if angle_unit not in _ANGLE_UNITS:
        raise ValueError(
            f"angle_unit must be one of {_ANGLE_UNITS!r}, got {angle_unit!r}"
        )
    labels = _CHART_LABELS.get(kind)
    if labels is None:
        return ChartData(
            title="Chart",
            x_label="Time",
            y_label="Value",
            x_unit="s",
            y_unit="",
            series=(),
            messages=(f"Unsupported chart type {kind!r}",),
            pixel_coordinates=False,
        )
    if kind in _PHASE_PAIRS:
        return _build_phase_chart(
            project, video_id, track_ids, kind, angle_unit=angle_unit
        )
    return _build_time_chart(
        project, video_id, track_ids, kind, smoothed=smoothed, angle_unit=angle_unit
    )


# ---------------------------------------------------------------------------
# 时间图（横轴 = 绝对源帧时间）
# ---------------------------------------------------------------------------


def _build_time_chart(
    project: Project,
    video_id: UUID,
    track_ids: tuple[UUID, ...],
    kind: ChartKind,
    *,
    smoothed: bool,
    angle_unit: str,
) -> ChartData:
    title, x_label, y_label = _CHART_LABELS[kind]
    angular_chart = kind in _ANGULAR_CHART_KINDS
    missing = _missing_frame_reason(project, video_id)
    if missing is not None:
        return _no_data_chart(
            title, x_label, y_label,
            "s" if kind in _TIME_CHART_KINDS else "", missing,
        )
    timeline = _video_timeline(project, video_id)
    active_calibration = _active_calibration(project, video_id)
    # 角度永远不是像素量；像素标志只描述线性位置图。
    pixel_coordinates = active_calibration is None and not angular_chart
    position_unit = active_calibration.unit if active_calibration is not None else "px"
    source_kind = _source_kind(kind, smoothed)
    expected_unit = _derived_unit(position_unit, source_kind)
    display_unit = _angular_display_unit(source_kind, angle_unit)
    angle_scale = _angle_display_factor(angle_unit)
    x_unit = "s" if kind in _TIME_CHART_KINDS else expected_unit
    y_unit = display_unit if angular_chart else expected_unit
    messages = _coordinate_messages(angular_chart, active_calibration)
    expected_width = 1 if source_kind in _ANGULAR_SOURCE_KINDS else 2
    tracks_by_id = {track.track_id: track for track in project.tracks}
    basis: ComparisonBasis | None = None
    series: list[ChartSeries] = []

    for track in _selected_tracks(tracks_by_id, track_ids, video_id, messages):
        record = _last_derived(project.derived, track.track_id, source_kind)
        if record is None:
            messages.append(
                f"Track {track.name!r} has no {source_kind} derived data; "
                "no chart data available"
            )
            continue
        status = _time_record_state(
            record, track, timeline, active_calibration, expected_unit, messages
        )
        if status is None:
            continue
        pending_basis: ComparisonBasis | None = None
        if angular_chart:
            reject = _angular_record_reject_reason(record)
            if reject is None and basis is not None:
                # 同量图内不混合不同参考 / 标定 / 平滑 / 时序来源的多轨迹。
                reject = comparison_mismatch_reason(record, basis, angular=True)
            if reject is not None:
                messages.append(
                    f"Track {track.name!r} {reject}; the series was ignored"
                )
                continue
            if basis is None:
                pending_basis = comparison_basis(record, angular=True)
                if pending_basis is None:
                    messages.append(
                        f"Track {track.name!r} has an unreadable computation "
                        "recipe; the series was ignored"
                    )
                    continue
        prepared = _prepared_rows(
            record, track, timeline, messages,
            expected_width=expected_width, source_kind=source_kind,
        )
        if prepared is None:
            continue
        if pending_basis is not None:
            # 比较基准只由实际可展示的序列建立；空 / 畸形首轨迹不得
            # 绑定后续正常轨迹。
            basis = pending_basis
        frames, values = prepared
        _approximate_timing_message(track, (record,), messages)
        if angular_chart:
            series.append(
                _angular_time_series(
                    record, track, timeline, frames, values, status,
                    display_unit=display_unit, angle_scale=angle_scale,
                    tracks_by_id=tracks_by_id,
                )
            )
        else:
            series.extend(
                _linear_time_series(
                    record, track, timeline, kind, frames, values, status
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


def _time_record_state(
    record: DerivedData,
    track: Track,
    timeline: Timeline,
    calibration: Calibration | None,
    expected_unit: str,
    messages: list[str],
) -> str | None:
    """时间图单记录的展示状态：'valid' / 'stale'；None = 已记录原因并忽略。

    记录 fps 与当前时序不一致时直接忽略（提示重算）；标定 / 区间与当前
    不同的缓存按 stale 明示只读展示，不静默当作最新。
    """

    if record.status == "stale":
        messages.append(
            f"Track {track.name!r} has stale {record.kind} derived data; "
            "the curve may be outdated"
        )
    elif record.status != "valid":
        messages.append(
            f"Track {track.name!r} has invalid {record.kind} status and was ignored"
        )
        return None
    fps_reason = fps_mismatch_reason(record, timeline)
    if fps_reason is not None:
        messages.append(
            f"Track {track.name!r} {fps_reason}; the series was ignored. "
            "Recompute the track"
        )
        return None
    expected_calibration = (
        calibration.calibration_id if calibration is not None else None
    )
    # 持久化的 stale 状态是事实，不因标定 / 区间恰好一致而被洗白成 valid；
    # 标定 / 区间不一致只会让展示进一步降级为 stale。
    status = record.status
    if record.calibration_ref != expected_calibration:
        status = "stale"
        messages.append(
            f"Track {track.name!r} uses a different calibration; shown as stale. "
            "Recompute the track"
        )
    elif zone_mismatch(record, timeline):
        status = "stale"
        messages.append(
            f"Track {track.name!r} was computed for a different working zone; "
            "shown as stale"
        )
    if record.unit != expected_unit:
        messages.append(
            f"Track {track.name!r} uses unit {record.unit!r}, but this chart expects "
            f"{expected_unit!r}; the incompatible series was ignored"
        )
        return None
    return status


def _angular_record_reject_reason(record: DerivedData) -> str | None:
    """角运动时间图记录的科学自洽核对；None = 可展示。

    ADR-0020：angular 结果恒带完整 timing_context，缺失即无法确认来源；
    参考配方必须可读、模式已知且与输入参考轨迹一致。
    """

    for check in (
        unreadable_step_reason,
        calibration_recipe_reject_reason,
        reference_reject_reason,
        timing_identity_reject_reason,
        smoothing_readable_reject_reason,
    ):
        reason = check(record)
        if reason is not None:
            return reason
    return None


def _angular_time_series(
    record: DerivedData,
    track: Track,
    timeline: Timeline,
    frames: tuple[int, ...],
    values: tuple[tuple[float, ...], ...],
    status: str,
    *,
    display_unit: str,
    angle_scale: float,
    tracks_by_id: dict[UUID, Track],
) -> ChartSeries:
    x_values = tuple(frame_to_time(frame, timeline) for frame in frames)
    y_values = tuple(row[0] * angle_scale for row in values)
    return ChartSeries(
        track_id=track.track_id,
        name=track.name,
        color=track.color,
        component=_ANGULAR_COMPONENTS[record.kind],
        frames=frames,
        x_values=x_values,
        y_values=y_values,
        connect=_wrapped_connect_flags(frames, values, record.kind),
        unit=display_unit,
        status=status,
        pipeline_summary=angular_pipeline_summary(record, tracks_by_id),
    )


def _linear_time_series(
    record: DerivedData,
    track: Track,
    timeline: Timeline,
    kind: ChartKind,
    frames: tuple[int, ...],
    values: tuple[tuple[float, ...], ...],
    status: str,
) -> tuple[ChartSeries, ...]:
    x_values, components = _chart_values(kind, frames, values, timeline)
    connect = _connect_flags(frames)
    return tuple(
        ChartSeries(
            track_id=track.track_id,
            name=track.name,
            color=track.color,
            component=component,
            frames=frames,
            x_values=x_values,
            y_values=y_values,
            connect=connect,
            unit=record.unit,
            status=status,
            pipeline_summary=pipeline_summary(record),
        )
        for component, y_values in components
    )


# ---------------------------------------------------------------------------
# 相空间图（同配方主量 + 一阶导量按源帧交集配对）
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _PhaseChartSpec:
    """一张相空间图的静态组装参数（图表级不变量，与单轨迹无关）。"""

    kind: ChartKind
    angular: bool
    primary_kind: str
    derivative_kind: str
    expected_primary_unit: str
    expected_derivative_unit: str
    width: int
    primary_display: str
    derivative_display: str
    angle_scale: float
    expected_calibration: UUID | None


def _build_phase_chart(
    project: Project,
    video_id: UUID,
    track_ids: tuple[UUID, ...],
    kind: ChartKind,
    *,
    angle_unit: str,
) -> ChartData:
    """相空间图：同配方主量 + 一阶导量按源帧交集配对，缺帧断线。"""

    title, x_label, y_label = _CHART_LABELS[kind]
    angular = kind == "theta_omega"
    primary_kind, derivative_kind = _PHASE_PAIRS[kind]
    missing = _missing_frame_reason(project, video_id)
    if missing is not None:
        return _no_data_chart(title, x_label, y_label, "", missing)
    timeline = _video_timeline(project, video_id)
    active_calibration = _active_calibration(project, video_id)
    pixel_coordinates = active_calibration is None and not angular
    position_unit = active_calibration.unit if active_calibration is not None else "px"
    if angular:
        primary_display = _angular_display_unit(primary_kind, angle_unit)
        derivative_display = _angular_display_unit(derivative_kind, angle_unit)
        spec = _PhaseChartSpec(
            kind=kind,
            angular=angular,
            primary_kind=primary_kind,
            derivative_kind=derivative_kind,
            expected_primary_unit=_ANGULAR_STORED_UNITS[primary_kind],
            expected_derivative_unit=_ANGULAR_STORED_UNITS[derivative_kind],
            width=1,
            primary_display=primary_display,
            derivative_display=derivative_display,
            angle_scale=_angle_display_factor(angle_unit),
            expected_calibration=(
                active_calibration.calibration_id
                if active_calibration is not None
                else None
            ),
        )
    else:
        primary_display = position_unit
        derivative_display = f"{position_unit}/s"
        spec = _PhaseChartSpec(
            kind=kind,
            angular=angular,
            primary_kind=primary_kind,
            derivative_kind=derivative_kind,
            expected_primary_unit=position_unit,
            expected_derivative_unit=derivative_display,
            width=2,
            primary_display=primary_display,
            derivative_display=derivative_display,
            angle_scale=1.0,
            expected_calibration=(
                active_calibration.calibration_id
                if active_calibration is not None
                else None
            ),
        )
    messages = _coordinate_messages(angular, active_calibration)
    tracks_by_id = {track.track_id: track for track in project.tracks}
    primary_basis: ComparisonBasis | None = None
    derivative_basis: ComparisonBasis | None = None
    have_basis = False
    series: list[ChartSeries] = []

    for track in _selected_tracks(tracks_by_id, track_ids, video_id, messages):
        primary = _last_derived(project.derived, track.track_id, spec.primary_kind)
        derivative = _last_derived(
            project.derived, track.track_id, spec.derivative_kind
        )
        if primary is None or derivative is None:
            _report_missing_pair(
                primary, derivative, spec.primary_kind, spec.derivative_kind,
                track, messages,
            )
            continue
        # mixed valid/stale：整组按 stale 展示（phase-6.2 计划 Invariants）；
        # DerivedData 的 status 只可能是 valid/stale，无 stale 即 valid。
        group_stale = primary.status == "stale" or derivative.status == "stale"
        if _phase_pair_rejected(primary, derivative, track, timeline, spec, messages):
            continue
        pending_primary: ComparisonBasis | None = None
        pending_derivative: ComparisonBasis | None = None
        if have_basis:
            mismatch = _pair_basis_mismatch(
                primary, derivative, primary_basis, derivative_basis,
                angular=angular,
            )
            if mismatch is not None:
                messages.append(
                    f"Track {track.name!r} {mismatch}; the pair was ignored"
                )
                continue
        else:
            pending_primary = comparison_basis(primary, angular=angular)
            pending_derivative = comparison_basis(derivative, angular=angular)
            if pending_primary is None or pending_derivative is None:
                messages.append(
                    f"Track {track.name!r} has an unreadable computation recipe; "
                    "the pair was ignored"
                )
                continue
        chart_series = _phase_track_series(
            track, timeline, spec, primary, derivative, group_stale,
            tracks_by_id, messages,
        )
        if chart_series is None:
            continue
        # 仅对实际展示的曲线披露 stale，拒绝或空数据不能承诺已绘制。
        if group_stale:
            messages.append(
                f"Track {track.name!r} phase pair contains stale results; "
                "the whole pair is shown as stale"
            )
        if _context_mismatch((primary, derivative), spec.expected_calibration, timeline):
            messages.append(
                f"Track {track.name!r} phase pair uses a different calibration or "
                "working zone; shown as stale. Recompute the track"
            )
        if not have_basis:
            # 比较基准只由实际可展示的配对建立；空交集 / 畸形首轨迹不得
            # 绑定后续正常轨迹。
            primary_basis = pending_primary
            derivative_basis = pending_derivative
            have_basis = True
        series.append(chart_series)

    return ChartData(
        title=title,
        x_label=x_label,
        y_label=y_label,
        x_unit=spec.primary_display,
        y_unit=spec.derivative_display,
        series=tuple(series),
        messages=tuple(messages),
        pixel_coordinates=pixel_coordinates,
    )


def _phase_track_series(
    track: Track,
    timeline: Timeline,
    spec: _PhaseChartSpec,
    primary: DerivedData,
    derivative: DerivedData,
    group_stale: bool,
    tracks_by_id: dict[UUID, Track],
    messages: list[str],
) -> ChartSeries | None:
    """行读取 → 源帧交集 → 单条相空间序列；不可组装时记录原因返回 None。"""

    prepared_primary = _prepared_rows(
        primary, track, timeline, messages,
        expected_width=spec.width, source_kind=spec.primary_kind,
    )
    if prepared_primary is None:
        return None
    prepared_derivative = _prepared_rows(
        derivative, track, timeline, messages,
        expected_width=spec.width, source_kind=spec.derivative_kind,
    )
    if prepared_derivative is None:
        return None
    primary_frames, primary_values = prepared_primary
    derivative_frames, derivative_values = prepared_derivative

    # 按源帧交集配对，绝不按行号 zip 两个稀疏结果。
    primary_by_frame = dict(zip(primary_frames, primary_values))
    derivative_by_frame = dict(zip(derivative_frames, derivative_values))
    frames = tuple(
        frame for frame in primary_frames if frame in derivative_by_frame
    )
    if not frames:
        messages.append(
            f"Track {track.name!r} has no common source frames between "
            f"{spec.primary_kind} and {spec.derivative_kind}; "
            "no phase-space chart available"
        )
        return None
    _approximate_timing_message(track, (primary, derivative), messages)
    return ChartSeries(
        track_id=track.track_id,
        name=track.name,
        color=track.color,
        component=spec.kind,
        frames=frames,
        x_values=tuple(
            primary_by_frame[frame][0] * spec.angle_scale for frame in frames
        ),
        y_values=tuple(
            derivative_by_frame[frame][0] * spec.angle_scale for frame in frames
        ),
        connect=_connect_flags(frames),
        unit=spec.derivative_display,
        status=(
            "stale"
            if group_stale
            or _context_mismatch(
                (primary, derivative), spec.expected_calibration, timeline
            )
            else "valid"
        ),
        pipeline_summary=(
            angular_pipeline_summary(primary, tracks_by_id)
            if spec.angular
            else pipeline_summary(primary)
        ),
    )


def _report_missing_pair(
    primary: DerivedData | None,
    derivative: DerivedData | None,
    primary_kind: str,
    derivative_kind: str,
    track: Track,
    messages: list[str],
) -> None:
    for record, record_kind in (
        (primary, primary_kind),
        (derivative, derivative_kind),
    ):
        if record is None:
            messages.append(
                f"Track {track.name!r} has no {record_kind} derived data; "
                "no chart data available"
            )


def _phase_pair_rejected(
    primary: DerivedData,
    derivative: DerivedData,
    track: Track,
    timeline: Timeline,
    spec: _PhaseChartSpec,
    messages: list[str],
) -> bool:
    """相空间单轨配对的科学核对；True = 已记录原因并忽略整对。

    单位 / 配对标定一致是硬拒绝；标定 / 区间与当前不同只降级为 stale
    展示（只读明示，phase-6.2 计划 Invariants）。
    """

    for record, expected in (
        (primary, spec.expected_primary_unit),
        (derivative, spec.expected_derivative_unit),
    ):
        if record.unit != expected:
            messages.append(
                f"Track {track.name!r} {record.kind} uses unit {record.unit!r}, "
                f"but this chart expects {expected!r}; the pair was ignored"
            )
            return True
    if primary.calibration_ref != derivative.calibration_ref:
        messages.append(
            f"Track {track.name!r} pair was computed under different calibrations "
            "and was ignored"
        )
        return True
    for record in (primary, derivative):
        reject = _phase_record_reject_reason(record, angular=spec.angular)
        if reject is not None:
            messages.append(f"Track {track.name!r} {reject}; the pair was ignored")
            return True
    recipe_reason = pair_recipe_reject_reason(
        primary, derivative, angular=spec.angular
    )
    if recipe_reason is not None:
        messages.append(f"Track {track.name!r} {recipe_reason}; the pair was ignored")
        return True
    timing_reason = pair_timing_reject_reason(primary, derivative, timeline)
    if timing_reason is not None:
        # 当前时序与缓存来源无法确认一致时明确拒绝配对，不猜测旧文件来源。
        messages.append(f"Track {track.name!r} {timing_reason}; the pair was refused")
        return True
    return False


def _phase_record_reject_reason(record: DerivedData, *, angular: bool) -> str | None:
    """相空间单条记录的自洽核对；配对间一致性由 pair_* 核对负责。"""

    for check in (unreadable_step_reason, calibration_recipe_reject_reason):
        reason = check(record)
        if reason is not None:
            return reason
    if angular:
        return reference_reject_reason(record)
    return None


def _pair_basis_mismatch(
    primary: DerivedData,
    derivative: DerivedData,
    primary_basis: ComparisonBasis | None,
    derivative_basis: ComparisonBasis | None,
    *,
    angular: bool,
) -> str | None:
    """后续轨迹与既定基准的同角色比较（主量对主量、导数对导数）。"""

    for record, basis in ((primary, primary_basis), (derivative, derivative_basis)):
        if basis is None:
            return "has an unreadable computation recipe"
        mismatch = comparison_mismatch_reason(record, basis, angular=angular)
        if mismatch is not None:
            return mismatch
    return None


def _context_mismatch(
    records: tuple[DerivedData, ...],
    expected_calibration: UUID | None,
    timeline: Timeline,
) -> bool:
    return any(
        record.calibration_ref != expected_calibration
        or zone_mismatch(record, timeline)
        for record in records
    )


# ---------------------------------------------------------------------------
# 组装公共辅助
# ---------------------------------------------------------------------------


def _missing_frame_reason(project: Project, video_id: UUID) -> str | None:
    """视频 / 时间线缺失时的无数据原因；None = 可以继续组装。"""

    if not any(item.video_id == video_id for item in project.videos):
        return f"Video {video_id} was not found; no chart data available"
    if not any(item.video_id == video_id for item in project.timelines):
        return f"Video {video_id} has no timeline; no chart data available"
    return None


def _video_timeline(project: Project, video_id: UUID) -> Timeline:
    return next(item for item in project.timelines if item.video_id == video_id)


def _selected_tracks(
    tracks_by_id: dict[UUID, Track],
    track_ids: tuple[UUID, ...],
    video_id: UUID,
    messages: list[str],
):
    """按选择顺序去重迭代属于当前视频的轨迹；越界 / 跨视频记录消息跳过。"""

    seen: set[UUID] = set()
    if not track_ids:
        messages.append("No tracks selected; no chart data available")
    for track_id in track_ids:
        if track_id in seen:
            continue
        seen.add(track_id)
        track = tracks_by_id.get(track_id)
        if track is None:
            messages.append(f"Track {track_id} was not found and was ignored")
            continue
        if track.video_id != video_id:
            messages.append(
                f"Track {track.name!r} does not belong to the current video "
                "and was ignored"
            )
            continue
        yield track


def _coordinate_messages(
    angular: bool, calibration: Calibration | None
) -> list[str]:
    if calibration is not None:
        return []
    if angular:
        return [
            "Video has no active calibration; angular results cannot be current "
            "and are shown as stale"
        ]
    return [
        "Video is not calibrated; using pixel coordinates (px, y-axis points down)"
    ]


def _prepared_rows(
    record: DerivedData,
    track: Track,
    timeline: Timeline,
    messages: list[str],
    *,
    expected_width: int,
    source_kind: str,
) -> tuple[tuple[int, ...], tuple[tuple[float, ...], ...]] | None:
    """行读取 + 空结果原因区分（导数短段 vs 区间内无有效数据）。"""

    prepared = prepare_derived_rows(
        record, track, timeline, messages, expected_width=expected_width
    )
    if prepared is None:
        return None
    frames, _values = prepared
    if not frames:
        if source_kind in _DERIVATIVE_SOURCE_KINDS:
            messages.append(
                f"Track {track.name!r} has too few continuous {source_kind} "
                "points to display"
            )
        else:
            messages.append(
                f"Track {track.name!r} has no valid data in the current working zone"
            )
        return None
    return prepared


def _approximate_timing_message(
    track: Track, records: tuple[DerivedData, ...], messages: list[str]
) -> None:
    if any(has_approximate_timing(record) for record in records):
        messages.append(
            f"Track {track.name!r} results were computed with user-accepted "
            "approximate timing; derivative values may be inaccurate"
        )


def _no_data_chart(
    title: str, x_label: str, y_label: str, x_unit: str, message: str
) -> ChartData:
    return ChartData(
        title=title,
        x_label=x_label,
        y_label=y_label,
        x_unit=x_unit,
        y_unit="",
        series=(),
        messages=(message,),
        pixel_coordinates=False,
    )


def _source_kind(kind: ChartKind, smoothed: bool) -> str:
    if kind in {"x_t", "y_t", "xy"}:
        return "smoothed_position" if smoothed else "world_position"
    if kind == "v_t":
        return "velocity"
    if kind == "a_t":
        return "acceleration"
    if kind == "theta_t":
        return "smoothed_angular_position" if smoothed else "angular_position"
    if kind == "omega_t":
        return "angular_velocity"
    return "angular_acceleration"


def _derived_unit(position_unit: str, source_kind: str) -> str:
    if source_kind == "velocity":
        return f"{position_unit}/s"
    if source_kind == "acceleration":
        return f"{position_unit}/s²"
    angular_unit = _ANGULAR_STORED_UNITS.get(source_kind)
    if angular_unit is not None:
        return angular_unit
    return position_unit


def _angle_display_factor(angle_unit: str) -> float:
    return _DEGREES_PER_RADIAN if angle_unit == ANGLE_UNIT_DEGREE else 1.0


def _angular_display_unit(source_kind: str, angle_unit: str) -> str:
    if angle_unit == ANGLE_UNIT_DEGREE:
        return _ANGULAR_DEGREE_UNITS.get(
            source_kind, _ANGULAR_STORED_UNITS.get(source_kind, "")
        )
    return _ANGULAR_STORED_UNITS.get(source_kind, "")


def _active_calibration(project: Project, video_id: UUID) -> Calibration | None:
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


def _wrapped_connect_flags(
    frames: tuple[int, ...],
    values: tuple[tuple[float, ...], ...],
    source_kind: str,
) -> tuple[bool, ...]:
    """时间图连线标志；原始 wrapped θ 相邻帧跨 ±π 的跳变断线。

    断线阈值与 unwrap 的 discont=π 一致（ADR-0019）：跳变严格大于 π 视为
    wrap 边界，不画虚假的跨界斜线；也不重新 unwrap 或写回数据。
    """

    connect = _connect_flags(frames)
    if source_kind != "angular_position" or not frames:
        return connect
    return tuple(
        flag and abs(values[index + 1][0] - values[index][0]) <= pi
        for index, flag in enumerate(connect[:-1])
    ) + (False,)


__all__ = [
    "ANGLE_UNIT_DEGREE",
    "ANGLE_UNIT_RAD",
    "ChartData",
    "ChartKind",
    "ChartSeries",
    "build_chart_data",
]
