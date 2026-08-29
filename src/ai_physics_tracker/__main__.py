"""`python -m ai_physics_tracker` 的组合根。"""

from ai_physics_tracker.application.video_session import VideoSession
from ai_physics_tracker.gui.app import run
from ai_physics_tracker.infrastructure.opencv_video_reader import OpenCVVideoReader

raise SystemExit(run(VideoSession(OpenCVVideoReader())))
