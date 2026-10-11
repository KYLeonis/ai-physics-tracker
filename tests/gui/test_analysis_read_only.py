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
