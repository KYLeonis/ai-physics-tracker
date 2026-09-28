"""TeacherModelReference 的可用性检查与 runtime self-test 编排(P1.3-S3/S5)。

契约 §4:模型文件缺失或被改动 → unavailable(不静默寻找替代文件);
static parse 只是 unverified——当前 runtime 真实 load 指定 checkpoint 并
对一次合法输入 infer 成功才 compatible。换 runtime 版本、checkpoint/
config 内容或 bodypart mapping 后兼容证据失效(effective state 回落
unverified)。CPU fallback 属产品合同,本层不自动 fallback。
"""

import logging
from pathlib import Path

from ai_physics_tracker.domain.teacher_model import TeacherModelReference
from ai_physics_tracker.domain.types import utc_now
from ai_physics_tracker.infrastructure.hashing import file_sha256 as _file_sha256

logger = logging.getLogger(__name__)


def teacher_model_availability(
    project_root: Path, model: TeacherModelReference
) -> tuple[str, str | None]:
    """对照 manifest 复核文件;返回 (state, reason)。

    文件齐全且逐项 size/SHA 一致 → 引用自身的 compatibility_state;
    否则 ("unavailable", 具体原因)。size 先比(便宜),不匹配即短路。
    """

    root = Path(project_root).resolve()
    for entry in model.manifest:
        candidate = root / entry.relative_path
        resolved = candidate.resolve()
        if not resolved.is_relative_to(root):
            return "unavailable", f"manifest path escapes project root: {entry.relative_path!r}"
        if not resolved.is_file():
            return "unavailable", f"file is missing: {entry.relative_path!r}"
        size = resolved.stat().st_size
        if size != entry.size:
            return (
                "unavailable",
                f"file size changed: {entry.relative_path!r} "
                f"(manifest {entry.size}, on disk {size})",
            )
        if _file_sha256(resolved) != entry.sha256:
            return (
                "unavailable",
                f"file content changed: {entry.relative_path!r} (sha256 mismatch)",
            )
    return model.compatibility_state, None


# ---------------------------------------------------------------------------
# P1.3-S5 — runtime compatibility self-test
# ---------------------------------------------------------------------------

SELFTEST_OPERATION = "selftest_model"


def resolve_pose_cfg_path(project_root: Path, model: TeacherModelReference) -> Path | None:
    """定位模型的 pose_cfg.yaml(推理 runner 的模型结构配置)。

    imported:manifest 中的 pose_cfg.yaml/pytorch_config.yaml 附加文件
    (无则无法自检,保持 unverified);trained:run 目录内 DLC 项目按
    pytorch 引擎真实布局解析(多匹配时取字典序首个并告警)。
    """

    root = Path(project_root).resolve()
    if model.origin == "imported":
        for entry in model.manifest:
            if Path(entry.relative_path).name in ("pose_cfg.yaml", "pytorch_config.yaml"):
                return root / entry.relative_path
        return None
    # DLC 3.x PyTorch 引擎真实布局在前(Engine.PYTORCH.model_folder_name =
    # "dlc-models-pytorch"、pose_cfg_name = "pytorch_config.yaml",已在
    # S5 review 对照安装源码核实);TF/mock 布局保留兼容既有测试资产
    run_root = root / "data" / "engines" / str(model.source_train_run_id)
    matches = sorted(
        run_root.glob(
            "dlc-project/dlc-models-pytorch/*/*/train/pytorch_config.yaml"
        )
    ) or sorted(
        run_root.glob("dlc-project/dlc-models/*/train/pose_cfg.yaml")
    )
    if len(matches) > 1:
        logger.warning(
            "multiple pose configs found for trained model %s; using %s "
            "(shuffle/trainingset disambiguation lands with S6 wiring)",
            model.model_id, matches[0],
        )
    return matches[0] if matches else None


def build_model_selftest_payload(
    project_root: Path,
    model: TeacherModelReference,
    video_path: Path,
    *,
    frame_index: int = 0,
    device: str = "cpu",
) -> dict[str, object]:
    """构造 selftest_model 请求的操作字段(fail closed:文件不可用即拒绝)。"""

    root = Path(project_root).resolve()
    state, reason = teacher_model_availability(root, model)
    if state == "unavailable":
        raise ValueError(f"model is unavailable; fix files before self-test: {reason}")
    pose_cfg = resolve_pose_cfg_path(root, model)
    if pose_cfg is None or not pose_cfg.is_file():
        raise ValueError(
            "pose_cfg.yaml is not part of the model bundle; a runtime self-test "
            "cannot run (model stays unverified)"
        )
    by_name = {Path(e.relative_path).name: e for e in model.manifest}
    config_entry = by_name.get(Path(model.config_path).name)
    checkpoint_entry = by_name.get(Path(model.checkpoint_path).name)
    if config_entry is None or checkpoint_entry is None:
        raise ValueError("manifest does not cover config/checkpoint entries")
    video_file = Path(video_path)
    if not video_file.is_file():
        raise ValueError(f"self-test input video is missing: {video_file}")
    if frame_index < 0:
        raise ValueError(f"frame_index must be non-negative, got {frame_index}")
    return {
        "config_path": str(root / model.config_path),
        "pose_cfg_path": str(pose_cfg),
        "pose_cfg_sha256": _file_sha256(pose_cfg),
        "checkpoint_path": str(root / model.checkpoint_path),
        "config_sha256": config_entry.sha256,
        "checkpoint_sha256": checkpoint_entry.sha256,
        "video_path": str(video_file),
        "frame_index": frame_index,
        # device 走协议级字段(build_request 的 device 参数),payload 不重复携带
        "expected_bodyparts": [target for _role, target in model.bodypart_mapping],
    }


