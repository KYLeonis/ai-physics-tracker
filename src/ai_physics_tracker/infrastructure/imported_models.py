"""教师模型的安全 YAML、受管文件导入与内容身份校验。"""

from concurrent.futures import CancelledError
import hashlib
import importlib.metadata
from pathlib import Path
from typing import Any
import platform
import shutil
import sys
from uuid import uuid4

from ai_physics_tracker.domain.imported_model import ImportedModel, MODEL_FILES


def check_cancel(cancel: Any) -> None:
    if cancel is not None and cancel.is_set():
        raise CancelledError()


def file_sha256(path: Path, cancel: Any = None) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            check_cancel(cancel)
            digest.update(chunk)
    check_cancel(cancel)
    return digest.hexdigest()


def read_model_config(config_path: Path, pose_path: Path) -> tuple[dict[str, Any], tuple[str, ...]]:
    import yaml  # DLC 已依赖 PyYAML；主线程不导入 DLC / Torch。

    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    pose = yaml.safe_load(pose_path.read_text(encoding="utf-8"))
    if not isinstance(config, dict) or not isinstance(pose, dict):
        raise ValueError("DLC configs must be YAML mappings")
    parts = config.get("bodyparts")
    if (config.get("engine") != "pytorch" or config.get("multianimalproject", False)
            or config.get("cropping", False) or not isinstance(parts, list)
            or not parts or any(not isinstance(p, str) or not p.strip() for p in parts)
            or len(set(parts)) != len(parts)):
        raise ValueError("Use a single-animal, uncropped PyTorch DLC project with named bodyparts")
    metadata = pose.get("metadata", {})
    if (not isinstance(metadata, dict) or metadata.get("bodyparts") != parts
            or metadata.get("unique_bodyparts", []) or metadata.get("with_identity", False)
            or len(metadata.get("individuals", [])) != 1 or pose.get("method") != "bu"):
        raise ValueError("Pose config must match the ordered bodyparts and use one bottom-up individual")
    data = pose.get("data", {})
    if not isinstance(data, dict) or data.get("colormode", "RGB") != "RGB":
        raise ValueError("This importer supports RGB models; select a matching RGB pose config")
    # 强制安全权重加载，不允许 YAML 覆盖为任意 pickle 对象反序列化。
    pose.setdefault("runner", {})["load_weights_only"] = True
    return pose, tuple(parts)


def import_model(root: Path, config: Path, pose: Path, checkpoint: Path, cancel: Any = None) -> ImportedModel:
    sources = (config, pose, checkpoint)
    if any(not p.is_file() or p.is_symlink() for p in sources) or checkpoint.suffix != ".pt":
        raise ValueError("Select regular config.yaml, pytorch_config.yaml and a .pt checkpoint")
    _, parts = read_model_config(config, pose)
    model_id = uuid4()
    parent = root.resolve() / "models"
    if parent.is_symlink():
        raise ValueError("Managed model directory must not be a symlink")
    parent.mkdir(exist_ok=True)
    staging = parent / f".{model_id}.importing"
    destination = parent / str(model_id)
    staging.mkdir()
    try:
        hashes = {}
        for name, source in zip(MODEL_FILES, sources):
            check_cancel(cancel)
            with source.open("rb") as incoming, (staging / name).open("xb") as outgoing:
                while chunk := incoming.read(1024 * 1024):
                    check_cancel(cancel)
                    outgoing.write(chunk)
            hashes[name] = file_sha256(staging / name, cancel)
            if hashes[name] != file_sha256(source, cancel):
                raise ValueError("Source model changed during import")
        _, copied_parts = read_model_config(staging / MODEL_FILES[0], staging / MODEL_FILES[1])
        if copied_parts != parts:
            raise ValueError("Model configs changed during import")
        model = ImportedModel(model_id, checkpoint.stem, parts, hashes)
        check_cancel(cancel)
        staging.rename(destination)
        return model
    finally:
        if staging.exists():
            shutil.rmtree(staging)


def verify_model(root: Path, model: ImportedModel, cancel: Any = None) -> tuple[dict[str, Any], Path]:
    folder = root / model.directory
    if folder.resolve() != root.resolve() / model.directory or any(
        p.is_symlink() for p in (root / "models", folder)
    ):
        raise ValueError("Model path must stay inside the managed project")
    for name in MODEL_FILES:
        path = folder / name
        if path.is_symlink() or not path.is_file() or file_sha256(path, cancel) != model.sha256[name]:
            raise ValueError(f"Imported model file changed or missing: {name}; import again")
    pose, parts = read_model_config(folder / MODEL_FILES[0], folder / MODEL_FILES[1])
    if parts != model.bodyparts:
        raise ValueError("Imported model bodypart order changed")
    return pose, folder / "checkpoint.pt"


def runtime_identity() -> dict[str, str]:
    versions = {}
    for package in ("torch", "deeplabcut"):
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            versions[package] = "unavailable"
    return {**versions, "python": platform.python_version(), "platform": sys.platform,
            "machine": platform.machine()}


def verified_self_test(model: ImportedModel, device: str) -> bool:
    evidence = model.self_test
    return (evidence.get("manifest_hash") == model.manifest_hash
            and evidence.get("runtime") == runtime_identity()
            and evidence.get("requested_device") == device
            and isinstance(evidence.get("frame_sha256"), str)
            and evidence.get("actual_device") in {"cpu", "cuda", "cuda:0", "mps"})
