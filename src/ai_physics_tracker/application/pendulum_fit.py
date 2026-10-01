"""冻结adopted测量并执行同一拟合core；科学产物复用已有原子存储。"""

from concurrent.futures import CancelledError
from dataclasses import asdict, dataclass
import json
from math import isfinite
from threading import Event
from typing import Callable
from uuid import UUID, uuid4

from ai_physics_tracker.application.adopted_measurement import (
    AdoptedMeasurementSnapshot, assert_adopted_measurement_current, build_adopted_measurement,
)
from ai_physics_tracker.application.pendulum_analysis import (
    analysis_input_state, analysis_video_stamp, angular_series_from_reconstruction,
    prepare_analysis_job, prepare_pendulum_reconstruction,
)
from ai_physics_tracker.application.project_session import ProjectSession, ProjectSessionError
from ai_physics_tracker.domain.pendulum_fit import FitSettings, compare_fits, fit_config, fit_pendulum
from ai_physics_tracker.domain.pendulum_ode import (
    DEFAULT_F_SCALE_RAD, M0, M1, InitialCondition, IntegrationSettings, ObjectiveRequest,
    resolve_student_initial_condition,
)
from ai_physics_tracker.domain.pendulum_reconstruction import reconstruct_pendulum, reconstruction_config
from ai_physics_tracker.domain.scientific_result import ResultColumn, ScientificResult
from ai_physics_tracker.domain.types import canonical_json_digest, utc_now
from ai_physics_tracker.infrastructure.scientific_payload import read_scientific_payload, write_scientific_payload

FIT_KIND = "pendulum-ode-fit-v1"
CORE_VERSION = "pendulum-fit-job-1.0.0"
HIGH_PRECISION = IntegrationSettings(2e-10, 2e-12)
COLUMNS = tuple(ResultColumn(name, dtype, unit) for name, dtype, unit in (
    ("frame_index", "int64", None), ("time_absolute_s", "float64", "s"),
    ("time_release_relative_s", "float64", "s"), ("theta_rad", "float64?", "rad"),
    ("is_qc_valid", "bool", None), ("qc_reasons", "string[]", None),
    ("relative_weight", "float64?", None),
    ("m0_theta_rad", "float64?", "rad"), ("m0_residual_rad", "float64?", "rad"),
    ("m1_theta_rad", "float64?", "rad"), ("m1_residual_rad", "float64?", "rad"),
))


@dataclass(frozen=True)
class FitOptions:
    end_frame_index: int
    models: tuple[str, ...] = (M0, M1)
    rest_confirmed: bool = False
    explicit_ic: InitialCondition | None = None
    integration: IntegrationSettings = HIGH_PRECISION
    maximum_samples: int = 500
    loss: str = "soft_l1"
    f_scale_rad: float = DEFAULT_F_SCALE_RAD
    m0_settings: FitSettings = FitSettings()
    m1_settings: FitSettings = FitSettings()

    def __post_init__(self) -> None:
        if type(self.end_frame_index) is not int or self.end_frame_index < 0:
            raise ValueError("fit end frame must be a nonnegative source frame")
        if self.models not in ((M0,), (M0, M1)):
            raise ValueError("choose M0 or M0 + M1 (with M0 warm start)")
        if type(self.rest_confirmed) is not bool:
            raise ValueError("rest confirmation must be explicit")
        if self.explicit_ic is not None and (
                not isinstance(self.explicit_ic, InitialCondition) or self.explicit_ic.source != "explicit"):
            raise ValueError("fit IC override must have explicit provenance")
        if not isinstance(self.integration, IntegrationSettings) or any(
                not isinstance(s, FitSettings) for s in (self.m0_settings, self.m1_settings)):
            raise ValueError("fit requires validated solver and optimizer settings")
        if type(self.maximum_samples) is not int or self.maximum_samples < 1:
            raise ValueError("fit sample limit must be a positive integer")
        if self.loss not in ("soft_l1", "linear"):
            raise ValueError("fit loss must be soft_l1 or linear")
        if type(self.f_scale_rad) not in (int, float) or not isfinite(self.f_scale_rad) or self.f_scale_rad <= 0:
            raise ValueError("fit scale must be positive finite radians")


