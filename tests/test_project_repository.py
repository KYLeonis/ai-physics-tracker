"""项目持久化集成测试（AC-1/2/3/8）。"""

from dataclasses import replace
from datetime import UTC, datetime
import json
import os
from pathlib import Path, PurePosixPath
from uuid import uuid4

import pytest

from ai_physics_tracker.domain.calibration import Calibration
from ai_physics_tracker.domain.derived import DerivedData, DerivedInput
from ai_physics_tracker.domain.project import add_calibration, add_video
from ai_physics_tracker.domain.timeline import Timeline
from ai_physics_tracker.domain.track import Track, TrackPoint
from ai_physics_tracker.domain.video import Video
from ai_physics_tracker.application.refinement_history import (
    ActivationRecord,
    PREDICTION_SUMMARY_KEY,
    PredictionSummary,
    REFINEMENT_ITERATION_KEY,
    REFINEMENT_STATE_KEY,
    RefinementIterationInfo,
    RefinementState,
    ValidationLabelSnapshot,
    ValidationSeries,
    attach_prediction_summary,
    attach_refinement_iteration,
    attach_refinement_state,
    extract_prediction_summary,
    extract_refinement_iteration,
    extract_refinement_state,
)
from ai_physics_tracker.application.suggested_frame_review import (
    ActiveReviewBatch,
    ReviewCandidate,
    ReviewPredictionSnapshot,
    ReviewRecord,
    SuggestedFrameReviewState,
    attach_review_state,
    extract_review_state,
    SUGGESTED_FRAME_REVIEW_KEY,
)
from ai_physics_tracker.domain.tracking_run import TrackingRun
from ai_physics_tracker.infrastructure.errors import (
    ProjectFormatError,
    UnsupportedSchemaVersionError,
)
from ai_physics_tracker.infrastructure.project_repository import ProjectRepository

_NOW = datetime(2026, 8, 29, tzinfo=UTC)


def _populated_project(repository: ProjectRepository, project_root: Path):
    project = repository.create(project_root, "单摆实验", "UTF-8 round trip")
    video_id = uuid4()
    video = Video(
        video_id,
        PurePosixPath("videos/单摆.mp4"),
        "单摆.mp4",
        1280,
        720,
        29.97,
        1000,
        original_path="/Users/example/单摆.mp4",
        container_format="mp4",
        extra_fields={"future_video_key": {"enabled": True}},
    )
    project = add_video(project, video, Timeline(video_id, 29.97, (100, 500)))
    track = Track(uuid4(), video_id, "摆球", "#11AAEE", _NOW)
    point = TrackPoint(
        uuid4(),
        track.track_id,
        100,
        100 / 29.97,
        400.25,
        300.75,
        "manual",
        "visible",
        "active",
        _NOW,
        _NOW,
        quality_flags=("user_locked",),
    )
    calibration = Calibration(
        uuid4(),
        video_id,
        "米尺",
        (0.0, 0.0),
        (200.0, 0.0),
        1.0,
        "m",
        _NOW,
        origin_px=(640.0, 700.0),
    )
    project = replace(
        project,
        tracks=(track,),
        observations=(point,),
        extra_fields={"future_root_key": [1, 2, 3]},
    )
    project = add_calibration(project, calibration)
    project = replace(
        project,
        active_calibration_by_video={video_id: calibration.calibration_id},
        derived=(
            DerivedData(
                uuid4(),
                track.track_id,
                "world_position",
                DerivedInput(track.track_id),
                ({"step": "pixel_to_world", "params": {}},),
                (100,),
                ((0.1, 0.2),),
                None,
                "m",
                "ai-physics-tracker:0.1.0",
                _NOW,
                "valid",
                calibration.calibration_id,
                extra_fields={"future_derived_key": "kept"},
            ),
        ),
    )
    return repository.save(project_root, project)


