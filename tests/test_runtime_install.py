"""独立 runtime 的下载信任、归档路径与激活事务回归，不联网、不写用户目录。"""

from concurrent.futures import CancelledError
import hashlib
import io
import json
from pathlib import Path
import re
import tarfile
from threading import Event

import pytest

from ai_physics_tracker.infrastructure import runtime_install as runtime
from ai_physics_tracker.infrastructure.errors import ExternalWorkerError


def artifact(data=b"python bytes"):
    return {"filename": "python.tar.gz", "url": "https://github.com/owner/repo/archive.tar.gz",
            "sha256": hashlib.sha256(data).hexdigest(), "size": len(data)}


class _FakeResponse(io.BytesIO):
    """带 status/headers/geturl 的离线应答；payload 读尽后再读会按需抛出网络层异常。"""

    def __init__(self, payload, status=200, content_range=None, eof_error=None):
        super().__init__(payload)
        self.status = status
        self.headers = {"Content-Range": content_range} if content_range else {}
        self._eof_error = eof_error

    def geturl(self):
        return "https://github.com/asset"

    def read(self, size=-1):
        block = super().read(size)
        if not block and self._eof_error is not None:
            raise self._eof_error
        return block


def _flaky_resuming_server(data, calls, *, drop_index=0, honor_range=True):
    """第 drop_index 次请求在半途断流；若客户端带 Range 且服务器支持则返回 206 续传。"""
    half = len(data) // 2

    def serve(request, *args, **kwargs):
        calls.append(request)
        range_header = request.headers.get("Range")
        if len(calls) > drop_index + 1 and range_header and honor_range:
            offset = int(re.match(r"bytes=(\d+)-", range_header).group(1))
            return _FakeResponse(data[offset:], status=206,
                                 content_range=f"bytes {offset}-{len(data) - 1}/{len(data)}")
        return _FakeResponse(data[:half], eof_error=ConnectionResetError("simulated proxy drop"))

    return serve


@pytest.mark.parametrize("change", [{"url": "http://github.com/archive"}, {"url": "https://evil.example/download"},
                                    {"filename": "../python"}, {"sha256": "bad"}, {"size": -1}])
def test_download_rejects_untrusted_manifest(change):
    with pytest.raises(runtime.RuntimeInstallError):
        runtime.validate_artifact({**artifact(), **change})


def test_truncated_download_never_becomes_cached_runtime(monkeypatch, tmp_path):
    class Response(io.BytesIO):
        def geturl(self):
            return "https://github.com/asset"

    monkeypatch.setattr(runtime, "urlopen", lambda *a, **k: Response(b"short"))
    with pytest.raises(runtime.RuntimeInstallError, match="Incomplete"):
        runtime.download_artifact(artifact(), tmp_path, Event(), lambda p: None)
    assert not list(tmp_path.iterdir())


def test_verified_cache_is_reused_without_network(monkeypatch, tmp_path):
    data = b"python bytes"
    target = tmp_path / "python.tar.gz"
    target.write_bytes(data)
    monkeypatch.setattr(runtime, "urlopen", lambda *a, **k: pytest.fail("network used"))
    assert runtime.download_artifact(artifact(data), tmp_path, Event(), lambda p: None) == target


@pytest.mark.parametrize("name,link", [("python/../../escape", ""), ("python/link", "../../escape"),
                                    ("/python/escape", ""), ("python\\escape", "")])
def test_python_archive_rejects_escaping_paths(tmp_path, name, link):
    archive = tmp_path / "python.tar.gz"
    with tarfile.open(archive, "w:gz") as tf:
        info = tarfile.TarInfo(name)
        if link:
            info.type = tarfile.SYMTYPE
            info.linkname = link
        tf.addfile(info)
    with pytest.raises((runtime.RuntimeInstallError, tarfile.FilterError)):
        runtime.extract_python(archive, tmp_path / "new", Event())
    assert not (tmp_path.parent / "escape").exists()


def test_failed_pointer_replace_preserves_old_environment(monkeypatch, tmp_path):
    pointer = tmp_path / runtime.POINTER_RELATIVE
    pointer.parent.mkdir(parents=True)
    pointer.write_text("old python\n", encoding="utf-8")
    python = tmp_path / "new/environment/bin/python"
    python.parent.mkdir(parents=True)
    python.touch()
    original = runtime.os.replace

    def reject_pointer(source, target):
        if Path(target) == pointer:
            raise OSError("injected file lock")
        original(source, target)

    monkeypatch.setattr(runtime.os, "replace", reject_pointer)
    with pytest.raises(OSError, match="file lock"):
        runtime.publish_runtime(tmp_path, python, {"status": "ready"}, runtime.RuntimeCancellation())
    assert pointer.read_text(encoding="utf-8") == "old python\n"
    assert not list(pointer.parent.glob("active.*.tmp"))


