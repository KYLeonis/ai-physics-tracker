"""Phase 3.1 标定 GUI（比例尺、原点、旋转、overlay）的 Qt offscreen 测试。

验证 phase3-requirements.md R1、R2、R3 以及 AC-1、AC-2：
- 绘制比例尺线段 + 输入已知长度 → 创建 Calibration
- 点击设置原点 → 更新 active calibration origin
- 调整旋转角度 → 更新 active calibration rotation_deg
- overlay 标定与坐标系随状态实时更新
- 标定选择器切换与删除
- Esc 退出标定交互模式
- Undo/Redo 恢复标定状态
"""

from pathlib import Path
from dataclasses import replace
import pytest
from PySide6.QtCore import QPointF, Qt
from PySide6.QtWidgets import QInputDialog
from pytestqt.qtbot import QtBot

from ai_physics_tracker.application.video_session import VideoSession
from ai_physics_tracker.gui.calibration_dialog import CalibrationDialog
from ai_physics_tracker.gui.main_window import MainWindow
from ai_physics_tracker.infrastructure.opencv_video_reader import OpenCVVideoReader
from ai_physics_tracker.infrastructure.project_repository import ProjectRepository
from ai_physics_tracker.infrastructure.ffprobe_timing import FFprobeTimingProbe


def _window() -> MainWindow:
    return MainWindow(
        lambda: VideoSession(OpenCVVideoReader()), ProjectRepository(), FFprobeTimingProbe()
    )


def _opened_window(qtbot: QtBot, synthetic_video_path: Path) -> MainWindow:
    window = _window()
    qtbot.addWidget(window)
    window.show()
    assert window.openVideo(synthetic_video_path, show_error=False)
    return window


def _inside_pos(window: MainWindow, pixel_x: float, pixel_y: float) -> QPointF:
    return window.videoView.mapFromScene(QPointF(pixel_x, pixel_y))


def test_draw_scale_button_toggles_mode_and_excludes_annotation(
    qtbot: QtBot, synthetic_video_path: Path
) -> None:
    window = _opened_window(qtbot, synthetic_video_path)

    # 未打开 Track 时进入标定模式
    window.drawScaleButton.click()
    assert window.drawScaleButton.isChecked()
    assert window.videoView.is_calibration_mode() == "scale"
    assert not window.videoView.is_annotation_mode()

    # 点击 Track 应退出标定模式进入标注模式
    window.addTrackButton.click()
    assert not window.drawScaleButton.isChecked()
    assert window.videoView.is_calibration_mode() is None
    assert window.videoView.is_annotation_mode()

    # 再次点击比例尺按钮应退出标注模式
    window.drawScaleButton.click()
    assert window.drawScaleButton.isChecked()
    assert window.videoView.is_calibration_mode() == "scale"
    assert not window.videoView.is_annotation_mode()


def test_draw_scale_line_creates_calibration(
    qtbot: QtBot, synthetic_video_path: Path, monkeypatch
) -> None:
    window = _opened_window(qtbot, synthetic_video_path)

    # 自动确认标定对话框 (1.0 m)
    monkeypatch.setattr(
        CalibrationDialog,
        "exec",
        lambda self: 1,  # QDialog.Accepted
    )

    window.drawScaleButton.click()
    p1 = _inside_pos(window, 10.0, 15.0)
    p2 = _inside_pos(window, 50.0, 15.0)

    qtbot.mousePress(window.videoView.viewport(), Qt.MouseButton.LeftButton, pos=p1)
    qtbot.mouseMove(window.videoView.viewport(), pos=p2)
    qtbot.mouseRelease(window.videoView.viewport(), Qt.MouseButton.LeftButton, pos=p2)

    session = window._annotation_session
    assert session is not None
    assert len(session.calibrations) == 1
    cal = session.calibrations[0]
    assert cal.name == "Calibration 1"
    assert cal.known_length == 1.0
    assert cal.unit == "mm"
    assert session.active_calibration(session.project.videos[0].video_id) == cal

    # UI 状态检查
    assert "Active: Calibration 1" in window.calibrationStatusLabel.text()
    assert window.setOriginButton.isEnabled()
    assert window.rotationSpinBox.isEnabled()
    assert window.deleteCalibrationButton.isEnabled()
    assert window.videoView.calibration_view() is not None