def test_create_save_move_and_load_round_trip(tmp_path: Path) -> None:
    repository = ProjectRepository()
    original_root = tmp_path / "实验A"
    saved = _populated_project(repository, original_root)
    (original_root / "videos" / "单摆.mp4").write_bytes(b"fixture")
    moved_root = tmp_path / "实验B"

    original_root.rename(moved_root)
    loaded = repository.load(moved_root)

    assert loaded == saved
    assert repository.resolve_video_path(moved_root, loaded.videos[0]) == (
        moved_root / "videos" / "单摆.mp4"
    )
    assert (moved_root / "data" / "engines").is_dir()
    assert (moved_root / "data" / "derived").is_dir()


def test_external_cross_drive_locator_round_trips_and_requests_relink(
    tmp_path: Path,
) -> None:
    repository = ProjectRepository()
    project_root = tmp_path / "project"
    project = repository.create(project_root, "external")
    video = Video(
        uuid4(),
        None,
        "pendulum.mp4",
        1920,
        1080,
        30.0,
        300,
        original_path=r"D:\Experiments\pendulum.mp4",
    )
    project = add_video(project, video, Timeline(video.video_id, 30.0, (0, 299)))

    saved = repository.save(project_root, project)
    loaded = repository.load(project_root)

    assert loaded == saved
    assert loaded.videos[0].file_path is None
    assert repository.resolve_video_path(project_root, loaded.videos[0]) is None


def test_external_locator_resolves_when_absolute_file_exists(tmp_path: Path) -> None:
    repository = ProjectRepository()
    external = tmp_path / "external.mp4"
    external.write_bytes(b"fixture")
    video = Video(
        uuid4(),
        None,
        "external.mp4",
        100,
        100,
        30.0,
        10,
        original_path=str(external),
    )

    assert repository.resolve_video_path(tmp_path / "project", video) == external


def test_missing_managed_video_falls_back_to_existing_original_path(
    tmp_path: Path,
) -> None:
    repository = ProjectRepository()
    external = tmp_path / "fallback.mp4"
    external.write_bytes(b"fixture")
    video = Video(
        uuid4(),
        PurePosixPath("videos/missing.mp4"),
        "missing.mp4",
        100,
        100,
        30.0,
        10,
        original_path=str(external),
    )

    assert repository.resolve_video_path(tmp_path / "project", video) == external


def test_project_relative_path_rejects_files_outside_project(tmp_path: Path) -> None:
    repository = ProjectRepository()
    project_root = tmp_path / "project"
    project_root.mkdir()
    external = tmp_path / "external.mp4"

    with pytest.raises(ValueError, match="outside the project"):
        repository.relative_video_path(project_root, external)


def test_schema_newer_than_supported_is_rejected_explicitly(tmp_path: Path) -> None:
    repository = ProjectRepository()
    project_root = tmp_path / "project"
    repository.create(project_root, "test")
    project_file = project_root / "project.json"
    payload = json.loads(project_file.read_text(encoding="utf-8"))
    payload["schema_version"] = 999
    project_file.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(UnsupportedSchemaVersionError, match="newer application"):
        repository.load(project_root)


def test_unknown_keys_survive_load_and_save_at_root_and_nested_object(
    tmp_path: Path,
) -> None:
    repository = ProjectRepository()
    project_root = tmp_path / "project"
    _populated_project(repository, project_root)

    loaded = repository.load(project_root)
    repository.save(project_root, loaded)
    payload = json.loads((project_root / "project.json").read_text(encoding="utf-8"))

    assert payload["future_root_key"] == [1, 2, 3]
    assert payload["videos"][0]["future_video_key"] == {"enabled": True}


def test_successful_save_rolls_previous_manifest_to_backup(tmp_path: Path) -> None:
    repository = ProjectRepository()
    project_root = tmp_path / "project"
    initial = repository.create(project_root, "version one")
    previous_manifest = (project_root / "project.json").read_text(encoding="utf-8")

    repository.save(project_root, replace(initial, name="version two"))

    assert (project_root / "project.backup.json").read_text(
        encoding="utf-8"
    ) == previous_manifest
    assert json.loads((project_root / "project.json").read_text(encoding="utf-8"))[
        "name"
    ] == "version two"


