"""图表科学配方与时序来源的读取、核对与披露（Qt-free）。

Phase 6.2 S1 从 ``chart_data.py`` 拆出的公共实现（phase-6.2 计划
Implementation Surface：科学配方校验 / 行适配与图表组装分离）。本模块只读取
``DerivedData`` 的 pipeline / input / timing_context，回答三类问题：

1. 一条记录的配方与时序来源是否**可读且自洽**——fail-closed：契约要求
   存在的字段缺失即视为无法确认，不把"两边都缺"当成一致；
2. 两条（或多条）记录是否**可比较**——同输入选择、同计算步骤、同参考 /
   标定、同时序来源；仅相空间配对允许 SG 导数阶 0→1 的差别；
3. 已接受结果的实际配方与时序来源如何**披露**给图例 / 状态栏。

基础配方事实由source_recipe读取 / 构造；本模块保留图表对比策略、
显示文案与行数据读取。同步 / 后台均记录fps / working_zone / 时序来源。
"""

from collections.abc import Mapping
from dataclasses import dataclass
from math import isfinite
from numbers import Integral
from uuid import UUID

from ai_physics_tracker.application.source_recipe import (
    SmoothingParameters,
    _finite_number,
    pipeline_step_names,
    unreadable_step_reason,
    has_step,
    step_params,
    smoothing_recipe,
    reference_recipe,
    unwrap_discont,
    calibration_recipe_reject_reason,
    reference_reject_reason,
    smoothing_readable_reject_reason,
    TimingIdentity,
    timing_context,
    recorded_fps,
    _strict_zone_pair,
    timing_identity,
    timing_identity_reject_reason,
    fps_mismatch_reason,
    zone_mismatch,
    has_approximate_timing,
    _FPS_TOLERANCE,
    KNOWN_STEP_NAMES,
)
from ai_physics_tracker.domain.derived import DerivedData
from ai_physics_tracker.domain.timeline import Timeline
from ai_physics_tracker.domain.track import Track

# ---------------------------------------------------------------------------
# 相空间配对核对（同轨迹，theta_omega / x_vx）
# ---------------------------------------------------------------------------


def pair_recipe_reject_reason(
    primary: DerivedData, derivative: DerivedData, *, angular: bool
) -> str | None:
    """同轨迹相空间配对的配方核对；仅允许 SG 导数阶 0→1 的差别。

    fail-closed（S1 rework F1）：整个 DerivedInput（source_filter /
    observation_selection / 参考轨迹等）与全部计算步骤必须一致；契约键
    缺失即拒绝，不把"两边都缺"当成一致；未知步骤按整体一致参与核对。
    """

    if primary.input != derivative.input:
        return "pair mixes values computed from different input selections"
    for record in (primary, derivative):
        reason = unreadable_step_reason(record)
        if reason is not None:
            return f"pair {reason}"
    primary_names = pipeline_step_names(primary)
    derivative_names = pipeline_step_names(derivative)
    if primary_names != derivative_names:
        return (
            "pair mixes values computed with different processing steps "
            f"({list(primary_names)} vs {list(derivative_names)})"
        )
    for name in dict.fromkeys(primary_names):
        reason = _pair_step_mismatch(primary, derivative, name)
        if reason is not None:
            return reason
    if angular and (unwrap_discont(primary) is None or unwrap_discont(derivative) is None):
        # 角量配对必须有可读的 unwrap 阈值；两边都缺不算一致。
        return "pair is missing a comparable unwrap step"
    return None


def _pair_step_mismatch(
    primary: DerivedData, derivative: DerivedData, step_name: str
) -> str | None:
    """同位置已知步骤的参数核对；消息对用户可读的语义特化。"""

    if step_name == "savitzky_golay":
        return _pair_smoothing_mismatch(primary, derivative)
    primary_params = step_params(primary, step_name)
    derivative_params = step_params(derivative, step_name)
    if primary_params is None or derivative_params is None:
        return f"pair has an unreadable {step_name} recipe"
    if dict(primary_params) != dict(derivative_params):
        if step_name == "angular_reference":
            return "pair mixes values computed with different angle references"
        return f"pair mixes values computed with different {step_name} recipes"
    return None


