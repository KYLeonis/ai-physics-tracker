"""构建侧：替换固定 Mac wheels 的 FFmpeg 动态闭包，保留 OpenCV API 和原许可。"""

import argparse
import base64
import csv
import ctypes
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from urllib.request import urlopen
import zipfile

REPO_ROOT = Path(__file__).resolve().parents[1]
FFMPEG_NAMES = ("libavcodec", "libavformat", "libavutil", "libswscale", "libswresample", "libavdevice")


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def dependencies(path: Path) -> list[str]:
    text = subprocess.check_output(["otool", "-L", str(path)], text=True)
    return [line.strip().split(" (", 1)[0] for line in text.splitlines()[1:]]


def write_wheel(root: Path, target: Path) -> None:
    """任何库字节修改都重写 RECORD，不能保留上游的旧 digest。"""
    record = next(root.glob("*.dist-info/RECORD"))
    output = io.StringIO(newline="")
    rows = csv.writer(output, lineterminator="\n")
    for path in sorted(root.rglob("*")):
        if path.is_file() and path != record:
            digest = base64.urlsafe_b64encode(bytes.fromhex(sha256(path))).decode().rstrip("=")
            rows.writerow((path.relative_to(root).as_posix(), "sha256=" + digest, path.stat().st_size))
    rows.writerow((record.relative_to(root).as_posix(), "", ""))
    record.write_text(output.getvalue(), encoding="utf-8")
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as wheel:
        for path in sorted(root.rglob("*")):
            if path.is_file():
                info = zipfile.ZipInfo(path.relative_to(root).as_posix(), date_time=(1980, 1, 1, 0, 0, 0))
                info.external_attr = (0o100644 << 16)
                wheel.writestr(info, path.read_bytes(), compress_type=zipfile.ZIP_DEFLATED)


def audit_libraries(root: Path) -> dict:
    """检查实际链接和 libavcodec 报告，OpenCV 旧 build-info 不能代表替换库。"""
    libraries = list(root.glob("*.dylib"))
    for stem in FFMPEG_NAMES:
        library = ctypes.CDLL(str(next(root.glob(stem + ".*.dylib"))))
        license_function = getattr(library, stem.removeprefix("lib") + "_license")
        configuration_function = getattr(library, stem.removeprefix("lib") + "_configuration")
        license_function.restype = configuration_function.restype = ctypes.c_char_p
        license_text = license_function().decode()
        configuration = configuration_function().decode()
        if license_text != "LGPL version 2.1 or later" or any(
            flag in configuration for flag in ("--enable-gpl", "--enable-nonfree", "--enable-version3")
        ):
            raise ValueError("FFmpeg library is not the approved LGPL build")
    for path in libraries:
        for dep in dependencies(path):
            if dep.startswith("@loader_path/") and not (root / Path(dep).name).is_file():
                raise ValueError(f"Missing library: {dep}")
            if not dep.startswith(("@loader_path/", "/usr/lib/", "/System/Library/")):
                raise ValueError(f"External or unrelocated library: {dep}")
    return {"license": license_text, "configuration": configuration,
            "libraries": {p.name: sha256(p) for p in libraries}}


