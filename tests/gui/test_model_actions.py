"""教师模型 GUI 的导入、自检、取消与上下文边界回归。"""

from concurrent.futures import CancelledError
from dataclasses import replace
from threading import Event
import time
from uuid import uuid4

from ai_physics_tracker.application.tracking_job import (
    prepare_tracking_request, run_tracking_worker, prepare_tracking_candidate,
)
from ai_physics_tracker.infrastructure.mock_engine_adapter import MockEngineAdapter
from ai_physics_tracker.infrastructure.imported_models import import_model
from ai_physics_tracker.infrastructure.task_runner import TaskResult
from tests.test_imported_models import model_sources, evidence
from tests.gui.test_tracking_actions import _FakeRunner, _opened_window


class ProbeHandle:
    def __init__(self, run_id, model):
        self.run_id = run_id
        self.model = model
        self.alive = True
        self.cancelled = False
        self.messages = []

    def poll_messages(self):
        messages,self.messages=self.messages,[]
        return messages

    def is_alive(self): return self.alive

    def cancel(self, timeout_s=1):
        self.cancelled=True
        self.alive=False


class ProbeRunner:
    def __init__(self): self.handle=None; self.release=Event(); self.started=Event()

    def start_task(self, run_id, target, root, model, video, video_id, frame, device):
        self.handle=ProbeHandle(run_id,model)
        self.args=(video,video_id,frame,device)
        self.started.set()
        return self.handle


def test_gui_import_probe_and_inference_request_without_training(qtbot, synthetic_video_path, tmp_path):
    window,session,track=_opened_window(qtbot,synthetic_video_path,tmp_path,_FakeRunner())
    actions=window.modelActions
    before=session.project.observations
    actions.importFiles(model_sources(tmp_path))
    qtbot.waitUntil(lambda: not actions.busy and not window.projectActions.busy, timeout=5000)
    assert len(session.project.imported_models)==1
    assert not session.tracking_runs()
    assert actions.bodyparts.count()==2
    assert not actions.inferButton.isEnabled()
    assert "self-test teacher" in window.trackingActions.panel.cardTitleLabel.text()
    runner=ProbeRunner();actions.runner=runner
    window.workflowHeader.nextStepButtons[0].click()
    qtbot.waitUntil(runner.started.is_set)
    assert actions.busy
    window.trackingActions.train()
    assert not window.trackingActions.pending
    assert not window.projectActions.requestWindowClose()
    assert not window.projectActions.actions[4].isEnabled()
    model=session.project.imported_models[0]
    proof={**evidence(model, video_id=window.activeVideoId, video_path=session.video_path(session.project.videos[0])),"frame_index":runner.args[2],"video_id":str(runner.args[1])}
    runner.handle.messages=[TaskResult(runner.handle.run_id,True,{"status":"completed","evidence":proof})]
    qtbot.waitUntil(lambda:not actions.busy and not window.projectActions.busy,timeout=5000)
    assert runner.handle.cancelled
    assert actions.inferButton.isEnabled()
    assert session.project.observations==before and not session.tracking_runs()
    assert "teacher model ready" in window.trackingActions.panel.cardTitleLabel.text()
    captured=[]
    window.trackingActions._start=lambda params,**kw:captured.append((params,kw))
    actions.bodyparts.setCurrentText("other")
    window.workflowHeader.nextStepButtons[0].click()
    assert captured[0][1]=={"imported_model_id":model.model_id,"imported_bodypart":"other"}
    assert not session.is_dirty


def test_cancel_late_probe_success_never_applies_evidence(qtbot, synthetic_video_path, tmp_path):
    window,session,_=_opened_window(qtbot,synthetic_video_path,tmp_path,_FakeRunner())
    actions=window.modelActions
    model=import_model(session.project_root,*model_sources(tmp_path));session.register_imported_model(model)
    actions.refresh();runner=ProbeRunner();actions.runner=runner
    actions.selfTest();qtbot.waitUntil(runner.started.is_set)
    actions.cancel()
    runner.handle.messages=[TaskResult(runner.handle.run_id,True,{"status":"completed","evidence":evidence(model, video_id=window.activeVideoId, video_path=session.video_path(session.project.videos[0]))})]
    qtbot.waitUntil(lambda:not actions.busy,timeout=3000)
    assert runner.handle.cancelled
    assert not session.project.imported_models[0].self_test
    assert not actions.inferButton.isEnabled()


def test_context_change_discards_probe(qtbot, synthetic_video_path, tmp_path):
    window,session,_=_opened_window(qtbot,synthetic_video_path,tmp_path,_FakeRunner())
    actions=window.modelActions
    model=import_model(session.project_root,*model_sources(tmp_path));session.register_imported_model(model)
    actions.refresh();runner=ProbeRunner();actions.runner=runner
    actions.selfTest();qtbot.waitUntil(runner.started.is_set)
    window._delivery_generation += 1
    runner.handle.messages=[TaskResult(runner.handle.run_id,True,{"status":"completed","evidence":evidence(model, video_id=window.activeVideoId, video_path=session.video_path(session.project.videos[0]))})]
    qtbot.waitUntil(lambda:not actions.busy,timeout=3000)
    assert not session.project.imported_models[0].self_test
    assert "context changed" in actions.status.text()


