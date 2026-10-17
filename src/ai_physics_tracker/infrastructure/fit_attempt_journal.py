"""拟合尝试日志的独立文件系统持久化。"""

from collections.abc import Mapping
from datetime import UTC, datetime
import json
import logging
import math
import os
from pathlib import Path
import tempfile
from typing import Any
from uuid import uuid4


logger = logging.getLogger(__name__)

_JOURNAL_VERSION = 1
_JOURNAL_FILE_NAME = "fit-attempts.json"


class _JournalDecodeError(ValueError):
    """日志内容无法作为当前版本读取。"""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class _UnsupportedJournalError(_JournalDecodeError):
    """日志版本不是当前实现支持的版本。"""


class _ProjectMismatchError(_JournalDecodeError):
    """日志属于另一个项目。"""


class FitAttemptJournal:
    """保存与项目成功结果槽独立的拟合尝试摘要。"""

    def __init__(self, project_id: str, root: Path | None = None) -> None:
        self._project_id = project_id
        self._root: Path | None = None
        self._attempts: list[dict[str, object]] = []
        self._top_level_extra: dict[str, object] = {}
        self._disk_bytes: bytes | None = None
        self._dirty = False
        self._read_only = False
        self._warning = ""
        self._load_pending = False
        self._transfer_pending = False
        self._transfer_expected = None

        if root is not None:
            self._load_root(Path(root))

    @property
    def attempts(self) -> list[dict[str, object]]:
        """返回当前尝试摘要的 JSON-safe 副本。"""

        return _json_clone(self._attempts)

    @property
    def project_id(self) -> str:
        """返回该日志绑定的项目标识。"""

        return self._project_id

    @property
    def warning(self) -> str:
        """返回最近一次需要用户注意的持久化警告。"""

        return self._warning

    @property
    def read_only(self) -> bool:
        """返回日志是否因兼容性或外部冲突而只读。"""

        return self._read_only

    def add(self, attempt: dict[str, object]) -> None:
        """加入一条尝试摘要，并在已绑定项目时立即持久化。"""

        record = _normalise_mapping(attempt, "attempt")
        identifier = record.get("id")
        if not isinstance(identifier, str) or not identifier:
            alternate = record.get("attempt_id")
            record["id"] = (
                alternate if isinstance(alternate, str) and alternate else str(uuid4())
            )

        _validate_attempts(self._attempts + [record])
        self._attempts.append(record)
        self._dirty = True
        self._persist()

    def finish(self, attempt_id: str, **updates: object) -> None:
        """合并一条尝试的终态字段，并在已绑定项目时立即持久化。"""

        merged = _normalise_mapping(updates, "finish updates")
        for attempt in self._attempts:
            if attempt.get("id") == attempt_id or attempt.get("attempt_id") == attempt_id:
                if "id" in merged and merged["id"] != attempt.get("id"):
                    raise ValueError("A fit attempt identity cannot be changed")
                candidate = [dict(item) if item is not attempt else item | merged for item in self._attempts]
                _validate_attempts(candidate)
                attempt.update(merged)
                self._dirty = True
                self._persist()
                return
        raise KeyError(f"unknown fit attempt id: {attempt_id}")

    def bind(self, root: Path | None) -> None:
        """绑定项目根目录，首次绑定或另存时写入当前内存日志。"""

        if root is None:
            self._root = None
            self._disk_bytes = None
            self._read_only = False
            self._warning = ""
            return

        destination = Path(root).resolve()
        if destination == self._root:
            return
        if self._read_only:
            # 冲突/未知内容不会因连续SaveAs复制相同字节而变成本实现拥有的数据。
            self._root = destination
            return

        path = _journal_path(destination)
        try:
            existing = _read_existing(path)
        except OSError as error:
            self._transfer_expected = self._disk_bytes
            self._transfer_pending = True
            self._root = destination
            self._disk_bytes = None
            self._read_only = False
            self._load_pending = True
            self._dirty = True
            self._warning = _read_warning(path, error)
            return

        if existing is not None:
            try:
                _parse_payload(existing, self._project_id)
            except _JournalDecodeError as error:
                self._root = destination
                self._disk_bytes = existing
                self._read_only = True
                self._warning = _decode_warning(error)
                return

        if existing is not None and existing != self._disk_bytes:
            self._root = destination
            self._disk_bytes = existing
            self._read_only = True
            self._warning = "Destination attempt log differs from the saved source; kept unchanged (read-only)."
            return
        self._load_pending = False
        self._root = destination
        self._disk_bytes = existing
        self._read_only = False
        self._warning = ""
        self._dirty = True
        self._persist()

    def retry(self) -> None:
        """重试最近一次未成功的文件写入。"""

        if self._read_only:
            return
        self._persist()

    def interrupt(self) -> None:
        """将当前仍在运行的尝试标记为中断并持久化。"""

        changed = False
        for attempt in self._attempts:
            if attempt.get("status") != "running":
                continue
            attempt["status"] = "interrupted"
            attempt["finished_at"] = datetime.now(UTC).isoformat()
            attempt["reason"] = "Interrupted because the fit attempt was stopped."
            changed = True
        if changed:
            self._dirty = True
            self._persist()

    def _load_root(self, root: Path) -> None:
        destination = root.resolve()
        path = _journal_path(destination)
        try:
            raw = _read_existing(path)
        except OSError as error:
            self._root = destination
            self._load_pending = True
            self._read_only = False
            self._warning = _read_warning(path, error)
            return

        if raw is None:
            self._root = destination
            return

        self._root = destination
        self._disk_bytes = raw
        try:
            attempts, top_level_extra = _parse_payload(raw, self._project_id)
        except _JournalDecodeError as error:
            self._read_only = True
            self._warning = _decode_warning(error)
            return

        self._attempts = attempts
        self._top_level_extra = top_level_extra
        if self._mark_reopened_attempts():
            self._dirty = True
            self._persist()

    def _mark_reopened_attempts(self) -> bool:
        changed = False
        for attempt in self._attempts:
            if attempt.get("status") != "running":
                continue
            attempt["status"] = "interrupted"
            attempt["finished_at"] = datetime.now(UTC).isoformat()
            attempt["reason"] = "Interrupted because the journal was reopened."
            changed = True
        return changed

    def _recover_read(self) -> bool:
        """读故障恢复后先接纳磁盘基线，再追加故障期间的新尝试。"""
        path = _journal_path(self._root)
        try:
            raw = _read_existing(path)
        except OSError as error:
            self._warning = _read_warning(path, error)
            return False
        try:
            loaded, extras = _parse_payload(raw, self._project_id) if raw is not None else ([], {})
            if self._transfer_pending:
                if raw is not None and raw != self._transfer_expected:
                    raise _JournalDecodeError("destination differs from the saved source")
            else:
                if {item["id"] for item in loaded} & {item["id"] for item in self._attempts}:
                    raise _JournalDecodeError("recovered log conflicts with in-memory attempt identities")
                for item in loaded:
                    if item.get("status") == "running":
                        item.update(status="interrupted", finished_at=datetime.now(UTC).isoformat(),
                                    reason="Interrupted before the journal could be read.")
                self._attempts = loaded + self._attempts
                self._top_level_extra = extras
        except _JournalDecodeError as error:
            self._read_only = True
            self._warning = _decode_warning(error)
            return False
        self._disk_bytes = raw
        self._load_pending = False
        self._transfer_pending = False
        self._dirty = True
        return True

    def _persist(self) -> None:
        if self._root is None or self._read_only:
            return
        if self._load_pending and not self._recover_read():
            return
        if not self._dirty:
            return

        path = _journal_path(self._root)
        try:
            serialized = _serialise_payload(
                self._project_id, self._attempts, self._top_level_extra
            )
        except (TypeError, ValueError) as error:
            self._warning = (
                f"Could not serialize fit attempt journal: {error}. "
                "Changes remain in memory."
            )
            return

        try:
            current = _read_existing(path)
        except OSError as error:
            self._warning = _write_warning(path, error)
            return

        if current != self._disk_bytes:
            self._read_only = True
            self._warning = (
                "Fit attempt journal changed on disk externally; the original file "
                "was kept and this journal is now read-only."
            )
            logger.warning("fit attempt journal external conflict: %s", path)
            return

        temporary: Path | None = None
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                newline="\n",
                dir=path.parent,
                prefix=f".{path.name}.",
                suffix=".tmp",
                delete=False,
            ) as handle:
                temporary = Path(handle.name)
                handle.write(serialized)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        except OSError as error:
            self._warning = _write_warning(path, error)
            logger.warning("fit attempt journal write failed: %s", path, exc_info=True)
            return
        finally:
            if temporary is not None and temporary.exists():
                try:
                    temporary.unlink()
                except OSError:
                    logger.warning("could not remove temporary fit journal: %s", temporary)

        self._disk_bytes = serialized.encode("utf-8")
        self._dirty = False
        self._warning = ""


