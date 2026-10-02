"""基础设施层：独立 AI 环境下载、校验、安装与验证后原子激活；不写用户工程。"""

from concurrent.futures import CancelledError
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import shutil
import signal
import subprocess
import tarfile
from threading import Event, Lock
import time
from typing import Callable
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
from uuid import uuid4

from ai_physics_tracker.infrastructure.external_worker import ExternalWorkerRunner, build_request


class RuntimeInstallError(RuntimeError):
    """可恢复的 runtime 安装/验证错误，旧环境不被替换。"""


class RuntimeCancellation(Event):
    """取消与最终发布串行化：先取消则不发布，先提交则报告成功。"""

    def __init__(self) -> None:
        super().__init__()
        self._commit_lock = Lock()
        self.committed = False

    def set(self) -> None:
        with self._commit_lock:
            if not self.committed:
                super().set()

    def commit(self, action: Callable[[], None]) -> None:
        with self._commit_lock:
            if self.is_set():
                raise CancelledError()
            action()
            self.committed = True


@dataclass(frozen=True)
class RuntimeProgress:
    stage: str
    detail: str
    completed: int = 0
    total: int = 0


TRUSTED_DOWNLOAD_HOSTS = frozenset({
    "github.com", "files.pythonhosted.org", "download.pytorch.org", "download-r2.pytorch.org",
})
MAX_EXTRACT_BYTES = 1024 * 1024 * 1024
MAX_EXTRACT_FILES = 30000
POINTER_RELATIVE = Path("runtimes/active.txt")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def atomic_json(path: Path, payload: dict) -> None:
    temporary = path.with_name(path.name + f".{uuid4().hex}.tmp")
    try:
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def validate_artifact(artifact: dict) -> None:
    if not isinstance(artifact, dict):
        raise RuntimeInstallError("Invalid download artifact")
    url = urlsplit(str(artifact.get("url", "")))
    name = artifact.get("filename")
    if url.scheme != "https" or url.hostname not in TRUSTED_DOWNLOAD_HOSTS or url.username or url.password:
        raise RuntimeInstallError("Runtime download must use a trusted HTTPS source")
    if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9_.+%-]+", name):
        raise RuntimeInstallError("Invalid download filename")
    if not re.fullmatch(r"[0-9a-f]{64}", str(artifact.get("sha256", ""))):
        raise RuntimeInstallError("Missing SHA256 for runtime download")
    size = artifact.get("size")
    if not isinstance(size, int) or isinstance(size, bool) or size <= 0:
        raise RuntimeInstallError("Missing download size")


def load_profiles(path: Path) -> tuple[dict, ...]:
    """读取应用随包固定清单；联网时不从 latest index 动态改变版本。"""
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != 1 or not isinstance(payload.get("profiles"), list):
        raise RuntimeInstallError("Unsupported runtime manifest")
    profiles = payload["profiles"]
    identifiers = set()
    for profile in profiles:
        identifier = profile.get("id", "")
        if not re.fullmatch(r"[a-z0-9-]+", identifier) or identifier in identifiers:
            raise RuntimeInstallError("Invalid or duplicate runtime profile")
        identifiers.add(identifier)
        validate_artifact(profile["python"])
        for artifact in profile["packages"]:
            validate_artifact(artifact)
            if not re.fullmatch(r"[A-Za-z0-9_.-]+", str(artifact.get("name", ""))):
                raise RuntimeInstallError("Invalid package name")
            # 唯一源码包是 DLC 的纯 Python filterpy；不让首次安装触发 C/C++ 编译。
            if not artifact["filename"].endswith(".whl") and artifact["name"].lower() != "filterpy":
                raise RuntimeInstallError("Runtime requires an unsupported source build")
    return tuple(profiles)


def profile_supported(profile: dict) -> bool:
    if profile["system"] != platform.system() or platform.machine().lower() not in profile["machines"]:
        return False
    if platform.system() == "Darwin":
        actual = tuple(int(part) for part in platform.mac_ver()[0].split(".")[:2])
        minimum = tuple(int(part) for part in profile["min_os_version"].split("."))
        return actual >= minimum
    return True


def extract_python(archive: Path, destination: Path, cancel: Event) -> None:
    """仅在独占新目录中解包，保留 PBS 内部合法链接，拒绝任何逃逸。"""
    with tarfile.open(archive, "r:gz") as stream:
        members = stream.getmembers()
        if len(members) > MAX_EXTRACT_FILES or sum(m.size for m in members) > MAX_EXTRACT_BYTES:
            raise RuntimeInstallError("Python archive exceeds extraction limits")
        for member in members:
            path = PurePosixPath(member.name)
            if not path.parts or path.parts[0] != "python" or ".." in path.parts or "\\" in member.name:
                raise RuntimeInstallError("Python archive has an unsafe path")
            if cancel.is_set():
                raise CancelledError()
            # Python 3.11/3.12 均显式使用 data filter，不能依赖解释器的默认行为。
            stream.extract(member, destination, filter="data")


