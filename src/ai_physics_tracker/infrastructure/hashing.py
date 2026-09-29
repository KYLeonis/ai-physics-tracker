"""共享的文件 SHA256 基础设施 helper(流式读取,大文件安全)。"""

import hashlib
from pathlib import Path


def file_sha256(path: Path, chunk_bytes: int = 1 << 20) -> str:
    """流式计算文件 SHA256;调用方负责文件存在性。"""

    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_bytes), b""):
            digest.update(chunk)
    return digest.hexdigest()
