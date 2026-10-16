"""临时诊断：Windows 窗口最小宽度贡献者。窄窗修复落地后删除本文件。"""

from PySide6.QtGui import QFontMetrics
from PySide6.QtWidgets import QApplication, QLabel, QPushButton, QStackedWidget, QWidget

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

    header = window.workflowHeader
    lines: list[str] = []

    def walk(widget: QWidget, indent: str) -> None:
        try:
            minimum_width = widget.minimumWidth()
            hint_width = widget.minimumSizeHint().width()
        except RuntimeError:
            return
        text = widget.text() if isinstance(widget, (QPushButton, QLabel)) else ""
        policy = widget.sizePolicy()
        lines.append(
            f"{indent}{widget.metaObject().className()} minW={minimum_width} "
            f"minHint={hint_width} pol={policy.horizontalPolicy()} vis={widget.isVisible()} "
            f"txt={text[:70]!r}"
        )
        for child in widget.findChildren(QWidget):
            if child.parentWidget() is widget:
                walk(child, indent + "  ")

    walk(header, "  ")

    font = QApplication.font()
    metrics = QFontMetrics(font)
    lines.append(
        f"font={font.family()} px={font.pixelSize()} pt={font.pointSize()} "
        f"dpr={window.devicePixelRatio()} ref_width="
        f"{metrics.horizontalAdvance('Fit formula / Measure intervals')}"
    )
    dock = window.trackingActions.panel
    lines.append(
        f"dock minW={dock.minimumWidth()} minHint={dock.minimumSizeHint().width()} "
        f"visible={dock.isVisible()} floating={dock.isFloating()}"
    )

    pages = []
    for stack in window.findChildren(QStackedWidget):
        pages.append(
            f"stack vis={stack.isVisible()} pageHints="
            + str([page.minimumSizeHint().width() for page in (stack.widget(i) for i in range(stack.count()))])
        )

    report = [
        "HEADER TREE:",
        *lines,
        f"stacks: {pages}",
        f"initial hint={compact} post-roundtrip hint={window.minimumSizeHint().width()} "
        f"requested={expanded} actual={window.size().width()}",
    ]
    assert window.size().width() == expanded, "\n".join(report)