def verify_model_selftest_result(
    model: TeacherModelReference, result: dict[str, object]
) -> dict[str, object]:
    """验证 worker 的 selftest_model result 并构造兼容证据(fail closed)。"""

    section = result.get("model_selftest")
    if not isinstance(section, dict):
        raise ValueError("self-test result misses the 'model_selftest' section")
    by_name = {Path(e.relative_path).name: e for e in model.manifest}
    config_entry = by_name.get(Path(model.config_path).name)
    checkpoint_entry = by_name.get(Path(model.checkpoint_path).name)
    if section.get("config_sha256") != (config_entry.sha256 if config_entry else None):
        raise ValueError("self-test config digest does not match the manifest")
    if section.get("checkpoint_sha256") != (
        checkpoint_entry.sha256 if checkpoint_entry else None
    ):
        raise ValueError("self-test checkpoint digest does not match the manifest")
    pose_sha = section.get("pose_cfg_sha256")
    if not isinstance(pose_sha, str) or not pose_sha:
        raise ValueError("self-test evidence misses the pose config digest")
    versions = section.get("versions")
    if not isinstance(versions, dict) or not versions.get("deeplabcut"):
        raise ValueError("self-test evidence misses runtime versions")
    actual_device = result.get("actual_device")
    if not isinstance(actual_device, str) or not actual_device:
        raise ValueError("self-test evidence misses the actual device")
    expected_targets = sorted(target for _role, target in model.bodypart_mapping)
    if sorted(section.get("bodyparts_found") or []) != expected_targets:
        raise ValueError(
            "self-test predicted bodyparts do not match the model mapping"
        )
    frame_sha = section.get("frame_sha256")
    if not isinstance(frame_sha, str) or not frame_sha:
        raise ValueError("self-test evidence misses the input frame digest")
    return {
        "kind": "runtime-selftest-v1",
        "checked_at": utc_now().isoformat(),
        "runtime": {
            "python": result.get("python"),
            "platform": result.get("platform"),
            "machine": result.get("machine"),
            "device": actual_device,
            "versions": dict(versions),
        },
        "input_frame": {
            "frame_index": section.get("frame_index"),
            "sha256": frame_sha,
        },
        "model_manifest_hash": model.manifest_hash,
        "pose_cfg_sha256": pose_sha,
        "bodypart_mapping": [
            [role, target] for role, target in model.bodypart_mapping
        ],
    }


def effective_compatibility_state(model: TeacherModelReference) -> str:
    """证据有效性裁决:manifest/mapping 变化后兼容证据失效 → unverified。

    文件可用性(unavailable)由 teacher_model_availability 单独判定;本函数
    只裁决"登记的 compatible 证据是否仍对应当前 manifest/mapping"。
    """

    if model.compatibility_state != "compatible":
        return model.compatibility_state
    evidence = model.self_test_evidence or {}
    if (
        evidence.get("model_manifest_hash") != model.manifest_hash
        or [tuple(pair) for pair in evidence.get("bodypart_mapping") or []]
        != [tuple(pair) for pair in model.bodypart_mapping]
    ):
        return "unverified"
    return "compatible"


def model_effective_state(
    project_root: Path, model: TeacherModelReference
) -> tuple[str, str | None]:
    """单一组合入口:文件可用性 → 证据有效性 → (trained)pose_cfg 内容复核。

    S5 review M2:契约 §4 的"换 config 内容撤销证据"不能依赖调用方记得
    分别调用两个函数;本函数是 GUI/导出侧的唯一裁决入口。顺序:文件
    缺失/改动 → unavailable;登记 compatible 但 manifest/mapping 证据过期
    → unverified;trained 模型的 pose_cfg(不在 manifest 内)内容与证据
    冻结值不一致 → unverified(附原因)。
    """

    state, reason = teacher_model_availability(project_root, model)
    if state == "unavailable":
        return state, reason
    if model.compatibility_state == "compatible":
        evidence = model.self_test_evidence or {}
        if evidence.get("model_manifest_hash") != model.manifest_hash:
            return "unverified", "model manifest changed after the compatibility evidence"
        if [tuple(p) for p in evidence.get("bodypart_mapping") or []] != [
            tuple(p) for p in model.bodypart_mapping
        ]:
            return "unverified", "bodypart mapping changed after the compatibility evidence"
        frozen_pose_sha = evidence.get("pose_cfg_sha256")
        if isinstance(frozen_pose_sha, str) and frozen_pose_sha:
            pose_cfg = resolve_pose_cfg_path(project_root, model)
            if pose_cfg is not None and pose_cfg.is_file():
                if _file_sha256(pose_cfg) != frozen_pose_sha:
                    return (
                        "unverified",
                        "pose config content changed after the compatibility evidence",
                    )
    return state, None
