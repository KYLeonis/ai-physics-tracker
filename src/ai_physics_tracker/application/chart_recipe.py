"""图表科学配方与时序来源的读取、核对与披露（Qt-free）。

Phase 6.2 S1 从 ``chart_data.py`` 拆出的公共实现（phase-6.2 计划
Implementation Surface：科学配方校验 / 行适配与图表组装分离）。本模块只读取
``DerivedData`` 的 pipeline / input / timing_context，回答三类问题：

1. 一条记录的配方与时序来源是否**可读且自洽**——fail-closed：契约要求
   存在的字段缺失即视为无法确认，不把"两边都缺"当成一致；
2. 两条（或多条）记录是否**可比较**——同输入选择、同计算步骤、同参考 /
   标定、同时序来源；仅相空间配对允许 SG 导数阶 0→1 的差别；
3. 已接受结果的实际配方与时序来源如何**披露**给图例 / 状态栏。

SG 参数契约以 ``kinematics_job.validate_smoothing_recipe`` 为准：
window_length / polyorder / deriv / mode 恒在，deriv>0 时另有 delta=1/fps。
时序上下文契约以 ADR-0020 为准：angular 结果恒带 fps_nominal /
working_zone / approximation；线性结果当前只写 fps / approximation
（区间来源由后续 GUI Slice 补记，缺失即不可配对，不猜测）。
"""

from collections.abc import Mapping
from dataclasses import dataclass
from math import isfinite
from numbers import Integral
from uuid import UUID

from ai_physics_tracker.application.kinematics_job import SmoothingParameters
from ai_physics_tracker.domain.derived import DerivedData
from ai_physics_tracker.domain.timeline import Timeline
from ai_physics_tracker.domain.track import Track

# fps 与时间比较容差（CODE_STANDARD §9.4；fps 经持久化往返后应精确相等，
# 容差只吸收序列化边缘误差，不放宽到半帧级别）。
_FPS_TOLERANCE = 1e-9

# 已知计算步骤；其余步骤按"整体一致"参与比较（不可读即拒绝）。
_KNOWN_STEP_NAMES = frozenset(
    {"calibration_transform", "angular_reference", "angular_unwrap", "savitzky_golay"}
)

_SG_CONTRACT_KEYS = ("window_length", "polyorder", "deriv", "mode")

_ANGULAR_REFERENCE_MODES = ("pendulum", "two_point")

# kind → 契约导数阶（与 kinematics_job.validate_smoothing_recipe 同一口径）；
# 带该 kind 的 SG 步骤 deriv 不匹配即视为不可读配方。
_SG_DERIV_ORDERS = {
    "smoothed_position": 0,
    "velocity": 1,
    "acceleration": 2,
    "smoothed_angular_position": 0,
    "angular_velocity": 1,
    "angular_acceleration": 2,
}

# 平滑 / 导数角量必须经 unwrap 后再 SG（ADR-0019 管线次序）；原始角度无
# SG / unwrap 为合法（wrapped 原样展示）。
_ANGULAR_SG_REQUIRED_KINDS = frozenset(
    {"smoothed_angular_position", "angular_velocity", "angular_acceleration"}
)


# ---------------------------------------------------------------------------
# 基础读取
# ---------------------------------------------------------------------------


def _finite_number(value: object) -> float | None:
    """严格数值读取：bool / 非数值 / 非有限一律 None，不猜测。"""

    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if isfinite(number) else None


def pipeline_step_names(derived: DerivedData) -> tuple[str | None, ...]:
    """pipeline 的步骤名序列；非映射步骤记为 None（由 unreadable_step_reason 拒绝）。"""

    return tuple(
        step.get("step") if isinstance(step, Mapping) else None
        for step in derived.pipeline
    )


def unreadable_step_reason(derived: DerivedData) -> str | None:
    """pipeline 中存在不可解析步骤时的原因；None = 全部步骤可读。"""

    for step in derived.pipeline:
        if not isinstance(step, Mapping):
            return "has an unreadable processing step"
        name = step.get("step")
        if not isinstance(name, str) or not name:
            return "has an unnamed processing step"
    return None


def has_step(derived: DerivedData, step_name: str) -> bool:
    return any(
        isinstance(step, Mapping) and step.get("step") == step_name
        for step in derived.pipeline
    )


def step_params(derived: DerivedData, step_name: str) -> Mapping | None:
    """取唯一指定名称步骤的参数；缺失 / 重复 / 参数不是映射返回 None。"""

    steps = [
        step
        for step in derived.pipeline
        if isinstance(step, Mapping) and step.get("step") == step_name
    ]
    if len(steps) != 1:
        return None
    params = steps[0].get("params")
    return params if isinstance(params, Mapping) else None