def options_payload(options: FitOptions) -> dict:
    return json.loads(json.dumps(asdict(options), allow_nan=False))


def options_from_payload(payload: dict) -> FitOptions:
    values = dict(payload)
    values["models"] = tuple(values["models"])
    values["integration"] = IntegrationSettings(**values["integration"])
    ic = values["explicit_ic"]
    values["explicit_ic"] = None if ic is None else InitialCondition(**{
        **ic, "support_frames": tuple(ic["support_frames"])})
    for key in ("m0_settings", "m1_settings"):
        settings = dict(values[key])
        for name in ("alpha1_bounds", "alpha2_bounds", "omega2_bounds"):
            settings[name] = None if settings[name] is None else tuple(settings[name])
        if settings["starts"] is not None:
            settings["starts"] = tuple(tuple(s) for s in settings["starts"])
        values[key] = FitSettings(**settings)
    return FitOptions(**values)


def _objective(session: ProjectSession, snapshot: AdoptedMeasurementSnapshot, options: FitOptions):
    reconstructed = reconstruct_pendulum(prepare_pendulum_reconstruction(session, snapshot))
    series = angular_series_from_reconstruction(reconstructed, snapshot.payload["video"]["fps_nominal"])
    ic = resolve_student_initial_condition(series, snapshot.payload["release_frame_index"],
        rest_confirmed=options.rest_confirmed, explicit=options.explicit_ic)
    if ic is None:
        raise ProjectSessionError("needs explicit IC: confirm rest with five valid pre-release frames, or enter theta0 and omega0")
    physical = snapshot.payload["physical"]
    request = ObjectiveRequest(series, tuple(r.relative_weight for r in reconstructed.frames), ic,
        snapshot.payload["release_frame_index"], options.end_frame_index, physical["length_m"],
        physical["g_m_s2"], maximum_samples=options.maximum_samples, f_scale_rad=options.f_scale_rad,
        integration=options.integration, loss=options.loss)
    return request, reconstructed


def resolved_fit_config(request: ObjectiveRequest, options: FitOptions) -> dict:
    return {"core_version": CORE_VERSION, "reconstruction": reconstruction_config(),
        "options": options_payload(options), "resolved_ic": asdict(request.initial_condition),
        "request_source": "explicit-fit-options (ADR-0020)",
        "models": {m: fit_config(request, options.m0_settings if m == M0 else options.m1_settings)
                   for m in options.models}}


def fit_signature(snapshot: AdoptedMeasurementSnapshot, config: dict) -> str:
    return canonical_json_digest({"measurement_digest": snapshot.digest, "config": config})


@dataclass(frozen=True)
class PendulumFitJob:
    session: ProjectSession
    experiment_id: UUID
    captured_state: tuple
    options: FitOptions


@dataclass(frozen=True)
class PendulumFitResult:
    record: ScientificResult
    payload: dict
    captured_state: tuple
    verified_video_stamp: tuple


def prepare_fit_job(session: ProjectSession, experiment_id: UUID, options: FitOptions) -> PendulumFitJob:
    if not isinstance(options, FitOptions):
        raise ProjectSessionError("fit requires validated options")
    base = prepare_analysis_job(session, experiment_id, options.end_frame_index)
    return PendulumFitJob(base.session, experiment_id, base.captured_state, options)