def _pair_smoothing_mismatch(primary: DerivedData, derivative: DerivedData) -> str | None:
    primary_recipe = smoothing_recipe(primary)
    derivative_recipe = smoothing_recipe(derivative)
    if primary_recipe is None or derivative_recipe is None:
        return "pair is missing its smoothing recipe"
    for key in ("window_length", "polyorder", "mode"):
        if primary_recipe[key] != derivative_recipe[key]:
            return "pair mixes values smoothed with different Savitzky-Golay settings"
    if primary_recipe["deriv"] != 0:
        return "pair primary is not a zeroth-order smoothed quantity"
    if derivative_recipe["deriv"] != 1:
        return "pair uses a derivative that is not first order"
    # delta（物理采样步长）只在导数上有契约意义，由 pair_timing_reject_reason
    # 与当前 fps 单独核对；主量 deriv=0 时 delta 不影响数值（scipy savgol 语义）。
    return None


def pair_timing_reject_reason(
    primary: DerivedData, derivative: DerivedData, timeline: Timeline
) -> str | None:
    """相空间配对的时序核对（fail-closed，S1 rework F2）。

    两条记录都必须带完整可读的 timing_context（fps / working_zone /
    approximation）并互相一致，记录 fps 还须与当前时序一致。旧线性记录
    的 SG delta 只证明导数采样步长，不能证明主量的 fps / 区间 / 授权
    来源，缺失上下文一律拒绝并提示重算。导数 SG 的 delta 与当前 fps 的
    核对保留为额外栅栏。
    """

    for record in (primary, derivative):
        reason = fps_mismatch_reason(record, timeline)
        if reason is not None:
            return reason
        if timing_identity(record) is None:
            detail = timing_identity_reject_reason(record)
            return (
                f"{detail}; its computation timing cannot be confirmed; "
                "recompute the track to record its timing source"
            )
    primary_identity = timing_identity(primary)
    derivative_identity = timing_identity(derivative)
    if primary_identity is None or derivative_identity is None:  # pragma: no cover
        return "pair has incomplete timing contexts"
    if abs(primary_identity.fps_nominal - derivative_identity.fps_nominal) > _FPS_TOLERANCE:
        return "pair mixes values computed at different frame rates"
    if primary_identity.working_zone != derivative_identity.working_zone:
        return "pair mixes values computed over different working zones"
    if primary_identity.approximation != derivative_identity.approximation:
        return "pair mixes values computed under different timing approximations"
    derivative_recipe = smoothing_recipe(derivative)
    delta = derivative_recipe["delta"] if derivative_recipe is not None else None
    if delta is None or abs(delta - 1.0 / timeline.fps_nominal) > _FPS_TOLERANCE:
        return (
            f"{derivative.kind} was differentiated with a sampling step that "
            "does not match the current timeline"
        )
    return None


# ---------------------------------------------------------------------------
# 同量多轨迹比较基准（S1 rework F3）
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ComparisonBasis:
    """同一张同量图中第一条被接受记录建立的比较基准。

    相空间图为主量 / 导数各持一个基准（同角色记录互相比较）；时间图为
    同 kind 记录互比。
    """

    calibration_ref: UUID | None
    input_selection: tuple[object, ...]
    step_names: tuple[str | None, ...]
    reference: dict[str, object] | None   # 角图比较用；非角图为 None
    smoothing: dict[str, object] | None   # 该 kind 无 SG 步骤时为 None
    unwrap: float | None                  # 无 unwrap 步骤时为 None
    unknown_steps: tuple[tuple[str, object], ...]
    timing: TimingIdentity


def input_selection(derived: DerivedData) -> tuple[object, ...]:
    """输入选择身份；不含主轨迹 id（多轨迹比较时必然不同）。"""

    extras = tuple(sorted(derived.input.extra_fields.items()))
    return (
        derived.input.source_filter,
        derived.input.include_superseded,
        derived.input.reference_track_id,
        extras,
    )