def smoothing_recipe(derived: DerivedData) -> dict[str, object] | None:
    """规整且经过值校验的 SG 配方；键缺失或值非法即 None（不把坏值当一致）。

    返回 dict 恒含 window_length / polyorder / deriv / mode / delta 五键：
    - window / polyorder 必须能构成合法的 :class:`SmoothingParameters`
      （奇数窗口、2 <= polyorder < window）；
    - deriv 必须与记录 kind 的契约导数阶一致（平滑 0 / 速度 1 / 加速度 2，
      线性与角量同口径）；mode 必须是当前契约的 ``interp``；
    - delta 出现时必须是有限正数；deriv>0 时 delta 缺失视为不可读。
    """

    params = step_params(derived, "savitzky_golay")
    if params is None:
        return None
    recipe: dict[str, object] = {}
    for key in _SG_CONTRACT_KEYS:
        if key not in params:
            return None
        recipe[key] = params[key]
    deriv = recipe["deriv"]
    if isinstance(deriv, bool) or not isinstance(deriv, int):
        return None
    expected_order = _SG_DERIV_ORDERS.get(derived.kind)
    if expected_order is not None and deriv != expected_order:
        return None
    if recipe["mode"] != "interp":
        return None
    try:
        SmoothingParameters(
            window_length=recipe["window_length"], polyorder=recipe["polyorder"]
        )
    except (TypeError, ValueError):
        return None
    delta_value = params.get("delta")
    if delta_value is None:
        delta = None
    else:
        delta = _finite_number(delta_value)
        if delta is None or delta <= 0:
            return None
    if deriv > 0 and delta is None:
        return None
    recipe["delta"] = delta
    return recipe


def reference_recipe(derived: DerivedData) -> Mapping | None:
    """取唯一 angular_reference 步骤的参数；缺失 / 重复 / 不可读返回 None。"""

    return step_params(derived, "angular_reference")


def unwrap_discont(derived: DerivedData) -> float | None:
    """unwrap 步骤的显式不连续阈值；缺失 / 重复 / 不可读返回 None。"""

    params = step_params(derived, "angular_unwrap")
    if params is None:
        return None
    return _finite_number(params.get("discont"))


# ---------------------------------------------------------------------------
# 单记录自洽性核对
# ---------------------------------------------------------------------------


def calibration_recipe_reject_reason(derived: DerivedData) -> str | None:
    """calibration_transform 步骤与 calibration_ref 互相印证；不一致拒绝。

    契约（kinematics_job.validated_batch）：有标定时步骤参数记录同一 id，
    无标定时不得出现该步骤。
    """

    steps = [
        step
        for step in derived.pipeline
        if isinstance(step, Mapping) and step.get("step") == "calibration_transform"
    ]
    expected = str(derived.calibration_ref) if derived.calibration_ref is not None else None
    if not steps:
        return None if expected is None else (
            "does not record the calibration used by its results"
        )
    if len(steps) > 1:
        return "has more than one calibration_transform step"
    params = steps[0].get("params")
    if not isinstance(params, Mapping) or params.get("calibration_id") != expected:
        return "has a calibration recipe that does not match its recorded calibration"
    return None


def reference_reject_reason(derived: DerivedData) -> str | None:
    """角运动记录参考配方的自洽性；None = 可读、模式已知、与输入参考一致。"""

    reference = reference_recipe(derived)
    if reference is None:
        return "has no readable angular reference recipe"
    mode = reference.get("mode")
    if mode not in _ANGULAR_REFERENCE_MODES:
        return (
            f"has an unknown angular reference mode {mode!r}; comparability "
            "cannot be confirmed"
        )
    if mode == "pendulum":
        if derived.input.reference_track_id is not None:
            return (
                "has a pendulum reference but its input records a reference "
                "track; the pendulum definition is single-track"
            )
        pivot = reference.get("pivot_px")
        if (
            not isinstance(pivot, (list, tuple))
            or len(pivot) != 2
            or _finite_number(pivot[0]) is None
            or _finite_number(pivot[1]) is None
        ):
            return "has a pendulum reference with an unreadable pivot"
        return None
    raw_id = reference.get("reference_track_id")
    try:
        parsed = UUID(str(raw_id))
    except (ValueError, TypeError):
        return "has a two-point reference without a readable reference track"
    if parsed != derived.input.reference_track_id:
        return (
            "has a two-point reference recipe that does not match its input "
            "reference track"
        )
    return None