def download_artifact(artifact: dict, cache: Path, cancel: Event,
                      report: Callable[[RuntimeProgress], None]) -> Path:
    validate_artifact(artifact)
    target = cache / artifact["filename"]
    if target.is_file() and target.stat().st_size == artifact["size"] and sha256_file(target) == artifact["sha256"]:
        return target
    partial = target.with_name(target.name + ".part")
    # 不复用未验证的部分下载；重试会使用已经验证的其他缓存文件。
    try:
        with urlopen(Request(artifact["url"], headers={"User-Agent": "AI-Physics-Tracker/0.1"}), timeout=15) as source:
            if urlsplit(source.geturl()).scheme != "https":
                raise RuntimeInstallError("Runtime download redirected away from HTTPS")
            with partial.open("wb") as output:
                size = 0
                while block := source.read(256 * 1024):
                    if cancel.is_set():
                        raise CancelledError()
                    size += len(block)
                    if size > artifact["size"]:
                        raise RuntimeInstallError("Runtime download is larger than its manifest")
                    output.write(block)
                    report(RuntimeProgress("Downloading", artifact["filename"], size, artifact["size"]))
        if size != artifact["size"] or sha256_file(partial) != artifact["sha256"]:
            raise RuntimeInstallError(f"Incomplete download or SHA256 mismatch: {artifact['filename']}; retry installation")
        if cancel.is_set():
            raise CancelledError()
        os.replace(partial, target)
        return target
    finally:
        partial.unlink(missing_ok=True)


def _stop_process(process: subprocess.Popen) -> None:
    if os.name == "nt":
        outcome = subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                                 capture_output=True, timeout=10)
        if outcome.returncode and process.poll() is None:
            raise RuntimeInstallError("Could not cancel installer process tree")
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass  # 独占 process group 已退出，仍由 wait 回收父进程。
    process.wait(timeout=10)


def run_command(argv: list[str], log_path: Path, cancel: Event, *, timeout_s: float = 1800) -> None:
    """受信固定 argv 的安装进程，超时/取消都回收整树并保留日志。"""
    from ai_physics_tracker.infrastructure.external_worker import clean_python_environment, start_python_process

    if cancel.is_set():
        raise CancelledError()
    with log_path.open("ab") as log:
        log.write(("\nRunning: " + " ".join(argv) + "\n").encode("utf-8"))
        process = start_python_process(argv, env=clean_python_environment(), log=log)
        deadline = time.monotonic() + timeout_s
        try:
            while process.poll() is None:
                if cancel.wait(0.1):
                    raise CancelledError()
                if time.monotonic() > deadline:
                    raise RuntimeInstallError("Runtime installation timed out; retry or export diagnostics")
            if cancel.is_set():
                raise CancelledError()
            if process.returncode:
                raise RuntimeInstallError(f"Installation command failed (exit {process.returncode}); see {log_path}")
        except BaseException:
            if process.poll() is None:
                _stop_process(process)
            raise


def verify_runtime(python: Path, job_dir: Path, package_root: Path | None, cancel: Event,
                   *, device: str = "auto", expected_versions: dict | None = None) -> dict:
    request, _ = build_request("selftest_runtime", job_id=uuid4(), device=device, package_root=package_root,
                               extra={"verify_dlc": True})
    handle = ExternalWorkerRunner(python, package_root=package_root).start(job_dir, request)
    deadline = time.monotonic() + 180
    while handle.is_alive():
        if cancel.wait(0.1) or time.monotonic() > deadline:
            handle.cancel()
            if cancel.is_set():
                raise CancelledError()
            raise RuntimeInstallError("AI environment self-test timed out")
    if cancel.is_set():
        handle.cancel()
        raise CancelledError()
    result = handle.read_result()
    if result.get("status") != "success":
        raise RuntimeInstallError(f"AI environment self-test failed: {result.get('error')}; see {handle.worker_log_path}")
    if Path(result["executable"]).absolute() != python.absolute():
        raise RuntimeInstallError("AI self-test used a different Python interpreter")
    if expected_versions and not str(result["python"]).startswith("3.12."):
        raise RuntimeInstallError("AI runtime must use Python 3.12")
    for name, version in (expected_versions or {}).items():
        if result["versions"].get(name) != version:
            raise RuntimeInstallError(f"AI runtime version mismatch: {name}")
    return result


