"""图表面板参数 "?" 自绘帮助气泡测试（HR 反馈 2：QToolTip 渲染不可靠）。"""

from unittest.mock import Mock
from uuid import UUID

from PySide6.QtCore import QEvent, QPointF, QPoint, Qt
from PySide6.QtGui import QEnterEvent, QImage
from PySide6.QtWidgets import QApplication

from ai_physics_tracker.application.chart_data import ChartData, ChartSeries
from ai_physics_tracker.gui.chart_panel import ChartPanel

HELP_LABELS = ("sgHelp", "orderHelp", "sourceHelp")


def _panel(qtbot) -> ChartPanel:
    panel = ChartPanel(None if QApplication.instance() else QApplication([]))
    qtbot.addWidget(panel)
    return panel


def _xy_chart_data() -> ChartData:
    return ChartData(
        title="x-y",
        x_label="x",
        y_label="y",
        x_unit="px",
        y_unit="px",
        series=(
            ChartSeries(
                track_id=UUID(int=1),
                name="Track 1",
                color="#e6194b",
                component="position",
                frames=(0, 1, 2),
                x_values=(10.0, 20.0, 30.0),
                y_values=(15.0, 25.0, 35.0),
                connect=(True, True, False),
                unit="px",
                status="valid",
                pipeline_summary="",
            ),
        ),
        messages=(),
        pixel_coordinates=True,
    )


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
    data = _xy_chart_data()
    panel.plots["xy"].renderData(data)
    panel.tabs.setCurrentIndex(4)
    target = tmp_path / "chart.png"
    monkeypatch.setattr(
        QFileDialog, "getSaveFileName",
        lambda *args, **kwargs: (str(target), "PNG image (*.png)"),
    )
    grabs = {}
    for kind, plot in panel.plots.items():
        spy = Mock(wraps=plot.grab)
        monkeypatch.setattr(plot, "grab", spy)
        grabs[kind] = spy

    panel._savePng()

    assert panel.currentPlot.data is data
    assert grabs["xy"].call_count == 1
    assert sum(spy.call_count for spy in grabs.values()) == 1
    assert target.is_file()
    assert target.stat().st_size > 0
    assert target.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"  # PNG 魔数
    image = QImage(str(target))
    assert not image.isNull()
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
    keep = tmp_path / "keep.txt"
    keep.write_text("keep", encoding="utf-8")

    # 取消对话框：不写新文件，状态栏保持上一条消息不变
    before_files = {
        path.relative_to(tmp_path): path.read_bytes()
        for path in tmp_path.iterdir()
        if path.is_file()
    }
    monkeypatch.setattr(
        QFileDialog, "getSaveFileName", lambda *args, **kwargs: ("", "")
    )
    before = panel.statusLabel.text()
    panel._savePng()
    after_files = {
        path.relative_to(tmp_path): path.read_bytes()
        for path in tmp_path.iterdir()
        if path.is_file()
    }
    assert after_files == before_files
    assert panel.statusLabel.text() == before


def test_save_png_reports_failure_without_mutating_chart_data(
    qtbot, tmp_path, monkeypatch
) -> None:
    from PySide6.QtWidgets import QFileDialog

    panel = _panel(qtbot)
    data = _xy_chart_data()
    panel.plots["xy"].renderData(data)
    panel.tabs.setCurrentIndex(4)
    target = tmp_path / "failed.png"
    monkeypatch.setattr(
        QFileDialog, "getSaveFileName",
        lambda *args, **kwargs: (str(target), "PNG image (*.png)"),
    )
    failed_pixmap = Mock()
    failed_pixmap.save.return_value = False
    monkeypatch.setattr(panel.plots["xy"], "grab", lambda: failed_pixmap)
    before_data = panel.currentPlot.data
    before_items = tuple(panel.currentPlot._items)

    panel._savePng()

    failed_pixmap.save.assert_called_once_with(str(target), "PNG")
    assert panel.statusLabel.text() == f"Failed to save chart: {target}"
    assert panel.currentPlot.data is before_data
    assert tuple(panel.currentPlot._items) == before_items
    assert not target.exists()
