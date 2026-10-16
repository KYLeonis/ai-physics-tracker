"""P6.3.1 用途入口与分析工具 header 的 GUI 回归。"""

from tests.gui.test_signal_analysis import _window


def test_analysis_purpose_buttons_route_existing_tabs_without_writing(
    qtbot, synthetic_video_path
):
    window, session, _track_id = _window(qtbot, synthetic_video_path)
    before = session.project

    expected = {
        "explore": (0, None),
        "measure": (1, 1),
        "fit": (1, 0),
    }
    for purpose, (tab_index, method_index) in expected.items():
        button = window.analysisPurposeButtons[purpose]
        assert button.isVisible()
        assert "Input:" in button.toolTip() and "Output:" in button.toolTip()
        button.click()
        assert window.currentWorkspace == "analysis"
        assert window.analysisTabs.currentIndex() == tab_index
        if method_index is not None:
            assert window.chartActions.signalPanel.methods.currentIndex() == method_index
        assert window.analysisPurpose == purpose
        assert purpose.replace("_", " ") in window.analysisPurposeLabel.text().lower()
        assert session.project == before


def test_analysis_tools_keeps_fit_default_and_can_retain_explicit_method(
    qtbot, synthetic_video_path
):
    window, session, _track_id = _window(qtbot, synthetic_video_path)
    before = session.project
    panel = window.chartActions.signalPanel

    panel.methods.setCurrentIndex(1)
    window.openAnalysisTools()
    assert window.analysisTabs.currentIndex() == 1
    assert panel.methods.currentIndex() == 0

    panel.methods.setCurrentIndex(1)
    window.openAnalysisTools(method_index=None)
    assert panel.methods.currentIndex() == 1
    assert session.project == before


def test_analysis_tools_header_uses_purpose_source_guidance(
    qtbot, synthetic_video_path
):
    window, session, _track_id = _window(qtbot, synthetic_video_path)
    window.trackingActions._context_key = None
    window.trackingActions.refresh()

    header = window.workflowHeader
    assert "Fit a formula" in header.nextStepLabel.text()
    assert "20" not in header.nextStepLabel.text()
    assert header.nextStepButtons[0].text() == "Preview initial curve"

    window.openAnalysisPurpose("measure")
    window.trackingActions._context_key = None
    window.trackingActions.refresh()
    assert "Measure repeat intervals" in header.nextStepLabel.text()
    assert "20" not in header.nextStepLabel.text()
    assert header.nextStepButtons[0].text() == "Show source"
    assert session.project.observations