def _journal_path(root: Path) -> Path:
    return root / "analysis" / _JOURNAL_FILE_NAME


def _read_existing(path: Path) -> bytes | None:
    """读取日志字节；仅当日志确实不存在时返回 None。

    路径组件被普通文件占用时，POSIX 报 NotADirectoryError，而 Windows 也报
    FileNotFoundError（WinError 2/3），不能一律当作“日志不存在”，否则读故障
    会被错误归类为新日志并在恢复时误判外部冲突。此处显式重新抛出，交由调用
    方按读故障处理。
    """

    try:
        return path.read_bytes()
    except FileNotFoundError:
        if path.parent.exists() and not path.parent.is_dir():
            raise
        return None


def _normalise_mapping(value: Mapping[str, object], label: str) -> dict[str, object]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{label} must be a mapping")
    try:
        cloned = json.loads(
            json.dumps(value, ensure_ascii=False, allow_nan=False),
        )
    except (TypeError, ValueError) as error:
        raise ValueError(f"{label} must contain only JSON-safe values") from error
    if not isinstance(cloned, dict):
        raise TypeError(f"{label} must be a JSON object")
    return cloned


def _json_clone(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=False, allow_nan=False))


def _serialise_payload(
    project_id: str,
    attempts: list[dict[str, object]],
    top_level_extra: dict[str, object],
) -> str:
    payload: dict[str, object] = dict(top_level_extra)
    payload.update(
        {
            "version": _JOURNAL_VERSION,
            "project_id": project_id,
            "attempts": attempts,
        }
    )
    return json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n"


