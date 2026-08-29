"""Desktop application bootstrap."""

import sys

from PySide6.QtWidgets import QApplication

from ai_physics_tracker.application.video_session import VideoSession
from ai_physics_tracker.gui.main_window import MainWindow


def run(session: VideoSession, argv: list[str] | None = None) -> int:
    """Start the Qt event loop and return its process exit code."""

    arguments = sys.argv if argv is None else argv
    app = QApplication.instance() or QApplication(arguments)
    window = MainWindow(session)
    window.show()
    return app.exec()
