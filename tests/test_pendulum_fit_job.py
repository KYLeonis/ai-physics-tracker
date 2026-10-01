"""P3.3真实应用链：tip-only、固定IC、取消/代际与immutable保存。"""

from concurrent.futures import CancelledError
from dataclasses import replace
from math import cos, sin
from threading import Event

import pytest

from ai_physics_tracker.application.pendulum_fit import (
    FitOptions, HIGH_PRECISION, discard_fit_result, load_fit_result, prepare_fit_job, run_fit_job, validated_fit_inputs,
)
from ai_physics_tracker.application.project_session import ProjectSession, ProjectSessionError
from ai_physics_tracker.domain.pendulum import QCExclusion
from ai_physics_tracker.domain.pendulum_fit import FitSettings
from ai_physics_tracker.domain.pendulum_ode import (
    M0, InitialCondition, PendulumParameters, evaluate_objective, simulate_pendulum,
)
from ai_physics_tracker.infrastructure.project_repository import ProjectRepository
from test_pendulum_analysis import analysis_session


def fit_session(tmp_path, synthetic_video_path):
    session, experiment = analysis_session(tmp_path, synthetic_video_path)
    # 测试声明长源时域；视频仅供hash/lifecycle，不进行像素解码或模型推理。
    session._project = replace(session.project,
        videos=tuple(replace(v, frame_count=126) for v in session.project.videos),
        timelines=tuple(replace(t, working_zone=(0, 125)) for t in session.project.timelines))
    session.set_release_frame(experiment.experiment_id, 5)
    times = tuple(i/10 for i in range(121))
    prediction = simulate_pendulum(M0, PendulumParameters(.03, 9.81/.5),
        InitialCondition(.3, 0., "explicit"), times, HIGH_PRECISION)
    for frame in range(126):
        theta = .3 if frame < 5 else prediction.theta_rad[frame-5]
        session.mark_point(experiment.roles.tip, frame, 100*sin(theta), 100*cos(theta))
    options = FitOptions(125, models=(M0,), rest_confirmed=True,
                         m0_settings=FitSettings(max_nfev=60))
    return session, session.pendulum_experiment(experiment.experiment_id), options


def test_tip_only_fixed_ic_full_payload_reopen_saveas_and_stale_undo(tmp_path, synthetic_video_path):
    session, experiment, options = fit_session(tmp_path, synthetic_video_path)
    before = session.project
    progress = []
    result = run_fit_job(prepare_fit_job(session, experiment.experiment_id, options), Event(),
                         progress=lambda *values: progress.append(values))
    assert session.project == before and result.record.execution_status == "success"
    fit = result.payload["fits"][M0]
    assert fit["parameters"]["alpha1_s_inv"] == pytest.approx(.03, abs=2e-5)
    assert fit["parameters"]["omega2_s_inv2"] == pytest.approx(9.81/.5, abs=2e-5)
    assert result.payload["config"]["resolved_ic"]["support_frames"] == (0, 1, 2, 3, 4)
    assert len(result.payload["rows"]) == 126 and result.payload["rows"][0]["m0_theta_rad"] is None
    assert result.payload["rows"][-1]["m0_theta_rad"] is not None and progress[-1] == (M0, 3, 3)
    session.apply_pendulum_fit_result(result)
    path = session.project_root/result.record.payload.path
    discard_fit_result(session, result)
    assert path.exists()  # 已注册不能被cleanup删除
    session.save()
    reopened = ProjectSession.load(ProjectRepository(), session.project_root)
    payload, valid, _ = load_fit_result(reopened, reopened.project.scientific_results[-1])
    assert valid
    request, typed = validated_fit_inputs(payload, reopened.project.scientific_results[-1])
    assert request.initial_condition.theta0_rad == pytest.approx(.3, abs=1e-12)
    with pytest.raises(ValueError, match="identity"):
        validated_fit_inputs({**payload, "contract": "different-contract"}, reopened.project.scientific_results[-1])
    assert tuple(request.series.frame_indices[i] for i in typed[M0].trajectory.source_indices) == tuple(range(5, 126))
    session.save_as(tmp_path/"copy")
    assert load_fit_result(session, session.project.scientific_results[-1])[1]
    session.set_qc_exclusions(experiment.experiment_id, (QCExclusion(20, "occluded"),))
    assert not load_fit_result(session, replace(session.project.scientific_results[-1], freshness="valid"))[1]
    assert session.undo() and load_fit_result(session, session.project.scientific_results[-1])[1]


