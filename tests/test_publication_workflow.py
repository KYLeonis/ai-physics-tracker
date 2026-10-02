"""实验级状态与两条模型路径不依赖所选辅助轨；无需Qt或真实模型。"""

from dataclasses import replace
from threading import Event

from ai_physics_tracker.application.pendulum_analysis import prepare_analysis_job, run_analysis_job
from ai_physics_tracker.application.publication_workflow import publication_task_card
from ai_physics_tracker.application.workflow_projection import project_workflow_state
from test_pendulum_analysis import analysis_session
from test_pendulum_fit_job import fit_session
from ai_physics_tracker.application.pendulum_fit import prepare_fit_job, run_fit_job
from ai_physics_tracker.domain.pendulum import PhysicalParameters
from test_experiment_inference_job import _prepared


def test_fresh_setup_acquires_tip_before_setting_radius(tmp_path, synthetic_video_path):
    session, experiment, _, _ = _prepared(tmp_path, synthetic_video_path)
    session.set_fixed_pivot(experiment.experiment_id, (0., 0.))
    session.set_true_vertical(experiment.experiment_id, (0., 0.), (0., 1.))
    session.confirm_true_vertical(experiment.experiment_id)
    session.set_physical(experiment.experiment_id, PhysicalParameters(.5, 9.81, 'ruler', 'standard'))
    session.set_release_frame(experiment.experiment_id, 0)
    session.add_calibration(experiment.video_id, (0., 0.), (0., 100.), .5, 'm')

    def setup_card():
        current = session.pendulum_experiment(experiment.experiment_id)
        state = project_workflow_state(session, None, session.tracking_runs(), experiment=current)
        return publication_task_card(session, current, state, "setup")

    assert setup_card().primary.action_id == "view_acquire"
    session.mark_point(experiment.roles.tip, 0, 0., 100.)
    assert setup_card().primary.action_id == "view_setup"
    session.set_tip_radius_reference(experiment.experiment_id, 100.)
    assert setup_card().primary.action_id == "view_acquire"


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
    session, experiment, _, _ = _prepared(tmp_path, synthetic_video_path)
    # 已登记教师模型；没有label/frame-set/fixed-check仍可先verify/infer。
    state = project_workflow_state(session, None, (), experiment=experiment)
    card = publication_task_card(session, experiment, state, "acquire")
    assert card.primary.action_id == "run_joint_inference"
    assert card.primary.enabled
    assert any(a.action_id == "import_teacher" for a in card.secondary)
    busy = publication_task_card(session, experiment, state, "analysis", activity="Training model…")
    assert busy.primary.action_id == "cancel_task"
    assert "preserves" in busy.explanation[1]
    assert session.project.scientific_results == ()


def test_training_cycle_tracks_labels_and_latest_model(tmp_path, synthetic_video_path):
    from ai_physics_tracker.application.annotation_join import canonical_label_digest, join_complete_frames
    from ai_physics_tracker.domain.pendulum import ExperimentFrameSet, ROLE_ORDER
    from ai_physics_tracker.domain.tracking_run import create_tracking_run, mark_run_completed
    from ai_physics_tracker.domain.types import utc_now

    session, experiment, _, _ = _prepared(tmp_path, synthetic_video_path)
    teacher = session.project.model_references[0]
    session._project = replace(session.project, model_references=(), tracking_runs=())

    def card():
        current = session.pendulum_experiment(experiment.experiment_id)
        state = project_workflow_state(session, None, session.tracking_runs(), experiment=current)
        return publication_task_card(session, current, state, "acquire")

    assert card().primary.action_id == "pick_landmark_frames"
    session.set_experiment_frame_set(experiment.experiment_id,
                                    ExperimentFrameSet((1, 2), "uniform", utc_now()))
    assert card().primary.action_id == "guided_marking"
    for frame in (1, 2):
        for role in ROLE_ORDER:
            session.mark_point(experiment.roles.track_id_for(role), frame, 10., 20.)
    assert card().primary.action_id == "train_current_labels"
    train = mark_run_completed(create_tracking_run(
        experiment.video_id, experiment.roles.track_ids(), "train",
        experiment_id=experiment.experiment_id, role_bindings=experiment.roles,
        config={"label_digest": canonical_label_digest(join_complete_frames(session.project, experiment))}))
    session.record_tracking_run(train)
    trained = replace(teacher, origin="trained", source_train_run_id=train.run_id,
                      source_experiment_id=experiment.experiment_id)
    session._project = replace(session.project, model_references=(trained,))
    assert card().primary.action_id == "run_joint_inference"
    infer = mark_run_completed(create_tracking_run(
        experiment.video_id, experiment.roles.track_ids(), "infer",
        experiment_id=experiment.experiment_id, role_bindings=experiment.roles,
        config={"model_id": str(trained.model_id)}))
    session.record_tracking_run(infer)
    assert card().primary.action_id == "review_joint_candidate"
    assert len(card().secondary) == 5  # 原有六个按钮持续提供完整循环
    session.mark_point(experiment.roles.tip, 1, 11., 20.)
    assert card().primary.action_id == "train_current_labels"
    assert "Labels changed" in card().explanation[1]


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
