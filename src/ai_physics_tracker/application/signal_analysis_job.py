"""应用层：单量分析的源快照、后台计算和双版本栅栏提交（ADR-0021）。"""

from concurrent.futures import CancelledError
from copy import deepcopy
from dataclasses import asdict, dataclass
import json
import math
from threading import Event
from uuid import UUID, uuid4

import numpy as np
import scipy

from ai_physics_tracker.application.chart_recipe import (
    calibration_recipe_reject_reason, reference_reject_reason, smoothing_readable_reject_reason,
    smoothing_recipe, timing_identity, unreadable_step_reason, prepare_derived_rows,
    pipeline_step_names, reference_recipe,
)
from ai_physics_tracker.application.kinematics_job import AnalysisInputs, analysis_inputs, derived_result_ids
from ai_physics_tracker.application.kinematics_job import SmoothingParameters, prepare_kinematics_job, KinematicsJob
from ai_physics_tracker.application.angular_job import AngularJob, AngularSpec, prepare_angular_job
from ai_physics_tracker.application.project_session import ProjectSession, ProjectSessionError
from ai_physics_tracker.domain.analysis import QUANTITIES, source_fingerprint, source_snapshot
from ai_physics_tracker.domain.angular import AngularReference, PendulumReference, TwoPointReference
from ai_physics_tracker.domain.calibration import Calibration
from ai_physics_tracker.domain.derived import ANGULAR_KINDS, KINEMATICS_KINDS, DerivedData, DerivedInput
from ai_physics_tracker.domain.expression import ExpressionError, evaluate_result_formula, parse_expression
from ai_physics_tracker.domain.function_fit import FitOutcome, FitSpec, fit_function
from ai_physics_tracker.domain.kinematics import derive_unit
from ai_physics_tracker.domain.recurrence import RecurrenceSpec, measure_recurrence
from ai_physics_tracker.domain.timeline import frame_to_time
from ai_physics_tracker.domain.types import utc_now


def signal_source(quantity: str, smoothed: bool = False) -> tuple[str, int]:
    """单量→明确源kind及列；速度 / 加速度始终披露其SG导数配方。"""
    if quantity not in QUANTITIES:
        raise ValueError("Unsupported analysis quantity")
    if quantity in ("theta", "omega", "alpha"):
        return ({"theta": "smoothed_angular_position" if smoothed else "angular_position",
                 "omega": "angular_velocity", "alpha": "angular_acceleration"}[quantity], 0)
    kind = ("smoothed_position" if smoothed else "world_position") if quantity in ("x", "y") else (
        "velocity" if quantity in ("vx", "vy") else "acceleration")
    return kind, 0 if quantity in ("x", "vx", "ax") else 1


@dataclass(frozen=True)
class SignalSelection:
    track_id: UUID
    quantity: str
    start_frame: int
    end_frame: int
    smoothed: bool = False

    def __post_init__(self) -> None:
        signal_source(self.quantity, self.smoothed)
        if (type(self.start_frame) is not int or type(self.end_frame) is not int
                or not 0 <= self.start_frame <= self.end_frame):
            raise ValueError("Select an ordered source-frame interval")


@dataclass(frozen=True)
class SignalAnalysisJob:
    """数据完全脱离活动会话；源版本与将被替换的目标版本独立捕获。"""

    inputs: AnalysisInputs
    source: DerivedData
    selection: SignalSelection
    samples: tuple[tuple[int, float, float, float, int], ...]
    spec: FitSpec | RecurrenceSpec
    previous_derived_ids: tuple[UUID, ...]
    result_formulas: tuple[tuple[str, str], ...] = ()

    @property
    def kind(self) -> str:
        family = "function_fit" if isinstance(self.spec, FitSpec) else "signal_recurrence"
        return f"{family}_{self.selection.quantity}"


@dataclass(frozen=True)
class SignalAnalysisResult:
    job: SignalAnalysisJob
    record: DerivedData | None
    fit_outcome: FitOutcome | None = None