def test_save_as_copies_portable_assets_and_supplied_project_state(tmp_path: Path) -> None:
    repository = ProjectRepository()
    source_root = tmp_path / "source"
    saved = _populated_project(repository, source_root)
    asset = source_root / "videos" / "单摆.mp4"
    asset.write_bytes(b"fixture")
    destination_root = tmp_path / "destination"

    copied = repository.save_as(
        source_root,
        destination_root,
        replace(saved, name="另存实验"),
    )

    assert repository.load(destination_root) == copied
    assert (destination_root / "videos" / "单摆.mp4").read_bytes() == b"fixture"
    assert repository.close(copied) is None


def test_interrupted_atomic_replace_leaves_original_manifest_intact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = ProjectRepository()
    project_root = tmp_path / "project"
    initial = repository.create(project_root, "stable")
    project_file = project_root / "project.json"
    original = project_file.read_text(encoding="utf-8")

    def fail_replace(source: Path, destination: Path) -> None:
        raise OSError(f"simulated interruption: {source} -> {destination}")

    monkeypatch.setattr(os, "replace", fail_replace)
    with pytest.raises(OSError, match="simulated interruption"):
        repository.save(project_root, replace(initial, name="not committed"))

    assert project_file.read_text(encoding="utf-8") == original
    assert (project_root / "project.json.tmp").exists()


def test_primary_replace_failure_after_backup_publish_keeps_original_consistent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = ProjectRepository()
    project_root = tmp_path / "project"
    initial = repository.create(project_root, "stable")
    project_file = project_root / "project.json"
    repository.save(project_root, replace(initial, name="version two"))
    primary_before = project_file.read_text(encoding="utf-8")
    backup_file = project_root / "project.backup.json"
    backup_before = backup_file.read_text(encoding="utf-8")
    real_replace = os.replace

    def fail_primary_replace(source: Path, destination: Path) -> None:
        if destination == project_file:
            raise OSError("simulated primary replacement failure")
        real_replace(source, destination)

    monkeypatch.setattr(os, "replace", fail_primary_replace)
    with pytest.raises(OSError, match="primary replacement failure"):
        repository.save(project_root, replace(initial, name="not committed"))

    assert project_file.read_text(encoding="utf-8") == primary_before
    assert backup_file.read_text(encoding="utf-8") == backup_before


def test_backup_publish_failure_rolls_primary_and_existing_backup_back(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = ProjectRepository()
    project_root = tmp_path / "project"
    initial = repository.create(project_root, "version one")
    version_two = repository.save(project_root, replace(initial, name="version two"))
    project_file = project_root / "project.json"
    backup_file = project_root / "project.backup.json"
    primary_before = project_file.read_text(encoding="utf-8")
    backup_before = backup_file.read_text(encoding="utf-8")
    real_replace = os.replace

    def fail_backup_replace(source: Path, destination: Path) -> None:
        if destination == backup_file:
            raise OSError("simulated backup replacement failure")
        real_replace(source, destination)

    monkeypatch.setattr(os, "replace", fail_backup_replace)
    with pytest.raises(OSError, match="backup replacement failure"):
        repository.save(project_root, replace(version_two, name="version three"))

    assert project_file.read_text(encoding="utf-8") == primary_before
    assert backup_file.read_text(encoding="utf-8") == backup_before


def test_save_rejects_same_video_registered_as_managed_and_external(
    tmp_path: Path,
) -> None:
    repository = ProjectRepository()
    project_root = tmp_path / "project"
    project = repository.create(project_root, "duplicates")
    managed_path = project_root / "videos" / "a.mp4"
    first = Video(uuid4(), PurePosixPath("videos/a.mp4"), "a", 10, 10, 30.0, 10)
    second = Video(
        uuid4(), None, "same a", 10, 10, 30.0, 10, original_path=str(managed_path)
    )
    project = add_video(project, first, Timeline(first.video_id, 30.0, (0, 9)))
    project = add_video(project, second, Timeline(second.video_id, 30.0, (0, 9)))

    with pytest.raises(ValueError, match="same filesystem locator"):
        repository.save(project_root, project)


def test_save_rejects_distinct_paths_to_the_same_existing_file(tmp_path: Path) -> None:
    repository = ProjectRepository()
    project_root = tmp_path / "project"
    project = repository.create(project_root, "hard-link duplicate")
    managed_path = project_root / "videos" / "a.mp4"
    managed_path.write_bytes(b"fixture")
    external_alias = tmp_path / "alias.mp4"
    os.link(managed_path, external_alias)
    first = Video(uuid4(), PurePosixPath("videos/a.mp4"), "a", 10, 10, 30.0, 10)
    second = Video(
        uuid4(), None, "alias", 10, 10, 30.0, 10, original_path=str(external_alias)
    )
    project = add_video(project, first, Timeline(first.video_id, 30.0, (0, 9)))
    project = add_video(project, second, Timeline(second.video_id, 30.0, (0, 9)))

    with pytest.raises(ValueError, match="same filesystem locator"):
        repository.save(project_root, project)


def test_load_rejects_observation_outside_video_frame_range(tmp_path: Path) -> None:
    repository = ProjectRepository()
    project_root = tmp_path / "project"
    _populated_project(repository, project_root)
    project_file = project_root / "project.json"
    payload = json.loads(project_file.read_text(encoding="utf-8"))
    payload["observations"][0]["frame_index"] = payload["videos"][0]["frame_count"]
    project_file.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ProjectFormatError, match="frame_count"):
        repository.load(project_root)


