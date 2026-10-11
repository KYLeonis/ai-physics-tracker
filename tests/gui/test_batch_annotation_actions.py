"""选定建议帧的连续修正、暂停和训练建议；不自动执行训练。"""

from uuid import uuid4

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QListWidgetItem

from ai_physics_tracker.application.suggested_frame_review import ActiveReviewBatch, ReviewCandidate, ReviewPredictionSnapshot
from tests.gui.test_tracking_actions import _FakeRunner, _opened_window
from tests.gui.test_suggested_frame_review_actions import _setup_infer_run_with_prediction


def test_selected_representative_batch_advances_and_pauses(qtbot, synthetic_video_path, tmp_path):
    window, session, track = _opened_window(qtbot, synthetic_video_path, tmp_path, _FakeRunner())
    actions = window.batchAnnotationActions
    panel = window.trackingActions.panel
    for f in (3,4):
        item=QListWidgetItem(f"Frame {f}"); item.setData(Qt.ItemDataRole.UserRole,f)
        panel.suggestedFramesList.addItem(item); item.setSelected(True)
    actions.refresh()
    assert not actions.selectionGroup.isHidden()
    assert actions.labelButton.isEnabled()
    actions.labelButton.click()
    assert actions.batch.frames == (3,4)
    qtbot.waitUntil(lambda: window.presented_frame_index == 3 and not window._has_pending_request)
    actions.handleClick(20,30)
    assert actions.batch.index == 1
    window._exitAnnotationMode()
    assert actions.batch.paused
    window.setWorkspace("analysis"); window.setWorkspace("acquire")
    assert not window.videoView.is_annotation_mode()
    assert not actions.handleClick(99,99)
    actions.resume()
    qtbot.waitUntil(lambda: window.presented_frame_index == 4 and not window._has_pending_request)
    actions.skip()
    assert actions.batch.finished and actions.batch.corrected == 1
    assert session.manual_points(track)[-1].frame_index == 3
    assert len(session.manual_points(track)) == 4
    assert not window.trackingActions.pending
    assert window.trackingActions._current_workflow_state.execution.annotation_batch.finished
    assert "selected frames corrected" in panel.cardTitleLabel.text()
    qtbot.waitUntil(lambda: not window.projectActions.busy)
    assert not session.is_dirty


def test_difficult_frame_batch_preserves_unselected_and_skip_records(qtbot, synthetic_video_path, tmp_path):
    window, session, track = _opened_window(qtbot, synthetic_video_path, tmp_path, _FakeRunner())
    run = _setup_infer_run_with_prediction(window,tmp_path)
    candidates=tuple(ReviewCandidate(f, ReviewPredictionSnapshot(10,20,0.4),
                                    {},{},("low_confidence",),0.8) for f in (1,2,3))
    session.set_active_review_batch(run.run_id,ActiveReviewBatch(uuid4(),{},candidates))
    window.reviewActions.onRunSelected(run.run_id)
    window.trackingActions.refresh()
    panel=window.trackingActions.panel
    panel.reviewCandidatesList.clearSelection()
    for i in (0,1): panel.reviewCandidatesList.item(i).setSelected(True)
    window.batchAnnotationActions.correctButton.click()
    batch=window.batchAnnotationActions
    assert batch.batch.frames == (1,2)
    qtbot.waitUntil(lambda: window.presented_frame_index == 1 and not window._has_pending_request)
    before=len(session.manual_points(track))
    batch.handleClick(44,55)
    batch.skip()
    state=session.get_suggested_frame_review(run.run_id)
    assert len(state.reviewed_frames) == 1
    record=state.reviewed_frames[1]
    assert record.disposition == "corrected"
    point=next(p for p in session.project.observations if p.point_id == record.manual_point_id)
    assert point.pixel_x == 44 and point.source == "manual"
    assert len(session.manual_points(track)) == before
    # 一次 Undo 同时回滚人工点和 corrected 记录。
    session.undo()
    assert not session.get_suggested_frame_review(run.run_id).reviewed_frames
    qtbot.waitUntil(lambda: not window.projectActions.busy)


def test_out_of_zone_or_wrong_presented_frame_cannot_write(qtbot, synthetic_video_path, tmp_path):
    window, session, _ = _opened_window(qtbot, synthetic_video_path, tmp_path, _FakeRunner())
    batch=window.batchAnnotationActions
    batch.start((99,)); assert batch.batch is None
    before=session.project.observations
    batch.start((4,))
    window._presented_frame_index=0
    assert batch.handleClick(55,66)
    assert session.project.observations == before and batch.batch.index == 0
    batch.pause()


def test_manual_navigation_pauses_batch_and_resume_returns_to_target(qtbot, synthetic_video_path, tmp_path):
    window, session, _ = _opened_window(qtbot, synthetic_video_path, tmp_path, _FakeRunner())
    batch = window.batchAnnotationActions
    batch.start((3, 4))
    qtbot.waitUntil(lambda: window.presented_frame_index == 3 and not window._has_pending_request)
    window.jumpToFrame(1)
    assert batch.batch.paused and not window.videoView.is_annotation_mode()
    batch.resume()
    qtbot.waitUntil(lambda: window.presented_frame_index == 3 and not window._has_pending_request)
    assert batch.active and window.videoView.is_annotation_mode()
    window.startPlayback()
    assert batch.batch.paused
    window.stopPlayback()


def test_batch_selection_does_not_reenter_task_panel_during_list_clear(qtbot, synthetic_video_path, tmp_path, monkeypatch):
    window, session, _ = _opened_window(qtbot, synthetic_video_path, tmp_path, _FakeRunner())
    panel = window.trackingActions.panel
    calls = []
    monkeypatch.setattr(window.trackingActions, "refresh", lambda *_args: calls.append(True))
    item = QListWidgetItem("candidate")
    item.setData(Qt.ItemDataRole.UserRole, 1)
    panel.reviewCandidatesList.addItem(item)
    item.setSelected(True)
    assert window.batchAnnotationActions.correctButton.isEnabled()
    panel.setReviewBatch(None, None)
    assert not calls
    window.batchAnnotationActions._selectionChanged()
    assert not window.batchAnnotationActions.correctButton.isEnabled()


def test_explicit_single_correct_can_edit_while_batch_is_paused(qtbot, synthetic_video_path, tmp_path):
    from PySide6.QtCore import QPointF
    window, session, _ = _opened_window(qtbot, synthetic_video_path, tmp_path, _FakeRunner())
    run = _setup_infer_run_with_prediction(window, tmp_path)
    candidate = ReviewCandidate(1, ReviewPredictionSnapshot(10,20,0.4), {},{},(),0.8)
    session.set_active_review_batch(run.run_id, ActiveReviewBatch(uuid4(),{},(candidate,)))
    window.reviewActions.onRunSelected(run.run_id)
    window.batchAnnotationActions.start((1,), run.run_id)
    qtbot.waitUntil(lambda: window.presented_frame_index == 1 and not window._has_pending_request)
    window.reviewActions.startCorrectCurrent()
    assert window.batchAnnotationActions.batch.paused
    point = window.videoView.mapFromScene(QPointF(20, 30))
    assert point is not None
    window._onAnnotationClicked(point)
    assert session.get_suggested_frame_review(run.run_id).reviewed_frames[1].disposition == "corrected"
    assert window.batchAnnotationActions.batch.frames == (1,)
