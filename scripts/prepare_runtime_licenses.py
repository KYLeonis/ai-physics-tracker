"""从经校验的 PBS full archive 与已安装环境收录原许可文本，不改写内容。"""

import argparse
import hashlib
from pathlib import Path
import shutil
import subprocess
import tarfile


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--python-archive", type=Path, required=True)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--site-packages", type=Path)
    args = parser.parse_args()
    if hashlib.sha256(args.python_archive.read_bytes()).hexdigest() != args.sha256:
        raise ValueError("PBS full archive SHA mismatch")
    args.output.mkdir(parents=True, exist_ok=True)
    process = subprocess.Popen(["zstd", "-dc", str(args.python_archive)], stdout=subprocess.PIPE)
    with tarfile.open(fileobj=process.stdout, mode="r|") as stream:
        for member in stream:
            if member.isfile() and (member.name.startswith("python/licenses/") or member.name == "python/PYTHON.json"):
                target = args.output / "bootstrap" / Path(member.name).name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(stream.extractfile(member).read())
    if process.wait():
        raise RuntimeError("Could not read PBS full archive")
    if args.site_packages:
        for metadata in args.site_packages.glob("*.dist-info"):
            for source in metadata.rglob("*"):
                if source.is_file() and ("licenses" in source.relative_to(metadata).parts or
                        source.name.lower().startswith(("license", "copying", "notice", "authors"))):
                    target = args.output / "packages" / source.relative_to(args.site_packages)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(source, target)
    print("Collected", sum(1 for p in args.output.rglob("*") if p.is_file()), "license/material files")


if __name__ == "__main__":
    main()