def test_load_rejects_duplicate_observation_ids(tmp_path: Path) -> None:
    repository = ProjectRepository()
    project_root = tmp_path / "project"
    _populated_project(repository, project_root)
    project_file = project_root / "project.json"
    payload = json.loads(project_file.read_text(encoding="utf-8"))
    payload["observations"].append(dict(payload["observations"][0]))
    project_file.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ProjectFormatError, match="point_id values must be unique"):
        repository.load(project_root)


def test_corrupt_json_reports_backup_recovery_path(tmp_path: Path) -> None:
    repository = ProjectRepository()
    project_root = tmp_path / "project"
    repository.create(project_root, "test")
    (project_root / "project.json").write_text("{broken", encoding="utf-8")

    with pytest.raises(ProjectFormatError, match="project.backup.json"):
        repository.load(project_root)


def test_suggested_frame_review_roundtrip_and_null_provenance(tmp_path: Path) -> None:
    repository = ProjectRepository()
    project_root = tmp_path / "project"
    project = _populated_project(repository, project_root)
    video = project.videos[0]
    track = project.tracks[0]

    req_id = uuid4()
    point_id = uuid4()

    c1 = ReviewCandidate(
        frame_index=12,
        prediction=ReviewPredictionSnapshot(pixel_x=321.5, pixel_y=205.0, confidence=0.42),
        components={"uncertainty": 0.8},
        raw_components={"uncertainty": 0.58},
        reasons=("low_confidence",),
        total_score=0.8,
    )
    c2 = ReviewCandidate(
        frame_index=20,
        prediction=None,  # missing prediction
        components={"jump": 0.9},
        raw_components={"jump": 4.5},
        reasons=("jump_outlier",),
        total_score=0.85,
    )
    batch = ActiveReviewBatch(request_id=req_id, params_snapshot={"top_n": 10}, candidates=(c1, c2))

    r1 = ReviewRecord(
        disposition="corrected",
        reviewed_at="2026-09-03T12:00:00Z",
        request_id=req_id,
        prediction=c1.prediction,
        manual_point_id=point_id,
    )
    r2 = ReviewRecord(
        disposition="skipped",
        reviewed_at="2026-09-03T12:05:00Z",
        request_id=req_id,
        prediction=None,
        manual_point_id=None,
    )
    state = SuggestedFrameReviewState(active_batch=batch, reviewed_frames={12: r1, 20: r2})

    run = TrackingRun(
        run_id=uuid4(),
        video_id=video.video_id,
        track_id=track.track_id,
        engine="dlc",
        engine_version="3.0.1",
        task_type="infer",
        config={},
        source_detail="test-infer",
        created_at=_NOW,
        status="completed",
        completed_at=_NOW,
        extra_fields={"sibling_plugin_key": 42},
    )
    run_with_review = attach_review_state(run, state)

    project_with_run = replace(project, tracking_runs=(run_with_review,))
    repository.save(project_root, project_with_run)

    # 1. Inspect on-disk JSON directly
    payload = json.loads((project_root / "project.json").read_text(encoding="utf-8"))
    run_json = payload["tracking_runs"][0]
    assert run_json["sibling_plugin_key"] == 42
    assert SUGGESTED_FRAME_REVIEW_KEY in run_json
    rev_json = run_json[SUGGESTED_FRAME_REVIEW_KEY]

    # Verify candidates JSON structure
    assert rev_json["active_batch"]["candidates"][0]["prediction"] == {
        "pixel_x": 321.5,
        "pixel_y": 205.0,
        "confidence": 0.42,
    }
    assert rev_json["active_batch"]["candidates"][1]["prediction"] is None  # null in json

    # Verify reviewed_frames keys are decimal strings
    assert "12" in rev_json["reviewed_frames"]
    assert rev_json["reviewed_frames"]["12"]["disposition"] == "corrected"
    assert rev_json["reviewed_frames"]["12"]["manual_point_id"] == str(point_id)
    assert "20" in rev_json["reviewed_frames"]
    assert rev_json["reviewed_frames"]["20"]["disposition"] == "skipped"
    assert rev_json["reviewed_frames"]["20"]["manual_point_id"] is None

    # 2. Reload and extract state
    loaded_project = repository.load(project_root)
    loaded_run = loaded_project.tracking_runs[0]
    assert loaded_run.extra_fields["sibling_plugin_key"] == 42
    loaded_state = extract_review_state(loaded_run)
    assert loaded_state is not None
    assert loaded_state.active_batch is not None
    assert loaded_state.active_batch.request_id == req_id
    assert len(loaded_state.active_batch.candidates) == 2
    assert loaded_state.active_batch.candidates[1].prediction is None
    assert loaded_state.reviewed_frames[12].disposition == "corrected"
    assert loaded_state.reviewed_frames[12].manual_point_id == point_id
    assert loaded_state.reviewed_frames[20].disposition == "skipped"


