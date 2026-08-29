"""Filesystem repository for portable schema-versioned project directories."""

from collections.abc import Callable
from dataclasses import replace
import json
import os
from pathlib import Path, PurePosixPath
import shutil
from typing import cast

from ai_physics_tracker.domain.project import Project, create_project
from ai_physics_tracker.domain.types import utc_now
from ai_physics_tracker.domain.video import Video
from ai_physics_tracker.infrastructure.errors import (
    ProjectFormatError,
    UnsupportedSchemaVersionError,
)
from ai_physics_tracker.infrastructure.project_serializer import (
    CURRENT_SCHEMA_VERSION,
    project_from_payload,
    project_to_payload,
)

PROJECT_FILE_NAME = "project.json"
BACKUP_FILE_NAME = "project.backup.json"
Migration = Callable[[dict[str, object]], dict[str, object]]
_MIGRATIONS: dict[int, Migration] = {}


class ProjectRepository:
    """Create, load, save, and relocate project aggregates on local filesystems."""

    def create(
        self, project_root: Path, name: str, description: str | None = None
    ) -> Project:
        """Create the portable project directory and persist its initial manifest."""

        project_root.mkdir(parents=True, exist_ok=False)
        for relative in (
            Path("videos"),
            Path("data") / "engines",
            Path("data") / "derived",
            Path("models"),
        ):
            (project_root / relative).mkdir(parents=True)
        return self.save(project_root, create_project(name, description))

    def load(self, project_root: Path) -> Project:
        """Load a Project, rejecting corruption and unsupported schema versions."""

        project_file = project_root / PROJECT_FILE_NAME
        if not project_file.is_file():
            raise FileNotFoundError(f"project manifest not found: {project_file}")
        try:
            raw = json.loads(project_file.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                raise ValueError("root JSON value must be an object")
            payload = cast(dict[str, object], raw)
            migrated = _migrate_payload(payload)
            return project_from_payload(migrated)
        except UnsupportedSchemaVersionError:
            raise
        except ProjectFormatError as error:
            backup = project_root / BACKUP_FILE_NAME
            raise ProjectFormatError(
                f"cannot load {project_file}: {error}; "
                f"recovery backup may exist at {backup}"
            ) from error
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
            backup = project_root / BACKUP_FILE_NAME
            raise ProjectFormatError(
                f"cannot load {project_file}: {error}; "
                f"recovery backup may exist at {backup}"
            ) from error

    def save(self, project_root: Path, project: Project) -> Project:
        """Atomically save a Project and roll the previous manifest to one backup."""

        if not project_root.is_dir():
            raise FileNotFoundError(f"project directory not found: {project_root}")
        updated = replace(project, modified_at=utc_now())
        payload = project_to_payload(updated)
        serialized = json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
            allow_nan=False,
        ) + "\n"
        _atomic_write_manifest(project_root, serialized)
        return updated

    def save_as(
        self, source_root: Path, destination_root: Path, project: Project
    ) -> Project:
        """Copy the portable project unit, then atomically save the supplied state."""

        if not source_root.is_dir():
            raise FileNotFoundError(f"source project directory not found: {source_root}")
        shutil.copytree(
            source_root,
            destination_root,
            ignore=shutil.ignore_patterns("*.tmp"),
        )
        return self.save(destination_root, project)

    @staticmethod
    def close(project: Project) -> None:
        """End a lifecycle session; no-op because the repository retains no handles."""

    @staticmethod
    def resolve_video_path(project_root: Path, video: Video) -> Path | None:
        """Resolve project-managed first, then external; return None for relink."""

        if video.file_path is not None:
            managed = project_root.joinpath(*video.file_path.parts)
            if managed.exists():
                return managed
        if video.original_path is not None:
            external = Path(video.original_path)
            if external.exists():
                return external
        return None

    @staticmethod
    def relative_video_path(project_root: Path, video_path: Path) -> PurePosixPath:
        """Encode a copied project-managed video; external videos use original_path."""

        try:
            relative = video_path.resolve().relative_to(project_root.resolve())
        except ValueError as error:
            raise ValueError(
                "video is outside the project; store it as an external original_path "
                "or copy it into the project first"
            ) from error
        return PurePosixPath(relative.as_posix())


def _migrate_payload(payload: dict[str, object]) -> dict[str, object]:
    version = payload.get("schema_version")
    if isinstance(version, bool) or not isinstance(version, int):
        raise ProjectFormatError("schema_version must be an integer")
    if version > CURRENT_SCHEMA_VERSION:
        raise UnsupportedSchemaVersionError(
            f"project schema version {version} requires a newer application; "
            f"this version supports up to {CURRENT_SCHEMA_VERSION}"
        )
    migrated = payload
    while version < CURRENT_SCHEMA_VERSION:
        migration = _MIGRATIONS.get(version)
        if migration is None:
            raise ProjectFormatError(
                f"no migration path from schema version {version} "
                f"to {CURRENT_SCHEMA_VERSION}"
            )
        # Migration functions are added from schema v2 onward. Keeping the loop here
        # makes the guard explicit without inventing a pre-v1 format.
        migrated = migration(migrated)
        version += 1
    return migrated


def _atomic_write_manifest(project_root: Path, serialized: str) -> None:
    project_file = project_root / PROJECT_FILE_NAME
    project_tmp = project_root / f"{PROJECT_FILE_NAME}.tmp"
    backup_file = project_root / BACKUP_FILE_NAME
    backup_tmp = project_root / f"{BACKUP_FILE_NAME}.tmp"

    project_tmp.write_text(serialized, encoding="utf-8")
    if project_file.exists():
        shutil.copyfile(project_file, backup_tmp)
        os.replace(backup_tmp, backup_file)
    os.replace(project_tmp, project_file)
