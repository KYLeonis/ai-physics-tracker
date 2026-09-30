"""外部 worker 子进程入口(独立进程运行,无 Qt / ProjectSession 依赖)。

协议契约见 publication/spec/runtime-boundary.md Protocol v1:host 以
``python -m ai_physics_tracker.worker --request <request.json 路径>`` 启动本模块。
本模块绝不 import Qt / ProjectSession,绝不写 project.json;S1 受信操作
(hello / wait / fail / selftest_runtime)只读写所属 job 目录,不读取 job 目录外
的任何项目文件。stdout/stderr 由 host 重定向到 ``<job>/worker.log``,worker 自身
不重定向。
"""

import argparse
import hashlib
import json
import logging
import os
from pathlib import Path
import platform
import sys
import time
from typing import Any

from ai_physics_tracker.domain.types import canonical_json_digest, utc_now

PROTOCOL_VERSION = 1
HELLO_MESSAGE = "external worker ready"
CANCEL_POLL_INTERVAL_S = 0.05
REQUEST_FILE_NAME = "request.json"
RESULT_FILE_NAME = "result.json"
CANCEL_MARKER_NAME = "cancel.request"


def _verify_self(request: dict[str, Any]) -> None:
    """worker 侧自验:request 记录的源字节 SHA256 与本进程运行的源一致、协议版本受支持。

    源文件在 request 捕获后被改动即拒绝执行(fail closed)。
    """
    actual_sha256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    if request.get("worker_sha256") != actual_sha256:
        raise ValueError("Worker source changed since request capture")
    if request.get("protocol_version") != PROTOCOL_VERSION:
        raise ValueError(f"Unsupported protocol version: {request.get('protocol_version')!r}")


def _wait_for_cancellation(job_dir: Path, result: dict[str, Any]) -> None:
    """wait 操作:50ms 轮询 cancel.request marker,出现即以 cancelled 终态退出。"""
    marker = job_dir / CANCEL_MARKER_NAME
    while not marker.exists():
        time.sleep(CANCEL_POLL_INTERVAL_S)
    result["status"] = "cancelled"


def _run_selftest_runtime(request: dict[str, Any], result: dict[str, Any]) -> None:
    """selftest_runtime:import torch 做单张量前反向,记录 versions / actual_device。

    torch 不可用或所选 device 不可用时抛异常 → failed(不静默 fallback)。
    """
    import importlib.metadata

    import torch

    result["versions"] = {"torch": importlib.metadata.version("torch")}
    tensor = torch.ones(4, device=request["device"], requires_grad=True)
    (tensor * tensor).sum().backward()
    if not torch.isfinite(tensor.grad).all().item():
        raise RuntimeError("Nonfinite tensor self-test")
    result["actual_device"] = str(tensor.device)


class _MarkerCancelEvent:
    """cancel.request marker 的进程内轮询视图(DLCAdapter.train 的 cancel_event 形态)。"""

    def __init__(self, job_dir: Path) -> None:
        self._marker = job_dir / CANCEL_MARKER_NAME

    def is_set(self) -> bool:
        return self._marker.exists()


