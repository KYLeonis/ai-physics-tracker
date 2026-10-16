"""临时诊断：Windows 窗口最小宽度贡献者。窄窗修复落地后删除本文件。"""

from PySide6.QtWidgets import QApplication, QLayoutItem, QLabel, QPushButton

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
    assert window.currentWorkspace == "acquire"

    lines: list[str] = [f"initial compact={compact}"]

    def measure(tag: str) -> None:
        header = window.workflowHeader
        lines.append(
            f"{tag}: window={window.minimumSizeHint().width()} winMinW={window.minimumWidth()} "
            f"mainLay={window.layout().minimumSize().width()} "
            f"central={window.centralWidget().minimumSizeHint().width()} "
            f"stack={window._workspaceStack.minimumSizeHint().width()} "
            f"header={header.minimumSizeHint().width()} headerLay={header.layout().minimumSize().width()} "
            f"dockMinW={tracking_panel.minimumWidth()}"
        )

    def dump(layout, indent: str) -> None:
        if layout is None:
            return
        for index in range(layout.count()):
            item: QLayoutItem = layout.itemAt(index)
            widget = item.widget()
            if widget is not None:
                extra = f" txt={widget.text()[:36]!r}" if isinstance(widget, (QPushButton, QLabel)) else ""
                lines.append(
                    f"{indent}W {widget.metaObject().className()} itemMin={item.minimumSize().width()} "
                    f"hidden={widget.isHidden()}{extra}"
                )
            elif item.layout() is not None:
                lines.append(f"{indent}L {item.layout().metaObject().className()} itemMin={item.minimumSize().width()}")
                dump(item.layout(), indent + "  ")
            else:
                lines.append(f"{indent}S spacer itemMin={item.minimumSize().width()}")

    measure("pre-events")
    QApplication.processEvents()
    QApplication.processEvents()
    measure("post-events")
    lines.append("--- window layout dump ---")
    dump(window.layout(), "  ")
    lines.append("--- central layout dump ---")
    dump(window.centralWidget().layout(), "  ")
    lines.append("--- header layout dump ---")
    dump(window.workflowHeader.layout(), "  ")

    expanded = compact + 200
    window.resize(expanded, 760)
    lines.append(f"requested={expanded} actual={window.size().width()}")
    assert window.size().width() == expanded, "\n".join(lines)
