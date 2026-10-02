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
        runtime.publish_runtime(tmp_path, python, {"status": "ready"}, Event())
    assert pointer.read_text(encoding="utf-8") == "old python\n"
    assert not list(pointer.parent.glob("active.*.tmp"))


def test_cancelled_install_does_not_publish_pointer(tmp_path):
    cancel = Event()
    cancel.set()
    with pytest.raises(CancelledError):
        runtime.publish_runtime(tmp_path, tmp_path / "environment/bin/python", {}, cancel)
    assert not (tmp_path / runtime.POINTER_RELATIVE).exists()


def test_activation_keeps_stable_python_path(tmp_path):
    python = tmp_path / "中文 environment/bin/python"
    python.parent.mkdir(parents=True)
    python.touch()
    runtime.publish_runtime(tmp_path, python, {"status": "ready"}, Event())
    assert (tmp_path / runtime.POINTER_RELATIVE).read_text(encoding="utf-8").strip() == str(python)
    assert (python.parent.parent / "runtime-ready.json").exists()


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
