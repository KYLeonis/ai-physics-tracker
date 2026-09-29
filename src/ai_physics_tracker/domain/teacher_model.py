"""TeacherModelReference 域对象（P1.3-S3，契约 §4）。

联合训练（trained）或教师导入（imported，S4）产生的可验证模型引用：
manifest 逐文件冻结 size/SHA256，任何文件缺失或变化由可用性检查判定为
unavailable——不静默寻找替代文件。compatibility 的升级（真实 load+infer）
属 S5 self-test；本对象只保存状态与证据。
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID

from ai_physics_tracker.domain.pendulum import ROLE_ORDER
from ai_physics_tracker.domain.types import JsonObject, canonical_json_digest

MODEL_ORIGINS = ("trained", "imported")
MODEL_COMPATIBILITY_STATES = ("unverified", "compatible", "incompatible", "unavailable")
ENGINE_DEEPLABCUT_PYTORCH = "deeplabcut_pytorch"


@dataclass(frozen=True)
class ModelManifestEntry:
    """manifest 单文件条目；relative_path 为项目根相对 POSIX 路径。"""

    relative_path: str
    size: int
    sha256: str

    def __post_init__(self) -> None:
        if not self.relative_path or "\\" in self.relative_path:
            raise ValueError(
                f"manifest relative_path must be a non-empty POSIX path: {self.relative_path!r}"
            )
        parts = self.relative_path.split("/")
        if self.relative_path.startswith("/") or ".." in parts:
            raise ValueError(
                f"manifest path must be relative without '..': {self.relative_path!r}"
            )
        if self.size < 0:
            raise ValueError(f"manifest size must be non-negative: {self.size}")
        sha = self.sha256.strip().lower()
        if len(sha) != 64 or any(char not in "0123456789abcdef" for char in sha):
            raise ValueError(f"manifest sha256 must be a 64-char hex digest: {self.sha256!r}")
        # 归一为小写:availability 与小写 hexdigest 精确比较,大写条目会永久误报
        object.__setattr__(self, "sha256", sha)


def build_manifest_hash(manifest: tuple[ModelManifestEntry, ...]) -> str:
    """manifest 的 canonical digest;registration 与可用性检查共用同一算法。"""

    payload = {
        "kind": "teacher-model-manifest-v1",
        "files": [
            {
                "relative_path": entry.relative_path,
                "size": entry.size,
                "sha256": entry.sha256,
            }
            for entry in sorted(manifest, key=lambda item: item.relative_path)
        ],
    }
    return canonical_json_digest(payload)


@dataclass(frozen=True)
class TeacherModelReference:
    """契约 §4:trained/imported 模型的不可变引用。"""

    model_id: UUID
    origin: str
    created_at: datetime
    source_train_run_id: UUID | None = None
    source_experiment_id: UUID | None = None
    engine: str = ENGINE_DEEPLABCUT_PYTORCH
    engine_version: str = ""
    architecture_version: str = ""
    bodypart_mapping: tuple[tuple[str, str], ...] = ()
    config_path: str = ""
    checkpoint_path: str = ""
    manifest: tuple[ModelManifestEntry, ...] = ()
    manifest_hash: str = ""
    compatibility_state: str = "unverified"
    self_test_evidence: JsonObject | None = None
    extra_fields: JsonObject = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.model_id, UUID):
            raise ValueError("model_id must be a UUID")
        if self.origin not in MODEL_ORIGINS:
            raise ValueError(f"origin must be one of {MODEL_ORIGINS}, got {self.origin!r}")
        if self.origin == "imported" and self.source_train_run_id is not None:
            raise ValueError("imported model must not carry source_train_run_id")
        if self.origin == "trained":
            if not isinstance(self.source_train_run_id, UUID):
                raise ValueError("trained model must reference its source train run")
            if not isinstance(self.source_experiment_id, UUID):
                raise ValueError("trained model must reference its source experiment")
        if self.engine != ENGINE_DEEPLABCUT_PYTORCH:
            raise ValueError(f"unsupported engine: {self.engine!r}")
        if not self.manifest:
            raise ValueError("manifest must not be empty")
        paths = [entry.relative_path for entry in self.manifest]
        if len(set(paths)) != len(paths):
            raise ValueError("manifest contains duplicate relative paths")
        if self.config_path not in paths or self.checkpoint_path not in paths:
            raise ValueError(
                "config_path/checkpoint_path must reference manifest entries"
            )
        if len(self.bodypart_mapping) != len(ROLE_ORDER):
            raise ValueError("bodypart mapping must cover exactly four roles")
        targets = [target for _role, target in self.bodypart_mapping]
        if len(set(targets)) != len(targets) or any(not t for t in targets):
            raise ValueError("bodypart mapping targets must be unique and non-empty")
        if self.origin == "trained" and self.bodypart_mapping != tuple(
            (role, role) for role in ROLE_ORDER
        ):
            raise ValueError(
                "trained model bodypart mapping must be the canonical four-role identity"
            )
        if build_manifest_hash(self.manifest) != self.manifest_hash:
            raise ValueError("manifest_hash does not match the manifest entries")
        if self.compatibility_state not in MODEL_COMPATIBILITY_STATES:
            raise ValueError(
                f"compatibility_state must be one of {MODEL_COMPATIBILITY_STATES}, "
                f"got {self.compatibility_state!r}"
            )
        if self.compatibility_state == "compatible" and not self.self_test_evidence:
            raise ValueError("compatible state requires self-test evidence")
