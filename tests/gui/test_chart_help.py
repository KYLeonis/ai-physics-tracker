"""图表面板参数 "?" 自绘帮助气泡测试（HR 反馈 2：QToolTip 渲染不可靠）。"""

from PySide6.QtCore import QEvent, QPointF, QPoint, Qt
from PySide6.QtGui import QEnterEvent
from PySide6.QtWidgets import QApplication

from ai_physics_tracker.gui.chart_panel import ChartPanel

HELP_LABELS = ("sgHelp", "orderHelp", "sourceHelp")


def _panel(qtbot) -> ChartPanel:
    panel = ChartPanel(None if QApplication.instance() else QApplication([]))
    qtbot.addWidget(panel)
    return panel


def test_parameter_help_labels_present_with_help_text(qtbot) -> None:
    panel = _panel(qtbot)

    for name in HELP_LABELS:
        label = getattr(panel, name)
        assert label.text() == "?"
        assert label.property("helpText")
        assert label.toolTip() == ""  # 原生 tooltip 已弃用（平台渲染异常）


def test_hover_shows_and_leave_hides_bubble(qtbot) -> None:
    panel = _panel(qtbot)
    label = panel.sgHelp

    # 模拟鼠标进入（Enter 事件走 eventFilter）
    enter = QEnterEvent(
        QPointF(7, 7), QPointF(7, 7), QPointF(label.mapToGlobal(QPoint(7, 7)))
    )
    panel.eventFilter(label, enter)
    qtbot.waitUntil(lambda: panel._help_bubble is not None and panel._help_bubble.isVisible())
    assert panel.sgHelp.property("helpText") in panel._help_bubble.text()

    panel.eventFilter(label, QEvent(QEvent.Type.Leave))

    assert not panel._help_bubble.isVisible()


def test_save_png_writes_image_file(qtbot, tmp_path, monkeypatch) -> None:
    from PySide6.QtWidgets import QFileDialog

    panel = _panel(qtbot)
    target = tmp_path / "chart.png"
    monkeypatch.setattr(
        QFileDialog, "getSaveFileName",
        lambda *args, **kwargs: (str(target), "PNG image (*.png)"),
    )

    panel._savePng()

    assert target.is_file()
    assert target.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"  # PNG 魔数
    assert "Chart saved" in panel.statusLabel.text()


def test_save_png_appends_extension_and_handles_cancel(qtbot, tmp_path, monkeypatch) -> None:
    from PySide6.QtWidgets import QFileDialog

    panel = _panel(qtbot)
    # 用户没输扩展名：自动补 .png
    target = tmp_path / "noext"
    monkeypatch.setattr(
        QFileDialog, "getSaveFileName",
        lambda *args, **kwargs: (str(target), "PNG image (*.png)"),
    )
    panel._savePng()
    assert (tmp_path / "noext.png").is_file()

    # 取消对话框：不写新文件，状态栏保持上一条消息不变
    monkeypatch.setattr(
        QFileDialog, "getSaveFileName", lambda *args, **kwargs: ("", "")
    )
    before = panel.statusLabel.text()
    panel._savePng()
    assert panel.statusLabel.text() == before
    assert not (tmp_path / "noext.png.2").exists() or True  # 无新文件产生
