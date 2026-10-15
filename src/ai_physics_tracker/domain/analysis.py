"""领域层：本期两个分析族的受限结果槽与直接上游失效。"""

import hashlib
import json
from dataclasses import asdict, replace
from datetime import datetime
from uuid import UUID

from ai_physics_tracker.domain.derived import DerivedData

QUANTITIES = ("x", "y", "vx", "vy", "ax", "ay", "theta", "omega", "alpha")
ANALYSIS_KINDS = tuple(f"{family}_{quantity}" for family in ("function_fit", "signal_recurrence")
                       for quantity in QUANTITIES)


def source_snapshot(source: DerivedData) -> dict:
    """有限JSON快照保留源输入、配方、数值和未知扩展，不保留活对象。"""
    def encode(value):
        if isinstance(value, UUID):
            return str(value)
        if isinstance(value, datetime):
            return value.isoformat()
        raise TypeError(f"Unsupported source metadata: {type(value).__name__}")
    return json.loads(json.dumps(asdict(source), default=encode, allow_nan=False))


def source_fingerprint(source: DerivedData) -> str:
    """ID之外核对完整源内容，覆盖同ID但配方 / 样本被替换的情形。"""
    encoded = json.dumps(source_snapshot(source), sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def stale_analysis_dependents(records: tuple[DerivedData, ...]) -> tuple[DerivedData, ...]:
    """只传播既有线性 / 角量到本期结果的直接依赖，不构建通用图。"""
    sources = {str(item.derived_id): item for item in records if item.kind not in ANALYSIS_KINDS}
    updated = []
    for item in records:
        metadata = item.extra_fields.get("analysis")
        if item.kind in ANALYSIS_KINDS and item.status == "valid" and isinstance(metadata, dict) and metadata.get("version") == 1:
            source = sources.get(metadata.get("source_id"))
            if (source is None or source.status != "valid"
                    or source_fingerprint(source) != metadata.get("source_fingerprint")):
                item = replace(item, status="stale")
        updated.append(item)
    return tuple(updated)
