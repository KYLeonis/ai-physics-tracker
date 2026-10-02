"""从原生 pip dry-run report 生成固定 URL/SHA 的 runtime manifest；不自动发布。"""

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
from urllib.parse import unquote, urlsplit
from urllib.request import urlopen


BOOTSTRAPS = {
    "Darwin": ("aarch64-apple-darwin", "10cab8f6ed6202fdd81637aa6eda4af8d5b7eaa8fc42f9df3c6bea4923de0d93", 25023573),
    "Windows": ("x86_64-pc-windows-msvc", "52124cee54126f3f360eaa378288f6f64c402c983a3c14c95eff67f4af986aaa", 22013771),
}


def package_artifact(row: dict) -> dict:
    metadata = row["metadata"]
    name, version = metadata["name"], metadata["version"]
    download = row["download_info"]
    url = download["url"]
    filename = unquote(urlsplit(url).path.rsplit("/", 1)[-1])
    sha = download["archive_info"]["hashes"]["sha256"]
    with urlopen(f"https://pypi.org/pypi/{name}/{version.split('+')[0]}/json", timeout=30) as response:
        info = json.load(response)
    match = next((a for a in info["urls"] if a["filename"] == filename), None)
    if match:
        assert match["digests"]["sha256"] == sha, filename
        size = match["size"]
    else:
        # 官方 PyTorch CPU/CUDA wheel 不在 PyPI；取其固定 wheel URL 的元数据。
        with urlopen(url, timeout=30) as response:
            size = int(response.headers["Content-Length"])
    source = next((a for a in info["urls"] if a["packagetype"] == "sdist"), None)
    return {"name": name.lower().replace("_", "-"), "version": version, "filename": filename,
            "url": url, "size": size, "sha256": sha,
            "license": metadata.get("license_expression") or info["info"].get("license_expression") or
                       str(info["info"].get("license", "See upstream metadata"))[:300],
            "source_url": source["url"] if source else info["info"].get("project_url")}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--system", choices=BOOTSTRAPS, required=True)
    parser.add_argument("--device", choices=("cpu", "cuda"), default="cpu")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    with ThreadPoolExecutor(max_workers=4) as pool:
        packages = list(pool.map(package_artifact, json.loads(args.report.read_text(encoding="utf-8"))["install"]))
    target, sha, size = BOOTSTRAPS[args.system]
    filename = f"cpython-3.12.15+20261001-{target}-install_only_stripped.tar.gz"
    windows = args.system == "Windows"
    profile = {
        "id": "windows-x64-" + args.device if windows else "macos-arm64",
        "label": "Windows NVIDIA CUDA 13.0" if windows and args.device == "cuda" else
                 "Windows CPU" if windows else "Apple Silicon (CPU + MPS)",
        "system": args.system, "machines": ["amd64", "x86_64"] if windows else ["arm64", "aarch64"],
        "validation": "pending real installation", "python_version": "3.12.15",
        "python": {"filename": filename, "url": f"https://github.com/astral-sh/python-build-standalone/releases/download/20261001/{filename.replace('+','%2B')}",
                   "sha256": sha, "size": size},
        "packages": sorted(packages, key=lambda p: p["name"]),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({"schema_version": 1, "profiles": [profile]}, indent=2) + "\n", encoding="utf-8")
    print(profile["id"], len(packages), "packages; download GiB:", round(sum(p["size"] for p in packages)/1024**3, 2))


if __name__ == "__main__":
    main()
