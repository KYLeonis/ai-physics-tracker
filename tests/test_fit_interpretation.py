"""拟合解读冻结夹具：解析样例、64*eps 基线边界、尺度不变性与非法/溢出输入拒绝。"""

from dataclasses import FrozenInstanceError

import numpy as np
import pytest

from ai_physics_tracker.domain.fit_interpretation import FitInterpretation, interpret_fit


def test_exact_prediction_scores_full_improvement():
    # measured 本身是精确直线 y = 2x+1，预测与测量逐点相等。
    measured = np.array([1.0, 3.0, 5.0, 7.0])

    result = interpret_fit(measured, measured)

    assert result.rmse == 0.0
    assert result.improvement_percent == 100.0


def test_constant_mean_prediction_scores_zero_improvement():
    measured = np.array([1.0, 2.0, 3.0, 4.0])

    result = interpret_fit(measured, np.full(4, 2.5))

    # 预测恒等于样本均值时，拟合误差与基线是同一组残差幅值。
    assert result.improvement_percent == pytest.approx(0.0, abs=1e-12)
    assert result.rmse == pytest.approx(result.baseline_rmse, rel=1e-15)


def test_fit_worse_than_constant_baseline_gives_negative_improvement():
    measured = np.array([0.0, 1.0, 2.0, 3.0])

    result = interpret_fit(measured, np.full(4, 10.0))

    # 解析期望：残差 [10,9,8,7] -> rmse = sqrt(73.5)；中心化 [-1.5,-.5,.5,1.5] -> baseline = sqrt(1.25)。
    assert result.rmse == pytest.approx(np.sqrt(73.5), rel=1e-12)
    assert result.baseline_rmse == pytest.approx(np.sqrt(1.25), rel=1e-12)
    assert result.improvement_percent < 0.0


def test_constant_measured_signal_leaves_improvement_undefined():
    result = interpret_fit([3.0, 3.0, 3.0], [1.0, 5.0, 9.0])

    assert result.baseline_rmse == 0.0
    assert result.improvement_percent is None
    assert result.reason


def test_near_constant_signal_at_large_scale_leaves_improvement_undefined():
    # 1e-3 的波动在 1e12 的量级下低于 64*eps*max|measured|，数值上不可分辨。
    measured = np.array([1e12, 1e12 + 1e-3, 1e12])

    result = interpret_fit(measured, measured + 1.0)

    assert result.improvement_percent is None


def test_same_absolute_variation_resolves_at_unit_scale():
    # 与上一测试相同的绝对波动在量级 1 下完全可分辨：阈值是纯相对的，无绝对下限。
    measured = [1.0, 1.0 + 1e-3, 1.0]

    result = interpret_fit(measured, measured)

    assert result.improvement_percent == 100.0


def test_improvement_percentage_survives_extreme_scales():
    measured = np.array([0.0, 1.0, 2.0, 3.0, 4.0])
    predicted = np.array([0.1, 0.9, 2.2, 2.8, 4.1])

    reference = interpret_fit(measured, predicted)
    tiny = interpret_fit(measured * 1e-12, predicted * 1e-12)
    huge = interpret_fit(measured * 1e12, predicted * 1e12)

    assert tiny.baseline_rmse == pytest.approx(reference.baseline_rmse * 1e-12, rel=1e-9)
    assert huge.baseline_rmse == pytest.approx(reference.baseline_rmse * 1e12, rel=1e-9)
    for scaled in (tiny, huge):
        assert scaled.improvement_percent == pytest.approx(reference.improvement_percent, abs=1e-6)
        assert scaled.improvement_percent > 0.0


def test_baseline_at_resolution_threshold_is_undefined_but_just_above_is_kept():
    eps = float(np.finfo(float).eps)

    # [1±64eps] 中心化后恰为 ±64eps，baseline == 阈值边界（<= 语义）。
    at_limit = interpret_fit([1.0 - 64.0 * eps, 1.0 + 64.0 * eps], [1.0 - 64.0 * eps, 1.0 + 64.0 * eps])
    assert at_limit.improvement_percent is None

    above_limit = interpret_fit(
        [1.0 - 128.0 * eps, 1.0 + 128.0 * eps], [1.0 - 128.0 * eps, 1.0 + 128.0 * eps]
    )
    assert above_limit.improvement_percent == 100.0


@pytest.mark.parametrize("measured,predicted", [
    ([], []),
    ([1.0, 2.0], [1.0]),
    ([[1.0, 2.0]], [[1.0, 2.0]]),
    ([1.0, float("nan")], [1.0, 2.0]),
    ([1.0, 2.0], [1.0, float("inf")]),
])
def test_invalid_inputs_are_rejected(measured, predicted):
    with pytest.raises(ValueError):
        interpret_fit(measured, predicted)


def test_residual_overflow_is_rejected_instead_of_producing_infinity():
    # 有限输入之差超出 float 范围：拒绝而不是返回 inf 指标。
    with pytest.raises(ValueError):
        interpret_fit([-1.5e308, -1.5e308], [1.5e308, 1.5e308])


def test_improvement_overflow_is_rejected_instead_of_producing_negative_infinity():
    # baseline = 1e-280 可分辨，但 rmse/baseline = 1e580 溢出：拒绝而不是返回 -inf。
    with pytest.raises(ValueError):
        interpret_fit([1e-280, -1e-280], [1e300, -1e300])


def test_result_is_frozen():
    result = interpret_fit([1.0, 2.0], [1.5, 2.5])

    assert isinstance(result, FitInterpretation)
    with pytest.raises(FrozenInstanceError):
        result.rmse = 0.0


def test_large_finite_constant_does_not_overflow_the_baseline_mean():
    result=interpret_fit([1e308,1e308],[1e308,1e308])
    assert result.rmse==0
    assert result.baseline_rmse==0
    assert result.improvement_percent is None
