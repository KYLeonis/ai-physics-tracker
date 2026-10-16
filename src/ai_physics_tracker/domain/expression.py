"""领域层：受限实数表达式；同一语义树负责计算和数学排版。"""

import ast
import math
import re
from dataclasses import dataclass, field
from typing import Mapping

import numpy as np
import numpy.typing as npt

MAX_EXPRESSION_LENGTH = 1000
MAX_EXPRESSION_NODES = 200
MAX_EXPRESSION_DEPTH = 24
MAX_PARAMETERS = 20
FUNCTIONS = {
    "sin": np.sin, "cos": np.cos, "exp": np.exp, "log": np.log,
    "sqrt": np.sqrt, "abs": np.abs,
}
_GREEK = {name: "\\" + name for name in (
    "alpha", "beta", "gamma", "delta", "theta", "omega", "phi", "Omega", "Gamma",
)}


class ExpressionError(ValueError):
    """表达式错误；position是用户原始文本内0起算的位置。"""

    def __init__(self, message: str, position: int = 0) -> None:
        super().__init__(message)
        self.position = position


@dataclass(frozen=True)
class MathExpression:
    """已校验的表达式；参数名保持原身份，t为唯一自变量。"""

    text: str
    parameter_names: tuple[str, ...]
    latex: str
    uses_time: bool
    _tree: ast.expr = field(repr=False, compare=False)

    def evaluate(
        self, time_s: npt.ArrayLike, parameters: Mapping[str, float],
    ) -> npt.NDArray[np.float64]:
        """计算实数模型；任何坏预测均拒绝，不删除对应样本。"""
        time = np.asarray(time_s, dtype=float)
        if time.ndim != 1 or not np.all(np.isfinite(time)):
            raise ExpressionError("Time must be a finite 1D array")
        if set(parameters) != set(self.parameter_names):
            raise ExpressionError("Parameter names do not match the expression")
        if not all(math.isfinite(value) for value in parameters.values()):
            raise ExpressionError("Parameters must be finite real numbers")
        try:
            with np.errstate(all="raise", under="ignore"):
                value = np.asarray(_evaluate(self._tree, time, parameters), dtype=float)
                output = np.broadcast_to(value, time.shape).copy()
        except (FloatingPointError, OverflowError, ZeroDivisionError, ValueError) as exc:
            raise ExpressionError(f"Model is outside the finite real domain: {exc}") from exc
        if not np.all(np.isfinite(output)):
            raise ExpressionError("Model produced a non-finite value")
        return output


def parse_expression(text: str) -> MathExpression:
    """解析有限数学语法；不执行Python代码，不推测隐式乘法。"""
    if not text.strip() or len(text) > MAX_EXPRESSION_LENGTH:
        raise ExpressionError(f"Expression must contain 1–{MAX_EXPRESSION_LENGTH} characters")
    if "\n" in text or "\r" in text:
        raise ExpressionError("Use a single-line expression")
    # ^与**同义；映射保留错误位置相对于原始输入，而非扩写后的文本。
    normalized, positions = "", []
    for index, char in enumerate(text):
        replacement = "**" if char == "^" else char
        normalized += replacement
        positions.extend([index] * len(replacement))
    leading = len(normalized) - len(normalized.lstrip())
    try:
        tree = ast.parse(normalized.strip(), mode="eval").body
    except (SyntaxError, RecursionError) as exc:
        offset = leading + max(0, (getattr(exc, "offset", 1) or 1) - 1)
        raise ExpressionError("Invalid expression syntax; use explicit multiplication (*)",
                              positions[min(offset, len(positions) - 1)]) from exc
    if len(list(ast.walk(tree))) > MAX_EXPRESSION_NODES:
        raise ExpressionError("Expression contains too many operations")
    names: list[str] = []

    def validate(node: ast.expr, depth: int = 0) -> None:
        offset = leading + node.col_offset
        position = positions[min(offset, len(positions) - 1)]
        if depth > MAX_EXPRESSION_DEPTH:
            raise ExpressionError("Expression nesting is too deep", position)
        if isinstance(node, ast.Constant):
            if (type(node.value) not in (int, float)
                    or abs(node.value) > np.finfo(float).max or not math.isfinite(node.value)):
                raise ExpressionError("Only finite real constants are allowed", position)
        elif isinstance(node, ast.Name):
            if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", node.id) or node.id in FUNCTIONS:
                raise ExpressionError("Invalid or reserved parameter name", position)
            if node.id not in ("t", "pi") and node.id not in names:
                names.append(node.id)
        elif isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow)):
            validate(node.left, depth + 1)
            validate(node.right, depth + 1)
        elif isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            validate(node.operand, depth + 1)
        elif (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
              and node.func.id in FUNCTIONS and len(node.args) == 1 and not node.keywords):
            validate(node.args[0], depth + 1)
        else:
            raise ExpressionError("Unsupported syntax or function", position)

    validate(tree)
    if len(names) > MAX_PARAMETERS:
        raise ExpressionError(f"At most {MAX_PARAMETERS} parameters are allowed")
    return MathExpression(text, tuple(names), _latex(tree),
                          any(isinstance(node, ast.Name) and node.id == "t" for node in ast.walk(tree)), tree)