def test_set_origin_updates_active_calibration(
    qtbot: QtBot, synthetic_video_path: Path, monkeypatch
) -> None:
    window = _opened_window(qtbot, synthetic_video_path)
    monkeypatch.setattr(CalibrationDialog, "exec", lambda self: 1)

    # 先绘制标定
    window._onScaleLineDrawn(QPointF(10.0, 10.0), QPointF(50.0, 10.0))
    session = window._annotation_session
    assert session is not None

    # 进入设置原点模式
    window.setOriginButton.click()
    assert window.videoView.is_calibration_mode() == "origin"

    # 点击 (20.0, 30.0) 作为原点
    target = _inside_pos(window, 20.0, 30.0)
    qtbot.mouseClick(window.videoView.viewport(), Qt.MouseButton.LeftButton, pos=target)

    active = session.active_calibration(session.project.videos[0].video_id)
    assert active is not None
    assert active.origin_px is not None
    assert abs(active.origin_px[0] - 20.0) <= 1.0
    assert abs(active.origin_px[1] - 30.0) <= 1.0
    assert not window.setOriginButton.isChecked()
    assert window.videoView.is_calibration_mode() is None


def test_rotation_spinbox_updates_calibration(
    qtbot: QtBot, synthetic_video_path: Path, monkeypatch
) -> None:
    window = _opened_window(qtbot, synthetic_video_path)
    monkeypatch.setattr(CalibrationDialog, "exec", lambda self: 1)

    window._onScaleLineDrawn(QPointF(10.0, 10.0), QPointF(50.0, 10.0))
    session = window._annotation_session
    assert session is not None
    video_id = session.project.videos[0].video_id

    window.rotationSpinBox.setValue(45.0)

    active = session.active_calibration(video_id)
    assert active is not None
    assert active.rotation_deg == 45.0
    assert window.videoView.calibration_view().rotation_deg == 45.0


def test_switch_and_delete_calibration(
    qtbot: QtBot, synthetic_video_path: Path, monkeypatch
) -> None:
    window = _opened_window(qtbot, synthetic_video_path)
    monkeypatch.setattr(CalibrationDialog, "exec", lambda self: 1)

    window._onScaleLineDrawn(QPointF(0.0, 0.0), QPointF(20.0, 0.0))
    window._onScaleLineDrawn(QPointF(0.0, 0.0), QPointF(40.0, 0.0))

    session = window._annotation_session
    assert session is not None
    video_id = session.project.videos[0].video_id
    assert len(session.calibrations) == 2

    # 当前 active 是 Calibration 2
    assert session.active_calibration(video_id).name == "Calibration 2"

    # 切换回 Calibration 1
    window.calibrationSelector.setCurrentIndex(0)
    assert session.active_calibration(video_id).name == "Calibration 1"

    # 删除当前 Calibration
    window.deleteCalibrationButton.click()
    assert len(session.calibrations) == 1
    assert session.active_calibration(video_id) is None
    assert window.calibrationSelector.currentIndex() == -1
    window.calibrationSelector.setCurrentIndex(0)
    assert session.active_calibration(video_id).name == "Calibration 2"


def test_esc_exits_calibration_modes(
    qtbot: QtBot, synthetic_video_path: Path
) -> None:
    window = _opened_window(qtbot, synthetic_video_path)

    window.drawScaleButton.click()
    assert window.videoView.is_calibration_mode() == "scale"

    window._exitAnnotationMode()
    assert not window.drawScaleButton.isChecked()
    assert window.videoView.is_calibration_mode() is None

    window.setOriginButton.setChecked(True)
    window._toggleSetOriginMode(True)
    assert window.videoView.is_calibration_mode() == "origin"

    window._exitAnnotationMode()
    assert not window.setOriginButton.isChecked()
    assert window.videoView.is_calibration_mode() is None


def test_undo_redo_calibration_updates_ui(
    qtbot: QtBot, synthetic_video_path: Path, monkeypatch
) -> None:
    window = _opened_window(qtbot, synthetic_video_path)
    monkeypatch.setattr(CalibrationDialog, "exec", lambda self: 1)

    window._onScaleLineDrawn(QPointF(10.0, 10.0), QPointF(50.0, 10.0))
    assert window.videoView.calibration_view() is not None
    assert window.undoButton.isEnabled()

    window.undoButton.click()
    assert window.videoView.calibration_view() is None
    assert window.calibrationStatusLabel.text() == "Status: Uncalibrated"

    window.redoButton.click()
    assert window.videoView.calibration_view() is not None
    assert "Active: Calibration 1" in window.calibrationStatusLabel.text()


