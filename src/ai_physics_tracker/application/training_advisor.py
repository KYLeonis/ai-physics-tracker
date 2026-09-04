"""应用层规则型 Training Advisor：纯函数、确定性、Qt-free（Phase 5.5）。

只消费不可变输入快照，输出单一下一步建议；不调用引擎、不读文件、不修改
ProjectSession、不产生随机性——同一输入永远得到同一输出（spec R7 / AC-8）。
建议是可重新计算的界面状态，不写入 project.json（ADR-0015）。
"""

from collections.abc import Sequence
from dataclasses import dataclass, field
from math import isfinite

# 固定阈值与档位（mini-plan 已批准的第一版可解释值；进入 evidence，不伪装成
# 统计显著性或通用物理精度标准）
RMSE_TREND_THRESHOLD = 0.05          # 相对变化 ≥±5% 视为 improved/worsened
GENERALIZATION_GAP_FACTOR = 1.5      # fixed-validation RMSE ≥ train RMSE × 1.5 触发
LABEL_MORE_TIERS = (10, 5, 3)        # 建议标注数量档位（从大到小取首个 ≤ 可用候选）
CORRECTION_YIELD_HIGH = 0.4          # 上一批次 correction yield 达到该值 → 建议加标注档
ADDITIONAL_EPOCHS_DEFAULT = 25
ADDITIONAL_EPOCHS_EXTENDED = 50
MIN_BATCH_SIZE = 1

ACTION_REVIEW_CANDIDATES = "review_candidates"
ACTION_LABEL_MORE = "label_more"
ACTION_RESUME = "resume"
ACTION_RESTART = "restart"
ACTION_STOP_AND_COMPARE = "stop_and_compare"
ACTION_FIX_PREREQUISITE = "fix_prerequisite"

ACTIONS = frozenset({
    ACTION_REVIEW_CANDIDATES, ACTION_LABEL_MORE, ACTION_RESUME,
    ACTION_RESTART, ACTION_STOP_AND_COMPARE, ACTION_FIX_PREREQUISITE,
})

# OOM 错误识别标记：Advisor 输入采集与 GUI 共用，避免两份清单漂移（review 7）
OOM_MARKERS = ("out of memory", "oom", "cuda out of memory", "not enough memory")


@dataclass(frozen=True)
class RoundMetrics:
    """一轮 completed 训练在同 series 下的评价快照（recent last）。

    metric_name/unit 用于确保只比较同名同单位指标；validation_series_id
    不同（或为 None）的轮次之间禁止计算 delta。
    """

    training_run_id: str
    validation_series_id: str | None
    train_rmse: float
    validation_rmse: float
    metric_name: str = "rmse"
    metric_unit: str = "px"


@dataclass(frozen=True)
class AdvisorInput:
    """Advisor 的不可变输入快照；由调用方从活动 session 采集。"""

    has_active_task: bool = False
    artifacts_missing: bool = False
    validation_valid: bool = True
    validation_invalid_reason: str | None = None
    last_train_failed: bool = False
    last_failure_is_oom: bool = False
    pending_candidates: int = 0
    completed_train_runs: int = 0
    new_labels_since_last_train: int = 0
    has_compatible_source: bool = False        # 存在可 resume 的 completed snapshot
    recent_rounds: tuple[RoundMetrics, ...] = ()  # 按完成时间升序（recent last）
    correction_yield: float | None = None      # 最近审核批次 corrected/reviewed
    uncovered_zone_segments: bool = False      # working zone 四等分缺 training label
    requested_batch_size: int = 8              # 用户当前表单 batch size（OOM 减半基准）
    requested_epochs: int = 50                 # 用户当前表单 epochs（restart 语境）

    def __post_init__(self) -> None:
        if type(self.pending_candidates) is not int or self.pending_candidates < 0:
            raise ValueError("pending_candidates must be a non-negative integer")
        if type(self.completed_train_runs) is not int or self.completed_train_runs < 0:
            raise ValueError("completed_train_runs must be a non-negative integer")
        if type(self.new_labels_since_last_train) is not int or self.new_labels_since_last_train < 0:
            raise ValueError("new_labels_since_last_train must be a non-negative integer")
        if type(self.requested_batch_size) is not int or self.requested_batch_size < 1:
            raise ValueError("requested_batch_size must be a positive integer")
        if type(self.requested_epochs) is not int or self.requested_epochs <= 0:
            raise ValueError("requested_epochs must be a positive integer")
        for round_metrics in self.recent_rounds:
            if not isinstance(round_metrics, RoundMetrics):
                raise ValueError("recent_rounds must contain RoundMetrics")
            for label, value in (("train_rmse", round_metrics.train_rmse),
                                 ("validation_rmse", round_metrics.validation_rmse)):
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    raise ValueError(f"{label} must be a finite number")
                if not isfinite(value) or value < 0:
                    raise ValueError(f"{label} must be finite and non-negative")
        if self.correction_yield is not None:
            if isinstance(self.correction_yield, bool) or \
                    not isinstance(self.correction_yield, (int, float)) or \
                    not isfinite(self.correction_yield) or not 0 <= self.correction_yield <= 1:
                raise ValueError("correction_yield must be in [0, 1]")