class _ResultLogQueue:
    """DLCAdapter.train 的 queue 形态:进度消息直写原始 stderr fd。

    不能用 logging:DLC 训练把 sys.stderr 重定向回本队列(redirect_stderr),
    logging→stderr→queue→logging 会无限递归(2026-09-28 真实 smoke 实测
    RecursionError)。fd 2 是 host 打开的 worker.log,直写即落日志。
    """

    def put(self, message: Any) -> None:
        text = getattr(message, "message", None)
        if text:
            try:
                os.write(2, (str(text).rstrip()[:4096] + "\n").encode("utf-8", "replace"))
            except OSError:
                pass  # 日志通道故障不影响训练主流程


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _run_train_experiment(request: dict[str, Any], job_dir: Path, result: dict[str, Any]) -> None:
    """train_experiment:P1.3-S2 联合训练操作(四 bodypart,唯一数据来自请求)。

    worker 不持有 session:rows/split/digest 全部来自请求 payload;视频
    身份(sha256)在本进程复核,prepare→worker 窗口内视频被替换即拒绝。
    DLC 项目创建在 job 目录内,config 与 snapshot 作为声明 outputs 由
    host 侧 containment+SHA 验证。
    """
    from uuid import UUID

    from ai_physics_tracker.application.experiment_export import ExperimentExportRow
    from ai_physics_tracker.application.experiment_training_job import RESULT_SECTION
    from ai_physics_tracker.application.tracking_types import TrainingParams
    from ai_physics_tracker.domain.pendulum import ROLE_ORDER
    from ai_physics_tracker.infrastructure.dlc_adapter import DLCAdapter, detect_device
    from ai_physics_tracker.infrastructure.opencv_video_reader import OpenCVVideoReader

    video_path = Path(request["video_path"])
    if not video_path.is_file():
        raise RuntimeError(f"training video is missing: {video_path}")
    actual_video_sha = _sha256_file(video_path)
    if actual_video_sha != request["video_sha256"]:
        raise RuntimeError(
            "training video changed since the request was prepared (sha256 mismatch)"
        )

    rows = tuple(
        ExperimentExportRow(
            frame_index=int(item["frame_index"]),
            coordinates=tuple(
                (float(pair[0]), float(pair[1])) for pair in item["coordinates"]
            ),
        )
        for item in request["rows"]
    )
    if not rows:
        raise RuntimeError("training request carries no annotation rows")

    # 设备权威源 = 协议级 request["device"](host 校验它与 actual_device);
    # params.device 仅在协议为 auto 时由 worker 解析(F1,S1–S3 review 扫描)
    requested_device = str(request.get("device", "cpu"))
    resolved_device = (
        detect_device() if requested_device == "auto" else requested_device
    )
    params_config = dict(request["params"])
    params_config["device"] = resolved_device
    params = TrainingParams.from_config(params_config)

    cancel_event = _MarkerCancelEvent(job_dir)
    queue = _ResultLogQueue()
    adapter = DLCAdapter()
    project_dir = job_dir / "dlc-project"
    config_path = adapter.create_project(
        project_name=project_dir.name,
        experimenter="AIPhysicsTracker",
        video_path=video_path,
        working_dir=job_dir,
        bodyparts=list(ROLE_ORDER),
    )
    reader = OpenCVVideoReader()
    try:
        reader.open(video_path)
        exported = adapter.export_experiment_annotations(
            rows, reader, config_path, scorer="AIPhysicsTracker"
        )
    finally:
        reader.close()
    if exported != len(rows):
        raise RuntimeError(
            f"exported {exported} rows but the request declared {len(rows)}"
        )
    adapter.create_training_dataset(
        config_path=config_path,
        num_shuffles=params.shuffle,
        train_indices=list(request["train_indices"]),
        test_indices=list(request["test_indices"]),
    )
    if cancel_event.is_set():
        raise _Cancelled()

    outcome = adapter.train(
        UUID(request["run_id"]), queue, cancel_event, config_path, params
    )
    if outcome.status == "cancelled":
        raise _Cancelled()
    if outcome.status != "completed" or not outcome.snapshot_path:
        raise RuntimeError(outcome.error_message or "training did not produce a model")
    snapshot = Path(outcome.snapshot_path).resolve()
    if not snapshot.is_relative_to(job_dir):
        raise RuntimeError(
            f"trained snapshot escapes the job directory: {snapshot}"
        )

    def _output(relative_to_job: Path) -> dict[str, Any]:
        resolved = relative_to_job.resolve()
        return {
            "path": resolved.relative_to(job_dir).as_posix(),
            "size": resolved.stat().st_size,
            "sha256": _sha256_file(resolved),
        }

    result["outputs"] = [_output(config_path), _output(snapshot)]
    result["actual_device"] = resolved_device
    result[RESULT_SECTION] = {
        "label_digest": request["label_digest"],
        "video_sha256": request["video_sha256"],
        "check_frames": list(request.get("check_frames", ())),
        "bodyparts": list(ROLE_ORDER),
        "engine_version": adapter.engine_version(),
        "config_path": result["outputs"][0]["path"],
        "model_snapshot": result["outputs"][1]["path"],
        "epochs_completed": outcome.epochs_completed,
    }


SELFTEST_MODEL_SECTION = "model_selftest"
INFERENCE_SECTION = "experiment_inference"