def repair_wheel(wheel: Path, prefix: Path, target: Path) -> dict:
    with tempfile.TemporaryDirectory(prefix="apt-opencv-wheel-") as temporary:
        root = Path(temporary)
        with zipfile.ZipFile(wheel) as archive:
            archive.extractall(root)  # 输入仅为下面固定 SHA 验证过的官方 wheel。
        cv2 = root / "cv2/cv2.abi3.so"
        old = root / "cv2/.dylibs"
        # OpenCV 的 AVIF 图像支持仍保留其非 FFmpeg 动态闭包，不能删整个目录。
        kept = set()

        def keep(name: str) -> None:
            if name in kept or name.startswith(FFMPEG_NAMES):
                return
            if not (old / name).is_file():
                raise ValueError(f"Missing original OpenCV dependency: {name}")
            kept.add(name)
            for dep in dependencies(old / name):
                if dep.startswith("@loader_path/") and Path(dep).name != name:
                    keep(Path(dep).name)

        for dep in dependencies(cv2):
            if dep.startswith("@loader_path/.dylibs/"):
                keep(Path(dep).name)
        for path in old.iterdir():
            if path.name not in kept:
                path.unlink()
        copied = {}
        for name in FFMPEG_NAMES:
            source = next(p for p in (prefix / "lib").glob(name + ".*.dylib") if not p.is_symlink())
            destination = old / source.name
            shutil.copyfile(source, destination)
            copied[name] = destination.name
        # 改 dylib 的绝对 install-id 和 OpenCV 的旧 patch 名称，major ABI 保持不变。
        for path in [cv2, *old.glob("*.dylib")]:
            changes = []
            if path != cv2:
                changes += ["-id", "@loader_path/" + path.name]
            for dep in dependencies(path):
                name = Path(dep).name
                stem = next((s for s in FFMPEG_NAMES if name.startswith(s + ".")), None)
                if stem:
                    # 4.11 wheel codec patch .100 → 7.1.1 .101；只允许同 major。
                    if name.split(".")[1] != copied[stem].split(".")[1]:
                        raise ValueError("FFmpeg major ABI mismatch")
                    replacement = "@loader_path/" + (".dylibs/" if path == cv2 else "") + copied[stem]
                    if dep != replacement:
                        changes += ["-change", dep, replacement]
            if changes:
                subprocess.run(["install_name_tool", *changes, str(path)], check=True, capture_output=True)
            identity = os.environ.get("APT_CODESIGN_IDENTITY", "-") or "-"
            signing = ["codesign", "--force", "--sign", identity]
            if identity != "-":
                signing += ["--timestamp", "--options", "runtime"]
            subprocess.run([*signing, str(path)], check=True, capture_output=True)
        evidence = audit_libraries(old)
        write_wheel(root, target)
        return evidence


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    cache = args.build / "original-wheels"
    cache.mkdir(exist_ok=True)
    inputs = json.loads((REPO_ROOT / "packaging/opencv_macos_inputs.json").read_text(encoding="utf-8"))
    result = {"schema_version": 1, "ffmpeg_source_sha256": sha256(args.build / "ffmpeg-7.1.1.tar.xz"), "wheels": []}
    for artifact in inputs["artifacts"]:
        original = cache / artifact["filename"]
        if not original.is_file():
            with urlopen(artifact["url"], timeout=60) as source, original.open("wb") as output:
                shutil.copyfileobj(source, output)
        if sha256(original) != artifact["sha256"] or original.stat().st_size != artifact["size"]:
            raise ValueError("Original OpenCV wheel differs from fixed input")
        target = args.output / artifact["filename"]
        prefix = Path((args.build / "prefix-path.txt").read_text(encoding="utf-8").strip())
        evidence = repair_wheel(original, prefix, target)
        result["wheels"].append({**artifact, "original_sha256": artifact["sha256"],
                                "sha256": sha256(target), "size": target.stat().st_size, "ffmpeg": evidence})
        print("Repaired", target.name, target.stat().st_size)
    (args.output / "manifest.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    # 精确对应源码与构建材料可与候选一起下载，未公开上传。
    with zipfile.ZipFile(args.output / "ffmpeg-corresponding-source.zip", "w", zipfile.ZIP_DEFLATED) as archive:
        archive.write(args.build / "ffmpeg-7.1.1.tar.xz", "ffmpeg-7.1.1.tar.xz")
        archive.write(args.build / "configure.log", "configure.log")
        for name in ("scripts/build_opencv_ffmpeg_lgpl.sh", "scripts/build_ffprobe_lgpl.sh", "scripts/prepare_opencv_lgpl.py",
                     "packaging/opencv_macos_inputs.json"):
            archive.write(REPO_ROOT / name, name)


if __name__ == "__main__":
    main()
