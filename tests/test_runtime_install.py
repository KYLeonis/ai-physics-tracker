"""独立 runtime 的下载信任、归档路径与激活事务回归，不联网、不写用户目录。"""

from concurrent.futures import CancelledError
import hashlib
import io
from pathlib import Path
import tarfile
from threading import Event

import pytest

from ai_physics_tracker.infrastructure import runtime_install as runtime


def artifact(data=b"python bytes"):
    return {"filename": "python.tar.gz", "url": "https://github.com/owner/repo/archive.tar.gz",
            "sha256": hashlib.sha256(data).hexdigest(), "size": len(data)}


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