def test_edit_scale_preserves_identity_raw_and_cancel_undo(
    qtbot: QtBot, synthetic_video_path: Path, monkeypatch,
) -> None:
    window = _opened_window(qtbot, synthetic_video_path)
    monkeypatch.setattr(CalibrationDialog, "exec", lambda self: 1)
    window._onScaleLineDrawn(QPointF(10, 10), QPointF(50, 10))
    window.addTrackButton.click()
    session = window.analysisSession
    track = session.tracks[0]
    for frame_index in range(5):
        session.mark_point(track.track_id, frame_index, 20 + frame_index, 30)
    session.compute_kinematics(track.track_id)
    before = session.project
    original = session.active_calibration(window.activeVideoId)
    monkeypatch.setattr(CalibrationDialog, "exec", lambda self: 0)
    window.editScaleButton.click()
    assert session.project == before

    def accept(dialog):
        assert dialog.lengthSpinBox.value() == pytest.approx(original.known_length)
        dialog.lengthSpinBox.setValue(2.5)
        dialog.unitComboBox.setCurrentText("cm")
        dialog.nameEdit.setText("Corrected scale")
        return 1
    monkeypatch.setattr(CalibrationDialog, "exec", accept)
    window.editScaleButton.click()
    changed = session.active_calibration(window.activeVideoId)
    assert changed == replace(original, known_length=2.5, unit="cm", name="Corrected scale")
    assert session.project.observations == before.observations
    assert all(item.status == "stale" for item in session.project.derived)
    assert window.videoView.calibration_view().known_length == pytest.approx(2.5)
    window.undoButton.click()
    assert session.project == before
    window.redoButton.click()
    assert session.active_calibration(window.activeVideoId) == changed
    stable = session.project
    def invalid_name(dialog):
        dialog.nameEdit.setText("   ")
        return 1
    monkeypatch.setattr(CalibrationDialog, "exec", invalid_name)
    window.editScaleButton.click()
    assert session.project == stable
    assert "Scale update failed" in window.statusBar().currentMessage()


def test_edit_scale_without_changes_keeps_full_precision_and_clean_state(
    qtbot: QtBot, synthetic_video_path: Path, tmp_path: Path, monkeypatch,
) -> None:
    window = _opened_window(qtbot, synthetic_video_path)
    monkeypatch.setattr(CalibrationDialog, "exec", lambda self: 1)
    window._onScaleLineDrawn(QPointF(10, 10), QPointF(50, 10))
    session = window.analysisSession
    original = replace(session.active_calibration(window.activeVideoId), known_length=1 / 3)
    session.update_calibration(original)
    session.save_as(tmp_path / "precise")
    before = session.project
    window.editScaleButton.click()
    assert session.project == before
    assert not session.is_dirty and not session.can_undo


def test_delete_inactive_preserves_active_results_and_is_undoable(
    qtbot: QtBot, synthetic_video_path: Path, monkeypatch,
) -> None:
    window = _opened_window(qtbot, synthetic_video_path)
    monkeypatch.setattr(CalibrationDialog, "exec", lambda self: 1)
    window._onScaleLineDrawn(QPointF(0, 0), QPointF(20, 0))
    window._onScaleLineDrawn(QPointF(0, 0), QPointF(40, 0))
    window.addTrackButton.click()
    session = window.analysisSession
    track = session.tracks[0]
    session.mark_point(track.track_id, 0, 20, 20)
    session.compute_kinematics(track.track_id)
    before = session.project
    inactive = session.calibrations[0]
    active = session.active_calibration(window.activeVideoId)
    monkeypatch.setattr(QInputDialog, "getItem", lambda *args: (args[3][0], False))
    window.deleteInactiveCalibrationButton.click()
    assert session.project == before
    def choose(*args):
        assert len(args[3]) == 1 and inactive.name in args[3][0]
        return args[3][0], True
    monkeypatch.setattr(QInputDialog, "getItem", choose)
    window.deleteInactiveCalibrationButton.click()
    assert session.calibrations == (active,)
    assert session.active_calibration(window.activeVideoId) == active
    assert session.project.observations == before.observations
    assert session.project.derived == before.derived
    assert not window.deleteInactiveCalibrationButton.isEnabled()
    window.undoButton.click()
    assert session.project == before
    window.redoButton.click()
    assert session.calibrations == (active,)
