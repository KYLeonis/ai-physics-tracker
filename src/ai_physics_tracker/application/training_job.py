"""应用层训练准备：导出标注、复用 DLC 项目并登记 pending TrackingRun。"""

from dataclasses import replace
import logging
from pathlib import Path
from typing import Any
from uuid import UUID

from ai_physics_tracker.application.project_session import (
    ProjectSession,
    ProjectSessionError,
)
from ai_physics_tracker.domain.tracking_run import (
    TrackingRun,
    create_tracking_run,
)
from ai_physics_tracker.application.refinement_history import (
    RefinementIterationInfo,
    ValidationLabelSnapshot,
    attach_refinement_iteration,
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
    mode: str = "restart",
    resume_from_run_id: UUID | None = None,
) -> tuple[TrackingRun, Path]:
    """为指定 Track 准备 DLC 项目、导出最新标注并登记 pending TrackingRun。

    mode/resume_from_run_id（ADR-0015）：记录 lineage 到迭代解释层与 config；
    resume 的 snapshot 文件校验由调用方在 worker 启动前完成。
    """
    if mode not in {"restart", "resume"}:
        raise ProjectSessionError(f"Unknown training mode: {mode!r}")
    if mode == "resume" and resume_from_run_id is None:
        raise ProjectSessionError("Resume training requires a resume source run")
    if mode == "restart" and resume_from_run_id is not None:
        raise ProjectSessionError("restart mode must not carry a resume source run")

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

    sorted_manual_points = sorted(manual_points, key=lambda p: p.frame_index)

    # Phase 5.4: 检查当前 Track 的 refinement 状态与 active validation series
    ref_state = session.get_refinement_state(track_id)
    active_series = ref_state.active_series
    train_indices: list[int] | None = None
    test_indices: list[int] | None = None
    training_label_snapshots: list[ValidationLabelSnapshot] = []

    if active_series is not None:
        valid, invalid_reason = session.validate_active_validation_series(track_id)
        if not valid:
            raise ProjectSessionError(
                f"Active validation series '{active_series.name}' is invalid: {invalid_reason}. "
                f"Please create a new validation series or deactivate it before training."
            )
        val_frame_set = set(active_series.frame_indices)
        train_indices = [
            i for i, p in enumerate(sorted_manual_points) if p.frame_index not in val_frame_set
        ]
        test_indices = [
            i for i, p in enumerate(sorted_manual_points) if p.frame_index in val_frame_set
        ]
        if not train_indices:
            raise ProjectSessionError(
                f"All active manual points belong to validation series '{active_series.name}'. "
                f"At least one manual point must be available for training."
            )
        for i in train_indices:
            p = sorted_manual_points[i]
            training_label_snapshots.append(
                ValidationLabelSnapshot(
                    point_id=p.point_id,
                    frame_index=p.frame_index,
                    pixel_x=p.pixel_x,
                    pixel_y=p.pixel_y,
                    modified_at=p.modified_at.isoformat(),
                )
            )
        validation_series_id = active_series.series_id
    else:
        for p in sorted_manual_points:
            training_label_snapshots.append(
                ValidationLabelSnapshot(
                    point_id=p.point_id,
                    frame_index=p.frame_index,
                    pixel_x=p.pixel_x,
                    pixel_y=p.pixel_y,
                    modified_at=p.modified_at.isoformat(),
                )
            )
        validation_series_id = None

    actual_adapter.create_training_dataset(
        config_path=config_path,
        num_shuffles=actual_params.shuffle,
        train_indices=train_indices,
        test_indices=test_indices,
    )

    completed_train_runs = [
        r
        for r in session.tracking_runs()
        if r.track_id == track_id and r.task_type == "train" and r.status == "completed"
    ]
    iteration_index = len(completed_train_runs)
    previous_training_run_id = completed_train_runs[-1].run_id if completed_train_runs else None
    source_infer_run_id = ref_state.active_infer_run_id

    review_summary_dict: dict[str, Any] | None = None
    if source_infer_run_id is not None:
        rev_sum = session.get_review_summary(source_infer_run_id)
        if rev_sum is not None:
            review_summary_dict = {
                "total_candidates": rev_sum.total_candidates,
                "reviewed_count": rev_sum.total_reviewed,
                "pending_count": rev_sum.pending_count,
                "accepted_count": rev_sum.accepted_count,
                "skipped_count": rev_sum.skipped_count,
                "corrected_count": rev_sum.corrected_count,
                "is_complete": rev_sum.is_complete,
            }

    iter_info = RefinementIterationInfo(
        iteration_index=iteration_index,
        previous_training_run_id=previous_training_run_id,
        source_infer_run_id=source_infer_run_id,
        validation_series_id=validation_series_id,
        training_labels=tuple(training_label_snapshots),
        review_summary=review_summary_dict,
        training_mode=mode,
        resume_from_training_run_id=resume_from_run_id,
    )

    executed_config = actual_params.to_config()
    executed_config["training_mode"] = mode
    run = create_tracking_run(
        video_id=track.video_id,
        track_id=track_id,
        task_type="train",
        engine="dlc",
        engine_version=actual_adapter.engine_version(),
        config=executed_config,
    )
    run = attach_refinement_iteration(run, iter_info)
    if session.project_root is not None:
        try:
            relative_config = config_path.resolve().relative_to(session.project_root.resolve()).as_posix()
        except ValueError:
            relative_config = None
        if relative_config is not None:
            run = replace(run, extra_fields={**run.extra_fields, "config_path": relative_config})
    session.record_tracking_run(run)

    return run, config_path
