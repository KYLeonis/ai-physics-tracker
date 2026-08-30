"""`python -m ai_physics_tracker` 的组合根。"""

import os
from pathlib import Path

from ai_physics_tracker.application.video_session import VideoSession
from ai_physics_tracker.gui.app import run
from ai_physics_tracker.infrastructure.opencv_video_reader import OpenCVVideoReader
from ai_physics_tracker.infrastructure.project_repository import ProjectRepository
from ai_physics_tracker.infrastructure.ffprobe_timing import FFprobeTimingProbe

raise SystemExit(
    run(lambda: VideoSession(OpenCVVideoReader()), ProjectRepository(),
        FFprobeTimingProbe(Path(os.environ["AI_PHYSICS_FFPROBE"]) if os.environ.get("AI_PHYSICS_FFPROBE") else None))
)