def _parse_payload(
    raw: bytes, project_id: str
) -> tuple[list[dict[str, object]], dict[str, object]]:
    try:
        payload = json.loads(
            raw.decode("utf-8"),
            parse_constant=_reject_json_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError, TypeError) as error:
        raise _JournalDecodeError("the file is corrupt or truncated") from error

    if not isinstance(payload, dict):
        raise _JournalDecodeError("the file root is not a JSON object")

    version = payload.get("version")
    if not isinstance(version, int) or isinstance(version, bool) or version != _JOURNAL_VERSION:
        raise _UnsupportedJournalError("the file uses an unsupported journal version")
    if payload.get("project_id") != project_id:
        raise _ProjectMismatchError("the file belongs to a different project")

    attempts = payload.get("attempts")
    if not isinstance(attempts, list) or any(not isinstance(item, dict) for item in attempts):
        raise _JournalDecodeError("the attempts field is corrupt")

    _validate_attempts(attempts)
    known = {"version", "project_id", "attempts"}
    top_level_extra = {
        key: value for key, value in payload.items() if key not in known
    }
    return ([dict(item) for item in attempts], top_level_extra)


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON constant {value}")


def _decode_warning(error: _JournalDecodeError) -> str:
    return (
        f"Fit attempt journal {error.reason}; the original file was preserved "
        "and the journal is read-only."
    )


def _read_warning(path: Path, error: OSError) -> str:
    return (
        f"Could not read fit attempt journal {path}: {error}. "
        "Changes remain in memory; retry when the file can be read."
    )


def _write_warning(path: Path, error: OSError) -> str:
    return (
        f"Could not save fit attempt journal {path}: {error}. "
        "Changes remain in memory; retry is available."
    )


def _validate_attempts(attempts: list[dict[str, object]]) -> None:
    """读写边界共享已拥有字段的合法性校验，未知字段保留。"""
    identifiers = set()
    for attempt in attempts:
        identity = attempt.get("id")
        if not isinstance(identity, str) or not identity or identity in identifiers:
            raise _JournalDecodeError("attempt identities are missing or duplicated")
        identifiers.add(identity)
        if not isinstance(attempt.get("status"), str) or not attempt["status"]:
            raise _JournalDecodeError("attempt status is missing or invalid")
        for key in ("status", "formula", "reason", "started_at", "finished_at", "quantity"):
            if key in attempt and not isinstance(attempt[key], str):
                raise _JournalDecodeError(f"attempt {key} is not text")
        elapsed = attempt.get("elapsed_s")
        if elapsed is not None:
            try:
                valid_elapsed = type(elapsed) in (int, float) and math.isfinite(elapsed) and elapsed >= 0
            except OverflowError:
                valid_elapsed = False
            if not valid_elapsed:
                raise _JournalDecodeError("attempt elapsed time is not a finite nonnegative number")
