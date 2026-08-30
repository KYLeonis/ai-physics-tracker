"""桌面应用启动入口。"""

import sys
from typing import Callable

from PySide6.QtWidgets import QApplication

from ai_physics_tracker.application.project_session import ProjectRepositoryPort
from ai_physics_tracker.application.video_session import VideoSession
from ai_physics_tracker.application.video_timing import VideoTimingProbe
from ai_physics_tracker.gui.main_window import MainWindow


def run(
    session_factory: Callable[[], VideoSession],
    annotation_repository: ProjectRepositoryPort,
    timing_probe: VideoTimingProbe,
    argv: list[str] | None = None,
) -> int:
    """启动 Qt 事件循环，返回进程退出码。"""

    arguments = sys.argv if argv is None else argv
    app = QApplication.instance() or QApplication(arguments)
    window = MainWindow(session_factory, annotation_repository, timing_probe)
    window.show()
    return app.exec()
