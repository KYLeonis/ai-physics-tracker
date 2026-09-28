"""TeacherModelReference 的可用性检查(P1.3-S3,Qt-free 纯读取)。

契约 §4:模型文件缺失或被改动 → unavailable(不静默寻找替代文件);此处
只报告事实,不修改引用。compatibility 的判定(runtime self-test)属 S5。
"""

import hashlib
import logging
from pathlib import Path

from ai_physics_tracker.domain.teacher_model import TeacherModelReference

logger = logging.getLogger(__name__)


def _file_sha256(path: Path, chunk_bytes: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_bytes), b""):
            digest.update(chunk)
    return digest.hexdigest()


def teacher_model_availability(
    project_root: Path, model: TeacherModelReference
) -> tuple[str, str | None]:
    """对照 manifest 复核文件;返回 (state, reason)。

    文件齐全且逐项 size/SHA 一致 → 引用自身的 compatibility_state;
    否则 ("unavailable", 具体原因)。size 先比(便宜),不匹配即短路。
    """

    root = Path(project_root).resolve()
    for entry in model.manifest:
        candidate = root / entry.relative_path
        resolved = candidate.resolve()
        if not resolved.is_relative_to(root):
            return "unavailable", f"manifest path escapes project root: {entry.relative_path!r}"
        if not resolved.is_file():
            return "unavailable", f"file is missing: {entry.relative_path!r}"
        size = resolved.stat().st_size
        if size != entry.size:
            return (
                "unavailable",
                f"file size changed: {entry.relative_path!r} "
                f"(manifest {entry.size}, on disk {size})",
            )
        if _file_sha256(resolved) != entry.sha256:
            return (
                "unavailable",
                f"file content changed: {entry.relative_path!r} (sha256 mismatch)",
            )
    return model.compatibility_state, None
