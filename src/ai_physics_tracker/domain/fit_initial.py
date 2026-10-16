"""领域层：识别有限示例结构并给出可检查的数值初值，不判定物理模型。"""

import ast
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from ai_physics_tracker.domain.expression import MathExpression, parse_expression
from ai_physics_tracker.domain.function_fit import FitSpec

MIN_OSCILLATION_SAMPLES = 24
MIN_VISIBLE_CYCLES = 2.0
CONSTANT_RTOL = 64 * np.finfo(float).eps


@dataclass(frozen=True)
class InitialEstimate:
    """空values表示无法可靠估算；reason始终可向用户解释。"""

    family: str
    values: tuple[tuple[str, float], ...]
    reason: str


def _sum_terms(node: ast.expr, sign: int = 1) -> list[tuple[int, ast.expr]]:
    if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub)):
        return _sum_terms(node.left, sign) + _sum_terms(node.right, sign if isinstance(node.op, ast.Add) else -sign)
    if isinstance(node, ast.UnaryOp):
        return _sum_terms(node.operand, -sign if isinstance(node.op, ast.USub) else sign)
    return [(sign, node)]


def _factors(node: ast.expr) -> list[ast.expr]:
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mult):
        return _factors(node.left) + _factors(node.right)
    return [node]


def _name(node: ast.expr) -> str | None:
    return node.id if isinstance(node, ast.Name) and node.id not in ("t", "pi") else None


def _time_parameter(node: ast.expr) -> str | None:
    factors = _factors(node)
    names = [_name(item) for item in factors if not (isinstance(item, ast.Name) and item.id == "t")]
    return names[0] if len(factors) == 2 and len(names) == 1 else None


def _roles(expression: MathExpression) -> tuple[str, dict[str, str | tuple[int, int]]]:
    terms = _sum_terms(expression._tree)
    polynomial = {}
    for sign, term in terms:
        factors = _factors(term)
        names = [_name(item) for item in factors if _name(item)]
        powers = [1 if isinstance(item, ast.Name) and item.id == "t" else
                  2 if isinstance(item, ast.BinOp) and isinstance(item.op, ast.Pow)
                  and isinstance(item.left, ast.Name) and item.left.id == "t"
                  and isinstance(item.right, ast.Constant) and item.right.value == 2 else None
                  for item in factors if not _name(item)]
        if len(names) != 1 or any(power is None for power in powers):
            break
        degree = sum(powers)
        if degree > 2 or names[0] in polynomial or any(value[0] == degree for value in polynomial.values()):
            break
        polynomial[names[0]] = (degree, sign)
    else:
        degrees = sorted(value[0] for value in polynomial.values())
        if degrees in ([0], [0, 1], [0, 1, 2]):
            return ("constant", "linear", "quadratic")[len(degrees)-1], polynomial
    if len(terms) != 2 or any(sign != 1 for sign, _term in terms):
        return "unsupported", {}
    offset = next((_name(term) for _sign, term in terms if _name(term)), None)
    wave = next((term for _sign, term in terms if _name(term) is None), None)
    if offset is None or wave is None:
        return "unsupported", {}
    factors = _factors(wave)
    amplitude = next((_name(item) for item in factors if _name(item)), None)
    cosine = [item for item in factors if isinstance(item, ast.Call) and item.func.id == "cos"]
    decay = [item for item in factors if isinstance(item, ast.Call) and item.func.id == "exp"]
    if amplitude is None or len(cosine) != 1 or len(decay) > 1 or len(factors) != 2 + len(decay):
        return "unsupported", {}
    angle = _sum_terms(cosine[0].args[0])
    if len(angle) != 2 or any(sign != 1 for sign, _term in angle):
        return "unsupported", {}
    frequency = next((_time_parameter(term) for _sign, term in angle if _time_parameter(term)), None)
    phase = next((_name(term) for _sign, term in angle if _name(term)), None)
    if not frequency or not phase:
        return "unsupported", {}
    roles = {"offset": offset, "amplitude": amplitude, "frequency": frequency, "phase": phase}
    if decay:
        exponent = decay[0].args[0]
        sign = 1
        if isinstance(exponent, ast.UnaryOp) and isinstance(exponent.op, ast.USub):
            sign, exponent = -1, exponent.operand
        factors = _factors(exponent)
        unsigned = []
        for factor in factors:
            if isinstance(factor, ast.UnaryOp) and isinstance(factor.op, ast.USub):
                sign *= -1
                factor = factor.operand
            unsigned.append(factor)
        if len(unsigned) != 2 or sign != -1:
            return "unsupported", {}
        beta = _time_parameter(ast.BinOp(left=unsigned[0], op=ast.Mult(), right=unsigned[1]))
        if not beta:
            return "unsupported", {}
        roles["decay"] = beta
    if len(set(roles.values())) != len(roles) or set(roles.values()) != set(expression.parameter_names):
        return "unsupported", {}
    return "damped oscillation" if decay else "oscillation", roles