def test_cancelled_install_does_not_publish_pointer(tmp_path):
    cancel = runtime.RuntimeCancellation()
    cancel.set()
    with pytest.raises(CancelledError):
        runtime.publish_runtime(tmp_path, tmp_path / "environment/bin/python", {}, cancel)
    assert not (tmp_path / runtime.POINTER_RELATIVE).exists()


def test_activation_keeps_stable_python_path(tmp_path):
    python = tmp_path / "中文 environment/bin/python"
    python.parent.mkdir(parents=True)
    python.touch()
    runtime.publish_runtime(tmp_path, python, {"status": "ready"}, runtime.RuntimeCancellation())
    assert (tmp_path / runtime.POINTER_RELATIVE).read_text(encoding="utf-8").strip() == str(python)
    assert (python.parent.parent / "runtime-ready.json").exists()


def test_cancel_and_activation_have_one_commit_order(tmp_path):
    from threading import Thread

    cancel = runtime.RuntimeCancellation()
    entered, release = Event(), Event()

    def publish():
        entered.set()
        assert release.wait(2)

    committing = Thread(target=lambda: cancel.commit(publish))
    committing.start()
    assert entered.wait(2)
    cancelling = Thread(target=cancel.set)
    cancelling.start()
    release.set()
    committing.join(2)
    cancelling.join(2)
    assert cancel.committed and not cancel.is_set()


def test_macos_profile_rejects_old_os_before_downloading(monkeypatch):
    monkeypatch.setattr(runtime.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(runtime.platform, "machine", lambda: "arm64")
    monkeypatch.setattr(runtime.platform, "mac_ver", lambda: ("13.7", (), ""))
    assert not runtime.profile_supported({"system": "Darwin", "machines": ["arm64"], "min_os_version": "14.0"})


@pytest.mark.parametrize("device", ["auto", "cpu", "cuda"])
def test_runtime_verification_uses_protocol_identity(monkeypatch, tmp_path, device):
    python = tmp_path / "environment/bin/python"

    class Handle:
        def is_alive(self):
            return False

        def read_result(self):
            return {"status": "success", "executable": str(python), "python": "3.12.15",
                    "versions": {"deeplabcut": "3.0.1"}}

    class Runner:
        def __init__(self, *args, **kwargs):
            pass

        def start(self, job, request):
            assert request["job_id"] and request["verify_dlc"] is True
            assert request["device"] == device
            return Handle()

    monkeypatch.setattr(runtime, "ExternalWorkerRunner", Runner)
    result = runtime.verify_runtime(python, tmp_path / "check", None, Event(),
                                    device=device, expected_versions={"deeplabcut": "3.0.1"})
    assert result["status"] == "success"


def test_cuda_profile_cannot_activate_after_cpu_fallback(monkeypatch, tmp_path):
    pointer = tmp_path / runtime.POINTER_RELATIVE
    pointer.parent.mkdir(parents=True)
    pointer.write_text("old runtime\n", encoding="utf-8")
    profile = {"id": "windows-x64-cuda", "system": "Windows", "python": artifact(), "packages": []}
    monkeypatch.setattr(runtime, "profile_supported", lambda p: True)
    monkeypatch.setattr(runtime, "download_artifact", lambda *args: tmp_path / "fake.tar.gz")
    monkeypatch.setattr(runtime, "extract_python", lambda *args: None)
    monkeypatch.setattr(runtime, "run_command", lambda *args: None)

    def reject_cuda(*args, **kwargs):
        assert kwargs["device"] == "cuda"
        raise runtime.RuntimeInstallError("CUDA unavailable")

    monkeypatch.setattr(runtime, "verify_runtime", reject_cuda)
    with pytest.raises(runtime.RuntimeInstallError, match="CUDA unavailable"):
        runtime.install_runtime(tmp_path, profile, None, runtime.RuntimeCancellation(), lambda p: None)
    assert pointer.read_text(encoding="utf-8") == "old runtime\n"


@pytest.mark.parametrize("error", [CancelledError(), runtime.RuntimeInstallError("injected installer failure")])
def test_install_failure_releases_lock_and_keeps_old_pointer(monkeypatch, tmp_path, error):
    pointer = tmp_path / runtime.POINTER_RELATIVE
    pointer.parent.mkdir(parents=True)
    pointer.write_text("old runtime\n", encoding="utf-8")
    profile = {"id": "test", "system": runtime.platform.system(),
               "machines": [runtime.platform.machine().lower()], "min_os_version": "14.0",
               "python": artifact(), "packages": []}
    monkeypatch.setattr(runtime, "download_artifact", lambda *args: tmp_path / "fake.tar.gz")
    monkeypatch.setattr(runtime, "extract_python", lambda *args: None)

    def fail(*args, **kwargs):
        raise error

    monkeypatch.setattr(runtime, "run_command", fail)
    for _ in range(2):
        with pytest.raises(type(error)):
            runtime.install_runtime(tmp_path, profile, None, runtime.RuntimeCancellation(), lambda p: None)
        assert pointer.read_text(encoding="utf-8") == "old runtime\n"


def test_frozen_environment_removes_bundle_path_and_python_configuration(monkeypatch, tmp_path):
    import sys
    from ai_physics_tracker.infrastructure.external_worker import clean_python_environment

    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path / "bundle"), raising=False)
    monkeypatch.setenv("PATH", str(tmp_path / "bundle") + runtime.os.pathsep + str(tmp_path / "system"))
    monkeypatch.setenv("PYTHONHOME", "wrong")
    monkeypatch.setenv("PYTHONPATH", "wrong")
    env = clean_python_environment()
    assert env["PATH"] == str(tmp_path / "system")
    assert "PYTHONHOME" not in env and "PYTHONPATH" not in env


