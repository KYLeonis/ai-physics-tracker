"""`python -m ai_physics_tracker` 与 frozen 应用的组合根。"""

import multiprocessing
import os
from pathlib import Path


def _timing_probe_path() -> Path | None:
    """显式 env 覆盖 > frozen 随包 FFprobe > None（PATH 查找，dev 既有行为）。"""

    override = os.environ.get("AI_PHYSICS_FFPROBE")
    if override:
        return Path(override)
    from ai_physics_tracker.gui.launch_context import bundled_ffprobe

    return bundled_ffprobe()


def main(argv: list[str] | None = None) -> int:
    # frozen 多进程（task_runner 的 spawn）必须在任何子进程派生前注册引导
    multiprocessing.freeze_support()
    from ai_physics_tracker.gui.launch_context import (
        configure_file_logging,
        set_application_identity,
    )
    from ai_physics_tracker.application.video_session import VideoSession
    from ai_physics_tracker.gui.app import run
    from ai_physics_tracker.infrastructure.opencv_video_reader import OpenCVVideoReader
    from ai_physics_tracker.infrastructure.project_repository import ProjectRepository
    from ai_physics_tracker.infrastructure.ffprobe_timing import FFprobeTimingProbe

    # 应用身份先于文件日志/AppDataLocation 解析(否则落到通用目录)
    set_application_identity()
    configure_file_logging()
    return run(
        lambda: VideoSession(OpenCVVideoReader()),
        ProjectRepository(),
        FFprobeTimingProbe(_timing_probe_path()),
        argv=argv,
    )


if __name__ == "__main__":
    raise SystemExit(main())
