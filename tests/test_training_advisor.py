"""规则型 Training Advisor（Phase 5.5 R7 / AC-8）表驱动单元测试。

固定 9 条规则的优先级、有限参数档位、同 series 比较边界与确定性。
"""

import pytest

from ai_physics_tracker.application.training_advisor import (
    ACTION_FIX_PREREQUISITE,
    ACTION_LABEL_MORE,
    ACTION_RESTART,
    ACTION_RESUME,
    ACTION_REVIEW_CANDIDATES,
    ACTION_STOP_AND_COMPARE,
    ADDITIONAL_EPOCHS_DEFAULT,
    ADDITIONAL_EPOCHS_EXTENDED,
    AdvisorInput,
    RoundMetrics,
    recommend_training_action,
)

SERIES = "series-a"
SERIES_B = "series-b"


def _round(run_id: str, val_rmse: float, train_rmse: float, series: str = SERIES) -> RoundMetrics:
    return RoundMetrics(
        training_run_id=run_id,
        validation_series_id=series,
        train_rmse=train_rmse,
        validation_rmse=val_rmse,
    )


def test_prerequisite_rules_take_highest_priority() -> None:
    base = dict(completed_train_runs=1, has_compatible_source=True)
    assert recommend_training_action(AdvisorInput(has_active_task=True, **base)).action \
        == ACTION_FIX_PREREQUISITE
    assert recommend_training_action(AdvisorInput(artifacts_missing=True, **base)).action \
        == ACTION_FIX_PREREQUISITE
    rec = recommend_training_action(AdvisorInput(
        validation_valid=False, validation_invalid_reason="labels modified", **base))
    assert rec.action == ACTION_FIX_PREREQUISITE
    assert any("labels modified" in e for e in rec.evidence)


def test_oom_failure_halves_batch_and_keeps_mode() -> None:
    rec = recommend_training_action(AdvisorInput(
        last_train_failed=True, last_failure_is_oom=True,
        requested_batch_size=8, completed_train_runs=1,
    ))
    assert rec.action == ACTION_RESTART
    assert rec.batch_size == 4
    assert rec.training_mode is None  # 保持用户原 mode/source
    assert any("batch size" in limit for limit in rec.limits)

    # batch 已为 1 时不再减半
    rec_min = recommend_training_action(AdvisorInput(
        last_train_failed=True, last_failure_is_oom=True, requested_batch_size=1))
    assert rec_min.batch_size == 1

    # 非 OOM 失败不触发该规则（无可比评价时落入 freeze 建议且无 batch 参数）
    rec_other = recommend_training_action(AdvisorInput(
        last_train_failed=True, completed_train_runs=1))
    assert rec_other.action == ACTION_FIX_PREREQUISITE
    assert rec_other.batch_size is None


def test_pending_candidates_block_training() -> None:
    improving = (_round("r1", 5.0, 4.0), _round("r2", 4.6, 3.9))
    rec = recommend_training_action(AdvisorInput(
        pending_candidates=7, recent_rounds=improving, completed_train_runs=2))
    assert rec.action == ACTION_REVIEW_CANDIDATES
    assert "7" in rec.evidence[0]


def test_first_training_is_restart() -> None:
    rec = recommend_training_action(AdvisorInput(completed_train_runs=0, requested_epochs=60))
    assert rec.action == ACTION_RESTART
    assert rec.epochs == 60
    assert rec.training_mode == ACTION_RESTART


def test_new_labels_resume_or_restart() -> None:
    base = dict(completed_train_runs=1, has_compatible_source=True, new_labels_since_last_train=5)
    rec = recommend_training_action(AdvisorInput(**base))
    assert rec.action == ACTION_RESUME
    assert rec.epochs == ADDITIONAL_EPOCHS_DEFAULT

    # validation 已恶化 → 规则 5 要求 restart（即使有兼容 snapshot）
    rounds = (_round("r1", 5.0, 4.0), _round("r2", 6.0, 4.0))  # val +20%
    rec_worsened = recommend_training_action(AdvisorInput(**base, recent_rounds=rounds))
    assert rec_worsened.action == ACTION_RESTART

    # 无兼容 snapshot → restart
    rec_no_source = recommend_training_action(AdvisorInput(
        completed_train_runs=1, has_compatible_source=False, new_labels_since_last_train=5))
    assert rec_no_source.action == ACTION_RESTART