def _unknown_steps(derived: DerivedData) -> tuple[tuple[str, object], ...]:
    """按参数结构比较未知步骤，JSON 字典键序不改变计算配方。"""

    return tuple(
        (str(step.get("step")), step.get("params"))
        for step in derived.pipeline
        if isinstance(step, Mapping) and step.get("step") not in KNOWN_STEP_NAMES
    )


def comparison_basis(derived: DerivedData, *, angular: bool) -> ComparisonBasis | None:
    """建立比较基准；记录自身配方或时序不可读时返回 None（fail-closed）。"""

    smoothing = None
    if has_step(derived, "savitzky_golay"):
        smoothing = smoothing_recipe(derived)
        if smoothing is None:
            return None
    unwrap = None
    if has_step(derived, "angular_unwrap"):
        unwrap = unwrap_discont(derived)
        if unwrap is None:
            return None
    reference = None
    if angular:
        params = reference_recipe(derived)
        if params is None:
            return None
        reference = dict(params)
    timing = timing_identity(derived)
    if timing is None:
        return None
    return ComparisonBasis(
        calibration_ref=derived.calibration_ref,
        input_selection=input_selection(derived),
        step_names=pipeline_step_names(derived),
        reference=reference,
        smoothing=smoothing,
        unwrap=unwrap,
        unknown_steps=_unknown_steps(derived),
        timing=timing,
    )


def comparison_mismatch_reason(
    derived: DerivedData, basis: ComparisonBasis, *, angular: bool
) -> str | None:
    """与既定基准不一致的原因；None = 可在同量图中比较。"""

    if derived.calibration_ref != basis.calibration_ref:
        return (
            "uses a different calibration; same-quantity comparison requires "
            "the same world coordinates"
        )
    if angular:
        # 参考差异优先于输入选择差异：角度定义不同是更根本的不可比原因，
        # 先于笼统的 input selection 报告，消息才有可操作的具体原因。
        params = reference_recipe(derived)
        reference = dict(params) if params is not None else None
        if reference != basis.reference:
            return _reference_mismatch_text(reference, basis.reference)
    if input_selection(derived) != basis.input_selection:
        return "is computed from a different input selection"
    if unreadable_step_reason(derived) is not None:
        return "has an unreadable computation recipe"
    if pipeline_step_names(derived) != basis.step_names:
        return "uses different processing steps"
    smoothing = (
        smoothing_recipe(derived) if has_step(derived, "savitzky_golay") else None
    )
    if smoothing != basis.smoothing:
        return "was smoothed with different Savitzky-Golay settings"
    unwrap = unwrap_discont(derived) if has_step(derived, "angular_unwrap") else None
    if unwrap != basis.unwrap:
        return "uses a different unwrap recipe"
    if _unknown_steps(derived) != basis.unknown_steps:
        return "uses different additional processing steps"
    timing = timing_identity(derived)
    if timing is None:
        return "has an unreadable recorded timing context"
    if abs(timing.fps_nominal - basis.timing.fps_nominal) > _FPS_TOLERANCE:
        return (
            f"was computed at {timing.fps_nominal:g} fps while this chart compares "
            f"{basis.timing.fps_nominal:g} fps results"
        )
    if timing.working_zone != basis.timing.working_zone:
        return "was computed over a different working zone"
    if timing.approximation != basis.timing.approximation:
        return "was computed under a different timing approximation"
    return None


def _reference_mismatch_text(
    reference: dict[str, object] | None, basis_reference: dict[str, object] | None
) -> str:
    """参考定义不一致的消息：同模式参数不同与模式不同分开表述。"""

    derived_mode = reference.get("mode") if reference else None
    basis_mode = basis_reference.get("mode") if basis_reference else None
    if not derived_mode or not basis_mode:
        return "has an unreadable angle reference; comparability cannot be confirmed"
    if derived_mode == basis_mode:
        return (
            "uses a different reference parameter set within the same "
            f"{basis_mode or 'unreadable'} angle definition"
        )
    return (
        f"uses a {derived_mode or 'unreadable'} angle definition; this chart "
        f"compares {basis_mode or 'unreadable'} angles only"
    )