def test_imported_pipeline_candidate_and_explicit_activation_preserve_manual(qtbot, synthetic_video_path, tmp_path):
    from queue import Queue
    from ai_physics_tracker.application.tracking_types import InferenceParams
    window,session,track=_opened_window(qtbot,synthetic_video_path,tmp_path,_FakeRunner())
    model=import_model(session.project_root,*model_sources(tmp_path))
    model=replace(model,self_test=evidence(model, video_id=window.activeVideoId, video_path=session.video_path(session.project.videos[0])))
    session.register_imported_model(model)
    manual=session.manual_points(track)
    params=InferenceParams(0.0)
    req=prepare_tracking_request(session,track,params,imported_model_id=model.model_id,imported_bodypart="tip")
    session.record_tracking_run(req.run)
    result=run_tracking_worker(req.run.run_id,Queue(),Event(),req,MockEngineAdapter())
    candidate=prepare_tracking_candidate(session.project,req,session.project_root/result["result_path"])
    assert not candidate.observations_changed
    assert session.apply_tracking_candidate(candidate)
    run=session.tracking_runs()[0]
    assert run.status=="completed" and run.task_type=="infer"
    assert "training_run_id" not in run.config
    assert run.config["bodypart"]=="tip"
    assert not session.get_refinement_state(track).active_infer_run_id
    session.activate_infer_run(track,run.run_id)
    assert session.manual_points(track)==manual
    assert len(session.effective_points(track))==5
    assert not any(r.task_type=="train" for r in session.tracking_runs())


def test_model_registration_waits_for_existing_save(qtbot, synthetic_video_path, tmp_path):
    from concurrent.futures import Future
    window, session, _ = _opened_window(qtbot, synthetic_video_path, tmp_path, _FakeRunner())
    actions = window.modelActions
    model = import_model(session.project_root, *model_sources(tmp_path))
    actions._begin("import", session)
    future = Future(); future.set_result(model)
    actions._future = future
    window.projectActions.busy = True
    actions._poll()
    assert actions.busy and not session.project.imported_models
    window.projectActions.busy = False
    actions._poll()
    assert session.project.imported_models == (model,)
    qtbot.waitUntil(lambda: not window.projectActions.busy, timeout=3000)
    assert not session.is_dirty


def test_project_model_import_survives_detached_video_switch(qtbot, synthetic_video_path, tmp_path):
    from concurrent.futures import Future
    window, session, _ = _opened_window(qtbot, synthetic_video_path, tmp_path, _FakeRunner())
    actions = window.modelActions
    model = import_model(session.project_root, *model_sources(tmp_path))
    actions._begin("import", session)
    future = Future(); future.set_result(model); actions._future = future
    current = session.detached()
    window._annotation_session = current
    other_path = tmp_path / "other.avi"
    other_path.write_bytes(synthetic_video_path.read_bytes())
    other = replace(current.project.videos[0], video_id=uuid4(), file_path=None, original_path=str(other_path))
    current._project = replace(current.project, videos=(*current.project.videos, other),
                               timelines=(*current.project.timelines, replace(current.project.timelines[0], video_id=other.video_id)))
    window._annotation_video_id = other.video_id
    window._delivery_generation += 1
    actions._poll()
    assert current.project.imported_models == (model,)
    assert not session.project.imported_models
    qtbot.waitUntil(lambda: not window.projectActions.busy, timeout=3000)
    assert not current.is_dirty


def test_retest_cancel_revocation_is_persisted_before_worker_start(qtbot, synthetic_video_path, tmp_path):
    from ai_physics_tracker.application.project_session import ProjectSession
    from ai_physics_tracker.infrastructure.project_repository import ProjectRepository
    from ai_physics_tracker.application.workflow_projection import MODE_INSPECT
    window, session, _ = _opened_window(qtbot, synthetic_video_path, tmp_path, _FakeRunner())
    actions = window.modelActions
    model = import_model(session.project_root, *model_sources(tmp_path))
    model = replace(model, self_test=evidence(model, video_id=window.activeVideoId,
                                             video_path=session.video_path(session.project.videos[0])))
    session.register_imported_model(model); session.save(); actions.refresh()
    assert actions.isVerified()
    runner = ProbeRunner(); actions.runner = runner
    actions.selfTest()
    qtbot.waitUntil(runner.started.is_set, timeout=3000)
    reopened = ProjectSession.load(ProjectRepository(), session.project_root)
    assert not reopened.project.imported_models[0].self_test
    state = actions.window.trackingActions._current_workflow_state
    from ai_physics_tracker.application.workflow_projection import select_task_card
    assert select_task_card(state).mode == MODE_INSPECT
    actions.cancel()
    qtbot.waitUntil(lambda: not actions.busy, timeout=3000)
    assert not actions.isVerified()
    assert not ProjectSession.load(ProjectRepository(), session.project_root).project.imported_models[0].self_test


def test_revocation_save_failure_does_not_start_probe(qtbot, synthetic_video_path, tmp_path, monkeypatch):
    from ai_physics_tracker.application.project_session import ProjectSession
    window, session, _ = _opened_window(qtbot, synthetic_video_path, tmp_path, _FakeRunner())
    actions = window.modelActions
    model = import_model(session.project_root, *model_sources(tmp_path))
    session.register_imported_model(model); actions.refresh()
    runner = ProbeRunner(); actions.runner = runner
    def fail(_session):
        raise OSError("disk full")
    monkeypatch.setattr(ProjectSession, "save", fail)
    actions.selfTest()
    qtbot.waitUntil(lambda: not actions.busy and not window.projectActions.busy, timeout=3000)
    assert not runner.started.is_set()
    assert "save failed" in actions.status.text()