def test_improved_series_suggests_resume_with_tiered_epochs() -> None:
    improving = (_round("r1", 5.0, 4.0), _round("r2", 4.6, 3.9))  # val -8%
    rec = recommend_training_action(AdvisorInput(recent_rounds=improving, completed_train_runs=2))
    assert rec.action == ACTION_RESUME
    assert rec.epochs == ADDITIONAL_EPOCHS_DEFAULT

    # train 与 validation 都仍改善 → 50 一档
    both = (_round("r1", 5.0, 4.0), _round("r2", 4.4, 3.2))
    rec_both = recommend_training_action(AdvisorInput(recent_rounds=both, completed_train_runs=2))
    assert rec_both.epochs == ADDITIONAL_EPOCHS_EXTENDED


def test_worsened_or_gap_routes_to_label_more_or_restart() -> None:
    worsened = (_round("r1", 4.0, 3.0), _round("r2", 5.0, 3.0))  # val +25%
    rec_candidates = recommend_training_action(
        AdvisorInput(recent_rounds=worsened, completed_train_runs=2, pending_candidates=6))
    assert rec_candidates.action == ACTION_LABEL_MORE
    assert rec_candidates.label_count == 5

    rec_no_candidates = recommend_training_action(
        AdvisorInput(recent_rounds=worsened, completed_train_runs=2))
    assert rec_no_candidates.action == ACTION_RESTART

    # generalization gap：validation ≥ 1.5× train（val 绝对值在 ±5% 内也算）
    gap = (_round("r1", 4.0, 2.0), _round("r2", 4.1, 2.0))
    rec_gap = recommend_training_action(
        AdvisorInput(recent_rounds=gap, completed_train_runs=2, pending_candidates=4))
    assert rec_gap.action == ACTION_LABEL_MORE
    assert any("generalization gap" in e for e in rec_gap.evidence)


def test_plateau_routes_by_uncovered_segments() -> None:
    plateau = (_round("r1", 4.0, 3.0), _round("r2", 4.02, 3.0))  # +0.5%
    rec_segments = recommend_training_action(AdvisorInput(
        recent_rounds=plateau, completed_train_runs=2, uncovered_zone_segments=True,
        pending_candidates=8))
    assert rec_segments.action == ACTION_LABEL_MORE
    assert any("plateau" in e for e in rec_segments.evidence)

    rec_stop = recommend_training_action(AdvisorInput(
        recent_rounds=plateau, completed_train_runs=2))
    assert rec_stop.action == ACTION_STOP_AND_COMPARE


def test_no_comparable_validation_states_limits() -> None:
    # 两轮 series 不同 → 无可比评价；有新增标签 → resume 但明示限制
    mixed = (_round("r1", 4.0, 3.0, series=SERIES), _round("r2", 4.0, 3.0, series=SERIES_B))
    rec_resume = recommend_training_action(AdvisorInput(
        recent_rounds=mixed, completed_train_runs=2, new_labels_since_last_train=3,
        has_compatible_source=True))
    assert rec_resume.action == ACTION_RESUME
    assert any("cannot judge" in limit for limit in rec_resume.limits)

    # 无新增标签 → 建议先冻结 validation
    rec_freeze = recommend_training_action(AdvisorInput(recent_rounds=mixed, completed_train_runs=2))
    assert rec_freeze.action == ACTION_FIX_PREREQUISITE
    assert any("Freeze" in limit or "freeze" in limit for limit in rec_freeze.limits)

    # 单轮也无法比较
    single = (_round("r1", 4.0, 3.0),)
    assert recommend_training_action(AdvisorInput(recent_rounds=single, completed_train_runs=1)) \
        .action == ACTION_FIX_PREREQUISITE


@pytest.mark.parametrize("yield_value,candidates,expected", [
    (0.6, 10, 10),   # 高 correction yield → 大档
    (None, 10, 5),   # 无证据 → 默认 5
    (None, 4, 3),    # 候选不足 5 → 3
    (None, 2, 2),    # 候选不足 3 → 不超过可用候选数
    (0.8, 4, 3),     # 想要大档但候选只有 4
])
def test_label_count_tiers_are_finite_and_capped(yield_value, candidates, expected) -> None:
    worsened = (_round("r1", 4.0, 3.0), _round("r2", 5.0, 3.0))
    rec = recommend_training_action(AdvisorInput(
        recent_rounds=worsened, completed_train_runs=2,
        pending_candidates=candidates, correction_yield=yield_value))
    assert rec.action == ACTION_LABEL_MORE
    assert rec.label_count == expected


