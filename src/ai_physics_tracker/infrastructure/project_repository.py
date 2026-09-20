"""面向可移植、带 schema 版本项目目录的文件系统仓储。"""

from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import shutil
import tempfile
from threading import RLock
from typing import cast

from ai_physics_tracker.domain.project import (
    PUBLICATION_REQUIRED_CAPABILITIES,
    MigrationRecord,
    Project,
    create_project,
)
from ai_physics_tracker.domain.types import utc_now
from ai_physics_tracker.domain.video import Video
from ai_physics_tracker.infrastructure.errors import (
    ProjectFormatError,
    UnsupportedSchemaVersionError,
)
from ai_physics_tracker.infrastructure.project_serializer import (
    CURRENT_SCHEMA_VERSION,
    LEGACY_SCHEMA_VERSION,
    project_from_payload,
    project_to_payload,
)

PROJECT_FILE_NAME = "project.json"
BACKUP_FILE_NAME = "project.backup.json"


class ProjectRepository:
    """在本地文件系统上创建、加载、保存与迁移项目聚合。"""

    def __init__(self) -> None:
        # 同一窗口的手动保存与后台 autosave 共享 repository。Windows 不允许
        # 两个 writer 同时打开固定的 project.json.tmp，因此在 repository
        # 边界串行化完整提交（含 backup 轮转），也避免并发保存交错发布。
        self._save_lock = RLock()

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
            _guard_schema_version(payload)
            project = project_from_payload(payload)
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

        with self._save_lock:
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

    def save_as_publication(
        self, source_root: Path, destination_root: Path, project: Project
    ) -> Project:
        """v1→v2 显式 Save As 迁移（ADR-0017）：新目录、新 schema，原件不动。

        `project` 是调用方在已加载 v1 状态上构造的 publication candidate
        （required_capabilities 已置、无既有 migration 记录）；本方法读取
        source manifest 校验其确为 v1 且 project_id 一致，计算 manifest
        sha256 写入 MigrationRecord，再复用 staging/copy/原子发布路径。
        任何失败保持源目录与调用方会话零改动。
        """

        source_root = source_root.resolve()
        if not source_root.is_dir():
            raise FileNotFoundError(f"source project directory not found: {source_root}")
        manifest_path = source_root / PROJECT_FILE_NAME
        if not manifest_path.is_file():
            raise FileNotFoundError(f"project manifest not found: {manifest_path}")
        manifest_bytes = manifest_path.read_bytes()
        try:
            source_payload = json.loads(manifest_bytes.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError(f"source manifest is not valid JSON: {error}") from error
        if not isinstance(source_payload, dict):
            raise ValueError("source manifest root JSON value must be an object")
        source_version = source_payload.get("schema_version")
        if source_version != LEGACY_SCHEMA_VERSION:
            raise ValueError(
                "save-as publication source must be a schema v1 project; "
                f"got schema_version {source_version!r}"
            )
        if source_payload.get("project_id") != str(project.project_id):
            raise ValueError(
                "publication candidate project_id does not match the source manifest"
            )
        declared = set(project.required_capabilities)
        if declared != set(PUBLICATION_REQUIRED_CAPABILITIES):
            raise ValueError(
                "save-as publication requires a publication candidate "
                "with the required capabilities declared"
            )
        if project.migration is not None:
            raise ValueError("publication candidate must not carry an existing migration record")
        candidate = replace(
            project,
            migration=MigrationRecord(
                source_schema_version=LEGACY_SCHEMA_VERSION,
                source_manifest_sha256=hashlib.sha256(manifest_bytes).hexdigest(),
            ),
        )
        destination_root = destination_root.resolve()
        if destination_root == source_root or source_root in destination_root.parents:
            raise ValueError("save-as destination cannot be the source or its child")
        return self._publish_project(destination_root, candidate, source_root)

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


def _guard_schema_version(payload: dict[str, object]) -> None:
    """只做版本守卫，不做自动迁移（ADR-0017）。

    v1 是被永久支持的终态格式：generic 项目加载/保存始终留在 v1；
    升级到 v2 只能经显式 Save As publication 迁移，因此这里不存在
    payload 级迁移链。未知更高版本明确拒绝。
    """

    version = payload.get("schema_version")
    if isinstance(version, bool) or not isinstance(version, int):
        raise ProjectFormatError("schema_version must be an integer")
    if version > CURRENT_SCHEMA_VERSION:
        raise UnsupportedSchemaVersionError(
            f"project schema version {version} requires a newer application; "
            f"this version supports up to {CURRENT_SCHEMA_VERSION}"
        )
    if version < LEGACY_SCHEMA_VERSION:
        raise ProjectFormatError(
            f"no migration path from schema version {version}"
        )


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
