"""参考能量解析恒等式、typed payload及事务/lifecycle真实应用链。"""

from concurrent.futures import CancelledError
from dataclasses import replace
from math import cos, sqrt
from threading import Event

import numpy as np
import pytest

from ai_physics_tracker.application.pendulum_analysis import (
    load_analysis_result, prepare_analysis_job, run_analysis_job,
)
from ai_physics_tracker.application.experiment_inference_job import verify_experiment_inference_result
from ai_physics_tracker.application.project_session import ProjectSession, ProjectSessionError
from ai_physics_tracker.domain.angular_analysis import AngularSeries, analyze_angular_series
from ai_physics_tracker.domain.pendulum import ROLE_ORDER, PhysicalParameters, QCExclusion
from ai_physics_tracker.domain.pendulum_energy import reference_energy, energy_config
from ai_physics_tracker.infrastructure.project_repository import ProjectRepository
from ai_physics_tracker.infrastructure.scientific_payload import read_scientific_payload, write_scientific_payload
from test_experiment_inference_job import _prepared, _result


@pytest.mark.parametrize('amplitude', [.3, 1.4])
def test_nonlinear_undamped_energy_identity(amplitude):
    q = 9.81/.7
    # 无阻尼非线性摆的独立解析能量关系，包含非小角度与两个转向点。
    theta = tuple(np.linspace(-amplitude, amplitude, 31))
    series = AngularSeries('a'*64, tuple(range(31)), tuple(i*.01 for i in range(31)),
                           tuple(float(v) for v in theta), (True,)*31, 100.)
    angular = analyze_angular_series(series)
    omega = tuple(sqrt(max(0, 2*q*(cos(v)-cos(amplitude)))) for v in theta)
    energy = reference_energy(series, replace(angular, omega_rad_s=omega, omega_reasons=(None,)*31), .7, 9.81)
    np.testing.assert_allclose(energy.total_s_inv2, q*(1-cos(amplitude)), atol=1e-12, rtol=1e-12)
    assert energy.q_s_inv2 == q
    assert energy_config()["sources"] == ["energy", "policy-student-v1"]


def test_energy_missing_finite_and_identity_boundaries():
    series = AngularSeries('a'*64, tuple(range(20)), tuple(i*.01 for i in range(20)), (.2,)*20, (True,)*20, 100.)
    angular = analyze_angular_series(series)
    energy = reference_energy(series, angular, 1, 9.81)
    assert energy == reference_energy(series, angular, 1., 9.81)
    short = replace(series, qc_valid=(True,)*5+(False,)*15)
    e = reference_energy(short, analyze_angular_series(short), 1, 9.81)
    assert all(v is None for v in e.total_s_inv2)
    assert e.potential_s_inv2[0] > 0 and e.potential_s_inv2[5] is None
    assert e.reasons[0] == 'short_segment'
    with pytest.raises(ValueError, match='source'):
        reference_energy(replace(series, theta_rad=(.3,)*20), angular, 1, 9.81)
    for length, g in [(0, 9), (True, 9), (1, float('inf')), (1e-300, 1e300)]:
        with pytest.raises(ValueError):
            reference_energy(series, angular, length, g)
    e = reference_energy(series, replace(angular, omega_rad_s=(1e308,)*20), 1, 9.81)
    assert e.total_s_inv2 == (None,)*20 and set(e.reasons) == {'nonfinite_energy'}


