"""教师模型导入核心(P1.3-S4,Qt-free 纯应用层,契约 §4)。

copy + validate:把外部 DLC 模型 bundle(config + checkpoint + 附加文件)
复制进项目受管路径 ``models/<model_id>/``,逐文件冻结 size/SHA256,复制后
显式重写 managed config 的 ``project_path``(不依赖原目录);YAML 仅安全
解析;不执行用户目录中的任何脚本。全部身份校验 fail closed:四 role 显式
映射、缺/重/多 bodypart、multi-animal/identity、cropping、非 pytorch
engine 一律拒绝。发布走兄弟 staging 目录 + ``os.replace`` 原子切换;
半拷贝残留只允许存在于 staging(下次导入开始时统一清扫),绝不发布
指向不完整 payload 的 manifest。
"""

import logging
import shutil
from pathlib import Path
from typing import Any
from uuid import UUID

from ai_physics_tracker.domain.pendulum import ROLE_ORDER
from ai_physics_tracker.domain.teacher_model import (
    ModelManifestEntry,
    TeacherModelReference,
    build_manifest_hash,
)
from ai_physics_tracker.domain.types import utc_now
from ai_physics_tracker.infrastructure.hashing import file_sha256

logger = logging.getLogger(__name__)

_STAGING_SUFFIX = ".staging"


class TeacherImportError(RuntimeError):
    """教师模型导入的 fail-closed 错误。"""


def parse_teacher_config(config_path: Path) -> dict[str, Any]:
    """safe YAML 解析 DLC config;非 mapping / 无 bodyparts 显式拒绝。"""

    try:
        import yaml

        parsed = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except Exception as error:  # EX2 模式:解析失败显式错误,不静默降级
        raise TeacherImportError(
            f"cannot parse the DLC config as YAML: {config_path}: {error}"
        ) from error
    if not isinstance(parsed, dict):
        raise TeacherImportError(f"DLC config is not a YAML mapping: {config_path}")
    bodyparts = parsed.get("bodyparts")
    if not isinstance(bodyparts, list) or not bodyparts or not all(
        isinstance(item, str) and item for item in bodyparts
    ):
        raise TeacherImportError(
            f"DLC config has no usable bodyparts list: {config_path}"
        )
    if len(set(bodyparts)) != len(bodyparts):
        raise TeacherImportError(
            f"DLC config bodyparts contain duplicates: {bodyparts}"
        )
    return parsed


def validate_teacher_bundle(
    config: dict[str, Any], bodypart_mapping: tuple[tuple[str, str], ...]
) -> None:
    """身份校验(契约 §4 fail-closed 清单)。"""

    if [role for role, _target in bodypart_mapping] != list(ROLE_ORDER):
        raise TeacherImportError(
            f"bodypart mapping must cover the four canonical roles in order: "
            f"{list(ROLE_ORDER)}"
        )
    targets = [target for _role, target in bodypart_mapping]
    if len(set(targets)) != len(targets) or any(not t for t in targets):
        raise TeacherImportError("bodypart mapping targets must be unique and non-empty")
    config_bodyparts = set(config["bodyparts"])
    if set(targets) != config_bodyparts:
        raise TeacherImportError(
            f"bodypart mapping {sorted(targets)} does not match the config "
            f"bodyparts {sorted(config_bodyparts)}; missing/duplicate/extra "
            "bodyparts are rejected"
        )
    if config.get("multianimalproject"):
        raise TeacherImportError("multi-animal DLC projects are not supported")
    if config.get("identity"):
        raise TeacherImportError("identity DLC projects are not supported")
    if config.get("cropping"):
        raise TeacherImportError("cropped DLC projects are not supported")
    engine = config.get("engine")
    if engine != "pytorch":
        raise TeacherImportError(
            f"unsupported or missing DLC engine {engine!r}; only explicit "
            "pytorch models are accepted"
        )


def _resolve_source(source_root: Path, relative: str) -> Path:
    """把 bundle 内相对路径解析到源根之内;逃逸/绝对/symlink 出口拒绝。"""

    candidate = Path(relative)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise TeacherImportError(
            f"bundle file path must be relative without '..': {relative!r}"
        )
    resolved_root = source_root.resolve()
    resolved = (resolved_root / candidate).resolve()
    if not resolved.is_relative_to(resolved_root):
        raise TeacherImportError(
            f"bundle file path escapes the source directory: {relative!r}"
        )
    if not resolved.is_file():
        raise TeacherImportError(f"bundle file is missing: {relative!r}")
    return resolved


