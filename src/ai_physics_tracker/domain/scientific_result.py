"""Publication 科学结果 envelope 值对象（契约 §7）。

P1 只实现 envelope 的结构验证与无损保存：reader 必须能校验合法
`scientific-results-v1` envelope 并原样保存；数值 producer 属于 P2–P4。
跨对象引用（experiment 存在性）由聚合校验负责。
"""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import PurePosixPath
from uuid import UUID

from ai_physics_tracker.domain.paths import validate_managed_relative_path
from ai_physics_tracker.domain.types import (
    JsonObject,
    require_aware_datetime,
)

RESULT_CONTRACT_VERSION = 1
EXECUTION_STATUSES = frozenset(
    {"success", "nonconverged", "failed", "cancelled", "insufficient_data"}
)
FRESHNESS_STATES = frozenset({"valid", "stale"})
PAYLOAD_FORMATS = frozenset({"json", "csv"})


def is_sha256_hex(value: str) -> bool:
    """64 位小写十六进制 sha256 表示。"""

    return len(value) == 64 and all(char in "0123456789abcdef" for char in value)


@dataclass(frozen=True)
class ResultColumn:
    """typed payload 的单列声明：名称、dtype 与单位（None = 无量纲）。"""

    name: str
    dtype: str
    unit: str | None = None

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("result column name must not be blank")
        if not self.dtype.strip():
            raise ValueError("result column dtype must not be blank")


@dataclass(frozen=True)
class ResultPayload:
    """bulk payload 的外部定位：格式、项目内相对路径、大小、hash 与列声明。

    payload 文件本身是 immutable 外置产物；这里只存定位事实，路径必须
    通过 managed 相对路径校验（契约 §1）。
    """

    format: str
    path: PurePosixPath
    size_bytes: int
    sha256: str
    columns: tuple[ResultColumn, ...]
    extra_fields: JsonObject = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        if self.format not in PAYLOAD_FORMATS:
            raise ValueError(f"unsupported payload format: {self.format}")
        validate_managed_relative_path(self.path, "payload path")
        if self.size_bytes < 0:
            raise ValueError("payload size_bytes must be non-negative")
        if not is_sha256_hex(self.sha256):
            raise ValueError("payload sha256 must be a 64-hex digest")
        if not self.columns:
            raise ValueError("payload must declare at least one column")


@dataclass(frozen=True)
class ScientificResult:
    """单条科学结果 record：身份、上游、执行/新鲜度状态与 payload envelope。

    `input_digest` 是提交时冻结的 canonical 组件 digest（契约 §6）；
    `freshness` 与执行状态分离，输入变化只置 stale 不改写执行事实。
    `payload` 为 None 表示纯 manifest 轻量 scalar 结果（契约 §7）。
    """

    result_id: UUID
    experiment_id: UUID
    kind: str
    created_at: datetime
    input_digest: str
    core_version: str
    execution_status: str
    freshness: str = "valid"
    contract_version: int = RESULT_CONTRACT_VERSION
    payload: ResultPayload | None = None
    extra_fields: JsonObject = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        if not self.kind.strip():
            raise ValueError("result kind must not be blank")
        require_aware_datetime(self.created_at, "created_at")
        if self.contract_version != RESULT_CONTRACT_VERSION:
            raise ValueError(f"unsupported result contract_version: {self.contract_version}")
        if not is_sha256_hex(self.input_digest):
            raise ValueError("result input_digest must be a 64-hex sha256 digest")
        if not self.core_version.strip():
            raise ValueError("result core_version must not be blank")
        if self.execution_status not in EXECUTION_STATUSES:
            raise ValueError(f"unknown execution status: {self.execution_status}")
        if self.freshness not in FRESHNESS_STATES:
            raise ValueError(f"unknown freshness state: {self.freshness}")