def evaluate_result_formula(text: str, parameters: Mapping[str, float]) -> float:
    """结果换算只引用本次参数和常数，不允许t或其他换算结果。"""
    expression = parse_expression(text)
    if expression.uses_time or not set(expression.parameter_names) <= parameters.keys():
        raise ExpressionError("Result formula may only reference fitted parameters and constants")
    selected = {name: parameters[name] for name in expression.parameter_names}
    return float(expression.evaluate([0.0], selected)[0])


def _evaluate(node: ast.expr, time: np.ndarray, parameters: Mapping[str, float]):
    if isinstance(node, ast.Constant):
        return np.float64(node.value)
    if isinstance(node, ast.Name):
        return time if node.id == "t" else np.float64(math.pi if node.id == "pi" else parameters[node.id])
    if isinstance(node, ast.Call):
        return FUNCTIONS[node.func.id](_evaluate(node.args[0], time, parameters))
    if isinstance(node, ast.UnaryOp):
        value = _evaluate(node.operand, time, parameters)
        return -value if isinstance(node.op, ast.USub) else value
    left, right = _evaluate(node.left, time, parameters), _evaluate(node.right, time, parameters)
    operation = {ast.Add: np.add, ast.Sub: np.subtract, ast.Mult: np.multiply,
                 ast.Div: np.divide, ast.Pow: np.power}[type(node.op)]
    return operation(left, right)


def _latex(node: ast.expr) -> str:
    if isinstance(node, ast.Constant):
        text = str(node.value)
        if "e" in text.lower():
            base, exponent = text.lower().split("e")
            return base + r"\times 10^{" + str(int(exponent)) + "}"
        return text
    if isinstance(node, ast.Name):
        if node.id == "pi":
            return r"\pi"
        if node.id in _GREEK:
            return _GREEK[node.id]
        if len(node.id) == 1:
            return node.id
        return r"\mathrm{" + node.id.replace("_", r"\_") + "}"
    if isinstance(node, ast.Call):
        content = _latex(node.args[0])
        name = node.func.id
        if name == "sqrt":
            return r"\sqrt{" + content + "}"
        if name == "abs":
            return r"\left|" + content + r"\right|"
        return "\\" + name + r"\left(" + content + r"\right)"
    if isinstance(node, ast.UnaryOp):
        return ("-" if isinstance(node.op, ast.USub) else "+") + r"\left(" + _latex(node.operand) + r"\right)"
    left, right = _latex(node.left), _latex(node.right)
    if isinstance(node.op, ast.Div):
        return r"\frac{" + left + "}{" + right + "}"
    if isinstance(node.op, ast.Pow):
        return r"\left(" + left + r"\right)^{" + right + "}"
    symbol = {ast.Add: "+", ast.Sub: "-", ast.Mult: r"\cdot "}[type(node.op)]
    return r"\left(" + left + symbol + right + r"\right)"