def test_cancel_midfit_publish_late_and_video_change_rejected(tmp_path, synthetic_video_path, monkeypatch):
    import ai_physics_tracker.application.pendulum_fit as use_case
    session, experiment, options = fit_session(tmp_path, synthetic_video_path)
    job = prepare_fit_job(session, experiment.experiment_id, options)
    cancel = Event(); cancel.set()
    with pytest.raises(CancelledError):
        run_fit_job(job, cancel)
    cancel.clear()
    with pytest.raises(CancelledError):
        run_fit_job(job, cancel, progress=lambda *args: cancel.set())
    assert not list((session.project_root/"data/derived").glob("*.json"))
    result = run_fit_job(job, Event())
    session.mark_point(experiment.roles.tip, 10, 1., 100.)
    with pytest.raises(ProjectSessionError, match="inputs changed"):
        session.apply_pendulum_fit_result(result)
    session.undo()
    original = synthetic_video_path.read_bytes()
    synthetic_video_path.write_bytes(original+b"changed")
    with pytest.raises(ProjectSessionError, match="video changed"):
        session.apply_pendulum_fit_result(result)
    assert not load_fit_result(session, result.record)[1]
    synthetic_video_path.write_bytes(original)
    discard_fit_result(session, result)
    assert not (session.project_root/result.record.payload.path).exists()
    write = use_case.write_scientific_payload
    cancel = Event()
    def cancel_after_publish(*args):
        reference = write(*args)
        cancel.set()
        return reference
    monkeypatch.setattr(use_case, "write_scientific_payload", cancel_after_publish)
    with pytest.raises(CancelledError):
        run_fit_job(prepare_fit_job(session, experiment.experiment_id, options), cancel)
    assert not list((session.project_root/"data/derived").glob("*.json"))


def test_ic_failure_disk_failure_and_insufficient_data_keep_previous_fit(tmp_path, synthetic_video_path, monkeypatch):
    import ai_physics_tracker.application.pendulum_fit as use_case
    session, experiment, options = fit_session(tmp_path, synthetic_video_path)
    result = run_fit_job(prepare_fit_job(session, experiment.experiment_id, options), Event())
    session.apply_pendulum_fit_result(result)
    before = session.project
    with pytest.raises(ProjectSessionError, match="explicit IC"):
        run_fit_job(prepare_fit_job(session, experiment.experiment_id, replace(options, rest_confirmed=False)), Event())
    with monkeypatch.context() as patch:
        patch.setattr(use_case, "write_scientific_payload", lambda *a: (_ for _ in ()).throw(OSError("disk full")))
        with pytest.raises(OSError, match="disk full"):
            run_fit_job(prepare_fit_job(session, experiment.experiment_id, options), Event())
    assert session.project == before and load_fit_result(session, result.record)[1]
    session.set_qc_exclusions(experiment.experiment_id, tuple(QCExclusion(i, "occluded") for i in range(10, 100)))
    partial = run_fit_job(prepare_fit_job(session, experiment.experiment_id, options), Event())
    assert partial.record.execution_status == "insufficient_data"
    assert partial.payload["fits"][M0]["parameters"] is None
    assert session.project.scientific_results[0].result_id == result.record.result_id


