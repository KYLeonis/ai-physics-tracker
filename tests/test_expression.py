"""受限公式的计算、排版和拒绝边界。"""

import numpy as np
import pytest

from ai_physics_tracker.domain.expression import ExpressionError, evaluate_result_formula, parse_expression


def test_power_precedence_and_associativity_match_the_display_tree():
    assert parse_expression("-t^2").evaluate([3], {})[0] == pytest.approx(-9, abs=1e-12)
    assert parse_expression("(-t)^2").evaluate([3], {})[0] == pytest.approx(9, abs=1e-12)
    assert parse_expression("2^3^2").evaluate([0], {})[0] == pytest.approx(512, abs=1e-12)
    assert parse_expression("-t^2").latex != parse_expression("(-t)^2").latex
    assert r"\frac{1}{\left(t+1\right)}" == parse_expression("1/(t+1)").latex


def test_parameters_retain_identity_and_constants_broadcast():
    expression = parse_expression("At + A*t + Omega*cos(t) + omega")
    assert expression.parameter_names == ("At", "A", "Omega", "omega")
    np.testing.assert_allclose(parse_expression("c").evaluate([1, 2], {"c": 4}), [4, 4], atol=1e-12)
    assert r"\Omega" in expression.latex and r"\omega" in expression.latex


@pytest.mark.parametrize("text", [
    "__import__('os')", "t.real", "t[0]", "lambda: 1", "[1]", "True", "1j", "sin(t, t)",
    "cos(x=t)", "sin", "_a+t", "a if t else b", "2t", "t//2", "t%2", "sum(t)", "nan",
])
def test_rejects_unsupported_syntax(text):
    # nan只是普通标识符，无法绕过有限参数检查。
    if text == "nan":
        with pytest.raises(ExpressionError):
            parse_expression(text).evaluate([0], {"nan": float("nan")})
    else:
        with pytest.raises(ExpressionError):
            parse_expression(text)


@pytest.mark.parametrize("text", ["1/0", "sqrt(-1)", "log(0)", "exp(1000)", "(-1)^0.5", "1e309"])
def test_rejects_nonfinite_real_model(text):
    with pytest.raises(ExpressionError):
        parse_expression(text).evaluate([0], {})


def test_resource_limits_and_original_error_position():
    for text in ("1+" * 600 + "1", "-" * 50 + "t", "+".join("t" for _ in range(120))):
        with pytest.raises(ExpressionError):
            parse_expression(text)
    with pytest.raises(ExpressionError) as error:
        parse_expression("t^2 + @")
    assert error.value.position == 6


def test_result_formula_does_not_infer_period_or_accept_time():
    assert evaluate_result_formula("2*pi/Omega", {"Omega": 2, "A": 3}) == pytest.approx(np.pi, abs=1e-12)
    for text in ("t", "other", "1/(Omega-Omega)"):
        with pytest.raises(ExpressionError):
            evaluate_result_formula(text, {"Omega": 2})


def test_all_supported_functions_share_finite_numeric_path():
    expression = parse_expression("sin(pi/2)+cos(0)+exp(0)+log(exp(2))+sqrt(4)+abs(-3)")
    np.testing.assert_allclose(expression.evaluate([0, 2], {}), [10, 10], atol=1e-12)
