"""面向可移植、带 schema 版本项目目录的文件系统仓储。"""

from collections.abc import Callable
from dataclasses import replace
import json
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import shutil
import tempfile
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
    """在本地文件系统上创建、加载、保存与迁移项目聚合。"""

    def create(
        self, project_root: Path, name: str, description: str | None = None
    ) -> Project:
        """创建可移植的项目目录并持久化初始 manifest。"""

        return self.create_from_project(project_root, create_project(name, description))

    def create_from_project(self, project_root: Path, project: Project) -> Project:
        """首次保存当前快照，保留 ID；成功发布前不绑定调用方会话。"""

        if any(video.file_path is not None for video in project.videos):
            raise ValueError("first save requires external video references")
        return self._publish_project(project_root, project)

    def load(self, project_root: Path) -> Project:
        """加载 Project，拒绝损坏数据与不支持的 schema 版本。"""

        project_file = project_root / PROJECT_FILE_NAME
        if not project_file.is_file():
            raise FileNotFoundError(f"project manifest not found: {project_file}")
        try:
            raw = json.loads(project_file.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                raise ValueError("root JSON value must be an object")
            payload = cast(dict[str, object], raw)
            migrated = _migrate_payload(payload)
            project = project_from_payload(migrated)
            _validate_resolved_video_locators(project_root, project)
            return project
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
        """原子保存 Project，并将上一个 manifest 轮转为一篇备份。"""

        if not project_root.is_dir():
            raise FileNotFoundError(f"project directory not found: {project_root}")
        updated = replace(project, modified_at=utc_now())
        _validate_resolved_video_locators(project_root, updated)
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
        """复制可移植项目单元，再原子保存传入的状态。"""

        source_root = source_root.resolve()
        destination_root = destination_root.resolve()
        if not source_root.is_dir():
            raise FileNotFoundError(f"source project directory not found: {source_root}")
        if destination_root == source_root or source_root in destination_root.parents:
            raise ValueError("save-as destination cannot be the source or its child")
        return self._publish_project(destination_root, project, source_root)

    def _publish_project(
        self, destination: Path, project: Project, source_root: Path | None = None
    ) -> Project:
        """新目录先暂存再发布；失败保留明确的恢复路径，不自动删除文件。"""

        destination = destination.resolve()
        if (PureWindowsPath(destination.name).is_reserved()
                or destination.name.endswith((".", " "))
                or any(char in '<>:"\\|?*' for char in destination.name)):
            raise ValueError("project directory name is not Windows-safe")
        if destination.exists():
            raise FileExistsError(f"project destination already exists: {destination}")
        if not destination.parent.is_dir():
            raise FileNotFoundError(f"destination parent not found: {destination.parent}")
        _validate_resolved_video_locators(destination, project)
        staging = Path(tempfile.mkdtemp(prefix=f".{destination.name}.pending-", dir=destination.parent))
        try:
            if source_root is not None:
                if any(item.is_symlink() for item in source_root.rglob("*")):
                    raise ValueError("project assets must not contain symlinks")
                shutil.copytree(source_root, staging, dirs_exist_ok=True,
                                ignore=shutil.ignore_patterns("*.tmp"))
            else:
                for relative in ("videos", "data/engines", "data/derived", "models"):
                    (staging / relative).mkdir(parents=True)
            saved = self.save(staging, project)
            if destination.exists():
                raise FileExistsError(f"project destination appeared during save: {destination}")
            staging.rename(destination)
            return saved
        except Exception as error:
            # 原项目与目标绑定均未提交；保留本次暂存产物供用户选择恢复/清理。
            raise ProjectFormatError(
                f"project publication failed: {error}; recovery staging: {staging}"
            ) from error

    @staticmethod
    def close(project: Project) -> None:
        """结束一次生命周期会话；仓储不保留句柄，因此是 no-op。"""

    @staticmethod
    def resolve_video_path(project_root: Path, video: Video) -> Path | None:
        """先解析项目托管路径，再解析外部路径；返回 None 表示需要 relink。"""

        if video.file_path is not None:
            managed = project_root.joinpath(*video.file_path.parts)
            root_resolved = project_root.resolve()
            managed_resolved = managed.resolve()
            try:
                managed_resolved.relative_to(root_resolved)
            except ValueError:
                return None
            if managed.exists():
                return managed
        if video.original_path is not None:
            external = Path(video.original_path)
            if external.exists():
                return external
        return None

    @staticmethod
    def relative_video_path(project_root: Path, video_path: Path) -> PurePosixPath:
        """编码已复制入项目的托管视频；外部视频使用 original_path。"""

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
        # 迁移函数从 schema v2 起才存在。此处保留循环是为了显式表达守卫
        # 逻辑，而不是虚构出一个 pre-v1 格式。
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
    os.replace(project_tmp, project_file)
    if backup_tmp.exists():
        try:
            os.replace(backup_tmp, backup_file)
        except OSError:
            # 主文件已提交，但备份发布失败。从仍完好的暂存文件恢复旧的主文件，
            # 保证调用方永远不会看到主/备不一致的“保存失败”状态。
            os.replace(backup_tmp, project_file)
            raise


def _validate_resolved_video_locators(project_root: Path, project: Project) -> None:
    resolved: set[str] = set()
    candidates: list[Path] = []
    for video in project.videos:
        candidate: Path | None = None
        if video.file_path is not None:
            candidate = project_root.joinpath(*video.file_path.parts)
        elif video.original_path is not None:
            external = Path(video.original_path)
            if external.is_absolute():
                candidate = external
        if candidate is None:
            continue
        if candidate.exists() and any(
            existing.exists() and os.path.samefile(candidate, existing)
            for existing in candidates
        ):
            raise ValueError("multiple videos resolve to the same filesystem locator")
        key = os.path.normcase(str(candidate.resolve()))
        if key in resolved:
            raise ValueError("multiple videos resolve to the same filesystem locator")
        resolved.add(key)
        candidates.append(candidate)