def test_linear_loss_objective_and_options_are_explicit_and_validated():
    from test_pendulum_fit import _request
    from ai_physics_tracker.application.pendulum_fit import options_from_payload, options_payload
    request, truth = _request(M0)
    linear = replace(request, loss="linear")
    evaluation = evaluate_objective(linear, M0, replace(truth, alpha1_s_inv=.04))
    assert evaluation.cost_rad2 == pytest.approx(.5*sum(r*r for r in evaluation.residual_rad), abs=1e-12)
    options = FitOptions(240, explicit_ic=InitialCondition(.7, -.4, "explicit"), loss="linear",
                         m0_settings=FitSettings(starts=((.02, 40.),)))
    assert options_from_payload(options_payload(options)) == options
    with pytest.raises(ValueError):
        replace(options, rest_confirmed=1)
    with pytest.raises(ValueError):
        replace(options, loss="cauchy")


def test_matching_payload_and_manifest_cannot_forge_fit_provenance(tmp_path, synthetic_video_path):
    from copy import deepcopy
    from uuid import uuid4
    from ai_physics_tracker.infrastructure.scientific_payload import write_scientific_payload
    session, experiment, options = fit_session(tmp_path, synthetic_video_path)
    result = run_fit_job(prepare_fit_job(session, experiment.experiment_id, options), Event())
    forged = deepcopy(result.payload)
    forged["config"]["models"][M0]["sources"] = ["fabricated-source"]
    result_id = uuid4()
    reference = write_scientific_payload(session.project_root, result_id, forged, result.record.payload.columns)
    record = replace(result.record, result_id=result_id, payload=reference,
                     extra_fields={**result.record.extra_fields, "config": forged["config"]})
    with pytest.raises(ProjectSessionError, match="provenance"):
        load_fit_result(session, record)


def test_later_fit_interval_preserves_release_ic_and_raw_source_times(tmp_path, synthetic_video_path):
    from ai_physics_tracker.domain.pendulum_ode import fit_eligibility, fit_valid_indices
    from ai_physics_tracker.application.pendulum_fit import _objective
    from ai_physics_tracker.application.adopted_measurement import build_adopted_measurement
    session, experiment, options = fit_session(tmp_path, synthetic_video_path)
    options = replace(options, start_frame_index=25)
    request, _ = _objective(session, build_adopted_measurement(session, experiment.experiment_id), options)
    assert request.initial_condition.support_frames == (0, 1, 2, 3, 4)
    assert request.release_frame_index == 5 and request.fit_start_frame_index == 25
    assert fit_eligibility(request).required_count == 51
    assert request.series.time_release_relative_s[fit_valid_indices(request)[0]] == pytest.approx(2., abs=1e-12)
    result = run_fit_job(prepare_fit_job(session, experiment.experiment_id, options), Event())
    fit = result.payload["fits"][M0]
    assert fit["parameters"]["alpha1_s_inv"] == pytest.approx(.03, abs=2e-5)
    assert result.payload["rows"][24]["m0_theta_rad"] is None
    assert result.payload["rows"][25]["m0_theta_rad"] is not None
    assert fit["sample_time_s"][0] == pytest.approx(2., abs=1e-12)
    assert load_fit_result(session, result.record)[1]


def test_model_specific_settings_return_unavailable_comparison_without_invalid_warm_start(tmp_path, synthetic_video_path):
    session, experiment, options = fit_session(tmp_path, synthetic_video_path)
    session.set_qc_exclusions(experiment.experiment_id, tuple(QCExclusion(i, "occluded") for i in range(10, 100)))
    result = run_fit_job(prepare_fit_job(session, experiment.experiment_id,
        replace(options, models=(M0, "M1_linear_quadratic"))), Event())
    assert result.record.execution_status == "insufficient_data"
    assert result.payload["comparison"]["status"] == "not_comparable"
    assert result.payload["comparison"]["reason"] == "inputs_or_configuration_differ"



def test_fit_prepare_rejects_pre_release_start_and_accepts_interval_boundaries(tmp_path, synthetic_video_path):
    session, experiment, options = fit_session(tmp_path, synthetic_video_path)
    with pytest.raises(ProjectSessionError, match="at or after release"):
        prepare_fit_job(session, experiment.experiment_id, replace(options, start_frame_index=4))
    assert prepare_fit_job(session, experiment.experiment_id, replace(options, start_frame_index=5)).options.start_frame_index == 5
    assert prepare_fit_job(session, experiment.experiment_id, replace(options, start_frame_index=125)).options.start_frame_index == 125


