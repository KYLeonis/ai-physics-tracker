"""v1→v2 Save As publication 迁移服务测试(P1.1-S2)。

覆盖契约 §1:source 保持 v1 原样、UUID/unknown siblings 保留、migration
记录 source manifest SHA、copy/发布失败保留 staging 恢复路径且源零改动。
"""

import hashlib
import json
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

import pytest

from ai_physics_tracker.domain.pendulum import (
    PendulumRoles,
    create_pendulum_experiment,
)
from ai_physics_tracker.domain.project import (
    PUBLICATION_REQUIRED_CAPABILITIES,
    Project,
)
from ai_physics_tracker.domain.track import Track
from ai_physics_tracker.domain.tracking_run import TrackingRun
from ai_physics_tracker.domain.types import utc_now
from ai_physics_tracker.infrastructure import project_repository as repository_module
from ai_physics_tracker.infrastructure.errors import ProjectFormatError
from ai_physics_tracker.infrastructure.project_repository import ProjectRepository
from test_pendulum_experiment import _timeline, _track, _video


def _v1_project() -> tuple[Project, tuple[Track, ...]]:
    video = _video()
    tracks = tuple(
        _track(video, name) for name in ("tip", "body top", "body bottom", "pivot")
    )
    run = TrackingRun(
        run_id=uuid4(),
        video_id=video.video_id,
        member_track_ids=(tracks[0].track_id,),
        engine="dlc",
        engine_version="3.0.1",
        task_type="train",
        config={},
        source_detail="dlc:train:legacy",
        created_at=utc_now(),
        status="completed",
        completed_at=utc_now(),
        model_snapshot="snap",
    )
    project = Project(
        project_id=uuid4(),
        name="legacy source",
        created_at=utc_now(),
        modified_at=utc_now(),
        videos=(video,),
        timelines=(_timeline(video),),
        tracks=tracks,
        tracking_runs=(run,),
        extra_fields={"custom_note": "keep me"},
    )
    return project, tracks


def _saved_v1_source(repository: ProjectRepository, root: Path) -> Project:
    project, _ = _v1_project()
    return repository.create_from_project(root, project)


@pytest.fixture
def v1_source(tmp_path: Path) -> tuple[ProjectRepository, Path, Project]:
    repository = ProjectRepository()
    root = tmp_path / "source"
    project = _saved_v1_source(repository, root)
    (root / "notes").mkdir()
    (root / "notes" / "extra.txt").write_text("sibling", encoding="utf-8")
    repository.save(root, project)
    return repository, root, repository.load(root)