def _recorded_source_settings(records: list[DerivedData]) -> tuple[SmoothingParameters, AngularReference | None]:
    """拟合独立选轨迹时沿用该轨迹配方，不借用另一轨迹的控件。"""
    parameters = SmoothingParameters()
    reference = None
    for record in records:
        recipe = smoothing_recipe(record)
        if recipe is not None:
            parameters = SmoothingParameters(recipe["window_length"], recipe["polyorder"])
            break
    for record in records:
        recipe = reference_recipe(record)
        if recipe is None:
            continue
        try:
            if recipe.get("mode") == "pendulum":
                reference = PendulumReference(tuple(recipe["pivot_px"]))
            elif recipe.get("mode") == "two_point":
                reference = TwoPointReference(UUID(str(recipe["reference_track_id"])))
            else:
                raise ValueError("Unsupported recorded reference")
        except (KeyError, TypeError, ValueError) as error:
            raise ProjectSessionError("Recorded angular reference is unreadable; confirm the intended reference first") from error
        break
    return parameters, reference


def prepare_signal_source(
    session: ProjectSession, selection: SignalSelection, parameters: SmoothingParameters | None,
    reference: AngularReference | None = None,
) -> KinematicsJob | AngularJob | None:
    """只准备当前量；parameters为None时沿用本轨迹记录，未知或重复源不覆盖。"""
    track = next((item for item in session.tracks if item.track_id == selection.track_id), None)
    if track is None:
        raise ProjectSessionError("Select an existing track")
    inputs = analysis_inputs(session, track.video_id, (track.track_id,))
    if not inputs.timeline.working_zone[0] <= selection.start_frame <= selection.end_frame <= inputs.timeline.working_zone[1]:
        raise ProjectSessionError("Analysis interval must be inside the working zone")
    kind, _ = signal_source(selection.quantity, selection.smoothed)
    supported_steps = {"calibration_transform", "angular_reference", "angular_unwrap", "savitzky_golay"}
    sources = [item for item in session.project.derived if item.track_id == track.track_id and item.kind == kind]
    if len(sources) > 1:
        raise ProjectSessionError("Source is ambiguous; inspect the duplicate results before recomputing")
    angular = kind in ANGULAR_KINDS
    if angular and parameters is not None and (inputs.calibration is None or reference is None):
        raise ProjectSessionError("Angular source needs a calibration and an applied reference. Use Set calibration / reference below.")
    if sources:
        source = sources[0]
        names = pipeline_step_names(source)
        if unreadable_step_reason(source) or any(name not in supported_steps for name in names):
            raise ProjectSessionError("Source has an unsupported recipe; automatic replacement is unavailable")
        identity = timing_identity(source)
        fresh = (source.status == "valid" and source.calibration_ref == (
            inputs.calibration.calibration_id if inputs.calibration else None) and identity is not None
            and abs(identity.fps_nominal - inputs.timeline.fps_nominal) <= 1e-9
            and identity.working_zone == inputs.timeline.working_zone and identity.approximation == inputs.timing_detail)
        if fresh:
            _validate_source(source, inputs)
            if parameters is None:
                return None
            smoothing = smoothing_recipe(source)
            same_smoothing = smoothing is None or (
                smoothing["window_length"] == parameters.window_length and smoothing["polyorder"] == parameters.polyorder)
            expected_reference = ({"mode": "pendulum", "pivot_px": list(reference.pivot_px)}
                                  if isinstance(reference, PendulumReference) else
                                  {"mode": "two_point", "reference_track_id": str(reference.reference_track_id)}
                                  if reference is not None else None)
            if same_smoothing and (not angular or reference_recipe(source) == expected_reference):
                return None
    kinds = ANGULAR_KINDS if angular else KINEMATICS_KINDS
    group = [item for item in session.project.derived if item.track_id == track.track_id and item.kind in kinds]
    if len({item.kind for item in group}) != len(group) or any(
            unreadable_step_reason(item) or any(name not in supported_steps
                for name in pipeline_step_names(item)) for item in group):
        raise ProjectSessionError("Source group has duplicate or unsupported recipes; inspect it before recomputing")
    for item in group:
        identity = timing_identity(item)
        if "timing_context" in item.extra_fields and identity is None:
            raise ProjectSessionError("Source has an unreadable timing recipe; inspect it before recomputing")
        calibration = next((value for value in session.calibrations if value.calibration_id == item.calibration_ref), None)
        _validate_source_recipe(item, identity.fps_nominal if identity else None, calibration)
    if parameters is None:
        parameters, reference = _recorded_source_settings(sources + [item for item in group if item.kind != kind])
    if angular:
        if inputs.calibration is None or reference is None:
            raise ProjectSessionError("Angular source needs a calibration and an applied reference. Use Set calibration / reference below.")
        return prepare_angular_job(session, track.video_id, (AngularSpec(track.track_id, reference),), parameters)
    return prepare_kinematics_job(session, track.video_id, (track.track_id,), parameters)