def test_transient_drop_is_retried_with_range_resume(monkeypatch, tmp_path):
    import ssl
    from urllib.error import URLError
    monkeypatch.setattr(runtime, "DOWNLOAD_RETRY_BACKOFF_S", (0, 0, 0, 0))
    data = b"x" * 4096
    drops = [ConnectionResetError("reset"), TimeoutError("read timed out"),
             ssl.SSLEOFError("EOF in violation"), URLError(ConnectionResetError("connect reset"))]
    for index, drop in enumerate(drops):
        cache = tmp_path / f"case{index}"
        cache.mkdir()
        calls = []
        monkeypatch.setattr(runtime, "urlopen", _flaky_resuming_server(data, calls))
        progress = []
        target = runtime.download_artifact(artifact(data), cache, Event(), progress.append)
        assert target.read_bytes() == data
        assert len(calls) == 2
        assert calls[1].headers.get("Range") == f"bytes={len(data) // 2}-"
        assert any(p.stage == "Retrying download" for p in progress)
        assert list(cache.iterdir()) == [target]


def test_server_ignoring_range_restarts_whole_file(monkeypatch, tmp_path):
    monkeypatch.setattr(runtime, "DOWNLOAD_RETRY_BACKOFF_S", (0, 0, 0, 0))
    data = b"y" * 2048
    calls = []
    half = len(data) // 2

    def serve(request, *args, **kwargs):
        calls.append(request)
        if len(calls) == 1:
            return _FakeResponse(data[:half], eof_error=TimeoutError("stalled stream"))
        return _FakeResponse(data)

    monkeypatch.setattr(runtime, "urlopen", serve)
    target = runtime.download_artifact(artifact(data), tmp_path, Event(), lambda p: None)
    assert target.read_bytes() == data
    assert [c.headers.get("Range") for c in calls] == [None, f"bytes={half}-"]
    assert list(tmp_path.iterdir()) == [target]


def test_retry_exhaustion_raises_and_cleans_partial(monkeypatch, tmp_path):
    monkeypatch.setattr(runtime, "DOWNLOAD_RETRY_ATTEMPTS", 3)
    monkeypatch.setattr(runtime, "DOWNLOAD_RETRY_BACKOFF_S", (0, 0))
    data = b"z" * 100
    calls = []

    def serve(request, *args, **kwargs):
        calls.append(request)
        return _FakeResponse(data[:10], eof_error=ConnectionResetError("drop"))

    monkeypatch.setattr(runtime, "urlopen", serve)
    with pytest.raises(runtime.RuntimeInstallError, match="3 attempts"):
        runtime.download_artifact(artifact(data), tmp_path, Event(), lambda p: None)
    assert len(calls) == 3
    assert list(tmp_path.iterdir()) == []


