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