def _copy_file(source: Path, destination: Path) -> None:
    """单文件复制(可注入故障的接缝);目标父目录先行创建。"""

    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def import_teacher_model(
    project_root: Path,
    source_root: Path,
    config_relative: str,
    checkpoint_relative: str,
    bodypart_mapping: tuple[tuple[str, str], ...],
    model_id: UUID,
    extra_files: tuple[str, ...] = (),
) -> TeacherModelReference:
    """验证→staging 复制→路径重写→manifest→原子发布;返回 imported 引用。

    本函数不触碰 session/undo——登记进项目由 session 动作承担。发布原子性:
    全部文件先进 ``models/<model_id>.staging``,最后 ``os.replace`` 切换为
    ``models/<model_id>``;任何失败只可能留下 staging 残留(下次导入先清)。
    """

    project_root = Path(project_root).resolve()
    source_root = Path(source_root).resolve()
    if not source_root.is_dir():
        raise TeacherImportError(f"source bundle directory is missing: {source_root}")

    config_source = _resolve_source(source_root, config_relative)
    checkpoint_source = _resolve_source(source_root, checkpoint_relative)
    extra_sources = tuple(
        _resolve_source(source_root, relative) for relative in extra_files
    )

    config = parse_teacher_config(config_source)
    validate_teacher_bundle(config, bodypart_mapping)

    models_root = project_root / "models"
    models_root.mkdir(parents=True, exist_ok=True)
    destination_root = models_root / str(model_id)
    staging_root = models_root / f"{model_id}{_STAGING_SUFFIX}"
    if destination_root.exists():
        raise TeacherImportError(
            f"managed model directory already exists: {destination_root}"
        )
    # 半拷贝残留按契约 §6 允许存在,但绝不复用:导入开始时清扫全部
    # models/*.staging(每次导入的 model_id 全新,清扫不影响并发语义之外的行为)
    for stale in models_root.glob(f"*{_STAGING_SUFFIX}"):
        shutil.rmtree(stale, ignore_errors=True)
    staging_root.mkdir(parents=True)

    managed_prefix = f"models/{model_id}"
    entries: list[ModelManifestEntry] = []

    def _publish_name(source: Path) -> str:
        return source.name  # managed 副本保留 basename(含 Unicode)

    try:
        # 1) config:重写 project_path 后落 staging;原字节 SHA 记入 provenance
        import yaml

        rewritten = dict(config)
        original_config_sha = file_sha256(config_source)
        rewritten["project_path"] = destination_root.as_posix()
        config_copy = staging_root / "config.yaml"
        config_copy.write_text(
            yaml.safe_dump(rewritten, sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )
        entries.append(
            ModelManifestEntry(
                relative_path=f"{managed_prefix}/config.yaml",
                size=config_copy.stat().st_size,
                sha256=file_sha256(config_copy),
            )
        )

        # 2) checkpoint 与附加文件:字节级复制,保留 basename
        checkpoint_copy = staging_root / _publish_name(checkpoint_source)
        _copy_file(checkpoint_source, checkpoint_copy)
        entries.append(
            ModelManifestEntry(
                relative_path=f"{managed_prefix}/{checkpoint_copy.name}",
                size=checkpoint_copy.stat().st_size,
                sha256=file_sha256(checkpoint_copy),
            )
        )
        for extra_source in extra_sources:
            extra_copy = staging_root / _publish_name(extra_source)
            if extra_copy.exists():
                raise TeacherImportError(
                    f"two bundle files share the basename {extra_copy.name!r}"
                )
            _copy_file(extra_source, extra_copy)
            entries.append(
                ModelManifestEntry(
                    relative_path=f"{managed_prefix}/{extra_copy.name}",
                    size=extra_copy.stat().st_size,
                    sha256=file_sha256(extra_copy),
                )
            )
        if len({entry.relative_path for entry in entries}) != len(entries):
            raise TeacherImportError("bundle file basenames collide inside the managed copy")

        manifest = tuple(entries)
        reference = TeacherModelReference(
            model_id=model_id,
            origin="imported",
            created_at=utc_now(),
            source_train_run_id=None,
            source_experiment_id=None,
            bodypart_mapping=bodypart_mapping,
            config_path=f"{managed_prefix}/config.yaml",
            checkpoint_path=f"{managed_prefix}/{checkpoint_copy.name}",
            manifest=manifest,
            manifest_hash=build_manifest_hash(manifest),
            compatibility_state="unverified",
            extra_fields={
                "original_config_sha256": original_config_sha,
                "original_checkpoint_basename": checkpoint_source.name,
                "source_config_relative": config_relative,
                "original_project_path": str(config.get("project_path", "")),
                # video_sets 不重写:infer 的视频由调用参数提供,config 内
                # 原机器绝对路径仅作历史 provenance 保留(P1.4 决策)
            },
        )

        # 3) 原子发布:staging → managed 目录
        os_replace_dir(staging_root, destination_root)
    except Exception:
        # 失败只留下 staging 残余;不发布任何 manifest,不动旧文件
        logger.exception("teacher import failed; staging kept for diagnosis")
        raise

    logger.info(
        "imported teacher model %s from %s (%d files)",
        model_id, source_root, len(manifest),
    )
    return reference


def os_replace_dir(source: Path, destination: Path) -> None:
    """目录原子切换(POSIX rename 语义;目标必须不存在)。"""

    import os

    os.replace(source, destination)