def test_http_404_fails_immediately_while_502_is_retried(monkeypatch, tmp_path):
    from urllib.error import HTTPError
    data = b"w" * 512
    calls = []

    def serve_404(request, *args, **kwargs):
        calls.append(request)
        raise HTTPError(request.full_url, 404, "Not Found", None, None)

    monkeypatch.setattr(runtime, "urlopen", serve_404)
    with pytest.raises(HTTPError):
        runtime.download_artifact(artifact(data), tmp_path, Event(), lambda p: None)
    assert len(calls) == 1
    assert list(tmp_path.iterdir()) == []

    calls.clear()
    pending = [HTTPError("https://github.com/asset", 502, "Bad Gateway", None, None)]

    def serve_502_then_ok(request, *args, **kwargs):
        calls.append(request)
        if pending:
            raise pending.pop(0)
        return _FakeResponse(data)

    monkeypatch.setattr(runtime, "DOWNLOAD_RETRY_BACKOFF_S", (0, 0, 0, 0))
    monkeypatch.setattr(runtime, "urlopen", serve_502_then_ok)
    target = runtime.download_artifact(artifact(data), tmp_path, Event(), lambda p: None)
    assert target.read_bytes() == data
    assert len(calls) == 2


def test_cancel_during_backoff_aborts_without_further_attempts(monkeypatch, tmp_path):
    data = b"q" * 256
    calls = []
    cancel = Event()
    monkeypatch.setattr(runtime, "urlopen", _flaky_resuming_server(data, calls))

    def report(progress):
        if progress.stage == "Retrying download":
            cancel.set()

    monkeypatch.setattr(runtime, "DOWNLOAD_RETRY_BACKOFF_S", (30.0, 30.0))
    with pytest.raises(CancelledError):
        runtime.download_artifact(artifact(data), tmp_path, cancel, report)
    assert len(calls) == 1
    assert list(tmp_path.iterdir()) == []


def _write_ready_install(root, profile):
    digest = hashlib.sha256(json.dumps(profile, sort_keys=True).encode()).hexdigest()
    folder = root / "runtimes" / "installs" / (profile["id"] + "-ready01")
    python = folder / ("environment/Scripts/python.exe" if runtime.os.name == "nt" else "environment/bin/python")
    python.parent.mkdir(parents=True)
    python.write_bytes(b"stub")
    (folder / "selftest").mkdir()
    (folder / "selftest" / "request.json").write_text("{}\n", encoding="utf-8")
    runtime.atomic_json(folder / "install-state.json",
                        {"status": "ready", "manifest_sha256": digest,
                         "opencv_replacements": {}, "executable": str(python)})
    return python


@pytest.fixture
def install_profile():
    return {"id": "test-cpu", "system": runtime.platform.system(),
            "machines": [runtime.platform.machine().lower()], "min_os_version": "14.0",
            "python": artifact(), "packages": []}


def test_install_reuses_verified_ready_install_without_reinstall(monkeypatch, tmp_path, install_profile):
    profile = install_profile
    python = _write_ready_install(tmp_path, profile)
    pointer = tmp_path / runtime.POINTER_RELATIVE
    pointer.parent.mkdir(parents=True, exist_ok=True)
    pointer.write_text("old runtime\n", encoding="utf-8")

    def forbidden(*args, **kwargs):
        raise AssertionError("fresh install path used although a ready install exists")

    monkeypatch.setattr(runtime, "download_artifact", forbidden)
    monkeypatch.setattr(runtime, "extract_python", forbidden)
    monkeypatch.setattr(runtime, "run_command", forbidden)

    def accept(*args, **kwargs):
        return {"status": "success", "executable": str(python), "python": "3.12.15", "versions": {}}

    monkeypatch.setattr(runtime, "verify_runtime", accept)
    progress = []
    result = runtime.install_runtime(tmp_path, profile, None, runtime.RuntimeCancellation(), progress.append)
    assert result == python
    assert pointer.read_text(encoding="utf-8").strip() == str(python)
    assert any(p.stage == "Re-verifying" for p in progress)


@pytest.mark.parametrize("failure", [runtime.RuntimeInstallError("interpreter corrupted"),
                                     ExternalWorkerError("invalid worker result"),
                                     OSError("interpreter cannot start")])