def smoothing_readable_reject_reason(derived: DerivedData) -> str | None:
    """SG 契约核对：带步骤必须可读；要求 SG 的角量缺步骤 / 缺 unwrap 拒绝。

    平滑与导数角量必须经 unwrap 后再做 SG（ADR-0019 管线次序），缺任一
    步骤即无法确认来源；原始角度（angular_position / world_position 等）
    无 SG / unwrap 为合法。
    """

    if has_step(derived, "savitzky_golay"):
        if smoothing_recipe(derived) is None:
            return "has an unreadable Savitzky-Golay recipe"
    elif derived.kind in _ANGULAR_SG_REQUIRED_KINDS:
        return f"{derived.kind} is missing its Savitzky-Golay smoothing step"
    if derived.kind in _ANGULAR_SG_REQUIRED_KINDS and unwrap_discont(derived) is None:
        return f"{derived.kind} is missing a readable unwrap step"
    return None


# ---------------------------------------------------------------------------
# 时序上下文（ADR-0020）
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TimingIdentity:
    """一条记录完整可读的时序来源：记录 fps、working_zone 与近似授权说明。"""

    fps_nominal: float
    working_zone: tuple[int, int]
    approximation: str | None


def timing_context(derived: DerivedData) -> Mapping | None:
    context = derived.extra_fields.get("timing_context")
    return context if isinstance(context, Mapping) else None


def recorded_fps(context: Mapping) -> float | None:
    return _finite_number(context.get("fps_nominal"))


def _strict_zone_pair(zone_value: object) -> tuple[int, int] | None:
    """working_zone 的严格读取：两个非 bool 整数且 0 <= start <= end。

    不做 ``int()`` 强转猜测：0.5、'0' 之类的值说明来源未按契约写入，
    一律视为不可读，由调用方拒绝。
    """

    if not isinstance(zone_value, (list, tuple)) or len(zone_value) != 2:
        return None
    start, end = zone_value
    if (
        isinstance(start, bool)
        or isinstance(end, bool)
        or not isinstance(start, Integral)
        or not isinstance(end, Integral)
    ):
        return None
    zone = (int(start), int(end))
    if zone[0] < 0 or zone[1] < zone[0]:
        return None
    return zone


def timing_identity(derived: DerivedData) -> TimingIdentity | None:
    """完整可读的时序身份；任一字段缺失或不可读返回 None。

    fps 必须是有限正数；working_zone 必须是两个非 bool 整数且
    0 <= start <= end；approximation 字段必须存在且为 None 或非空 str。
    缺失不是"与任何来源一致"。
    """

    context = timing_context(derived)
    if context is None:
        return None
    fps = recorded_fps(context)
    if fps is None or fps <= 0:
        return None
    zone = _strict_zone_pair(context.get("working_zone"))
    if zone is None:
        return None
    if "approximation" not in context:
        return None
    approximation = context.get("approximation")
    if approximation is not None and (
        not isinstance(approximation, str) or not approximation
    ):
        return None
    return TimingIdentity(fps, zone, approximation)


def timing_identity_reject_reason(derived: DerivedData) -> str | None:
    """时序来源不完整 / 不可读的具体原因；None = 完整可读。"""

    context = timing_context(derived)
    if context is None:
        return f"{derived.kind} has no recorded timing context"
    fps = recorded_fps(context)
    if fps is None or fps <= 0:
        return f"{derived.kind} has an unreadable recorded timing context"
    if _strict_zone_pair(context.get("working_zone")) is None:
        if not isinstance(context.get("working_zone"), (list, tuple)):
            return f"{derived.kind} does not record a working zone"
        return f"{derived.kind} has an unreadable recorded working zone"
    if "approximation" not in context:
        return f"{derived.kind} does not record its timing approximation"
    approximation = context.get("approximation")
    if approximation is not None and (
        not isinstance(approximation, str) or not approximation
    ):
        return f"{derived.kind} has an unreadable timing approximation record"
    return None


def fps_mismatch_reason(derived: DerivedData, timeline: Timeline) -> str | None:
    """缓存 fps 与当前时序不一致的原因；无记录时不判定（由调用方把关）。"""

    context = timing_context(derived)
    if context is None:
        return None
    fps = recorded_fps(context)
    if fps is None or fps <= 0:
        return None  # 不可读来源由 timing_identity_reject_reason 披露。
    if abs(fps - timeline.fps_nominal) > _FPS_TOLERANCE:
        return (
            f"was computed at {fps:g} fps while the current timeline runs "
            f"at {timeline.fps_nominal:g} fps"
        )
    return None


def zone_mismatch(derived: DerivedData, timeline: Timeline) -> bool:
    """缓存 working_zone 与当前区间不一致（无记录时不判定）。"""

    context = timing_context(derived)
    if context is None:
        return False
    zone = _strict_zone_pair(context.get("working_zone"))
    return zone is not None and zone != timeline.working_zone


def has_approximate_timing(derived: DerivedData) -> bool:
    context = timing_context(derived)
    if context is None:
        return False
    approximation = context.get("approximation")
    return isinstance(approximation, str) and bool(approximation)


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
        if isinstance(step, Mapping) and step.get("step") not in _KNOWN_STEP_NAMES
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