# ---------------------------------------------------------------------------
# 披露（图例 / 状态栏摘要）
# ---------------------------------------------------------------------------


def _format_pivot(pivot: object) -> str | None:
    """支点像素坐标的安全格式化；损坏字符不得让 GUI 崩溃（S1 rework F3）。"""

    if not isinstance(pivot, (list, tuple)) or len(pivot) != 2:
        return None
    x = _finite_number(pivot[0])
    y = _finite_number(pivot[1])
    if x is None or y is None:
        return None
    return f"({x:g}, {y:g})"


def reference_summary(derived: DerivedData, tracks_by_id: dict[UUID, Track]) -> str:
    """图例用参考披露：单摆显示实际支点，两点显示参考轨迹名。"""

    reference = reference_recipe(derived)
    if reference is None:
        return "angular reference unavailable"
    mode = reference.get("mode")
    if mode == "pendulum":
        pivot_text = _format_pivot(reference.get("pivot_px"))
        if pivot_text is not None:
            return f"pendulum pivot px {pivot_text}"
        return "pendulum pivot (unreadable)"
    if mode == "two_point":
        raw_id = reference.get("reference_track_id")
        try:
            reference_track = tracks_by_id.get(UUID(str(raw_id)))
        except (ValueError, TypeError, AttributeError):
            reference_track = None
        label = reference_track.name if reference_track is not None else str(raw_id)
        return f"two-point A→B (reference: {label})"
    return f"angular reference {mode}"


def _smoothing_summary(derived: DerivedData) -> str:
    """SG 实际参数的简短摘要；无 SG 步骤时按步骤名 / raw 归纳。"""

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
        return f"Savitzky-Golay window={window_length!r}, polyorder={polyorder!r}"
    if step_names:
        if step_names == ["calibration_transform"]:
            return "calibration"
        return " → ".join(step_names)
    return "raw"


def timing_summary(derived: DerivedData) -> str:
    """缓存时序来源披露：记录 fps / 区间 / 近似授权，包括不可读来源。

    与写入契约的缺口同样披露（如线性结果暂无 working_zone 记录时显示
    "zone unrecorded"），让"来源未记录"可见而不是伪装完整。
    """

    context = timing_context(derived)
    if context is None:
        return ("timing source unreadable" if "timing_context" in derived.extra_fields
                else "timing source unrecorded")
    fps = recorded_fps(context)
    fps_text = f"{fps:g} fps" if fps is not None else "fps unrecorded"
    zone = _strict_zone_pair(context.get("working_zone"))
    zone_text = (f"frames {zone[0]}–{zone[1]}" if zone is not None else
                 "zone unreadable" if "working_zone" in context else "zone unrecorded")
    reason = timing_identity_reject_reason(derived)
    if reason is not None:
        # 字段缺失 ≠ 精确时序：来源未按契约写入时如实披露缺口。
        approx_text = ("timing source unreadable" if "unreadable" in reason
                       else "timing source unrecorded")
    else:
        approximation = context.get("approximation")
        if approximation is None:
            approx_text = "exact timing"
        elif isinstance(approximation, str) and approximation:
            # 近似时显示实际授权说明，不给笼统标签。
            approx_text = f"approximate timing ({approximation})"
        else:
            approx_text = "timing source unrecorded"
    return f"{fps_text} · {zone_text} · {approx_text}"


def pipeline_summary(derived: DerivedData) -> str:
    """线性记录的管线摘要：SG 实际参数 + 缓存时序披露。"""

    base = _smoothing_summary(derived)
    timing = timing_summary(derived)
    return f"{base} · {timing}"


def angular_pipeline_summary(
    derived: DerivedData, tracks_by_id: dict[UUID, Track]
) -> str:
    """角运动记录的管线摘要：参考 · SG · 缓存时序披露。"""

    parts = [reference_summary(derived, tracks_by_id)]
    if has_step(derived, "savitzky_golay"):
        parts.append(_smoothing_summary(derived))
    timing = timing_summary(derived)
    parts.append(timing)
    return " · ".join(parts)


