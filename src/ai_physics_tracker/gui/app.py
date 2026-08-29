"""桌面应用启动入口。"""

import sys

from PySide6.QtWidgets import QApplication

from ai_physics_tracker.application.project_session import ProjectRepositoryPort
from ai_physics_tracker.application.video_session import VideoSession
from ai_physics_tracker.gui.main_window import MainWindow


def run(
    session: VideoSession,
    annotation_repository: ProjectRepositoryPort,
    argv: list[str] | None = None,
) -> int:
    """启动 Qt 事件循环，返回进程退出码。"""

    arguments = sys.argv if argv is None else argv
    app = QApplication.instance() or QApplication(arguments)
    window = MainWindow(session, annotation_repository)
    window.show()
    return app.exec()
