"""图表面板参数 "?" 帮助提示的轻量测试（HR 反馈 2）。"""

from PySide6.QtWidgets import QApplication

from ai_physics_tracker.gui.chart_panel import ChartPanel


def test_parameter_help_labels_present_with_tooltips(qtbot) -> None:
    panel = ChartPanel(None if QApplication.instance() else QApplication([]))
    qtbot.addWidget(panel)

    for label in (panel.sgHelp, panel.orderHelp, panel.sourceHelp):
        assert label.text() == "?"
        assert label.toolTip()  # 有中文解释与调参效果说明