class TestSaveAsPublication:
    def test_writes_v2_copy_and_preserves_source_bytes(self, v1_source):
        repository, root, project = v1_source
        manifest_bytes = (root / "project.json").read_bytes()
        candidate = replace(
            project, required_capabilities=PUBLICATION_REQUIRED_CAPABILITIES
        )
        destination = root.parent / "publication-copy"
        saved = repository.save_as_publication(root, destination, candidate)

        # 源目录零改动：manifest 字节一致、无新增 backup、sibling 仍在源内
        assert (root / "project.json").read_bytes() == manifest_bytes
        assert not (root / "project.backup.json.tmp").exists()
        assert (root / "notes" / "extra.txt").read_text(encoding="utf-8") == "sibling"

        # 目标是 v2，保留 UUID/unknown 字段/资产副本
        assert saved.required_capabilities == PUBLICATION_REQUIRED_CAPABILITIES
        reloaded = repository.load(destination)
        assert str(reloaded.project_id) == str(project.project_id)
        assert reloaded.extra_fields["custom_note"] == "keep me"
        assert (destination / "notes" / "extra.txt").exists()
        manifest = json.loads((destination / "project.json").read_text(encoding="utf-8"))
        assert manifest["schema_version"] == 2
        assert manifest["migration"]["source_schema_version"] == 1
        assert manifest["migration"]["source_manifest_sha256"] == hashlib.sha256(
            manifest_bytes
        ).hexdigest()

        # legacy run 迁移为单成员形态
        assert len(reloaded.tracking_runs) == 1
        assert reloaded.tracking_runs[0].member_track_ids == (
            project.tracking_runs[0].member_track_ids[0],
        )

    def test_migration_can_carry_experiment_in_same_transaction(self, v1_source):
        repository, root, project = v1_source
        tracks = project.tracks
        roles = PendulumRoles(
            tip=tracks[0].track_id,
            body_top=tracks[1].track_id,
            body_bottom=tracks[2].track_id,
            pivot=tracks[3].track_id,
        )
        experiment = create_pendulum_experiment(uuid4(), project.videos[0].video_id, roles)
        candidate = replace(
            project,
            required_capabilities=PUBLICATION_REQUIRED_CAPABILITIES,
            experiments=(experiment,),
        )
        destination = root.parent / "with-experiment"
        repository.save_as_publication(root, destination, candidate)
        reloaded = repository.load(destination)
        assert len(reloaded.experiments) == 1
        assert reloaded.experiments[0].roles == roles
        # 源仍是可独立打开的 v1
        assert repository.load(root).required_capabilities == ()

    def test_rejects_non_v1_source(self, v1_source):
        repository, root, project = v1_source
        candidate = replace(
            project, required_capabilities=PUBLICATION_REQUIRED_CAPABILITIES
        )
        first = root.parent / "already-v2"
        repository.save_as_publication(root, first, candidate)
        # 对已是 v2 的目录再次迁移必须拒绝，不允许就地升级链
        with pytest.raises(ValueError, match="schema v1"):
            repository.save_as_publication(
                first, root.parent / "again", repository.load(first)
            )

    def test_rejects_candidate_project_id_mismatch(self, v1_source):
        repository, root, project = v1_source
        foreign, _ = _v1_project()
        with pytest.raises(ValueError, match="project_id does not match"):
            repository.save_as_publication(
                root,
                root.parent / "mismatch",
                replace(foreign, required_capabilities=PUBLICATION_REQUIRED_CAPABILITIES),
            )

    def test_rejects_candidate_without_capabilities_or_with_migration(self, v1_source):
        repository, root, project = v1_source
        with pytest.raises(ValueError, match="publication candidate"):
            repository.save_as_publication(root, root.parent / "plain", project)

    def test_rejects_destination_equal_or_inside_source(self, v1_source):
        repository, root, project = v1_source
        candidate = replace(
            project, required_capabilities=PUBLICATION_REQUIRED_CAPABILITIES
        )
        with pytest.raises(ValueError, match="cannot be the source"):
            repository.save_as_publication(root, root, candidate)
        with pytest.raises(ValueError, match="cannot be the source"):
            repository.save_as_publication(root, root / "child", candidate)

    def test_copy_failure_preserves_source_and_reports_staging(
        self, v1_source, monkeypatch
    ):
        repository, root, project = v1_source
        manifest_bytes = (root / "project.json").read_bytes()
        candidate = replace(
            project, required_capabilities=PUBLICATION_REQUIRED_CAPABILITIES
        )

        def broken_copytree(*args: object, **kwargs: object) -> None:
            raise OSError("disk full during copy")

        monkeypatch.setattr(repository_module.shutil, "copytree", broken_copytree)
        with pytest.raises(ProjectFormatError, match="recovery staging"):
            repository.save_as_publication(
                root, root.parent / "broken", candidate
            )
        assert (root / "project.json").read_bytes() == manifest_bytes

    def test_unicode_destination_directory_supported(self, v1_source):
        repository, root, project = v1_source
        candidate = replace(
            project, required_capabilities=PUBLICATION_REQUIRED_CAPABILITIES
        )
        destination = root.parent / "单摆-公开实验"
        repository.save_as_publication(root, destination, candidate)
        assert (destination / "project.json").is_file()

    def test_windows_reserved_destination_rejected(self, v1_source):
        repository, root, project = v1_source
        candidate = replace(
            project, required_capabilities=PUBLICATION_REQUIRED_CAPABILITIES
        )
        with pytest.raises(ValueError, match="Windows-safe"):
            repository.save_as_publication(root, root.parent / "CON", candidate)
