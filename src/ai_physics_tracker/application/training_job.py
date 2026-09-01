"""应用层训练准备：导出标注、复用 DLC 项目并登记 pending TrackingRun。"""

from dataclasses import replace
import logging
from pathlib import Path
from uuid import UUID

from ai_physics_tracker.application.project_session import (
    ProjectSession,
    ProjectSessionError,
)
from ai_physics_tracker.domain.tracking_run import (
    TrackingRun,
    create_tracking_run,
)
from ai_physics_tracker.infrastructure.dlc_adapter import DLCAdapter
from ai_physics_tracker.infrastructure.engine_adapter import (
    EngineAdapter,
    TrainingParams,
)
from ai_physics_tracker.infrastructure.opencv_video_reader import OpenCVVideoReader

logger = logging.getLogger(__name__)

MIN_MANUAL_POINTS_FOR_TRAINING = 3


def prepare_training(
    session: ProjectSession,
    track_id: UUID,
    video_reader: OpenCVVideoReader,
    params: TrainingParams | None = None,
    adapter: EngineAdapter | None = None,
    working_dir: Path | None = None,
) -> tuple[TrackingRun, Path]:
    """为指定 Track 准备 DLC 项目、导出最新标注并登记 pending TrackingRun。"""

    track = next((t for t in session.tracks if t.track_id == track_id), None)
    if track is None:
        raise ProjectSessionError(f"Unknown track_id: {track_id}")

    if any(r.track_id == track_id and r.status == "running" for r in session.tracking_runs()):
        raise ProjectSessionError("This track already has an active engine task")

    manual_points = tuple(
        point for point in session.manual_points(track_id) if point.status == "active"
    )
    if len(manual_points) < MIN_MANUAL_POINTS_FOR_TRAINING:
        raise ProjectSessionError(
            f"At least {MIN_MANUAL_POINTS_FOR_TRAINING} active manual points are required for training, got {len(manual_points)}"
        )

    video = next((v for v in session.project.videos if v.video_id == track.video_id), None)
    if video is None:
        raise ProjectSessionError(f"Video not found for track: {track.name}")

    resolved_video_path = session.resolve_video_path(video)
    if resolved_video_path is None or not resolved_video_path.is_file():
        raise ProjectSessionError(f"Cannot resolve local video file for: {video.display_name}")

    actual_adapter = adapter or DLCAdapter()
    actual_params = params or TrainingParams()

    track_prefix = str(track_id)[:8]
    if working_dir is not None:
        base_dir = working_dir
    elif session.project_root is not None:
        base_dir = session.project_root / "data" / "engines" / "dlc"
    else:
        raise ProjectSessionError("Save the project or supply a training working directory")

    base_dir.mkdir(parents=True, exist_ok=True)
    proj_name = f"dlc_{track_prefix}"
    proj_dir = base_dir / proj_name

    config_path = proj_dir / "config.yaml"
    if not config_path.is_file():
        config_path = actual_adapter.create_project(
            project_name=proj_name,
            experimenter="AIPhysicsTracker",
            video_path=resolved_video_path,
            working_dir=base_dir,
            bodyparts=["target"],
        )

    exported_count = actual_adapter.export_annotations(
        track_points=manual_points,
        video_reader=video_reader,
        config_path=config_path,
        scorer="AIPhysicsTracker",
        bodyparts=["target"],
    )
    logger.info(
        "Exported %d annotations to DLC project: %s",
        exported_count,
        config_path,
    )

    actual_adapter.create_training_dataset(
        config_path=config_path,
        num_shuffles=actual_params.shuffle,
    )

    run = create_tracking_run(
        video_id=track.video_id,
        track_id=track_id,
        task_type="train",
        engine="dlc",
        engine_version=actual_adapter.engine_version(),
        config=actual_params.to_config(),
    )
    if session.project_root is not None:
        try:
            relative_config = config_path.resolve().relative_to(session.project_root.resolve()).as_posix()
        except ValueError:
            relative_config = None
        if relative_config is not None:
            run = replace(run, extra_fields={"config_path": relative_config})
    session.record_tracking_run(run)

    return run, config_path
