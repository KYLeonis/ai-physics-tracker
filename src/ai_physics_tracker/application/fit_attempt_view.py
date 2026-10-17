"""应用层：从拟合尝试摘要重建当前源上的只读展示曲线。"""

from dataclasses import asdict, dataclass
import json
import math
from collections.abc import Mapping, Sequence
from uuid import UUID

import numpy as np

from ai_physics_tracker.application.project_session import ProjectSession, ProjectSessionError
from ai_physics_tracker.application.signal_analysis_job import (
    SignalSelection,
    prepare_signal_analysis,
)
from ai_physics_tracker.domain.analysis import source_fingerprint, source_snapshot
from ai_physics_tracker.domain.expression import ExpressionError, parse_expression
from ai_physics_tracker.domain.fit_interpretation import interpret_fit
from ai_physics_tracker.domain.function_fit import FitParameter, FitSpec


_RECONSTRUCTION_NOTE = (
    "Reconstructed against the current matching source; this is not a complete "
    "historical snapshot."
)


@dataclass(frozen=True)
class AttemptView:
    """一次历史拟合的只读显示结果。

    ``metadata`` 采用已保存分析结果的字段形状，因而可以交给现有的图表和
    ``explain_fit`` 展示逻辑。它只表示“当前源与历史身份匹配时”的重建结果，
    不代表重新发布了 ``DerivedData`` 或恢复了工程状态。
    """

    spec: FitSpec | None
    selection: SignalSelection | None
    metadata: dict[str, object] | None
    reason: str
    samples: tuple[tuple[int, float, float, float, int], ...] = ()
    prediction: tuple[float, ...] = ()
    residual: tuple[float, ...] = ()

    @property
    def is_available(self) -> bool:
        """返回是否成功生成了可显示的历史曲线。"""

        return self.metadata is not None


def rebuild_fit_attempt_view(
    session: ProjectSession,
    attempt: Mapping[str, object],
) -> AttemptView:
    """在当前项目源上只读重建一条已记录的拟合尝试。

    该函数只调用 ``prepare_signal_analysis`` 获取当前源样本和输入守卫，随后
    用日志中的参数直接评估表达式；它不会调用拟合器、提交结果、保存文件或
    修改会话的授权 / dirty / Undo 状态。失败、拒绝、取消和身份不匹配的记录
    返回没有曲线的 ``AttemptView``，并在 ``reason`` 中给出原因。
    """

    if not isinstance(attempt, Mapping):
        return AttemptView(None, None, None, "Fit attempt record is not a mapping")

    selection, selection_error = _selection_from_attempt(attempt)
    if selection_error:
        return AttemptView(None, selection, None, selection_error)

    spec, spec_error = _spec_from_attempt(attempt)
    if spec_error:
        return AttemptView(spec, selection, None, spec_error)
    assert selection is not None and spec is not None

    status = attempt.get("status")
    summary = attempt.get("summary")
    if status != "completed":
        return AttemptView(
            spec,
            selection,
            None,
            f"Fit attempt status is {status!r}; only a completed successful attempt can be reconstructed.",
        )
    if not isinstance(summary, Mapping):
        return AttemptView(spec, selection, None, "Completed fit attempt has no readable result summary")
    if summary.get("status") not in ("success", "given_parameters"):
        return AttemptView(
            spec,
            selection,
            None,
            f"Recorded fit summary status is {summary.get('status')!r}; no successful curve is available.",
        )

    try:
        job = prepare_signal_analysis(session, selection, spec)
    except (ProjectSessionError, TypeError, ValueError, OverflowError) as error:
        # 这里把准备守卫转成展示原因；表达式和输入的详细校验仍由现有契约完成。
        return AttemptView(
            spec,
            selection,
            None,
            f"Historical fit cannot be reconstructed from the current project: {error}",
        )

    identity_error = _check_source_identity(attempt, job)
    if identity_error:
        return AttemptView(spec, selection, None, identity_error)

    try:
        parameter_values = _parameter_values(summary, spec)
        expression = parse_expression(spec.expression)
        time_s = np.asarray([row[2] for row in job.samples], dtype=float)
        measured = np.asarray([row[3] for row in job.samples], dtype=float)
        prediction_array = expression.evaluate(time_s, parameter_values)
        with np.errstate(over="raise", invalid="raise"):
            residual_array = measured - prediction_array
        if (prediction_array.shape != time_s.shape or residual_array.shape != time_s.shape
                or not np.all(np.isfinite(prediction_array))
                or not np.all(np.isfinite(residual_array))):
            raise ValueError("Reconstructed prediction or residual is not finite")
        interpretation = interpret_fit(measured, prediction_array)
        _check_recorded_rmse(summary, interpretation.rmse)
    except (ExpressionError, FloatingPointError, OverflowError, TypeError, ValueError) as error:
        return AttemptView(
            spec,
            selection,
            None,
            f"Recorded parameters cannot reproduce a finite prediction on the current samples: {error}",
        )

    prediction = tuple(float(value) for value in prediction_array)
    residual = tuple(float(value) for value in residual_array)
    metadata = _display_metadata(job, spec, summary, prediction, residual)
    return AttemptView(
        spec,
        selection,
        metadata,
        _RECONSTRUCTION_NOTE,
        tuple(job.samples),
        prediction,
        residual,
    )