def prepare_signal_analysis(
    session: ProjectSession, selection: SignalSelection, spec: FitSpec | RecurrenceSpec,
    result_formulas: tuple[tuple[str, str], ...] = (),
) -> SignalAnalysisJob:
    """只选择新鲜且配方可读的源；不接收本期分析结果作为输入。"""
    track = next((item for item in session.tracks if item.track_id == selection.track_id), None)
    if track is None:
        raise ProjectSessionError("Select an existing track")
    kind, component = signal_source(selection.quantity, selection.smoothed)
    sources = [item for item in session.project.derived if item.track_id == track.track_id and item.kind == kind]
    if len(sources) != 1:
        raise ProjectSessionError(f"Recompute {kind}: exactly one source result is required")
    source = deepcopy(sources[0])
    track_ids = (track.track_id,) + ((source.input.reference_track_id,) if source.input.reference_track_id else ())
    inputs = deepcopy(analysis_inputs(session, track.video_id, track_ids))
    _validate_source(source, inputs)
    start, end = selection.start_frame, selection.end_frame
    if not inputs.timeline.working_zone[0] <= start <= end <= inputs.timeline.working_zone[1]:
        raise ProjectSessionError("Analysis interval must be inside the working zone")
    messages: list[str] = []
    rows = prepare_derived_rows(source, track, inputs.timeline, messages,
                                expected_width=1 if kind in ANGULAR_KINDS else 2)
    if rows is None:
        raise ProjectSessionError("; ".join(messages))
    samples = []
    segment = 0
    previous = None
    for frame, row in zip(*rows):
        if not start <= frame <= end:
            continue
        if previous is not None and frame != previous + 1:
            segment += 1
        absolute = frame_to_time(frame, inputs.timeline)
        samples.append((frame, absolute, absolute - frame_to_time(start, inputs.timeline), row[component], segment))
        previous = frame
    if not samples:
        raise ProjectSessionError("No valid source samples in this interval")
    if isinstance(spec, RecurrenceSpec) and spec.wrapped_angle != (kind == "angular_position"):
        raise ProjectSessionError("Wrapped-angle crossing setting must match the selected source")
    family = "function_fit" if isinstance(spec, FitSpec) else "signal_recurrence"
    target = f"{family}_{selection.quantity}"
    old = [item for item in session.project.derived if item.track_id == track.track_id and item.kind == target]
    if len(old) > 1 or (old and _analysis_metadata(old[0]) is None):
        raise ProjectSessionError("Target result is ambiguous or has an unsupported version; it is read-only")
    names = [name for name, _ in result_formulas]
    if any(not name.strip() for name in names) or len(set(names)) != len(names):
        raise ProjectSessionError("Result names must be nonblank and distinct")
    if result_formulas and not isinstance(spec, FitSpec):
        raise ProjectSessionError("Result formulas belong to function fitting")
    return SignalAnalysisJob(inputs, source, selection, tuple(samples), spec,
                             derived_result_ids(session, {(track.track_id, target)}), tuple(result_formulas))