@dataclass(frozen=True)
class AdvisorRecommendation:
    """单一下一步建议：动作、参数、证据与限制。"""

    action: str
    epochs: int | None = None
    batch_size: int | None = None
    label_count: int | None = None
    training_mode: str | None = None       # resume 时 "resume"/"restart" 语义提示
    evidence: tuple[str, ...] = field(default_factory=tuple)
    limits: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.action not in ACTIONS:
            raise ValueError(f"action must be one of {sorted(ACTIONS)}, got {self.action!r}")
        if self.training_mode is not None and self.training_mode not in {"restart", "resume"}:
            raise ValueError(
                f"training_mode must be 'restart', 'resume' or None, got {self.training_mode!r}")
        for label, value in (("epochs", self.epochs), ("batch_size", self.batch_size),
                             ("label_count", self.label_count)):
            if value is not None and (type(value) is not int or value < 1):
                raise ValueError(f"{label} must be a positive integer or None")
        for group in (self.evidence, self.limits):
            if any(not isinstance(item, str) or not item.strip() for item in group):
                raise ValueError("evidence and limits must contain non-empty strings")


def recommend_training_action(inp: AdvisorInput) -> AdvisorRecommendation:
    """按固定优先级返回第一条命中的规则建议（同一输入同一输出）。"""
    if inp.has_active_task or inp.artifacts_missing or not inp.validation_valid:
        reasons = []
        if inp.has_active_task:
            reasons.append("an AI task is currently running")
        if inp.artifacts_missing:
            reasons.append("model/config artifacts of a referenced run are missing")
        if not inp.validation_valid:
            reasons.append(
                f"active validation series is invalid: {inp.validation_invalid_reason or 'modified'}"
            )
        return AdvisorRecommendation(
            action=ACTION_FIX_PREREQUISITE,
            evidence=tuple(reasons),
            limits=("Resolve the prerequisite before starting another training iteration.",),
        )

    if inp.last_train_failed and inp.last_failure_is_oom:
        halved = max(inp.requested_batch_size // 2, MIN_BATCH_SIZE)
        return AdvisorRecommendation(
            action=ACTION_RESTART,
            batch_size=halved,
            training_mode=None,  # 保持用户原 mode/source，只调 batch（plan 规则 2）
            evidence=("last training failed with an out-of-memory error",),
            limits=(
                f"batch size halved from {inp.requested_batch_size} to {halved}; "
                "keep your previous mode and resume source when retrying",
                "batch size is never increased without hardware evidence",
            ),
        )

    core = _core_recommendation(inp)

    # 规则 3：pending 候选不得被训练类建议跳过；label_more 本身就是
    # 审核/标注族动作（plan 规则 7"有候选时 label_more"），不抢占
    if inp.pending_candidates > 0 and core.action in {
        ACTION_RESTART, ACTION_RESUME, ACTION_STOP_AND_COMPARE, ACTION_FIX_PREREQUISITE,
    }:
        return AdvisorRecommendation(
            action=ACTION_REVIEW_CANDIDATES,
            evidence=(f"{inp.pending_candidates} difficult-frame candidate(s) await review",),
            limits=("Manual review comes first — do not skip review and retrain directly.",),
        )
    return core


def _core_recommendation(inp: AdvisorInput) -> AdvisorRecommendation:
    """规则 4–9 的核心建议（不含 pending 抢占）。"""
    if inp.completed_train_runs == 0:
        return AdvisorRecommendation(
            action=ACTION_RESTART,
            epochs=inp.requested_epochs,
            batch_size=inp.requested_batch_size,
            training_mode=ACTION_RESTART,
            evidence=("no completed training run on this track",),
            limits=("No resume source exists yet; start from the default parameters.",),
        )

    comparison = _same_series_comparison(inp.recent_rounds)
    new_labels = inp.new_labels_since_last_train > 0
    worsened = comparison is not None and _validation_worsened(comparison)

    if new_labels:
        # 规则 5：有新增标签优先 resume；validation 已恶化或无兼容 snapshot 则 restart
        if inp.has_compatible_source and not worsened:
            limits = ["Epochs value means additional epochs for this run (fine-tune)."]
            if comparison is None:
                # 规则 9：无可比评价时必须明示限制，不宣称改善
                limits.insert(0, "No comparable fixed-validation evaluation — "
                                 "cannot judge whether accuracy improved.")
            return AdvisorRecommendation(
                action=ACTION_RESUME,
                epochs=ADDITIONAL_EPOCHS_DEFAULT,
                training_mode=ACTION_RESUME,
                evidence=(f"{inp.new_labels_since_last_train} new manual label(s) since the last training",),
                limits=tuple(limits),
            )
        reasons = [f"{inp.new_labels_since_last_train} new manual label(s) since the last training"]
        if worsened:
            prev, last = comparison
            val_delta = (last.validation_rmse - prev.validation_rmse) / prev.validation_rmse
            reasons.append(
                f"validation RMSE worsened {val_delta:.1%} "
                f"({prev.validation_rmse:.4g} → {last.validation_rmse:.4g})"
            )
        if not inp.has_compatible_source:
            reasons.append("no compatible snapshot to resume from")
        return AdvisorRecommendation(
            action=ACTION_RESTART,
            epochs=inp.requested_epochs,
            batch_size=inp.requested_batch_size,
            training_mode=ACTION_RESTART,
            evidence=tuple(reasons),
            limits=("Resume requires a completed train run with an existing snapshot.",),
        )

    if comparison is not None:
        prev, last = comparison
        val_delta = (last.validation_rmse - prev.validation_rmse) / prev.validation_rmse
        train_delta = (last.train_rmse - prev.train_rmse) / prev.train_rmse
        series_note = f"validation series {last.validation_series_id}"
        gap = last.validation_rmse >= GENERALIZATION_GAP_FACTOR * last.train_rmse
        if val_delta <= -RMSE_TREND_THRESHOLD:
            both_improving = train_delta <= -RMSE_TREND_THRESHOLD
            epochs = ADDITIONAL_EPOCHS_EXTENDED if both_improving else ADDITIONAL_EPOCHS_DEFAULT
            return AdvisorRecommendation(
                action=ACTION_RESUME,
                epochs=epochs,
                training_mode=ACTION_RESUME,
                evidence=(
                    f"{series_note}: validation RMSE improved "
                    f"{abs(val_delta):.1%} ({prev.validation_rmse:.4g} → {last.validation_rmse:.4g})",
                    f"train RMSE {'improved' if train_delta < 0 else 'changed'} "
                    f"{abs(train_delta):.1%}",
                ),
                limits=(
                    "Epochs means additional epochs (fine-tune); at most one extension step, "
                    "never an automatic loop.",
                ),
            )
        if val_delta >= RMSE_TREND_THRESHOLD or gap:
            reasons = []
            if val_delta >= RMSE_TREND_THRESHOLD:
                reasons.append(f"{series_note}: validation RMSE worsened {val_delta:.1%} "
                               f"({prev.validation_rmse:.4g} → {last.validation_rmse:.4g})")
            if gap:
                reasons.append(
                    f"generalization gap: validation RMSE {last.validation_rmse:.4g} ≥ "
                    f"{GENERALIZATION_GAP_FACTOR}× train RMSE {last.train_rmse:.4g}"
                )
            if inp.pending_candidates > 0:
                return AdvisorRecommendation(
                    action=ACTION_LABEL_MORE,
                    label_count=_label_count(inp),
                    evidence=tuple(reasons),
                    limits=("Metrics are screening signals, not ground-truth accuracy.",),
                )
            return AdvisorRecommendation(
                action=ACTION_RESTART,
                epochs=inp.requested_epochs,
                batch_size=inp.requested_batch_size,
                training_mode=ACTION_RESTART,
                evidence=tuple(reasons),
                limits=("No candidates left to review; restart from scratch with current labels.",),
            )
        # plateau：±5% 以内
        if inp.uncovered_zone_segments:
            return AdvisorRecommendation(
                action=ACTION_LABEL_MORE,
                label_count=_label_count(inp),
                evidence=(
                    f"{series_note}: validation RMSE plateau "
                    f"(delta {val_delta:.1%} within ±{RMSE_TREND_THRESHOLD:.0%})",
                    "working zone has time segments without training labels",
                ),
                limits=("Metrics are screening signals, not ground-truth accuracy.",),
            )
        return AdvisorRecommendation(
            action=ACTION_STOP_AND_COMPARE,
            evidence=(
                f"{series_note}: validation RMSE plateau "
                f"(delta {val_delta:.1%} within ±{RMSE_TREND_THRESHOLD:.0%})",
                f"train RMSE {last.train_rmse:.4g}, validation RMSE {last.validation_rmse:.4g}",
            ),
            limits=(
                "Stop iterating: compare evaluations across the same series manually; "
                "coverage/confidence are not accuracy.",
            ),
        )

    # 规则 9：没有同一 series 的可比评价
    if new_labels:
        return AdvisorRecommendation(
            action=ACTION_RESUME,
            epochs=ADDITIONAL_EPOCHS_DEFAULT,
            training_mode=ACTION_RESUME,
            evidence=(f"{inp.new_labels_since_last_train} new manual label(s) since the last training",),
            limits=(
                "No comparable fixed-validation evaluation — cannot judge whether accuracy improved.",
                "Epochs means additional epochs (fine-tune).",
            ),
        )
    return AdvisorRecommendation(
        action=ACTION_FIX_PREREQUISITE,
        evidence=("no fixed validation series with a completed evaluation exists",),
        limits=(
            "Freeze a fixed validation series and retrain before iterating; "
            "without it the advisor cannot judge improvement.",
        ),
    )


def _same_series_comparison(
    rounds: Sequence[RoundMetrics],
) -> tuple[RoundMetrics, RoundMetrics] | None:
    """取最近一轮与其之前最近一轮同 series 且同名同单位指标的组合；否则 None。"""
    if len(rounds) < 2:
        return None
    last = rounds[-1]
    if last.validation_series_id is None:
        return None
    for previous in reversed(rounds[:-1]):
        if (previous.validation_series_id == last.validation_series_id
                and previous.metric_name == last.metric_name
                and previous.metric_unit == last.metric_unit
                and previous.validation_rmse > 0 and previous.train_rmse > 0):
            return previous, last
    return None


def _validation_worsened(comparison: tuple[RoundMetrics, RoundMetrics]) -> bool:
    prev, last = comparison
    if prev.validation_rmse <= 0:
        return False
    return (last.validation_rmse - prev.validation_rmse) / prev.validation_rmse >= RMSE_TREND_THRESHOLD


def _label_count(inp: AdvisorInput) -> int:
    """有限档位 10/5/3：yield 高或时间缺口 → 大档；不超过可用候选数。"""
    available = max(inp.pending_candidates, 1)
    want_large = (inp.correction_yield is not None and inp.correction_yield >= CORRECTION_YIELD_HIGH) \
        or inp.uncovered_zone_segments
    for tier in LABEL_MORE_TIERS:
        if tier <= available and (want_large or tier != LABEL_MORE_TIERS[0]):
            return tier
    return min(available, LABEL_MORE_TIERS[-1])
