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
    files = release_manifest.inventory(app)
    assert files["LICENSE"]["sha256"] == release_manifest.sha256(app / "LICENSE")
    (app / "credentials.txt").write_text("-----BEGIN PRIVATE KEY-----", encoding="utf-8")
    with pytest.raises(ValueError, match="Private-key material"):
        release_manifest.inventory(app)
    (app / "credentials.txt").unlink()
    (app / "video.mp4").write_bytes(b"user video")
    with pytest.raises(ValueError, match="Unexpected video"):
        release_manifest.inventory(app)
