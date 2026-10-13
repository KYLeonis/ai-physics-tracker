"""分析页参考视频的只读边界与获取轨迹编辑恢复回归。"""

from PySide6.QtCore import QPoint, QPointF
from tests.gui.test_tracking_actions import _FakeRunner, _opened_window


def test_analysis_cannot_reenable_or_write_annotations(qtbot, synthetic_video_path, tmp_path):
    window, session, track_id = _opened_window(qtbot, synthetic_video_path, tmp_path, _FakeRunner())
    before = session.project
    assert window.videoView.is_annotation_mode()
    window.setWorkspace("analysis")
    assert not window.videoView.is_annotation_mode()
    window._onTrackSelectionChanged()
    assert not window.videoView.is_annotation_mode()
    assert window.jumpToFrame(0)
    assert not window.videoView.is_annotation_mode()
    # 即使外部调用错误启用 view 的 mode，写入入口仍拒绝。
    window.videoView.set_annotation_mode(True)
    window._onAnnotationClicked(QPoint(5, 5))
    window._deleteCurrentManualPoint()
    assert not window.deletePointButton.isEnabled()
    window._onScaleLineDrawn(QPointF(0, 0), QPointF(20, 0))
    window._onOriginClicked(QPointF(5, 5))
    assert session.project == before
    window.setWorkspace("acquire")
    assert window.videoView.is_annotation_mode()
    assert window.selectedTrackId == track_id


def test_analysis_clears_calibration_mode_and_rejects_new_mode(qtbot, synthetic_video_path, tmp_path):
    window, _session, _track_id = _opened_window(qtbot, synthetic_video_path, tmp_path, _FakeRunner())
    window.drawScaleButton.click()
    window.setWorkspace("analysis")
    assert not window.drawScaleButton.isChecked()
    assert not window.setOriginButton.isChecked()
    window.drawScaleButton.click()
    assert not window.drawScaleButton.isChecked()
    window.setOriginButton.click()
    assert not window.setOriginButton.isChecked()


def test_analysis_shortcuts_and_hidden_mutators_cannot_write(qtbot, synthetic_video_path, tmp_path):
    from uuid import uuid4
    from ai_physics_tracker.application.suggested_frame_review import ActiveReviewBatch, ReviewCandidate, ReviewPredictionSnapshot
    from tests.gui.test_suggested_frame_review_actions import _setup_infer_run_with_prediction
    window, session, track = _opened_window(qtbot, synthetic_video_path, tmp_path, _FakeRunner())
    run = _setup_infer_run_with_prediction(window, tmp_path)
    candidate = ReviewCandidate(1, ReviewPredictionSnapshot(10,20,0.4), {},{},(),0.8)
    session.set_active_review_batch(run.run_id, ActiveReviewBatch(uuid4(),{},(candidate,)))
    window.reviewActions.onRunSelected(run.run_id)
    session.add_calibration(window.activeVideoId, (0,0), (20,0), 1, "m")
    session.mark_point(track, 3, 10, 20)
    window.setWorkspace("analysis")
    before = session.project
    for action in (window._undo, window._redo, window._addTrack, window._deleteSelectedTrack,
                   window._onReviewAcceptShortcut, window._onReviewSkipShortcut,
                   window._deleteActiveCalibration, window._deleteInactiveCalibration,
                   window._editActiveScale):
        action()
    window._onRotationChanged(90)
    window._onCalibrationSelected(-1)
    assert session.project == before
    assert not window.undoButton.isEnabled()
    window.setWorkspace("acquire")
    window._undo()
    assert session.project != before