def estimate_initial(
    time_s: npt.ArrayLike, values: npt.ArrayLike, expression: str, *,
    segment_indices: npt.ArrayLike | None = None, wrapped: bool = False,
) -> InitialEstimate:
    """ADR-0022：多项式回归或单段频谱/正余弦投影；不给未知结构编初值。"""
    parsed = parse_expression(expression)
    family, roles = _roles(parsed)
    manual = lambda reason: InitialEstimate(family, (), reason + " Enter initial values manually.")
    if not roles:
        return manual("This custom structure has no supported estimator.")
    time, signal = np.asarray(time_s, dtype=float), np.asarray(values, dtype=float)
    if (time.ndim != 1 or signal.shape != time.shape or not len(time)
            or not np.all(np.isfinite(time)) or not np.all(np.isfinite(signal))):
        return manual("Estimation needs matching finite samples.")
    if len(time) > 1 and np.any(np.diff(time) <= 0):
        return manual("Estimation needs increasing sample times.")
    scale = float(np.max(np.abs(signal)))
    signal_scale = scale or 1.0
    scaled = signal / signal_scale
    if family in ("constant", "linear", "quadratic"):
        degree = len(roles)-1
        if len(time) <= degree or (degree and time[-1] <= time[0]):
            return manual("Too few distinct samples for this polynomial.")
        # Polynomial.fit先缩放时间，convert将系数转回所选区间的相对t。
        polynomial = np.polynomial.Polynomial.fit(time, scaled, degree).convert() if degree else None
        coefficients = polynomial.coef if polynomial else [float(np.mean(scaled))]
        estimates = {name: coefficients[power] * sign * signal_scale for name, (power, sign) in roles.items()}
    else:
        if (len(time) < MIN_OSCILLATION_SAMPLES or (segment_indices is not None
                and len(set(np.asarray(segment_indices))) != 1)):
            return manual("Oscillation estimation needs at least 24 samples in one continuous segment.")
        if np.ptp(scaled) <= CONSTANT_RTOL:
            return manual("The source is constant or too close to constant.")
        if wrapped and np.any(np.abs(np.diff(signal)) > np.pi):
            return manual("Wrapped-angle jumps cannot seed a smooth oscillation.")
        step = np.diff(time)
        if not np.allclose(step, np.median(step), rtol=0.01, atol=0.0):
            return manual("Oscillation estimation needs approximately uniform sampling.")
        centered = scaled - np.mean(scaled)
        # Hann抑制端点泄漏；零填充细化峰值网格，不增加原信号的信息。
        size = 2 ** int(np.ceil(np.log2(len(time) * 8)))
        spectrum = np.abs(np.fft.rfft(centered * np.hanning(len(time)), n=size))
        spectrum[0] = 0
        frequency = np.fft.rfftfreq(size, d=float(np.median(step)))[int(np.argmax(spectrum))]
        if frequency * (time[-1]-time[0]) < MIN_VISIBLE_CYCLES:
            return manual("Fewer than two observable cycles; frequency is unreliable.")
        omega = 2 * np.pi * frequency
        decay = 0.0
        if "decay" in roles:
            centers, amplitudes = [], []
            for indices in np.array_split(np.arange(len(time)), 4):
                local = time[indices]
                design = np.column_stack((np.ones(len(local)), np.cos(omega*local), np.sin(omega*local)))
                coef = np.linalg.lstsq(design, scaled[indices], rcond=None)[0]
                amplitudes.append(np.hypot(coef[1], coef[2]))
                centers.append(np.mean(local))
            if min(amplitudes) > CONSTANT_RTOL:
                decay = max(0.0, -float(np.polyfit(centers, np.log(amplitudes), 1)[0]))
        envelope = np.exp(-decay*time)
        design = np.column_stack((np.ones(len(time)), envelope*np.cos(omega*time), envelope*np.sin(omega*time)))
        coef = np.linalg.lstsq(design, scaled, rcond=None)[0]
        estimates = {roles["offset"]: coef[0]*signal_scale,
                     roles["amplitude"]: np.hypot(coef[1], coef[2])*signal_scale,
                     roles["frequency"]: omega, roles["phase"]: np.arctan2(-coef[2], coef[1])}
        if "decay" in roles:
            estimates[roles["decay"]] = decay
    if not all(np.isfinite(value) for value in estimates.values()):
        return manual("Estimated parameters exceed the finite numerical range.")
    return InitialEstimate(family, tuple((name, float(estimates[name])) for name in parsed.parameter_names),
                           "Estimated from data; inspect and edit before Fit. Frequency is an initial guess, not a physical period.")


def adopt_estimate(spec: FitSpec, estimate: InitialEstimate) -> FitSpec:
    """整批采用建议，保留Fixed及边界；任何越界均拒绝以免部分覆盖。"""
    from dataclasses import replace
    if not estimate.values:
        raise ValueError(estimate.reason)
    values = dict(estimate.values)
    if set(values) != {parameter.name for parameter in spec.parameters}:
        raise ValueError("Estimate does not match the current parameters")
    parameters = tuple(parameter if parameter.fixed else replace(parameter, initial=values[parameter.name])
                       for parameter in spec.parameters)
    return replace(spec, parameters=parameters)
