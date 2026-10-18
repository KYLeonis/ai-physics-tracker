"""源信号计算配方的共同事实与读写；不决定缓存显示或结果发布策略。"""

from collections.abc import Mapping
from dataclasses import dataclass
from math import isfinite
from numbers import Integral
from uuid import UUID

from ai_physics_tracker.domain.angular import AngularReference, PendulumReference, TwoPointReference
from ai_physics_tracker.domain.derived import DerivedData
from ai_physics_tracker.domain.timeline import Timeline
from ai_physics_tracker.domain.types import JsonObject


@dataclass(frozen=True)
class SmoothingParameters:
    """二阶 SG 管线参数；与 ADR-0008 保持相同默认值。"""

    window_length: int = 7
    polyorder: int = 2

    def __post_init__(self) -> None:
        if (type(self.window_length) is not int or type(self.polyorder) is not int
                or self.window_length % 2 != 1 or not 2 <= self.polyorder < self.window_length):
            raise ValueError("SG window must be odd and satisfy 2 <= polynomial order < window")


# fps 与时间比较容差（CODE_STANDARD §9.4；fps 经持久化往返后应精确相等，
# 容差只吸收序列化边缘误差，不放宽到半帧级别）。
_FPS_TOLERANCE = 1e-9

# 已知计算步骤；其余步骤按"整体一致"参与比较（不可读即拒绝）。
KNOWN_STEP_NAMES = frozenset(
    {"calibration_transform", "angular_reference", "angular_unwrap", "savitzky_golay"}
)

_SG_CONTRACT_KEYS = ("window_length", "polyorder", "deriv", "mode")

_ANGULAR_REFERENCE_MODES = ("pendulum", "two_point")

# 生成与读取共用导数阶；带该kind的SG步骤阶数不符时不可读。
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


def smoothing_derivative_order(kind: str) -> int | None:
    """已知SG源的导数阶；原始位置 / 角度及其他kind返回None。"""
    return _SG_DERIV_ORDERS.get(kind)


def smoothing_step(kind: str, window_length: int, polyorder: int, fps_nominal: float) -> JsonObject:
    """按实际源kind构造SG步骤；不改变调用方的参数接受策略。"""
    order = smoothing_derivative_order(kind)
    if order is None:
        raise ValueError(f"{kind} does not use Savitzky-Golay smoothing")
    params: JsonObject = {"window_length": window_length, "polyorder": polyorder,
                          "deriv": order, "mode": "interp"}
    if order:
        params["delta"] = 1.0 / fps_nominal
    return {"step": "savitzky_golay", "params": params}


def reference_parameters(reference: AngularReference) -> JsonObject:
    """已确认角参考的记录形式；轨迹归属 / 计算资格由调用方检查。"""
    if isinstance(reference, PendulumReference):
        return {"mode": "pendulum", "pivot_px": list(reference.pivot_px)}
    if isinstance(reference, TwoPointReference):
        return {"mode": "two_point", "reference_track_id": str(reference.reference_track_id)}
    raise ValueError("Unsupported angular reference")


def recorded_reference(recipe: Mapping) -> AngularReference:
    """从已读取配方恢复角参考；仅转换，不授予数据使用或覆盖权限。"""
    try:
        if recipe.get("mode") == "pendulum":
            pivot = recipe.get("pivot_px")
            return PendulumReference((pivot[0], pivot[1]))
        if recipe.get("mode") == "two_point":
            return TwoPointReference(UUID(str(recipe.get("reference_track_id"))))
    except (KeyError, IndexError, TypeError, ValueError) as error:
        raise ValueError("Unreadable recorded angular reference") from error
    raise ValueError("Unsupported recorded angular reference")


def timing_parameters(timeline: Timeline, approximation: str | None) -> JsonObject:
    """同步与后台共用的时序来源记录；每次返回独立JSON值。"""
    return {"fps_nominal": timeline.fps_nominal, "working_zone": list(timeline.working_zone),
            "approximation": approximation}


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