def test_save_load_roundtrip_preserves_refinement_state_and_iteration(
    tmp_path: Path,
) -> None:
    repository = ProjectRepository()
    project_root = tmp_path / "refinement_project"
    project = _populated_project(repository, project_root)
    track = project.tracks[0]

    # 1. Setup RefinementState on Track
    snap = ValidationLabelSnapshot(uuid4(), 10, 100.5, 200.5, _NOW.isoformat())
    series = ValidationSeries(uuid4(), "Val Set A", _NOW.isoformat(), (snap,))
    rec = ActivationRecord(uuid4(), _NOW.isoformat(), "activate", None, uuid4(), 50, 2)
    ref_state = RefinementState(
        active_infer_run_id=uuid4(),
        activation_history=(rec,),
        active_validation_series_id=series.series_id,
        validation_series=(series,),
    )
    track_with_ref = attach_refinement_state(track, ref_state)

    # 2. Setup RefinementIterationInfo on train TrackingRun
    train_run = TrackingRun(
        run_id=uuid4(),
        video_id=track.video_id,
        track_id=track.track_id,
        engine="dlc",
        engine_version="3.0.1",
        task_type="train",
        config={},
        source_detail="test-train",
        created_at=_NOW,
        status="completed",
        completed_at=_NOW,
    )
    iter_info = RefinementIterationInfo(
        iteration_index=1,
        previous_training_run_id=None,
        source_infer_run_id=None,
        validation_series_id=series.series_id,
        training_labels=(snap,),
        review_summary={"accepted": 2, "corrected": 1},
    )
    train_run = attach_refinement_iteration(train_run, iter_info)

    # 3. Setup PredictionSummary on infer TrackingRun
    infer_run = TrackingRun(
        run_id=uuid4(),
        video_id=track.video_id,
        track_id=track.track_id,
        engine="dlc",
        engine_version="3.0.1",
        task_type="infer",
        config={},
        source_detail="test-infer",
        created_at=_NOW,
        status="completed",
        completed_at=_NOW,
    )
    pred_summary = PredictionSummary(
        row_count=100,
        eligible_count=80,
        missing_count=5,
        low_confidence_count=15,
        threshold=0.6,
        coverage=0.8,
    )
    infer_run = attach_prediction_summary(infer_run, pred_summary)

    project_updated = replace(
        project,
        tracks=(track_with_ref,),
        tracking_runs=(train_run, infer_run),
    )
    repository.save(project_root, project_updated)

    # Check on-disk json
    disk_payload = json.loads((project_root / "project.json").read_text(encoding="utf-8"))
    disk_track = disk_payload["tracks"][0]
    assert REFINEMENT_STATE_KEY in disk_track
    assert disk_track[REFINEMENT_STATE_KEY]["active_validation_series_id"] == str(series.series_id)

    disk_train = disk_payload["tracking_runs"][0]
    assert REFINEMENT_ITERATION_KEY in disk_train
    assert disk_train[REFINEMENT_ITERATION_KEY]["iteration_index"] == 1

    disk_infer = disk_payload["tracking_runs"][1]
    assert PREDICTION_SUMMARY_KEY in disk_infer
    assert disk_infer[PREDICTION_SUMMARY_KEY]["coverage"] == 0.8

    # Reload from disk and assert fidelity
    loaded = repository.load(project_root)
    loaded_track = loaded.tracks[0]
    loaded_state = extract_refinement_state(loaded_track)
    assert loaded_state.active_infer_run_id == ref_state.active_infer_run_id
    assert loaded_state.active_validation_series_id == series.series_id
    assert len(loaded_state.validation_series) == 1
    assert loaded_state.validation_series[0].name == "Val Set A"
    assert loaded_state.validation_series[0].label_snapshots[0].pixel_x == 100.5

    loaded_train = loaded.tracking_runs[0]
    loaded_iter = extract_refinement_iteration(loaded_train)
    assert loaded_iter is not None
    assert loaded_iter.iteration_index == 1
    assert loaded_iter.review_summary == {"accepted": 2, "corrected": 1}

    loaded_infer = loaded.tracking_runs[1]
    loaded_summary = extract_prediction_summary(loaded_infer)
    assert loaded_summary is not None
    assert loaded_summary.coverage == 0.8




