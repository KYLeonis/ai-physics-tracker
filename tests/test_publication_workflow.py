"""实验级状态与两条模型路径不依赖所选辅助轨；无需Qt或真实模型。"""

from dataclasses import replace
from threading import Event

from ai_physics_tracker.application.pendulum_analysis import prepare_analysis_job, run_analysis_job
from ai_physics_tracker.application.publication_workflow import publication_task_card
from ai_physics_tracker.application.workflow_projection import project_workflow_state
from test_pendulum_analysis import analysis_session
from test_pendulum_fit_job import fit_session
from ai_physics_tracker.application.pendulum_fit import prepare_fit_job, run_fit_job


def test_scientific_state_uses_tip_and_invalidates_after_manual_edit(tmp_path, synthetic_video_path):
    session, experiment = analysis_session(tmp_path, synthetic_video_path)
    result = run_analysis_job(prepare_analysis_job(session, experiment.experiment_id, 11), Event())
    session.apply_pendulum_analysis_result(result)
    for selected in (None, experiment.roles.tip, experiment.roles.body_bottom):
        state = project_workflow_state(session, selected, session.tracking_runs(), experiment=experiment)
        assert state.analysis.state == "latest"
        assert state.analysis.effective_frames == 12
        assert state.pendulum.experiment_id == experiment.experiment_id
        assert "select or create a track" not in state.prerequisites
    session.mark_point(experiment.roles.tip, 0, 0., 99.)
    state = project_workflow_state(session, None, session.tracking_runs(),
                                  experiment=session.pendulum_experiment(experiment.experiment_id))
    assert state.analysis.state == "needs_update"


def test_teacher_path_does_not_require_labels_or_fixed_check_and_busy_keeps_cancel(tmp_path, synthetic_video_path):
    session, experiment = analysis_session(tmp_path, synthetic_video_path)
    # _prepared fixture已登记模型；无frame-set/fixed-check仍可先verify/infer。
    session._project = replace(session.project, experiments=(replace(experiment, active_infer_run_id=None),))
    experiment = session.pendulum_experiment(experiment.experiment_id)
    state = project_workflow_state(session, None, (), experiment=experiment)
    card = publication_task_card(session, experiment, state, "acquire")
    assert card.primary.action_id == "run_joint_inference"
    assert card.primary.enabled
    assert any(a.action_id == "import_teacher" for a in card.secondary)
    busy = publication_task_card(session, experiment, state, "analysis", activity="Training model…")
    assert busy.primary.action_id == "cancel_task"
    assert "preserves" in busy.explanation[1]
    assert session.project.scientific_results == ()


def test_nonconverged_fit_is_visible_alone_and_with_successful_kinematics(tmp_path, synthetic_video_path):
    session, experiment, options = fit_session(tmp_path, synthetic_video_path)
    options = replace(options, m0_settings=replace(options.m0_settings, max_nfev=1))
    result = run_fit_job(prepare_fit_job(session, experiment.experiment_id, options), Event())
    assert result.record.execution_status == "nonconverged"
    session.apply_pendulum_fit_result(result)
    for with_kinematics in (False, True):
        if with_kinematics:
            analysis = run_analysis_job(prepare_analysis_job(session, experiment.experiment_id, 125), Event())
            session.apply_pendulum_analysis_result(analysis)
        state = project_workflow_state(session, None, session.tracking_runs(), experiment=experiment)
        assert state.analysis.state == "partial"
        assert any("nonconverged" in limit for limit in state.analysis.limitations)
