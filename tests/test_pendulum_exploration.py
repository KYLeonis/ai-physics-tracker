"""P4只读应用链：采用的fit来源、独立等价forward与非等价对照。"""

from concurrent.futures import CancelledError
from threading import Event

import pytest

from ai_physics_tracker.application.pendulum_exploration import read_fit_exploration, preview_equivalence
from ai_physics_tracker.application.pendulum_fit import prepare_fit_job, run_fit_job
from ai_physics_tracker.application.project_session import ProjectSessionError
from test_pendulum_fit_job import fit_session


def fitted_session(tmp_path, video_path):
    session, experiment, options = fit_session(tmp_path, video_path)
    result = run_fit_job(prepare_fit_job(session, experiment.experiment_id, options), Event())
    session.apply_pendulum_fit_result(result)
    return session, experiment, result.record


def test_exploration_uses_verified_fit_without_writing_results(tmp_path, synthetic_video_path):
    session, experiment, record = fitted_session(tmp_path, synthetic_video_path)
    before = session.project
    artifact = (session.project_root/record.payload.path).read_bytes()
    source = read_fit_exploration(session.detached(), record, Event())
    assert source.criticism.models[0].fit_identity_status == "valid"
    assert source.criticism.models[0].residuals.valid_count == 121
    assert source.criticism.comparison.reason == "both_models_required"
    equivalent = preview_equivalence(source, 1.12, False, None, Event())
    assert equivalent.forwards.status == "success"
    assert equivalent.forwards.raw_overlap_max_abs_difference_rad <= 1e-7
    assert equivalent.displayed_raw.alpha_a == pytest.approx(.12)
    assert equivalent.displayed_lumped.omega2_s_inv2 == pytest.approx(source.parameters.omega2_s_inv2)
    assert equivalent.forwards.time_s[-1] == 12.
    control = preview_equivalence(source, 1.12, True, None, Event())
    assert control.non_equivalent_control
    assert control.forwards.status == "non_equivalent_control"
    assert control.displayed_lumped.omega2_s_inv2 == pytest.approx(source.parameters.omega2_s_inv2*1.05)
    assert control.forwards.raw_overlap_max_abs_difference_rad > 1e-3
    assert session.project == before
    assert (session.project_root/record.payload.path).read_bytes() == artifact
    cancelled = Event(); cancelled.set()
    with pytest.raises(CancelledError): preview_equivalence(source, 1., False, None, cancelled)
    session.mark_point(experiment.roles.tip, 10, 1., 100.)
    with pytest.raises(ProjectSessionError, match="stale|changed"):
        read_fit_exploration(session.detached(), record, Event())