def run_fit_job(job: PendulumFitJob, cancel: Event, *,
                progress: Callable[[str, int, int], None] | None = None) -> PendulumFitResult:
    def check_cancel():
        if cancel.is_set():
            raise CancelledError()
    check_cancel()
    snapshot = build_adopted_measurement(job.session, job.experiment_id)
    request, reconstructed = _objective(job.session, snapshot, job.options)
    config = resolved_fit_config(request, job.options)
    fits = {}
    for model in job.options.models:
        fits[model] = fit_pendulum(request, model,
            job.options.m0_settings if model == M0 else job.options.m1_settings,
            warm_start=fits.get(M0) if model == M1 else None, check_cancel=check_cancel,
            progress=None if progress is None else lambda done, total, m=model: progress(m, done, total))
    check_cancel()
    rows = []
    for row in reconstructed.frames:
        rows.append({"frame_index": row.frame_index, "time_absolute_s": row.time_absolute_s,
            "time_release_relative_s": row.time_release_relative_s, "theta_rad": row.theta_rad,
            "is_qc_valid": row.is_qc_valid, "qc_reasons": row.qc_reasons,
            "relative_weight": row.relative_weight,
            "m0_theta_rad": None, "m0_residual_rad": None, "m1_theta_rad": None, "m1_residual_rad": None})
    for model, fit in fits.items():
        if fit.trajectory is not None:
            prefix = "m0" if model == M0 else "m1"
            for j, i in enumerate(fit.trajectory.source_indices):
                rows[i][prefix+"_theta_rad"] = fit.trajectory.prediction.theta_rad[j]
                rows[i][prefix+"_residual_rad"] = fit.trajectory.residual_rad[j]
    digest = fit_signature(snapshot, config)
    payload = {"contract": FIT_KIND, "input_digest": digest, "measurement": snapshot.payload,
        "measurement_digest": snapshot.digest, "config": config, "rows": rows,
        "fits": {m: asdict(f) for m, f in fits.items()},
        "comparison": asdict(compare_fits(fits[M0], fits[M1])) if M1 in fits else None}
    stamp = analysis_video_stamp(job.session, job.experiment_id)
    assert_adopted_measurement_current(job.session, snapshot)
    if analysis_video_stamp(job.session, job.experiment_id) != stamp:
        raise ProjectSessionError("video changed during fit verification")
    check_cancel()
    statuses = {f.status for f in fits.values()}
    status = "success" if statuses == {"success"} else (
        "insufficient_data" if statuses == {"insufficient_data"} else
        "nonconverged" if statuses <= {"success", "nonconverged"} else "failed")
    result_id = uuid4()
    reference = write_scientific_payload(job.session.project_root, result_id, payload, COLUMNS)
    record = ScientificResult(result_id, job.experiment_id, FIT_KIND, utc_now(), digest, CORE_VERSION,
        status, payload=reference, extra_fields={"measurement_digest": snapshot.digest,
            "config": config, "end_frame_index": job.options.end_frame_index})
    result = PendulumFitResult(record, payload, job.captured_state, stamp)
    if cancel.is_set():
        discard_fit_result(job.session, result)
        raise CancelledError()
    return result


def discard_fit_result(session: ProjectSession, result: PendulumFitResult) -> None:
    """只清理本任务未注册且hash匹配的产物；不能删除已提交历史结果。"""
    if session.project_root is None or any(r.result_id == result.record.result_id for r in session.project.scientific_results):
        return
    reference = result.record.payload
    if reference is not None:
        try:
            read_scientific_payload(session.project_root, reference)
        except (OSError, ValueError):
            return
        (session.project_root/reference.path).unlink(missing_ok=True)


def load_fit_result(session: ProjectSession, record: ScientificResult) -> tuple[dict, bool, str | None]:
    if record.kind != FIT_KIND or record.payload is None or session.project_root is None:
        raise ProjectSessionError("fit result has no readable payload")
    payload = read_scientific_payload(session.project_root, record.payload)
    if payload.get("contract") != FIT_KIND or payload.get("input_digest") != record.input_digest:
        raise ProjectSessionError("fit payload identity does not match record")
    try:
        options = options_from_payload(payload["config"]["options"])
        snapshot = build_adopted_measurement(session, record.experiment_id)
        request, _ = _objective(session, snapshot, options)
        expected = resolved_fit_config(request, options)
        if canonical_json_digest(payload["config"]) != canonical_json_digest(expected) or (
                canonical_json_digest(record.extra_fields["config"]) != canonical_json_digest(expected)):
            raise ValueError("saved fit configuration/provenance changed — recompute")
        current = fit_signature(snapshot, expected)
    except (ProjectSessionError, ValueError, KeyError, TypeError) as error:
        return payload, False, str(error)
    valid = current == record.input_digest and record.core_version == CORE_VERSION and record.freshness == "valid"
    return payload, valid, None if valid else "fit inputs changed — recompute"
