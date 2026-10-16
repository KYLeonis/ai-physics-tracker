"""临时诊断：Windows 窗口最小宽度贡献者。窄窗修复落地后删除本文件。"""

from PySide6.QtWidgets import QApplication, QLayoutItem, QWidget

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

    window.trackingActions.panel.setFloating(True)
    window.trackingActions.panel.resize(640, 480)
    window.trackingActions.panel.setFloating(False)

    window.setWorkspace("analysis")
    window.setWorkspace("acquire")
    qtbot.wait(50)

    lines: list[str] = []

    def dump_layout(layout, indent: str) -> None:
        if layout is None:
            return
        for index in range(layout.count()):
            item: QLayoutItem = layout.itemAt(index)
            widget = item.widget()
            if widget is not None:
                lines.append(
                    f"{indent}W {widget.metaObject().className()} itemMin={item.minimumSize().width()} "
                    f"widMinW={widget.minimumWidth()} hidden={widget.isHidden()} "
                    f"txt={widget.text()[:40]!r}" if hasattr(widget, "text") else
                    f"{indent}W {widget.metaObject().className()} itemMin={item.minimumSize().width()} "
                    f"widMinW={widget.minimumWidth()} hidden={widget.isHidden()}"
                )
            elif item.layout() is not None:
                lines.append(f"{indent}L {item.layout().metaObject().className()} itemMin={item.minimumSize().width()}")
                dump_layout(item.layout(), indent + "  ")
            else:
                lines.append(f"{indent}S spacer itemMin={item.minimumSize().width()}")

    header = window.workflowHeader
    lines.append(f"header layout cached min = {header.layout().minimumSize().width()}")
    dump_layout(header.layout(), "  ")
    header.layout().invalidate()
    header.layout().activate()
    lines.append(f"header layout after invalidate+activate min = {header.layout().minimumSize().width()}")
    lines.append(f"header minimumSizeHint after invalidate = {header.minimumSizeHint().width()}")

    central = window.centralWidget()
    central.layout().invalidate()
    central.layout().activate()
    lines.append(f"central fresh min = {central.minimumSizeHint().width()}")

    stack = window._workspaceStack
    stack.layout().invalidate()
    stack.layout().activate()
    lines.append(f"stack fresh min = {stack.minimumSizeHint().width()}")

    QApplication.processEvents()
    lines.append(f"window hint after full settle = {window.minimumSizeHint().width()}")

    expanded = compact + 200
    window.resize(expanded, 760)
    lines.append(f"initial={compact} requested={expanded} actual={window.size().width()}")
    assert window.size().width() == expanded, "\n".join(lines)