def _validate_source(source: DerivedData, inputs: AnalysisInputs) -> None:
    identity = timing_identity(source)
    calibration_id = inputs.calibration.calibration_id if inputs.calibration else None
    if (source.status != "valid" or source.calibration_ref != calibration_id or identity is None
            or abs(identity.fps_nominal - inputs.timeline.fps_nominal) > 1e-9
            or identity.working_zone != inputs.timeline.working_zone or identity.approximation != inputs.timing_detail):
        raise ProjectSessionError("Source is stale or its calibration / timing differs; recompute source first")
    _validate_source_recipe(source, identity.fps_nominal, inputs.calibration)


def _validate_source_recipe(source: DerivedData, fps_nominal: float | None, calibration: Calibration | None) -> None:
    """按记录自己的配方核对结构；过期不意味着可覆盖未知或损坏的数据。"""
    checks = [unreadable_step_reason, calibration_recipe_reject_reason, smoothing_readable_reject_reason]
    if source.kind in ANGULAR_KINDS:
        checks.append(reference_reject_reason)
    reasons = [check(source) for check in checks]
    if any(reason is not None for reason in reasons):
        raise ProjectSessionError("Source recipe unreadable: " + "; ".join(reason for reason in reasons if reason))
    names = [step["step"] for step in source.pipeline]
    angular = source.kind in ANGULAR_KINDS
    raw = source.kind in ("world_position", "angular_position")
    width = 1 if angular else 2
    if (any(type(frame) is not int or frame < 0 for frame in source.frames)
            or source.frames != tuple(sorted(set(source.frames))) or source.values is None
            or any(not isinstance(row, (tuple, list)) or len(row) != width
                   or any(not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value)
                          for value in row) for row in source.values)):
        raise ProjectSessionError("Source samples do not match the declared quantity")
    expected_steps = (["calibration_transform"] if source.calibration_ref else [])
    if angular:
        if source.calibration_ref is None:
            raise ProjectSessionError("Angular source requires a recorded calibration")
        expected_steps += ["angular_reference"] + ([] if raw else ["angular_unwrap"])
    if not raw:
        expected_steps.append("savitzky_golay")
    if names != expected_steps:
        raise ProjectSessionError("Source processing steps do not match its declared kind")
    derivative_order = 1 if source.kind in ("velocity", "angular_velocity") else 2 if source.kind in ("acceleration", "angular_acceleration") else 0
    base_units = (("rad",) if angular else (calibration.unit,) if calibration else
                  ("m", "cm", "mm") if source.calibration_ref else ("px",))
    if source.unit not in {derive_unit(base, derivative_order) for base in base_units}:
        raise ProjectSessionError("Source unit does not match its quantity / calibration")
    smoothing = smoothing_recipe(source)
    if derivative_order and (smoothing is None or (fps_nominal is not None and abs(smoothing["delta"] - 1/fps_nominal) > 1e-12)):
        raise ProjectSessionError("Source derivative timing does not match its recorded timeline")
    if source.kind in ("smoothed_position", "velocity", "acceleration") and smoothing_recipe(source) is None:
        raise ProjectSessionError("Source requires a readable smoothing recipe")
    if (source.input.source_filter is not None or source.input.include_superseded
            or source.input.extra_fields.get("observation_selection") != "effective"):
        raise ProjectSessionError("Source observation selection is unsupported; recompute source first")