def analysis_session(tmp_path, synthetic_video_path):
    session, experiment, run, request = _prepared(tmp_path, synthetic_video_path)
    folder = session.project_root / 'data' / 'engines' / str(run.run_id)
    session.update_tracking_run(verify_experiment_inference_result(session, run, request,
        _result(folder, request), folder))
    session.activate_experiment_candidate(experiment.experiment_id, run.run_id)
    session._verified_videos.add(experiment.video_id)
    session.set_fixed_pivot(experiment.experiment_id, (0., 0.))
    session.set_true_vertical(experiment.experiment_id, (0., 0.), (0., 1.))
    session.confirm_true_vertical(experiment.experiment_id)
    session.set_tip_radius_reference(experiment.experiment_id, 100.)
    session.set_physical(experiment.experiment_id, PhysicalParameters(.5, 9.81, 'ruler', 'standard'))
    session.set_release_frame(experiment.experiment_id, 0)
    session.add_calibration(experiment.video_id, (0., 0.), (0., 100.), .5, 'm')
    for frame in range(12):
        for role, (x, y) in zip(ROLE_ORDER, ((0, 100), (0, 10), (0, 20), (0, 0))):
            session.mark_point(experiment.roles.by_role()[role], frame, x, y)
    return session, session.pendulum_experiment(experiment.experiment_id)


def test_complete_payload_save_reopen_saveas_and_stale_undo(tmp_path, synthetic_video_path):
    session, experiment = analysis_session(tmp_path, synthetic_video_path)
    job = prepare_analysis_job(session, experiment.experiment_id, 11)
    before = session.project
    result = run_analysis_job(job, Event())
    assert session.project == before  # worker不可提交活动会话
    session.apply_pendulum_analysis_result(result)
    assert result.record.execution_status == 'success'
    rows = result.payload['rows']
    assert len(rows) == 12 and [r['frame_index'] for r in rows] == list(range(12))
    assert all(r['energy_s_inv2'] == pytest.approx(0, abs=1e-20) for r in rows)
    assert all(r['points_by_role']['tip']['confidence'] is None for r in rows)
    assert result.payload['tail']['reason'] == 'not_enough_complete_periods'
    session.save()
    reopened = ProjectSession.load(ProjectRepository(), session.project_root)
    assert load_analysis_result(reopened, reopened.project.scientific_results[-1])[1]
    session.save_as(tmp_path/'copy')
    assert load_analysis_result(session, session.project.scientific_results[-1])[1]
    old = session.project
    session.set_qc_exclusions(experiment.experiment_id, (QCExclusion(4, 'occluded'),))
    stale = session.project.scientific_results[-1]
    assert stale.execution_status == 'success' and stale.freshness == 'stale'
    assert not load_analysis_result(session, replace(stale, freshness='valid'))[1]  # 漏置flag也fail closed
    assert session.undo() and session.project == old
    assert load_analysis_result(session, session.project.scientific_results[-1])[1]
    with pytest.raises(ProjectSessionError, match='inputs changed'):
        session.apply_pendulum_analysis_result(result)  # Save As 改了根，不是捕获的项目单元


def test_cancel_stale_failure_and_immutable_payload(tmp_path, synthetic_video_path, monkeypatch):
    session, experiment = analysis_session(tmp_path, synthetic_video_path)
    job = prepare_analysis_job(session, experiment.experiment_id, 11)
    cancel = Event(); cancel.set()
    before = session.project
    with pytest.raises(CancelledError):
        run_analysis_job(job, cancel)
    assert session.project == before
    result = run_analysis_job(job, Event())
    session.mark_point(experiment.roles.tip, 1, 1., 100.)
    changed = session.project
    with pytest.raises(ProjectSessionError, match='inputs changed'):
        session.apply_pendulum_analysis_result(result)
    assert session.project == changed
    session.undo()
    session.apply_pendulum_analysis_result(result)
    path = session.project_root/result.record.payload.path
    original = path.read_bytes()
    with pytest.raises(FileExistsError):
        write_scientific_payload(session.project_root, result.record.result_id, {}, result.record.payload.columns)
    assert path.read_bytes() == original
    path.write_bytes(original+b' ')
    with pytest.raises(ValueError, match='hash'):
        read_scientific_payload(session.project_root, result.record.payload)
    path.write_bytes(original)
    session.set_release_frame(experiment.experiment_id, 10)
    partial = run_analysis_job(prepare_analysis_job(session, experiment.experiment_id, 11), Event())
    assert partial.record.execution_status == 'insufficient_data'
    assert all(r['energy_s_inv2'] is None for r in partial.payload['rows'])
    assert partial.payload['rows'][0]['time_release_relative_s'] == -1