def publish_runtime(data_root: Path, python: Path, evidence: dict, cancel: RuntimeCancellation) -> None:
    """先保存验证身份，最后原子替换小型指针；不移动含绝对路径的 venv。"""
    if cancel.is_set():
        raise CancelledError()
    atomic_json(python.parent.parent / "runtime-ready.json", evidence)
    pointer = data_root / POINTER_RELATIVE
    pointer.parent.mkdir(parents=True, exist_ok=True)
    temporary = pointer.with_name(f"active.{uuid4().hex}.tmp")
    try:
        temporary.write_text(str(python.absolute()) + "\n", encoding="utf-8")
        cancel.commit(lambda: os.replace(temporary, pointer))
    finally:
        temporary.unlink(missing_ok=True)


def install_runtime(data_root: Path, profile: dict, package_root: Path | None,
                    cancel: RuntimeCancellation, report: Callable[[RuntimeProgress], None]) -> Path:
    """在固定且独占的新版本目录安装，旧 active/runtime 原封不动保留。"""
    if not profile_supported(profile):
        raise RuntimeInstallError("Runtime profile does not match this computer (Apple Silicon requires macOS 14+)")
    data_root = data_root.absolute()
    parent = data_root / "runtimes"
    parent.mkdir(parents=True, exist_ok=True)
    # OS 文件锁随句柄关闭/进程退出释放，不留下需要判断 PID 的陈旧锁。
    lock = (parent / "install.lock").open("a+b")
    folder = parent / "installs" / (profile["id"] + "-" + uuid4().hex)
    log_path = folder / "install.log"
    digest = hashlib.sha256(json.dumps(profile, sort_keys=True).encode()).hexdigest()
    cache = data_root / "runtime-cache" / digest
    journal = {"status": "installing", "profile": profile["id"], "manifest_sha256": digest}
    try:
        try:
            if os.name == "nt":
                import msvcrt
                lock.write(b"0")
                lock.flush()
                lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            raise RuntimeInstallError("Another AI environment setup is running") from error
        folder.mkdir(parents=True)
        cache.mkdir(parents=True, exist_ok=True)
        atomic_json(folder / "install-state.json", journal)
        required = 3 * (profile["python"]["size"] + sum(a["size"] for a in profile["packages"])) + 512 * 1024**2
        if shutil.disk_usage(folder).free < required:
            raise RuntimeInstallError(f"Not enough free space; need approximately {required / 1024**3:.1f} GiB")
        report(RuntimeProgress("Downloading", "Python and pinned AI packages"))
        archive = download_artifact(profile["python"], cache, cancel, report)
        report(RuntimeProgress("Extracting", "Private Python"))
        extract_python(archive, folder, cancel)
        base_python = folder / ("python/python.exe" if os.name == "nt" else "python/bin/python3")
        report(RuntimeProgress("Creating environment", "Isolated Python 3.12"))
        run_command([str(base_python), "-m", "venv", str(folder / "environment")], log_path, cancel)
        python = folder / ("environment/Scripts/python.exe" if os.name == "nt" else "environment/bin/python")
        paths = {}
        for index, artifact in enumerate(profile["packages"]):
            report(RuntimeProgress("Downloading", f"Package {index+1}/{len(profile['packages'])}: {artifact['name']}"))
            paths[artifact["name"]] = download_artifact(artifact, cache, cancel, report)
        builders = {"setuptools", "wheel", "packaging"}
        for title, selected in (("Preparing installer", builders), ("Installing AI packages", set(paths))):
            lines = [f"{a['name']} @ {paths[a['name']].as_uri()} --hash=sha256:{a['sha256']}"
                     for a in profile["packages"] if a["name"] in selected]
            requirements = folder / ("build-requirements.txt" if selected == builders else "requirements.txt")
            requirements.write_text("\n".join(lines) + "\n", encoding="utf-8")
            report(RuntimeProgress(title, "Installing verified local packages; see log for details"))
            run_command([str(python), "-m", "pip", "install", "--no-index", "--require-hashes", "--no-deps",
                         "--no-build-isolation", "-r", str(requirements)], log_path, cancel)
        run_command([str(python), "-m", "pip", "check"], log_path, cancel)
        report(RuntimeProgress("Self-testing", "Torch forward/backward and DeepLabCut import"))
        versions = {a["name"]: a["version"] for a in profile["packages"] if a["name"] in {"torch", "torchvision", "deeplabcut", "numpy"}}
        result = verify_runtime(python, folder / "selftest", package_root, cancel, expected_versions=versions)
        evidence = {**journal, "status": "ready", "executable": str(python), "selftest": result}
        atomic_json(folder / "install-state.json", evidence)
        # 所有可能失败的持久化先完成，指针替换是最后一个提交点。
        publish_runtime(data_root, python, evidence, cancel)
        return python
    except BaseException as error:
        journal.update(status="cancelled" if isinstance(error, CancelledError) else "failed", error=str(error))
        if folder.is_dir():
            atomic_json(folder / "install-state.json", journal)
        # ponytail: 保留失败目录与日志便于诊断；需要时另做明确的旧环境清理入口。
        raise
    finally:
        lock.close()
