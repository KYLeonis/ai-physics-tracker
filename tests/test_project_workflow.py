"""ProjectSession 与 ProjectRepository 项目生命周期回归测试。

覆盖 Phase 2.4 的首存、另存、加载、失败恢复、dirty 语义、relink 与时序门禁。
测试只使用 ``tmp_path`` 下的路径和 fake CFR 元数据，不创建真实媒体文件。
"""

from copy import deepcopy
from dataclasses import replace
from pathlib import Path

import pytest

from ai_physics_tracker.application.project_session import (
    ProjectSession,
    ProjectSessionError,
)
from ai_physics_tracker.application.video import TimingStatus, VideoStreamInfo
from ai_physics_tracker.domain.project import Project, create_project
from ai_physics_tracker.domain.video import Video
from ai_physics_tracker.infrastructure import project_repository as repository_module
from ai_physics_tracker.infrastructure.errors import ProjectFormatError
from ai_physics_tracker.infrastructure.project_repository import ProjectRepository


def _video_info(
    fps_container: float = 10.0,
    frame_count: int = 6,
    timing_status: TimingStatus = "cfr",
) -> VideoStreamInfo:
    """构造测试用视频元数据；成功登记的默认状态必须是已确认 CFR。"""

    return VideoStreamInfo(
        width_px=64,
        height_px=48,
        fps_container=fps_container,
        frame_count=frame_count,
        container_format="fake",
        timing_status=timing_status,
    )


def _session_with_video(
    tmp_path: Path, repository: ProjectRepository | None = None
) -> tuple[ProjectSession, Video]:
    """创建含一个外部 fake CFR 视频的无根会话。"""

    active_repository = repository if repository is not None else ProjectRepository()
    session = ProjectSession.start(active_repository, name="workflow regression")
    video, _timeline = session.register_external_video(
        tmp_path / "missing-video.mp4", _video_info()
    )
    return session, video


def _staging_from_error(error: ProjectFormatError) -> Path:
    """从发布失败消息解析用户可恢复的暂存目录。"""

    marker = "recovery staging: "
    message = str(error)
    assert marker in message
    return Path(message.split(marker, 1)[1])


def test_rootless_first_save_preserves_ids_points_and_binds_clean_root(
    tmp_path: Path,
) -> None:
    repository = ProjectRepository()
    session, video = _session_with_video(tmp_path, repository)
    track = session.add_track(video.video_id, name="bob")
    point = session.mark_point(track.track_id, 3, 12.5, 24.25)
    before_save = deepcopy(session.project)
    destination = tmp_path / "first-project"

    saved = session.save_as(destination)

    assert saved.project_id == before_save.project_id
    assert saved.videos == before_save.videos
    assert saved.timelines == before_save.timelines
    assert saved.tracks == before_save.tracks
    assert saved.observations == (point,)
    assert saved.observations == before_save.observations
    assert session.project_root == destination.resolve()
    assert not session.is_dirty
    assert not session.can_undo
    assert not session.can_redo
    assert repository.load(destination) == saved