def test_payload_write_failure_preserves_previous_result(tmp_path, synthetic_video_path, monkeypatch):
    import ai_physics_tracker.application.pendulum_analysis as use_case
    session, experiment = analysis_session(tmp_path, synthetic_video_path)
    job = prepare_analysis_job(session, experiment.experiment_id, 11)
    result = run_analysis_job(job, Event())
    session.apply_pendulum_analysis_result(result)
    old = session.project
    def fail(*args):
        raise OSError('disk full')
    monkeypatch.setattr(use_case, 'write_scientific_payload', fail)
    with pytest.raises(OSError, match='disk full'):
        run_analysis_job(prepare_analysis_job(session, experiment.experiment_id, 11), Event())
    assert session.project == old
    assert load_analysis_result(session, result.record)[1]


def test_video_changed_after_worker_verification_is_rejected(tmp_path, synthetic_video_path):
    session, experiment = analysis_session(tmp_path, synthetic_video_path)
    result = run_analysis_job(prepare_analysis_job(session, experiment.experiment_id, 11), Event())
    before = session.project
    original = synthetic_video_path.read_bytes()
    synthetic_video_path.write_bytes(original+b'changed')
    with pytest.raises(ProjectSessionError, match='video changed'):
        session.apply_pendulum_analysis_result(result)
    assert session.project == before
    # 即便保守stale漏标，历史payload可看但SHA变化不能返回valid。
    assert not load_analysis_result(session, result.record)[1]
    synthetic_video_path.unlink()
    payload, valid, _ = load_analysis_result(session, result.record)
    assert payload['rows'] and not valid


def test_source_frame_inspection_preserves_trimmed_working_zone(synthetic_video_path):
    from ai_physics_tracker.application.video_session import VideoSession
    from ai_physics_tracker.application.playback import AsyncVideoSession
    from ai_physics_tracker.domain.timeline import Timeline
    from ai_physics_tracker.infrastructure.opencv_video_reader import OpenCVVideoReader
    from uuid import uuid4
    from queue import Queue
    delivered = Queue()
    session = VideoSession(OpenCVVideoReader())
    async_session = AsyncVideoSession(session, delivered.put, delivered.put)
    try:
        timeline = Timeline(uuid4(), 10., (2, 3))
        async_session.open(synthetic_video_path, timeline).result(timeout=5)
        async_session.request_frame(1)
        assert delivered.get(timeout=5).frame_index == 2  # 普通播放仍钳位
        async_session.request_frame(1, source_frame=True)
        assert delivered.get(timeout=5).frame_index == 1  # 科学图点是真实源帧
        assert async_session.snapshot().timeline == timeline
        async_session.request_frame(2)
        assert delivered.get(timeout=5).frame_index == 2
    finally:
        async_session.close()


def test_profile_upgrade_marks_historical_result_stale_without_rewriting_it(tmp_path, synthetic_video_path, monkeypatch):
    import ai_physics_tracker.application.pendulum_analysis as use_case

    session, experiment = analysis_session(tmp_path, synthetic_video_path)
    old_config = dict(use_case.reconstruction_config())
    old_config.update(profile_id='student-default-v1', profile_version='1.0.0',
                      profile_sha256='6b5b28065eebd0f0a26d42b6d279b4d4294af89e1a9bd5da5badaf9101e48d51')
    # 全四点静止数据在两版下数值相同；旧政策身份仍必须失效。
    with monkeypatch.context() as patch:
        patch.setattr(use_case, 'reconstruction_config', lambda: old_config)
        patch.setattr(use_case, 'CORE_VERSION', 'pendulum-core-analysis-1.0.0')
        result = run_analysis_job(prepare_analysis_job(session, experiment.experiment_id, 11), Event())
        session.apply_pendulum_analysis_result(result)
        assert load_analysis_result(session, result.record)[1]
    path = session.project_root / result.record.payload.path
    before = path.read_bytes()
    assert not load_analysis_result(session, result.record)[1]
    assert path.read_bytes() == before