def run_signal_analysis(job: SignalAnalysisJob, cancel: Event) -> SignalAnalysisResult:
    """后台纯计算；失败 / 取消不产生可覆盖旧成功结果的记录。"""
    if cancel.is_set():
        raise CancelledError()
    samples = np.asarray(job.samples, dtype=float)
    outcome = None
    if isinstance(job.spec, FitSpec):
        outcome = fit_function(samples[:, 2], samples[:, 3], job.spec, cancel.is_set)
        if outcome.status == "cancelled":
            raise CancelledError()
        if not outcome.is_publishable:
            return SignalAnalysisResult(job, None, outcome)
        summary = asdict(outcome)
        values = tuple(zip(outcome.prediction, outcome.residual))
        conversions = []
        for name, formula in job.result_formulas:
            try:
                value = evaluate_result_formula(formula, dict(outcome.parameter_values))
                conversions.append({"name": name, "formula": formula, "value": value, "error": None})
            except ExpressionError as exc:
                conversions.append({"name": name, "formula": formula, "value": None, "error": str(exc)})
        summary["result_formulas"] = conversions
    else:
        recurrence = measure_recurrence(samples[:, 0].astype(int), samples[:, 1], samples[:, 3], job.spec, cancel.is_set)
        summary = asdict(recurrence)
        values = tuple((float(value),) for value in samples[:, 3])
    if cancel.is_set():
        raise CancelledError()
    metadata = {
        "version": 1, "quantity": job.selection.quantity,
        "source_id": str(job.source.derived_id), "source_fingerprint": source_fingerprint(job.source),
        "source_snapshot": source_snapshot(job.source), "selection": asdict(job.selection) | {"track_id": str(job.selection.track_id)},
        "interval": [job.selection.start_frame, job.selection.end_frame],
        "samples": [dict(zip(("frame_index", "video_time_s", "relative_time_s", "value", "segment_index"), row)) for row in job.samples],
        "spec": asdict(job.spec), "syntax_version": 1, "scipy_version": scipy.__version__, "summary": summary,
    }
    # JSON边界提前验证，未知扩展中的非有限数也不能等到保存时才失败。
    metadata = json.loads(json.dumps(metadata, allow_nan=False))
    record = DerivedData(uuid4(), job.selection.track_id, job.kind,
                         DerivedInput(job.selection.track_id),
                         ({"step": "explicit_function_fit" if outcome else "same_direction_crossing", "params": metadata["spec"]},),
                         tuple(row[0] for row in job.samples), values, None, job.source.unit,
                         "ai-physics-tracker/p6.3", utc_now(), "valid", job.source.calibration_ref,
                         {"analysis": metadata})
    return SignalAnalysisResult(job, record, outcome)


def _analysis_metadata(record: DerivedData) -> dict | None:
    value = record.extra_fields.get("analysis")
    return value if isinstance(value, dict) and value.get("version") == 1 else None