def test_paired_payload_corruption_is_rejected_and_missing_or_changed_artifact_is_structured(tmp_path, synthetic_video_path):
    from copy import deepcopy
    from uuid import uuid4
    from ai_physics_tracker.infrastructure.scientific_payload import write_scientific_payload
    session, experiment, options = fit_session(tmp_path, synthetic_video_path)
    result = run_fit_job(prepare_fit_job(session, experiment.experiment_id, options), Event())
    mutations = [lambda p: p.update(rows=[]), lambda p: p["measurement"].update(release_frame_index=0),
        lambda p: p["rows"][10].update(theta_rad=0.), lambda p: p["fits"][M0].update(input_digest="0"*64),
        lambda p: p["fits"][M0]["trajectory"]["prediction"].update(theta_rad=[]),
        lambda p: p["fits"][M0].update(warnings=[]), lambda p: p["fits"][M0].pop("starts")]
    # 此合成fit默认无warning；用不同非法状态验证warning边界。
    mutations[5] = lambda p: p["fits"][M0].update(warnings=["fabricated"])
    for mutate in mutations:
        payload = deepcopy(result.payload); mutate(payload); result_id = uuid4()
        reference = write_scientific_payload(session.project_root, result_id, payload, result.record.payload.columns)
        record = replace(result.record, result_id=result_id, payload=reference)
        with pytest.raises(ProjectSessionError, match="invalid"):
            load_fit_result(session, record)
    path = session.project_root/result.record.payload.path
    path.write_bytes(b"broken")
    with pytest.raises(ProjectSessionError, match="unreadable"):
        load_fit_result(session, result.record)
    path.unlink()
    with pytest.raises(ProjectSessionError, match="unreadable"):
        load_fit_result(session, result.record)


def test_different_model_settings_execute_without_incompatible_warm_start(tmp_path, synthetic_video_path):
    from ai_physics_tracker.domain.pendulum_ode import M1
    session, experiment, options = fit_session(tmp_path, synthetic_video_path)
    options = replace(options, models=(M0, M1),
        m0_settings=FitSettings(max_nfev=3, starts=((.02, 19.62),)),
        m1_settings=FitSettings(max_nfev=4, starts=((.02, .005, 19.62),)))
    result = run_fit_job(prepare_fit_job(session, experiment.experiment_id, options), Event())
    assert all(result.payload["fits"][model]["starts"][0]["nfev"] > 0 for model in options.models)
    assert result.payload["comparison"]["status"] == "not_comparable"
    assert load_fit_result(session, result.record)[1]


def test_invalid_json_with_matching_reference_is_a_structured_load_error(tmp_path, synthetic_video_path):
    import hashlib
    from uuid import uuid4
    from ai_physics_tracker.application.pendulum_fit import COLUMNS, FIT_KIND, CORE_VERSION
    from ai_physics_tracker.domain.scientific_result import ScientificResult, ResultPayload
    from ai_physics_tracker.domain.types import utc_now
    from pathlib import PurePosixPath
    session, experiment, _ = fit_session(tmp_path, synthetic_video_path)
    data = b"{broken json"; relative = PurePosixPath("data/derived/broken.json")
    (session.project_root/relative).parent.mkdir(parents=True, exist_ok=True)
    (session.project_root/relative).write_bytes(data)
    reference = ResultPayload("json", relative, len(data), hashlib.sha256(data).hexdigest(), COLUMNS)
    record = ScientificResult(uuid4(), experiment.experiment_id, FIT_KIND, utc_now(), "0"*64,
        CORE_VERSION, "success", payload=reference)
    with pytest.raises(ProjectSessionError, match="unreadable"):
        load_fit_result(session, record)
