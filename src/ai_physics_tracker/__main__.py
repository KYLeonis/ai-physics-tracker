"""`python -m ai_physics_tracker` 的组合根。"""

from ai_physics_tracker.application.video_session import VideoSession
from ai_physics_tracker.gui.app import run
from ai_physics_tracker.infrastructure.opencv_video_reader import OpenCVVideoReader
from ai_physics_tracker.infrastructure.project_repository import ProjectRepository

raise SystemExit(
    run(VideoSession(OpenCVVideoReader()), ProjectRepository())
)
