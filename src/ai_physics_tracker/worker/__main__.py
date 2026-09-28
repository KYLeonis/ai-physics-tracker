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
