"""Record Mac build provenance and actual candidate hashes; never publish a release."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
from importlib import metadata
import json
import os
from pathlib import Path
import plistlib
import subprocess
import sys
import tomllib

REPO_ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN_SUFFIXES = {
    ".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v", ".mpg", ".mpeg", ".wmv",
    ".pt", ".pth", ".onnx", ".h5", ".hdf5", ".ckpt", ".safetensors",
    ".p12", ".pfx", ".key", ".p8", ".der",
}


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def git(*args: str) -> str:
    return subprocess.check_output(["git", "-C", str(REPO_ROOT), *args], text=True).strip()


def inventory(root: Path) -> dict[str, dict]:
    """Hash physical files and record links without following them outside the app."""
    files = {}
    for path in sorted(root.rglob("*")):
        name = path.relative_to(root).as_posix()
        if path.is_symlink():
            if not path.resolve(strict=True).is_relative_to(root.resolve()):
                raise ValueError(f"Bundle link escapes candidate: {name}")
            files[name] = {"link": os.readlink(path)}
        elif path.is_file():
            if path.suffix.lower() in FORBIDDEN_SUFFIXES:
                raise ValueError(f"Unexpected video, weight or private-key artifact: {name}")
            # Plain-text resources may include public certificates, but never private keys.
            try:
                content = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                content = ""
            if "PRIVATE KEY-----" in content:
                raise ValueError(f"Private-key material in candidate: {name}")
            files[name] = {"size": path.stat().st_size, "sha256": sha256(path)}
    return files


def validate_inputs(tracked: dict[str, str]) -> None:
    """Ignored files are not source provenance; refuse extra repo inputs collected by spec."""
    for directory in ("src/ai_physics_tracker", "resources/runtime", "packaging/licenses"):
        for path in (REPO_ROOT / directory).rglob("*"):
            if not path.is_file() or (directory.startswith("src/") and path.suffix != ".py"):
                continue
            name = path.relative_to(REPO_ROOT).as_posix()
            if name not in tracked or sha256(path) != tracked[name]:
                raise ValueError(f"Uncommitted bundle input: {name}")


def provenance() -> dict:
    if git("status", "--porcelain", "--untracked-files=normal"):
        raise ValueError("Commit tracked changes before recording build provenance")
    tracked = git("ls-files", "-z").rstrip("\0").split("\0")
    digests = {p: sha256(REPO_ROOT / p) for p in tracked}
    validate_inputs(digests)
    return {
        "schema_version": 1,
        "source_commit": git("rev-parse", "HEAD"),
        "version": tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"],
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "python": sys.version,
        "build_command": "bash packaging/build_macos.sh",
        "build_options": {"developer_id_requested": bool(os.environ.get("APT_CODESIGN_IDENTITY")),
                          "notarization_requested": bool(os.environ.get("APT_NOTARY_PROFILE"))},
        "build_packages": {d.metadata["Name"]: d.version for d in metadata.distributions()},
        "opencv_replacements": opencv_artifacts(Path(os.environ["APT_OPENCV_WHEELS"])) if os.environ.get("APT_OPENCV_WHEELS") else None,
        "tracked_sha256": digests,
    }


def probe(*args: str) -> dict:
    result = subprocess.run(args, capture_output=True, text=True, check=False)
    return {"returncode": result.returncode, "output": (result.stdout + result.stderr).strip()}


def opencv_artifacts(directory: Path) -> dict:
    """校验生成的 wheel 身份/hash，防止清单与随包实际文件分离。"""
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    inputs = json.loads((REPO_ROOT / "packaging/opencv_macos_inputs.json").read_text(encoding="utf-8"))["artifacts"]
    expected = {a["filename"]: a for a in inputs}
    actual = {a["filename"]: a for a in manifest["wheels"]}
    if len(actual) != len(manifest["wheels"]) or actual.keys() != expected.keys():
        raise ValueError("OpenCV replacement artifact set differs from fixed inputs")
    if manifest["ffmpeg_source_sha256"] != "733984395e0dbbe5c046abda2dc49a5544e7e0e1e2366bba849222ae9e3a03b1":
        raise ValueError("OpenCV FFmpeg source differs from approved source")
    for name, artifact in actual.items():
        original = expected[name]
        if (any(artifact[key] != original[key] for key in ("name", "version", "url"))
                or artifact["original_sha256"] != original["sha256"]
                or artifact["ffmpeg"]["license"] != "LGPL version 2.1 or later"
                or sha256(directory / name) != artifact["sha256"]):
            raise ValueError("OpenCV replacement provenance or SHA256 differs")
    return manifest


def candidate(app: Path, dmg: Path, smoke: Path, notary_app: Path | None, notary_dmg: Path | None) -> dict:
    resources = app / "Contents/Resources/resources"
    build = json.loads((resources / "build-info.json").read_text(encoding="utf-8"))
    if build["source_commit"] != git("rev-parse", "HEAD"):
        raise ValueError("Check out the exact candidate source commit before generating its manifest")
    if git("status", "--porcelain", "--untracked-files=normal"):
        raise ValueError("Source checkout changed since build")
    for name, digest in build["tracked_sha256"].items():
        if sha256(REPO_ROOT / name) != digest:
            raise ValueError(f"Source changed since build: {name}")
    validate_inputs(build["tracked_sha256"])
    expected = {name.removeprefix("src/"): digest for name, digest in build["tracked_sha256"].items()
                if name.startswith("src/ai_physics_tracker/") and name.endswith(".py")}
    actual = {p.relative_to(resources / "worker-src").as_posix(): sha256(p)
              for p in (resources / "worker-src").rglob("*.py")}
    if actual != expected:
        raise ValueError("Bundled worker sources differ from candidate source")
    for bundled, source in (("runtime/manifest.json", "resources/runtime/manifest.json"),
                            ("LICENSE", "LICENSE"), ("NOTICE-third-party.md", "packaging/NOTICE-third-party.md")):
        if sha256(resources / bundled) != build["tracked_sha256"][source]:
            raise ValueError(f"Bundled source material differs: {bundled}")
    with (app / "Contents/Info.plist").open("rb") as stream:
        info = plistlib.load(stream)
    if info["CFBundleShortVersionString"] != build["version"]:
        raise ValueError("Bundle version differs from source version")
    smoke_result = json.loads(smoke.read_text(encoding="utf-8"))
    if smoke_result.get("status") != "ok" or smoke_result.get("forbidden_modules") != []:
        raise ValueError("Native smoke did not pass host isolation")
    files = inventory(app)
    replacements = opencv_artifacts(resources / "opencv-lgpl")
    if replacements != build.get("opencv_replacements") or smoke_result.get("opencv_ffmpeg_license") != "LGPL version 2.1 or later":
        raise ValueError("Bundled OpenCV replacements differ from build or native license check")
    signature = probe("codesign", "-dv", "--verbose=4", str(app))
    verification = probe("codesign", "--verify", "--deep", "--strict", str(app))
    if verification["returncode"]:
        raise ValueError("Candidate app signature does not verify")
    developer_id = "Authority=Developer ID Application:" in signature["output"]
    receipts = {}
    if bool(notary_app) != bool(notary_dmg):
        raise ValueError("Provide both app and DMG notarization receipts")
    if notary_app and notary_dmg:
        for name, path in (("app", notary_app), ("dmg", notary_dmg)):
            receipt = json.loads(path.read_text(encoding="utf-8"))
            if receipt.get("status") != "Accepted":
                raise ValueError(f"Notarization was not Accepted: {name}")
            receipts[name] = receipt
    tickets = {"app": probe("xcrun", "stapler", "validate", str(app)),
               "dmg": probe("xcrun", "stapler", "validate", str(dmg))}
    gatekeeper = probe("spctl", "--assess", "--type", "execute", str(app))
    notarized = developer_id and bool(receipts) and all(p["returncode"] == 0 for p in tickets.values()) and gatekeeper["returncode"] == 0
    if receipts and not notarized:
        raise ValueError("Accepted receipts require valid Developer ID, staple tickets and Gatekeeper assessment")
    return {
        "schema_version": 1, "build": build,
        "dmg": {"filename": dmg.name, "size": dmg.stat().st_size, "sha256": sha256(dmg)},
        "ffmpeg_sources": {"filename": f"AIPhysicsTracker-{build['version']}-ffmpeg-sources.zip",
                           "sha256": sha256(dmg.parent / f"AIPhysicsTracker-{build['version']}-ffmpeg-sources.zip")},
        "app": {"name": app.name, "minimum_macos": info["LSMinimumSystemVersion"],
                "logical_bytes": sum(v.get("size", 0) for v in files.values()), "files": files},
        "native_smoke": {k: smoke_result[k] for k in ("status", "runtime_profiles", "joint_csv_frames", "forbidden_modules", "video_read_write_seek", "opencv_ffmpeg_license")},
        "signing": {"status": "developer_id_notarized" if notarized else "developer_id_unnotarized" if developer_id else "ad_hoc",
                    "signature": signature, "verification": verification, "staples": tickets,
                    "gatekeeper": gatekeeper, "receipts": receipts},
        "verification_references": {
            "source_ci_checks": f"https://github.com/KYLeonis/ai-physics-tracker/commit/{build['source_commit']}/checks",
            "ci_status": "Check the exact source checks; this build does not certify CI completion",
            "plan": "publication/plans/p6.4-release-preparation.md",
            "evidence": "publication/evidence/runtime/p6.4-release-preparation.md",
            "review": "docs/reviews/publication-p6.4-review.md",
        },
        "public_release_authorized": False,
        "pending_gates": ["actual dependency/source material review", "signed download human review", "installed teacher-import", "student two-path pilot",
                          "complete installed scientific export/recovery evidence", "Windows real-machine verification"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    source = commands.add_parser("provenance")
    source.add_argument("--output", type=Path, required=True)
    rc = commands.add_parser("candidate")
    for name in ("app", "dmg", "smoke", "output"):
        rc.add_argument(f"--{name}", type=Path, required=True)
    rc.add_argument("--notary-app", type=Path)
    rc.add_argument("--notary-dmg", type=Path)
    args = parser.parse_args()
    data = provenance() if args.command == "provenance" else candidate(
        args.app, args.dmg, args.smoke, args.notary_app, args.notary_dmg)
    args.output.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Recorded {args.command}: {args.output}")


if __name__ == "__main__":
    main()
