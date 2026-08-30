"""取得固定来源并校验 SHA-256 的 FFprobe；只写显式指定目录，不改系统配置。"""

import argparse
import hashlib
import os
from pathlib import Path
import platform
import urllib.request

# 固定 release 的原始二进制；摘要来自该 release 的 GitHub asset digest。
BASE_URL = "https://github.com/eugeneware/ffmpeg-static/releases/download/b6.1.1/"
ASSETS = {
    ("Darwin", "arm64"): ("ffprobe-darwin-arm64", "bb2db6f5d8cef919da12fbf592119a987202a8c060a886f3cab091f9cab90b64"),
    ("Darwin", "x86_64"): ("ffprobe-darwin-x64", "fa3add0ce901f7241abe0dfc0155d958fc834aca3f8ce61f87cc712ae669c1e0"),
    ("Windows", "AMD64"): ("ffprobe-win32-x64", "3a7e2dc003dc2cd1472827e4c7c4f056ae1ae0ae7c5bbc580c99b49827351ba4"),
}


def install(directory: Path) -> Path:
    """未通过摘要校验的文件不执行；已有非目标版本文件不覆盖。"""

    asset, expected = ASSETS[(platform.system(), platform.machine())]
    directory = directory.resolve()
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / ("ffprobe.exe" if platform.system() == "Windows" else "ffprobe")
    if target.exists():
        data = target.read_bytes()
    else:
        with urllib.request.urlopen(BASE_URL + asset, timeout=60) as response:
            data = response.read()
    if hashlib.sha256(data).hexdigest() != expected:
        raise RuntimeError("FFprobe SHA-256 mismatch; no executable was installed")
    if not target.exists():
        with target.open("xb") as output:
            output.write(data)
    target.chmod(target.stat().st_mode | 0o111)
    return target


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", required=True, type=Path)
    parser.add_argument("--github-path", action="store_true")
    args = parser.parse_args()
    executable = install(args.directory)
    if args.github_path:
        with Path(os.environ["GITHUB_PATH"]).open("a", encoding="utf-8") as output:
            output.write(str(executable.parent) + "\n")
    print(executable)


if __name__ == "__main__":
    main()
