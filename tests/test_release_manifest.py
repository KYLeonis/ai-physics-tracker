"""Release inventories must not include user data or follow external bundle links."""

import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location("release_manifest", Path(__file__).parents[1] / "scripts/release_manifest.py")
release_manifest = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release_manifest)


def test_release_inventory_hashes_files_and_rejects_private_material(tmp_path: Path) -> None:
    app = tmp_path / "app"
    app.mkdir()
    (app / "LICENSE").write_text("public license", encoding="utf-8")
    # Native TLS libraries include PEM label constants, not private credentials.
    (app / "tls.dylib").write_bytes(b"\xcf\xfa\xed\xfe" + b"PRIVATE KEY-----")
    files = release_manifest.inventory(app)
    assert files["LICENSE"]["sha256"] == release_manifest.sha256(app / "LICENSE")
    (app / "credentials.txt").write_text(" " * (2 * 1024**2) + "-----BEGIN PRIVATE KEY-----", encoding="utf-8")
    with pytest.raises(ValueError, match="Private-key material"):
        release_manifest.inventory(app)
    (app / "credentials.txt").unlink()
    (app / "video.mp4").write_bytes(b"user video")
    with pytest.raises(ValueError, match="Unexpected video"):
        release_manifest.inventory(app)


@pytest.mark.parametrize("name", ["video.mkv", "snapshot.h5", "private.p8"])
def test_release_inventory_rejects_other_private_artifact_types(tmp_path: Path, name: str) -> None:
    (tmp_path / name).write_bytes(b"private artifact")
    with pytest.raises(ValueError, match="Unexpected video, weight or private-key"):
        release_manifest.inventory(tmp_path)


def test_provenance_rejects_ignored_source_or_resource_inputs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(release_manifest, "REPO_ROOT", tmp_path)
    source = tmp_path / "resources/runtime/untracked.json"
    source.parent.mkdir(parents=True)
    source.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="Uncommitted bundle input"):
        release_manifest.validate_inputs({})


def test_candidate_rejects_a_source_commit_mismatch_before_signing_checks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    app = tmp_path / "app"
    resources = app / "Contents/Resources/resources"
    resources.mkdir(parents=True)
    (resources / "build-info.json").write_text('{"source_commit": "old"}', encoding="utf-8")
    monkeypatch.setattr(release_manifest, "git", lambda *args: "new")
    with pytest.raises(ValueError, match="exact candidate source commit"):
        release_manifest.candidate(app, tmp_path / "a.dmg", tmp_path / "smoke.json", None, None)