def test_broken_ready_install_falls_back_to_fresh_install(monkeypatch, tmp_path, install_profile, failure):
    profile = install_profile
    stale = _write_ready_install(tmp_path, profile)
    downloaded = []

    def record_download(*args, **kwargs):
        downloaded.append(args)
        return tmp_path / "fake.tar.gz"

    verify_calls = []

    def verify(python, *args, **kwargs):
        verify_calls.append(python)
        if len(verify_calls) == 1:
            raise failure
        return {"status": "success", "executable": str(python), "python": "3.12.15", "versions": {}}

    def fake_extract(archive, destination, *a):
        relative = "environment/Scripts/python.exe" if runtime.os.name == "nt" else "environment/bin/python"
        python = destination / relative
        python.parent.mkdir(parents=True, exist_ok=True)
        python.write_bytes(b"stub")

    monkeypatch.setattr(runtime, "download_artifact", record_download)
    monkeypatch.setattr(runtime, "extract_python", fake_extract)
    monkeypatch.setattr(runtime, "run_command", lambda *a: None)
    monkeypatch.setattr(runtime, "verify_runtime", verify)
    result = runtime.install_runtime(tmp_path, profile, None, runtime.RuntimeCancellation(), lambda p: None)
    assert downloaded and len(verify_calls) == 2
    assert result != stale and result.is_file()
    pointer = (tmp_path / runtime.POINTER_RELATIVE).read_text(encoding="utf-8").strip()
    assert pointer == str(result)


def test_repeated_reuse_keeps_old_selftest_and_uses_exclusive_worker_jobs(monkeypatch, tmp_path, install_profile):
    from ai_physics_tracker.infrastructure import external_worker

    python = _write_ready_install(tmp_path, install_profile)
    folder = python.parent.parent.parent
    old_request = folder / "selftest" / "request.json"
    jobs = []

    class ExitedProcess:
        returncode = 0

        def poll(self):
            return self.returncode

        def wait(self, timeout=None):
            return self.returncode

    def start(argv, **kwargs):
        request = Path(argv[-1])
        assert request.is_file()
        jobs.append(request.parent)
        return ExitedProcess()

    def read_result(handle):
        handle.join()
        return {"status": "success", "executable": str(python), "python": "3.12.15", "versions": {}}

    # 保留真实 verify_runtime 与 runner 的目录/请求检查，只替换 AI 子进程及其输出。
    monkeypatch.setattr(external_worker, "start_python_process", start)
    monkeypatch.setattr(external_worker.ExternalJobHandle, "read_result", read_result)
    monkeypatch.setattr(runtime, "download_artifact", lambda *a: pytest.fail("reusable environment reinstalled"))
    for _ in range(2):
        assert runtime.install_runtime(tmp_path, install_profile, None, runtime.RuntimeCancellation(), lambda p: None) == python
    assert len(jobs) == len(set(jobs)) == 2
    assert all(job.parent == folder and job != old_request.parent for job in jobs)
    assert old_request.read_text(encoding="utf-8") == "{}\n"


@pytest.mark.parametrize("failure", [CancelledError(), ExternalWorkerError("invalid worker result")])
def test_failed_reuse_and_fallback_preserve_pointer_and_release_lock(monkeypatch, tmp_path, install_profile, failure):
    python = _write_ready_install(tmp_path, install_profile)
    pointer = tmp_path / runtime.POINTER_RELATIVE
    pointer.write_text("old runtime\n", encoding="utf-8")

    def reject(*args, **kwargs):
        raise failure

    def download(*args, **kwargs):
        if isinstance(failure, CancelledError):
            pytest.fail("cancelled reuse started a fresh installation")
        raise runtime.RuntimeInstallError("fresh install failed")

    monkeypatch.setattr(runtime, "verify_runtime", reject)
    monkeypatch.setattr(runtime, "download_artifact", download)
    expected = CancelledError if isinstance(failure, CancelledError) else runtime.RuntimeInstallError
    message = None if expected is CancelledError else "fresh install failed"
    for _ in range(2):
        with pytest.raises(expected, match=message):
            runtime.install_runtime(tmp_path, install_profile, None, runtime.RuntimeCancellation(), lambda p: None)
        assert pointer.read_text(encoding="utf-8") == "old runtime\n"
        assert python.is_file()


def test_taskkill_cleanup_runs_without_console_window(monkeypatch):
    import os
    import subprocess

    if os.name != "nt":
        pytest.skip("Windows-specific console suppression")
    captured = {}

    class _FakeRun:
        returncode = 0

    class _FakeProcess:
        pid = 4242

        def poll(self):
            return None

        def wait(self, timeout=None):
            return 0

    def fake_run(argv, **kwargs):
        captured["argv"] = argv
        captured.update(kwargs)
        return _FakeRun()

    monkeypatch.setattr(runtime.subprocess, "run", fake_run)
    runtime._stop_process(_FakeProcess())
    assert captured["argv"][0] == "taskkill"
    assert captured.get("creationflags", 0) & subprocess.CREATE_NO_WINDOW