def _selection_from_attempt(
    attempt: Mapping[str, object],
) -> tuple[SignalSelection | None, str | None]:
    try:
        track_id = _uuid(attempt["track_id"], "track_id")
        quantity = attempt["quantity"]
        interval = attempt["interval"]
        smoothed = attempt["smoothed"]
        if not isinstance(quantity, str):
            raise ValueError("quantity must be text")
        if (not isinstance(interval, Sequence) or isinstance(interval, (str, bytes))
                or len(interval) != 2 or any(type(value) is not int for value in interval)):
            raise ValueError("interval must contain two integer frame indices")
        if type(smoothed) is not bool:
            raise ValueError("smoothed must be boolean")
        selection = SignalSelection(track_id, quantity, interval[0], interval[1], smoothed)
        return selection, None
    except (KeyError, TypeError, ValueError) as error:
        return None, f"Fit attempt selection is unreadable: {error}"


def _spec_from_attempt(
    attempt: Mapping[str, object],
) -> tuple[FitSpec | None, str | None]:
    raw_spec = attempt.get("spec")
    if not isinstance(raw_spec, Mapping):
        return None, "This fit attempt has no recorded FitSpec; its curve cannot be reconstructed."
    try:
        expression = raw_spec["expression"]
        raw_parameters = raw_spec["parameters"]
        max_evaluations = raw_spec.get("max_evaluations", 1000)
        if not isinstance(expression, str) or not isinstance(raw_parameters, Sequence):
            raise ValueError("spec requires an expression and parameter list")
        if type(max_evaluations) is not int:
            raise ValueError("max_evaluations must be an integer")
        parameters = []
        for raw_parameter in raw_parameters:
            if not isinstance(raw_parameter, Mapping):
                raise ValueError("each fit parameter must be an object")
            name = raw_parameter["name"]
            initial = raw_parameter.get("initial", 1.0)
            lower = raw_parameter.get("lower")
            upper = raw_parameter.get("upper")
            fixed = raw_parameter.get("fixed", False)
            if (not isinstance(name, str) or not _finite_number(initial)
                    or (lower is not None and not _finite_number(lower))
                    or (upper is not None and not _finite_number(upper))
                    or type(fixed) is not bool):
                raise ValueError("fit parameters must contain finite numeric values")
            parameters.append(FitParameter(name, float(initial),
                                            None if lower is None else float(lower),
                                            None if upper is None else float(upper), fixed))
        spec = FitSpec(expression, tuple(parameters), max_evaluations)
        formula = attempt.get("formula")
        if formula is not None and formula != spec.expression:
            raise ValueError("top-level formula differs from the recorded FitSpec")
        recorded_budget = attempt.get("max_evaluations")
        if recorded_budget is not None and recorded_budget != spec.max_evaluations:
            raise ValueError("top-level evaluation budget differs from the recorded FitSpec")
        return spec, None
    except (KeyError, TypeError, ValueError, ExpressionError) as error:
        return None, f"Recorded FitSpec is unreadable: {error}"


def _check_source_identity(attempt: Mapping[str, object], job) -> str | None:
    expected_id = str(job.source.derived_id)
    if attempt.get("source_id") != expected_id:
        return "Recorded source ID does not match the current source; no historical curve was reconstructed."
    try:
        expected_fingerprint = source_fingerprint(job.source)
    except (TypeError, ValueError, OverflowError) as error:
        return f"The current source fingerprint cannot be read: {error}"
    if attempt.get("source_fingerprint") != expected_fingerprint:
        return "Recorded source fingerprint does not match the current source; no historical curve was reconstructed."
    sample_count = attempt.get("sample_count")
    if type(sample_count) is not int or sample_count != len(job.samples):
        return "Recorded sample count does not match the current source interval; no historical curve was reconstructed."
    if attempt.get("unit") != job.source.unit:
        return "Recorded source unit does not match the current source; no historical curve was reconstructed."
    return None