def _run_infer_experiment(request: dict[str, Any], job_dir: Path, result: dict[str, Any]) -> None:
    """一次四 bodypart DLC analyze；raw artifact 留在 job 内，绝不写项目清单。"""

    from concurrent.futures import CancelledError
    from uuid import UUID

    from ai_physics_tracker.domain.pendulum import ROLE_ORDER
    from ai_physics_tracker.infrastructure.dlc_adapter import DLCAdapter

    paths = {
        "video": (Path(request["video_path"]), request["video_sha256"]),
        "config": (Path(request["config_path"]), request["config_sha256"]),
        "checkpoint": (Path(request["checkpoint_path"]), request["checkpoint_sha256"]),
        "pose_cfg": (Path(request["pose_cfg_path"]), request["pose_cfg_sha256"]),
    }
    for name, (path, digest) in paths.items():
        if not path.is_file() or _sha256_file(path) != digest:
            raise RuntimeError(f"joint inference {name} changed or is missing")
    mapping = tuple(tuple(pair) for pair in request["bodypart_mapping"])
    if tuple(role for role, _part in mapping) != ROLE_ORDER:
        raise RuntimeError("joint inference role mapping is not canonical")
    adapter = DLCAdapter()
    try:
        artifact, scorer, engine_version, device, parsed = adapter.infer_joint_artifact(
            UUID(request["run_id"]), _ResultLogQueue(), _MarkerCancelEvent(job_dir),
            config_path=paths["config"][0], video_path=paths["video"][0],
            checkpoint_path=paths["checkpoint"][0], pose_cfg_path=paths["pose_cfg"][0],
            output_dir=job_dir / "predictions", frame_count=int(request["frame_count"]),
            bodypart_mapping=mapping, batch_size=int(request["batch_size"]),
            device=str(request["device"]),
        )
    except CancelledError as error:
        raise _Cancelled() from error
    for name, (path, digest) in paths.items():
        if _sha256_file(path) != digest:
            raise RuntimeError(f"joint inference {name} changed during execution")
    relative = artifact.resolve().relative_to(job_dir).as_posix()
    result["outputs"] = [{
        "path": relative, "size": artifact.stat().st_size,
        "sha256": _sha256_file(artifact),
    }]
    result["actual_device"] = device
    import torch

    result[INFERENCE_SECTION] = {
        "input_digest": request["input_digest"],
        "video_sha256": request["video_sha256"],
        "model_manifest_hash": request["model_manifest_hash"],
        "bodypart_mapping": [list(pair) for pair in mapping],
        "frame_count": parsed.frame_count,
        "prediction_path": relative,
        "scorer": scorer,
        "engine_version": engine_version,
        "versions": {"deeplabcut": engine_version, "torch": str(torch.__version__)},
        "complete_count": parsed.complete_count,
        "missing_by_role": dict(parsed.missing_by_role),
    }


def _run_selftest_model(request: dict[str, Any], job_dir: Path, result: dict[str, Any]) -> None:
    """selftest_model:真实 load 指定 checkpoint 并对单帧合法输入推理(P1.3-S5)。

    契约 §4:static parse 只是 unverified;当前 runtime 实际加载 + 一次合法
    输入 infer 通过才 compatible。worker 侧:复核 config/checkpoint SHA
    (TOCTOU)、解码单帧、经 DLC PyTorch runner 推理、断言四 bodypart 预测
    有限。真实 DLC 链路由 S6 smoke 验证;无 torch/DLC 的环境按 failed 上报。
    """

    from ai_physics_tracker.infrastructure.dlc_adapter import (
        detect_device,
        run_model_selftest_inference,
    )

    config_path = Path(request["config_path"])
    pose_cfg_path = Path(request["pose_cfg_path"])
    checkpoint_path = Path(request["checkpoint_path"])
    video_path = Path(request["video_path"])
    for name, path in (("config", config_path), ("pose_cfg", pose_cfg_path),
                       ("checkpoint", checkpoint_path), ("video", video_path)):
        if not path.is_file():
            raise RuntimeError(f"selftest {name} file is missing: {path}")
    if _sha256_file(config_path) != request["config_sha256"]:
        raise RuntimeError("config changed since the self-test request was prepared")
    if _sha256_file(checkpoint_path) != request["checkpoint_sha256"]:
        raise RuntimeError("checkpoint changed since the self-test request was prepared")

    import cv2
    import numpy as np

    if not request.get("pose_cfg_sha256"):
        raise RuntimeError("self-test request misses pose_cfg_sha256")
    if _sha256_file(pose_cfg_path) != request["pose_cfg_sha256"]:
        raise RuntimeError("pose config changed since the self-test request was prepared")
    frame_index = int(request.get("frame_index", 0))
    if frame_index < 0:
        raise RuntimeError(f"frame_index must be non-negative, got {frame_index}")
    capture = cv2.VideoCapture(str(video_path))
    try:
        if not capture.isOpened():
            raise RuntimeError(f"cannot open the self-test input video: {video_path}")
        capture.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
        ok, frame = capture.read()
    finally:
        capture.release()
    if not ok or frame is None:
        raise RuntimeError(
            f"cannot decode frame {frame_index} of {video_path}; "
            "index may exceed the video length"
        )
    ok2, encoded = cv2.imencode(".png", frame)
    if not ok2:
        raise RuntimeError("cannot encode the self-test frame")
    frame_sha256 = hashlib.sha256(encoded.tobytes()).hexdigest()

    requested_device = str(request.get("device", "cpu"))
    resolved_device = detect_device() if requested_device == "auto" else requested_device
    # DLC 依赖按 ADR-0011 只存在于 dlc_adapter;worker 经 adapter 完成推理
    found, versions, _actual = run_model_selftest_inference(
        pose_cfg_path, checkpoint_path, np.asarray(frame), resolved_device
    )
    expected = list(request["expected_bodyparts"])
    # bottom-up runner 的输出键是输出名("bodyparts"),值形状 (n_ind, n_bp, 3);
    # bodypart 身份由 pytorch_config 的元数据顺序保证,此处按形状校验覆盖数
    if "bodyparts" not in found:
        raise RuntimeError(
            f"self-test predictions have no 'bodyparts' output; got keys {sorted(found)}"
        )
    array = np.asarray(found["bodyparts"], dtype=float)
    if array.ndim < 2 or array.shape[-2] != len(expected):
        raise RuntimeError(
            f"self-test 'bodyparts' shape {array.shape} does not cover "
            f"{len(expected)} expected bodyparts"
        )
    if array.size == 0 or not np.isfinite(array).all():
        raise RuntimeError("self-test predictions are empty or non-finite")

    result["actual_device"] = resolved_device
    result[SELFTEST_MODEL_SECTION] = {
        "config_sha256": request["config_sha256"],
        "checkpoint_sha256": request["checkpoint_sha256"],
        "pose_cfg_sha256": request["pose_cfg_sha256"],
        "frame_sha256": frame_sha256,
        "frame_index": frame_index,
        "bodyparts_found": sorted(expected),
        "versions": versions,
    }