def test_failed_save_preserves_dirty_project_and_undo_history(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = ProjectRepository()
    session, video = _session_with_video(tmp_path, repository)
    session.save_as(tmp_path / "project")
    track = session.add_track(video.video_id)
    session.mark_point(track.track_id, 1, 8.0, 9.0)
    before_failure = deepcopy(session.project)

    def fail_save(_project_root: Path, _project: Project) -> Project:
        raise OSError("simulated save failure")

    monkeypatch.setattr(repository, "save", fail_save)

    with pytest.raises(OSError, match="simulated save failure"):
        session.save()

    assert session.project == before_failure
    assert session.project_root == (tmp_path / "project").resolve()
    assert session.is_dirty
    assert session.can_undo
    assert not session.can_redo


def test_save_as_keeps_source_unchanged_and_later_save_targets_destination(
    tmp_path: Path,
) -> None:
    repository = ProjectRepository()
    session, video = _session_with_video(tmp_path, repository)
    track = session.add_track(video.video_id)
    session.mark_point(track.track_id, 0, 1.0, 2.0)
    source = tmp_path / "source-project"
    source_snapshot = session.save_as(source)
    source_manifest_before = (source / "project.json").read_text(encoding="utf-8")

    session.mark_point(track.track_id, 1, 3.0, 4.0)
    destination = tmp_path / "destination-project"
    destination_snapshot = session.save_as(destination)

    assert session.project_root == destination.resolve()
    assert repository.load(source) == source_snapshot
    assert (source / "project.json").read_text(encoding="utf-8") == source_manifest_before
    assert repository.load(destination) == destination_snapshot
    assert destination_snapshot.observations == session.project.observations

    session.mark_point(track.track_id, 2, 5.0, 6.0)
    latest = session.save()

    assert session.project_root == destination.resolve()
    assert repository.load(source) == source_snapshot
    assert repository.load(destination) == latest
    assert repository.load(destination).observations == session.project.observations
    assert not session.is_dirty


@pytest.mark.parametrize(
    ("target_kind", "expected_error"),
    (
        pytest.param("same", ValueError, id="same-directory"),
        pytest.param("child", ValueError, id="source-child"),
        pytest.param("existing", FileExistsError, id="existing-target"),
    ),
)
def test_save_as_rejects_same_child_and_existing_targets(
    tmp_path: Path,
    target_kind: str,
    expected_error: type[Exception],
) -> None:
    repository = ProjectRepository()
    session, _video = _session_with_video(tmp_path, repository)
    source = tmp_path / "source-project"
    session.save_as(source)
    before_rejection = deepcopy(session.project)

    if target_kind == "same":
        target = source
    elif target_kind == "child":
        target = source / "nested-project"
    else:
        target = tmp_path / "already-existing"
        target.mkdir()

    with pytest.raises(expected_error):
        session.save_as(target)

    assert session.project == before_rejection
    assert session.project_root == source.resolve()
    assert not session.is_dirty


def test_first_save_failure_keeps_rootless_session_and_staging_recovery_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = ProjectRepository()
    session, video = _session_with_video(tmp_path, repository)
    track = session.add_track(video.video_id)
    session.mark_point(track.track_id, 2, 10.0, 11.0)
    before_failure = deepcopy(session.project)
    destination = tmp_path / "first-project"

    def fail_save(_project_root: Path, _project: Project) -> Project:
        raise OSError("simulated first-save failure")

    monkeypatch.setattr(repository, "save", fail_save)

    with pytest.raises(ProjectFormatError, match="recovery staging:") as raised:
        session.save_as(destination)

    staging = _staging_from_error(raised.value)
    assert staging.is_dir()
    assert not destination.exists()
    assert session.project_root is None
    assert session.project == before_failure
    assert session.is_dirty
    assert session.can_undo


def test_save_as_copy_failure_keeps_source_binding_and_staging_recovery_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = ProjectRepository()
    session, _video = _session_with_video(tmp_path, repository)
    source = tmp_path / "source-project"
    session.save_as(source)
    before_failure = deepcopy(session.project)
    destination = tmp_path / "destination-project"

    def fail_copytree(*_args: object, **_kwargs: object) -> None:
        raise OSError("simulated copy failure")

    monkeypatch.setattr(repository_module.shutil, "copytree", fail_copytree)

    with pytest.raises(ProjectFormatError, match="recovery staging:") as raised:
        session.save_as(destination)

    staging = _staging_from_error(raised.value)
    assert staging.is_dir()
    assert not destination.exists()
    assert session.project_root == source.resolve()
    assert session.project == before_failure
    assert not session.is_dirty


def test_loaded_session_starts_clean_without_annotation_history(tmp_path: Path) -> None:
    repository = ProjectRepository()
    session, video = _session_with_video(tmp_path, repository)
    track = session.add_track(video.video_id)
    session.mark_point(track.track_id, 4, 31.0, 17.0)
    root = tmp_path / "project"
    saved = session.save_as(root)

    loaded = ProjectSession.load(repository, root)

    assert loaded.project == saved
    assert loaded.project_root == root.resolve()
    assert not loaded.is_dirty
    assert not loaded.can_undo
    assert not loaded.can_redo


def test_undo_after_save_returns_to_saved_snapshot_and_clean_state(tmp_path: Path) -> None:
    repository = ProjectRepository()
    session, video = _session_with_video(tmp_path, repository)
    track = session.add_track(video.video_id)
    root = tmp_path / "project"
    session.save_as(root)
    saved_snapshot = deepcopy(session.project)

    session.mark_point(track.track_id, 2, 20.0, 21.0)
    assert session.is_dirty
    assert session.can_undo

    assert session.undo()

    assert session.project == saved_snapshot
    assert session.project.observations == ()
    assert not session.is_dirty
    assert session.can_redo


def test_view_state_is_non_dirty_and_preserves_unknown_ui_keys(tmp_path: Path) -> None:
    repository = ProjectRepository()
    project = replace(
        create_project("view state"),
        ui_state={
            "third_party": {"opaque": [1, "keep"]},
            "workflow": {"current_frame": 2, "plugin_value": "preserve"},
        },
    )
    session = ProjectSession(repository, project)

    session.update_view_state({"current_frame": 7, "zoom_factor": 2.0})

    assert not session.is_dirty
    assert session.project.ui_state["third_party"] == {
        "opaque": [1, "keep"]
    }
    assert session.project.ui_state["workflow"] == {
        "current_frame": 7,
        "plugin_value": "preserve",
        "zoom_factor": 2.0,
    }

    root = tmp_path / "project"
    session.save_as(root)
    loaded = repository.load(root)
    assert loaded.ui_state == session.project.ui_state


def test_relink_marks_dirty_without_changing_raw_observations(tmp_path: Path) -> None:
    repository = ProjectRepository()
    session, video = _session_with_video(tmp_path, repository)
    track = session.add_track(video.video_id)
    session.mark_point(track.track_id, 2, 15.0, 16.0)
    root = tmp_path / "project"
    session.save_as(root)
    before_relink = deepcopy(session.project)
    new_path = tmp_path / "moved" / "missing-video.mp4"

    session.relink(video.video_id, new_path)

    relinked_video = next(
        item for item in session.project.videos if item.video_id == video.video_id
    )
    assert session.is_dirty
    assert relinked_video.video_id == before_relink.videos[0].video_id
    assert relinked_video.file_path is None
    assert relinked_video.original_path == str(new_path.resolve())
    assert session.project.observations == before_relink.observations
    assert session.project.tracks == before_relink.tracks
    assert session.project.timelines == before_relink.timelines


@pytest.mark.parametrize("timing_status", ("unknown", "vfr_suspected"))
def test_register_external_video_rejects_unknown_and_vfr_timing(
    tmp_path: Path, timing_status: TimingStatus
) -> None:
    session = ProjectSession.start(ProjectRepository())
    before_rejection = deepcopy(session.project)

    with pytest.raises(
        ProjectSessionError,
        match="video timing is not verified CFR; browsing only",
    ):
        session.register_external_video(
            tmp_path / "unverified-video.mp4",
            _video_info(timing_status=timing_status),
        )

    assert session.project == before_rejection
    assert not session.is_dirty
    assert session.project_root is None