def _parameter_values(summary: Mapping[str, object], spec: FitSpec) -> dict[str, float]:
    raw_values = summary.get("parameter_values")
    pairs: list[tuple[str, float]] = []
    if isinstance(raw_values, Mapping):
        items = raw_values.items()
    elif isinstance(raw_values, Sequence) and not isinstance(raw_values, (str, bytes)):
        items = raw_values
    else:
        raise ValueError("summary.parameter_values is missing or unreadable")
    for item in items:
        if isinstance(raw_values, Mapping):
            name, value = item
        else:
            if (not isinstance(item, Sequence) or isinstance(item, (str, bytes))
                    or len(item) != 2):
                raise ValueError("each parameter value must be a name/value pair")
            name, value = item[0], item[1]
        if not isinstance(name, str) or not _finite_number(value):
            raise ValueError("parameter names and values must be finite")
        pairs.append((name, float(value)))
    expected = tuple(parameter.name for parameter in spec.parameters)
    names = tuple(name for name, _ in pairs)
    if len(names) != len(set(names)) or set(names) != set(expected) or len(names) != len(expected):
        raise ValueError("summary.parameter_values must match the FitSpec parameter names exactly")
    values = dict(pairs)
    for parameter in spec.parameters:
        value = values[parameter.name]
        if parameter.fixed and not math.isclose(
                value, parameter.initial, rel_tol=1e-10, abs_tol=1e-12):
            raise ValueError(f"fixed parameter {parameter.name} differs from its recorded initial value")
        if parameter.lower is not None and value < parameter.lower:
            raise ValueError(f"parameter {parameter.name} is below its lower bound")
        if parameter.upper is not None and value > parameter.upper:
            raise ValueError(f"parameter {parameter.name} is above its upper bound")
    return values


def _check_recorded_rmse(summary: Mapping[str, object], expected: float) -> None:
    if "rmse" not in summary:
        return
    value = summary["rmse"]
    if not _finite_number(value) or not math.isclose(float(value), expected, rel_tol=1e-10, abs_tol=1e-12):
        raise ValueError("summary.rmse does not match the recorded parameters")


def _display_metadata(job, spec: FitSpec, summary: Mapping[str, object],
                      prediction: tuple[float, ...], residual: tuple[float, ...]) -> dict[str, object]:
    summary_copy = _json_copy(summary)
    parameter_values = _parameter_values(summary, spec)
    summary_copy["parameter_values"] = [
        [parameter.name, float(parameter_values[parameter.name])]
        for parameter in spec.parameters
    ]
    summary_copy["prediction"] = list(prediction)
    summary_copy["residual"] = list(residual)
    metadata = {
        "version": 1,
        "quantity": job.selection.quantity,
        "source_id": str(job.source.derived_id),
        "source_fingerprint": source_fingerprint(job.source),
        "source_snapshot": source_snapshot(job.source),
        "selection": asdict(job.selection) | {"track_id": str(job.selection.track_id)},
        "interval": [job.selection.start_frame, job.selection.end_frame],
        "samples": [
            dict(zip(("frame_index", "video_time_s", "relative_time_s", "value", "segment_index"), row))
            for row in job.samples
        ],
        "spec": asdict(spec),
        "syntax_version": 1,
        "summary": summary_copy,
        "reconstruction_note": _RECONSTRUCTION_NOTE,
    }
    return _json_copy(metadata)


def _uuid(value: object, name: str) -> UUID:
    if isinstance(value, UUID):
        return value
    if not isinstance(value, str):
        raise ValueError(f"{name} must be a UUID")
    return UUID(value)


def _finite_number(value: object) -> bool:
    return type(value) in (int, float) and math.isfinite(value)


def _json_copy(value: Mapping[str, object]) -> dict[str, object]:
    try:
        result = json.loads(json.dumps(value, ensure_ascii=False, allow_nan=False))
    except (TypeError, ValueError) as error:
        raise ValueError(f"record contains non-JSON data: {error}") from error
    if not isinstance(result, dict):
        raise ValueError("record must be a JSON object")
    return result