class _Cancelled(Exception):
    """worker 内部:协作取消到达,转 cancelled 终态。"""


def _execute_operation(
    operation: str,
    request: dict[str, Any],
    job_dir: Path,
    result: dict[str, Any],
) -> None:
    """受信操作白名单分发;未知 operation 一律 failed。"""
    if operation == "hello":
        result["message"] = HELLO_MESSAGE
    elif operation == "wait":
        _wait_for_cancellation(job_dir, result)
    elif operation == "fail":
        raise RuntimeError("Intentional failure")
    elif operation == "selftest_runtime":
        _run_selftest_runtime(request, result)
    elif operation == "train_experiment":
        try:
            _run_train_experiment(request, job_dir, result)
        except _Cancelled:
            result["status"] = "cancelled"
    elif operation == "selftest_model":
        _run_selftest_model(request, job_dir, result)
    elif operation == "infer_experiment":
        try:
            _run_infer_experiment(request, job_dir, result)
        except _Cancelled:
            result["status"] = "cancelled"
    else:
        raise ValueError(f"Unsupported operation: {operation!r}")


def _write_result(job_dir: Path, result: dict[str, Any]) -> None:
    """result 先写临时文件再 os.replace(原子可见,host 不会读到半成品)。"""
    tmp_path = job_dir / (RESULT_FILE_NAME + ".tmp")
    tmp_path.write_text(
        json.dumps(result, ensure_ascii=False, allow_nan=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(tmp_path, job_dir / RESULT_FILE_NAME)


def main() -> int:
    started_at = utc_now().isoformat()
    parser = argparse.ArgumentParser(
        prog="ai_physics_tracker.worker",
        description="External worker protocol v1 entry (see publication/spec/runtime-boundary.md)",
    )
    parser.add_argument("--request", type=Path, required=True, help="Path to request.json inside the job directory")
    args = parser.parse_args()

    # worker 是独立应用入口,在本进程内配置 handler;输出经 host 重定向进入 worker.log
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        stream=sys.stderr,
    )
    logger = logging.getLogger("ai_physics_tracker.worker")

    request_path = args.request.resolve()
    job_dir = request_path.parent
    request = json.loads(request_path.read_text(encoding="utf-8"))
    digest = canonical_json_digest(request)

    # 身份字段在任何终态都写入;host 在 success 时强制校验(runtime-boundary §Protocol v1)
    result: dict[str, Any] = {
        "protocol_version": PROTOCOL_VERSION,
        "job_id": request.get("job_id"),
        "request_digest": digest,
        "operation": request.get("operation"),
        "status": "failed",
        "python": sys.version,
        "executable": sys.executable,
        "platform": platform.platform(),
        "machine": platform.machine(),
        "worker_frozen": bool(getattr(sys, "frozen", False)),
        "outputs": [],
        "started_at": started_at,
        "finished_at": None,
    }
    try:
        _verify_self(request)
        operation = request["operation"]
        logger.info("worker operation=%s job_id=%s", operation, request.get("job_id"))
        _execute_operation(operation, request, job_dir, result)
        if result["status"] != "cancelled":
            result["status"] = "success"
    except Exception as error:
        # 唯一捕获点:任何操作失败都转为 failed 终态 + 结构化诊断(error dict 与日志
        # traceback),交给 host 侧 read_result 校验后决定恢复路径——不是静默吞错。
        logger.error("worker failed: %s", error, exc_info=True)
        result["status"] = "failed"
        result["error"] = {"type": type(error).__name__, "message": str(error)}
    result["finished_at"] = utc_now().isoformat()
    _write_result(job_dir, result)
    exit_code = 1 if result["status"] == "failed" else 0
    logger.info("worker finished status=%s exit_code=%d", result["status"], exit_code)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