def test_refinement_iteration_resume_lineage_roundtrip(tmp_path: Path) -> None:
    """ADR-0015 lineage（training_mode/resume source）经保存重开完整保留。"""
    from ai_physics_tracker.domain.project import create_project
    from ai_physics_tracker.domain.track import Track
    from ai_physics_tracker.domain.tracking_run import (
        create_tracking_run as _create_run,
    )
    from ai_physics_tracker.domain.types import utc_now as _utc_now

    root = tmp_path / "repo-proj"
    root.mkdir(parents=True)
    repo = ProjectRepository()
    project = create_project("lineage")

    video = Video(uuid4(), PurePosixPath("videos/a.mp4"), "a", 10, 10, 30.0, 10)
    project = add_video(project, video, Timeline(video.video_id, 30.0, (0, 9)))
    track = Track(track_id=uuid4(), video_id=video.video_id, name="T", color="#123456",
                  created_at=_utc_now())
    from dataclasses import replace as _replace_tracks
    project = _replace_tracks(project, tracks=(track,))

    parent_id = uuid4()
    run = _create_run(video.video_id, track.track_id, "train", engine="dlc")
    run = replace(run, config={**run.config, "epochs": 25, "training_mode": "resume"})
    run = attach_refinement_iteration(
        run,
        RefinementIterationInfo(
            iteration_index=2,
            previous_training_run_id=parent_id,
            source_infer_run_id=None,
            validation_series_id=None,
            training_labels=(),
            review_summary=None,
            training_mode="resume",
            resume_from_training_run_id=parent_id,
        ),
    )
    repo.save(root, replace(project, tracking_runs=(run,)))

    loaded = repo.load(root)
    loaded_run = loaded.tracking_runs[0]
    assert loaded_run.config["training_mode"] == "resume"
    info = extract_refinement_iteration(loaded_run)
    assert info is not None
    assert info.training_mode == "resume"
    assert info.resume_from_training_run_id == parent_id
