"""Mac wheel 替换保持完整 RECORD；runtime 拒绝损坏/身份不符的新包。"""

import base64
import csv
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import zipfile

import pytest

from ai_physics_tracker.infrastructure import runtime_install as runtime

spec = importlib.util.spec_from_file_location("prepare_opencv_lgpl", Path(__file__).parents[1] / "scripts/prepare_opencv_lgpl.py")
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


def test_repacked_wheel_record_covers_changed_and_removed_files(tmp_path):
    root = tmp_path / "wheel"
    (root / "cv2").mkdir(parents=True)
    (root / "package.dist-info").mkdir()
    (root / "cv2/libavcodec.dylib").write_bytes(b"replacement library")
    (root / "package.dist-info/RECORD").write_bytes(b"stale record")
    target = tmp_path / "repacked.whl"
    builder.write_wheel(root, target)
    with zipfile.ZipFile(target) as archive:
        rows = list(csv.reader(io.StringIO(archive.read("package.dist-info/RECORD").decode())))
        assert {row[0] for row in rows} == set(archive.namelist())
        for name, digest, size in rows:
            if name.endswith("/RECORD"):
                assert digest == size == ""
            else:
                data = archive.read(name)
                assert digest == "sha256=" + base64.urlsafe_b64encode(hashlib.sha256(data).digest()).decode().rstrip("=")
                assert int(size) == len(data)


@pytest.mark.parametrize("damage", [None, "changed_bytes", "wrong_original", "GPL", "duplicate", "missing"])
def test_runtime_replacement_identity_and_hash_preserve_old_pointer(tmp_path, monkeypatch, damage):
    directory = tmp_path / "replacements"
    directory.mkdir()
    filename = "opencv_python_headless-4.11.0.86-cp37-abi3-macosx_13_0_arm64.whl"
    wheel = directory / filename
    wheel.write_bytes(b"replacement wheel")
    original = {"name": "opencv-python-headless", "version": "4.11.0.86", "filename": filename,
                "sha256": "a" * 64, "url": "https://files.pythonhosted.org/original.whl", "size": 100}
    replacement = {**original, "original_sha256": original["sha256"], "sha256": runtime.sha256_file(wheel),
                   "size": wheel.stat().st_size, "ffmpeg": {"license": "LGPL version 2.1 or later"}}
    if damage == "changed_bytes":
        wheel.write_bytes(b"corruption")
    elif damage == "wrong_original":
        replacement["original_sha256"] = "b" * 64
    elif damage == "GPL":
        replacement["ffmpeg"]["license"] = "GPL version 3 or later"
    rows = [replacement, replacement] if damage == "duplicate" else [] if damage == "missing" else [replacement]
    (directory / "manifest.json").write_text(json.dumps({"schema_version": 1, "wheels": rows}), encoding="utf-8")
    profile = {"packages": [original]}
    pointer = tmp_path / runtime.POINTER_RELATIVE
    pointer.parent.mkdir()
    pointer.write_bytes(b"old runtime\n")
    if damage is None:
        assert runtime.verified_opencv_wheels(profile, directory)[original["name"]] == replacement
    else:
        monkeypatch.setattr(runtime, "profile_supported", lambda p: True)
        monkeypatch.setattr(runtime, "download_artifact", lambda *args: pytest.fail("Bad replacement must fail before downloading"))
        with pytest.raises(runtime.RuntimeInstallError):
            runtime.install_runtime(tmp_path, profile, None, runtime.RuntimeCancellation(), lambda p: None, opencv_wheels=directory)
    assert pointer.read_bytes() == b"old runtime\n"
