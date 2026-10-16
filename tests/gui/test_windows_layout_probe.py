"""临时诊断：Windows 窗口最小宽度贡献者。窄窗修复落地后删除本文件。"""

from PySide6.QtWidgets import QLabel, QPushButton, QStackedWidget, QWidget

from ai_physics_tracker.application.video_session import VideoSession
from ai_physics_tracker.gui.main_window import MainWindow
from ai_physics_tracker.infrastructure.ffprobe_timing import FFprobeTimingProbe
from ai_physics_tracker.infrastructure.opencv_video_reader import OpenCVVideoReader
from ai_physics_tracker.infrastructure.project_repository import ProjectRepository


def test_probe_window_min_width_after_workspace_roundtrip(qtbot) -> None:
    window = MainWindow(
        lambda: VideoSession(OpenCVVideoReader()), ProjectRepository(), FFprobeTimingProbe()
    )
    qtbot.addWidget(window)
    window.show()

    compact = max(900, window.minimumSizeHint().width())
    window.resize(compact, 520)

    tracking_panel = window.trackingActions.panel
    tracking_panel.setFloating(True)
    tracking_panel.resize(640, 480)
    tracking_panel.setFloating(False)

    window.setWorkspace("analysis")
    window.setWorkspace("acquire")

    expanded = compact + 200
    window.resize(expanded, 760)

    rows: list[str] = []

    def walk(widget: QWidget) -> None:
        try:
            minimum_width = widget.minimumWidth()
            hint_width = widget.minimumSizeHint().width()
        except RuntimeError:
            return
        if max(minimum_width, hint_width) >= 300:
            label = widget.text() if isinstance(widget, (QPushButton, QLabel)) else ""
            rows.append(
                f"W={max(minimum_width, hint_width):4d} {widget.metaObject().className()} "
                f"obj={widget.objectName() or '-'} minW={minimum_width} minHint={hint_width} "
                f"vis={widget.isVisible()} txt={label[:60]!r}"
            )
        for child in widget.findChildren(QWidget):
            if child.parentWidget() is widget:
                walk(child)

    walk(window)

    header = window.workflowHeader
    header_buttons = [
        button.text() for button in header.nextStepButtons if button.isVisible()
    ]
    pages = []
    for stack in window.findChildren(QStackedWidget):
        pages.append(
            f"stack vis={stack.isVisible()} pageHints="
            + str([page.minimumSizeHint().width() for page in (stack.widget(i) for i in range(stack.count()))])
        )

    report = [
        "MIN-WIDTH CONTRIBUTORS >=300:",
        *sorted(rows, reverse=True)[:30],
        f"header next buttons: {header_buttons}",
        f"stacks: {pages}",
        f"initial hint={compact} post-roundtrip hint={window.minimumSizeHint().width()} "
        f"requested={expanded} actual={window.size().width()}",
    ]
    assert window.size().width() == expanded, "\n".join(report)