# ---------------------------------------------------------------------------
# 行数据读取（按 working_zone 筛选与畸形拒绝）
# ---------------------------------------------------------------------------


def prepare_derived_rows(
    derived: DerivedData,
    track: Track,
    timeline: Timeline,
    messages: list[str],
    *,
    expected_width: int = 2,
) -> tuple[tuple[int, ...], tuple[tuple[float, ...], ...]] | None:
    """校验并按 working_zone 筛选一条派生数据，不改动原始对象。

    角运动 kind 的 values 是单列行（ADR-0019），线性 kind 是两列行；
    列数不符按畸形数据拒绝，不伪造缺列。
    """

    width_text = "one column" if expected_width == 1 else "two columns"

    if derived.values is None:
        if derived.payload_ref is not None:
            detail = f"external derived payload_ref={derived.payload_ref!r} is not supported"
        else:
            detail = "derived values are None; no inline values are available"
        messages.append(f"Track {track.name!r} {derived.kind}: {detail}")
        return None

    try:
        raw_frames = tuple(derived.frames)
        raw_values = tuple(derived.values)
    except (TypeError, ValueError):
        messages.append(f"Track {track.name!r} has unreadable {derived.kind} data")
        return None

    if len(raw_frames) != len(raw_values):
        messages.append(
            f"Track {track.name!r} has mismatched {derived.kind} frames/values lengths and was ignored"
        )
        return None

    frames: list[int] = []
    values: list[tuple[float, ...]] = []
    previous_frame: int | None = None
    for raw_frame, raw_value in zip(raw_frames, raw_values):
        if isinstance(raw_frame, bool) or not isinstance(raw_frame, Integral):
            messages.append(
                f"Track {track.name!r} has an invalid frame index in {derived.kind} and was ignored"
            )
            return None
        frame = int(raw_frame)
        if frame < 0 or (previous_frame is not None and frame <= previous_frame):
            messages.append(
                f"Track {track.name!r} has invalid frame order in {derived.kind} and was ignored"
            )
            return None
        previous_frame = frame

        if isinstance(raw_value, (str, bytes)):
            messages.append(
                f"Track {track.name!r} has non-numeric values in {derived.kind} and was ignored"
            )
            return None
        try:
            row = tuple(raw_value)
        except (TypeError, ValueError):
            messages.append(
                f"Track {track.name!r} has non-numeric values in {derived.kind} and was ignored"
            )
            return None
        if len(row) != expected_width:
            messages.append(
                f"Track {track.name!r} has values that are not {width_text} in {derived.kind} and was ignored"
            )
            return None
        try:
            numbers = tuple(float(item) for item in row)
        except (TypeError, ValueError, OverflowError):
            messages.append(
                f"Track {track.name!r} has non-numeric values in {derived.kind} and was ignored"
            )
            return None
        if not all(isfinite(number) for number in numbers):
            messages.append(
                f"Track {track.name!r} has non-finite values in {derived.kind} and was ignored"
            )
            return None
        if timeline.working_zone[0] <= frame <= timeline.working_zone[1]:
            frames.append(frame)
            values.append(numbers)

    return tuple(frames), tuple(values)


__all__ = [
    "ComparisonBasis",
    "TimingIdentity",
    "angular_pipeline_summary",
    "calibration_recipe_reject_reason",
    "comparison_basis",
    "comparison_mismatch_reason",
    "fps_mismatch_reason",
    "has_approximate_timing",
    "input_selection",
    "pipeline_summary",
    "pair_recipe_reject_reason",
    "pair_timing_reject_reason",
    "prepare_derived_rows",
    "reference_reject_reason",
    "reference_recipe",
    "reference_summary",
    "smoothing_readable_reject_reason",
    "smoothing_recipe",
    "step_params",
    "timing_identity",
    "timing_identity_reject_reason",
    "timing_summary",
    "unwrap_discont",
    "unreadable_step_reason",
    "zone_mismatch",
]