def test_cross_series_and_cross_metric_comparisons_are_rejected() -> None:
    # series 不同 → 无可比（不是 improved）
    rounds = (_round("r1", 5.0, 4.0, series=SERIES),
              _round("r2", 4.0, 4.0, series=SERIES_B))
    rec = recommend_training_action(AdvisorInput(recent_rounds=rounds, completed_train_runs=2))
    assert rec.action == ACTION_FIX_PREREQUISITE

    # 指标名不同 → 不比较
    renamed = (RoundMetrics("r1", SERIES, 5.0, 4.0, metric_name="rmse", metric_unit="mm"),
               RoundMetrics("r2", SERIES, 4.0, 4.0, metric_name="rmse", metric_unit="px"))
    rec_metric = recommend_training_action(AdvisorInput(recent_rounds=renamed, completed_train_runs=2))
    assert rec_metric.action == ACTION_FIX_PREREQUISITE


def test_determinism_same_input_same_output() -> None:
    rounds = (_round("r1", 5.0, 4.0), _round("r2", 4.6, 3.9))
    inp = AdvisorInput(recent_rounds=rounds, completed_train_runs=2, pending_candidates=2)
    assert recommend_training_action(inp) == recommend_training_action(inp)


def test_input_validation_rejects_bad_values() -> None:
    with pytest.raises(ValueError, match="pending_candidates"):
        AdvisorInput(pending_candidates=-1)
    with pytest.raises(ValueError, match="requested_batch_size"):
        AdvisorInput(requested_batch_size=0)
    with pytest.raises(ValueError, match="validation_rmse"):
        AdvisorInput(recent_rounds=(_round("r1", float("nan"), 1.0),))
    with pytest.raises(ValueError, match="correction_yield"):
        AdvisorInput(correction_yield=1.5)
    with pytest.raises(ValueError, match="action"):
        from ai_physics_tracker.application.training_advisor import AdvisorRecommendation
        AdvisorRecommendation(action="not-an-action")


def test_threshold_boundaries_are_inclusive() -> None:
    """±5% 恰好等于按 improved/worsened 处理（plan"至少 5%"，review 4a/4b）。"""
    exactly_improved = (_round("r1", 5.0, 4.0), _round("r2", 4.75, 4.0))  # val -5.0%
    rec = recommend_training_action(AdvisorInput(recent_rounds=exactly_improved,
                                                 completed_train_runs=2))
    assert rec.action == ACTION_RESUME

    exactly_worsened = (_round("r1", 4.0, 3.0), _round("r2", 4.2, 3.0))  # val +5.0%
    rec_w = recommend_training_action(AdvisorInput(recent_rounds=exactly_worsened,
                                                   completed_train_runs=2,
                                                   pending_candidates=5))
    assert rec_w.action == ACTION_LABEL_MORE

    exactly_gap = (_round("r1", 4.0, 2.0), _round("r2", 4.0, 2.0))  # 4.0 == 2.0 × 2 < 1.5×? no: 2×
    # 4.0 >= 1.5 × 2.0 → gap 成立
    rec_gap = recommend_training_action(AdvisorInput(recent_rounds=exactly_gap,
                                                     completed_train_runs=2,
                                                     pending_candidates=3))
    assert any("generalization gap" in e for e in rec_gap.evidence)

    just_below_gap = (_round("r1", 4.0, 2.0), _round("r2", 4.0, 2.8))  # 4.0 < 1.5×2.8=4.2
    rec_below = recommend_training_action(AdvisorInput(recent_rounds=just_below_gap,
                                                       completed_train_runs=2))
    assert not any("generalization gap" in e for e in rec_below.evidence)


def test_pending_candidates_preempt_fix_prerequisite() -> None:
    """pending 候选抢占 fix_prerequisite（review 1：不得建议"冻结后 retrain"）。"""
    rec = recommend_training_action(AdvisorInput(
        pending_candidates=5, completed_train_runs=1, recent_rounds=()))
    assert rec.action == ACTION_REVIEW_CANDIDATES
    # 抢占后不得携带 fix_prerequisite 的"冻结 validation 再训练"建议
    assert not any("Freeze" in limit for limit in rec.limits)


def test_worsened_without_candidates_never_suggests_label_more() -> None:
    """零候选 + 高 correction yield 不得建议低于最小档的标注数（review 2）。"""
    worsened = (_round("r1", 4.0, 3.0), _round("r2", 5.0, 3.0))
    rec = recommend_training_action(AdvisorInput(
        recent_rounds=worsened, completed_train_runs=2,
        pending_candidates=0, correction_yield=0.6))
    assert rec.action == ACTION_RESTART
    assert rec.label_count is None