def validated_analysis(session: ProjectSession, result: SignalAnalysisResult) -> tuple[DerivedData, ...]:
    """源内容和目标ID分别核对；失败原样保留活动会话。"""
    job, record = result.job, result.record
    if record is None or (result.fit_outcome is not None and not result.fit_outcome.is_publishable):
        raise ProjectSessionError("Analysis did not produce a publishable result")
    current = prepare_signal_analysis(session, job.selection, job.spec, job.result_formulas)
    if current != job:
        raise ProjectSessionError("Analysis source or target version changed; late result discarded")
    metadata = _analysis_metadata(record)
    if (record.kind != job.kind or record.track_id != job.selection.track_id or record.status != "valid"
            or record.input != DerivedInput(job.selection.track_id) or record.calibration_ref != job.source.calibration_ref
            or record.unit != job.source.unit or metadata is None
            or metadata.get("source_snapshot") != source_snapshot(job.source)
            or metadata.get("source_id") != str(job.source.derived_id)
            or metadata.get("quantity") != job.selection.quantity
            or metadata.get("source_fingerprint") != source_fingerprint(job.source)
            or metadata.get("spec") != json.loads(json.dumps(asdict(job.spec)))
            or metadata.get("interval") != [job.selection.start_frame, job.selection.end_frame]
            or record.frames != tuple(row[0] for row in job.samples)):
        raise ProjectSessionError("Analysis record does not match the requested source and recipe")
    expected_samples = [dict(zip(("frame_index", "video_time_s", "relative_time_s", "value", "segment_index"), row)) for row in job.samples]
    if metadata.get("samples") != expected_samples:
        raise ProjectSessionError("Analysis sample snapshot does not match its inputs")
    expected_width = 2 if isinstance(job.spec, FitSpec) else 1
    if record.values is None or any(len(row) != expected_width or not all(math.isfinite(v) for v in row) for row in record.values):
        raise ProjectSessionError("Analysis values are malformed")
    if isinstance(job.spec, FitSpec):
        outcome = result.fit_outcome
        if (outcome is None or record.values != tuple(zip(outcome.prediction, outcome.residual))
                or len(outcome.prediction) != len(job.samples)):
            raise ProjectSessionError("Fit values differ from the solver outcome")
        parameters = dict(outcome.parameter_values)
        try:
            for parameter in job.spec.parameters:
                value = parameters[parameter.name]
                if ((parameter.fixed and value != parameter.initial)
                        or (parameter.lower is not None and value < parameter.lower)
                        or (parameter.upper is not None and value > parameter.upper)):
                    raise ValueError("Parameter solution violates its constraints")
            predicted = parse_expression(job.spec.expression).evaluate(
                [row[2] for row in job.samples], parameters)
            measured = np.array([row[3] for row in job.samples])
            if (not np.allclose(predicted, outcome.prediction, rtol=1e-10, atol=1e-12)
                    or not np.allclose(measured-predicted, outcome.residual, rtol=1e-10, atol=1e-12)):
                raise ValueError("Prediction or residual does not match the declared model")
            summary = metadata.get("summary")
            expected = json.loads(json.dumps(asdict(outcome)))
            if not isinstance(summary, dict) or any(summary.get(key) != value for key, value in expected.items()):
                raise ValueError("Fit summary does not match the solver outcome")
        except (KeyError, ValueError) as error:
            raise ProjectSessionError(str(error)) from error
    else:
        samples = np.asarray(job.samples)
        expected = measure_recurrence(samples[:, 0].astype(int), samples[:, 1], samples[:, 3], job.spec)
        if (record.values != tuple((row[3],) for row in job.samples)
                or metadata.get("summary") != json.loads(json.dumps(asdict(expected)))):
            raise ProjectSessionError("Crossing events do not match the selected signal and settings")
    kept = tuple(item for item in session.project.derived if (item.track_id, item.kind) != (record.track_id, record.kind))
    previous = session.derived_data(record.track_id, record.kind)
    extras = deepcopy(previous.extra_fields) if previous else {}
    old_metadata = _analysis_metadata(previous) if previous else None
    if old_metadata:
        owned = {"version", "quantity", "source_id", "source_fingerprint", "source_snapshot", "selection", "interval", "samples", "spec", "syntax_version", "scipy_version", "summary"}
        metadata = {key: deepcopy(value) for key, value in old_metadata.items() if key not in owned} | metadata
        summary_owned = {"status", "message", "parameter_values", "prediction", "residual", "rmse", "evaluations", "solver_status", "result_formulas"} if isinstance(job.spec, FitSpec) else {
            "events", "intervals_s", "mean_interval_s", "sample_std_s", "measurement_status", "message"}
        old_summary = old_metadata.get("summary")
        if isinstance(old_summary, dict):
            metadata["summary"] = {key: deepcopy(value) for key, value in old_summary.items() if key not in summary_owned} | metadata["summary"]
    from dataclasses import replace
    extras.update(record.extra_fields)
    extras["analysis"] = metadata
    input_extras = deepcopy(previous.input.extra_fields) if previous else {}
    input_extras.update(record.input.extra_fields)
    return kept + (replace(record, extra_fields=extras, input=replace(record.input, extra_fields=input_extras)),)
