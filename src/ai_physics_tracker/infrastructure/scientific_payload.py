"""不可变科学 JSON 产物的项目内发布与完整性读取。"""

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import tempfile
from uuid import UUID

from ai_physics_tracker.domain.scientific_result import ResultColumn, ResultPayload


def write_scientific_payload(root: Path, result_id: UUID, payload: dict,
                             columns: tuple[ResultColumn, ...]) -> ResultPayload:
    relative = PurePosixPath(f"data/derived/{result_id}.json")
    destination = (root / relative).resolve()
    if not destination.is_relative_to(root.resolve()):
        raise ValueError("scientific payload escapes project root")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise FileExistsError("scientific payload is immutable")
    data = (json.dumps(payload, ensure_ascii=False, sort_keys=True,
                       separators=(",", ":"), allow_nan=False)+"\n").encode("utf-8")
    fd, name = tempfile.mkstemp(suffix=".tmp", dir=destination.parent)
    temporary = Path(name)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        # 同目录 hard link 原子发布且不覆盖既有 ID；支持 macOS/Windows NTFS。
        os.link(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    return ResultPayload("json", relative, len(data), hashlib.sha256(data).hexdigest(), columns)


def _reject_constant(value: str):
    raise ValueError(f"scientific JSON contains nonfinite {value}")


def read_scientific_payload(root: Path, reference: ResultPayload) -> dict:
    path = (root / reference.path).resolve()
    if not path.is_relative_to(root.resolve()) or not path.is_file():
        raise ValueError("scientific payload is unavailable")
    data = path.read_bytes()
    if len(data) != reference.size_bytes or hashlib.sha256(data).hexdigest() != reference.sha256:
        raise ValueError("scientific payload size/hash changed")
    if reference.format != "json":
        raise ValueError("pendulum analysis requires JSON payload")
    payload = json.loads(data.decode("utf-8"), parse_constant=_reject_constant)
    if not isinstance(payload, dict):
        raise ValueError("scientific payload must be an object")
    return payload
