"""桌面应用启动入口。"""

import sys
from typing import Callable

from PySide6.QtWidgets import QApplication

from ai_physics_tracker.application.project_session import ProjectRepositoryPort
from ai_physics_tracker.application.video_session import VideoSession
from ai_physics_tracker.application.video_timing import VideoTimingProbe
from ai_physics_tracker.gui.launch_context import set_application_identity
from ai_physics_tracker.gui.main_window import MainWindow


def run(
    session_factory: Callable[[], VideoSession],
    annotation_repository: ProjectRepositoryPort,
    timing_probe: VideoTimingProbe,
    argv: list[str] | None = None,
) -> int:
    """启动 Qt 事件循环，返回进程退出码。"""

    arguments = sys.argv if argv is None else argv
    # AppDataLocation（managed runtime 指针/文件日志）依赖应用身份，先于任何使用
    set_application_identity()
    app = QApplication.instance() or QApplication(arguments)
    window = MainWindow(session_factory, annotation_repository, timing_probe)
    window.show()
    return app.exec()
