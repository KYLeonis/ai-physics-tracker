"""外部 worker 协议(Protocol v1)host/worker 集成测试:真实外部进程,负例覆盖。

契约来源:publication/spec/runtime-boundary.md。测试用 ``sys.executable`` 作为
runtime_python,即每次测试都跑真实的独立解释器子进程。
"""

import hashlib
import importlib.util
import json
import os
from datetime import UTC, datetime
from pathlib import Path
import sys
import textwrap
import time
from typing import Any, Callable
from uuid import uuid4

import pytest

from ai_physics_tracker.infrastructure.external_worker import (
    ExternalWorkerError,
    ExternalWorkerRunner,
    build_request,
)

RUNTIME_PYTHON = sys.executable
JOIN_TIMEOUT_S = 30.0
POLL_INTERVAL_S = 0.05

# 忽略 cancel marker、只 spawn 一个长眠孙子进程的假 worker;用于验证强制回收整组
# (child 被留下即取消失败,runtime-boundary §取消)。经测试缝 worker_module 注入。
STUBBORN_STUB_SOURCE = textwrap.dedent(
    """
    import subprocess
    import sys
    from pathlib import Path

    request_path = Path(sys.argv[sys.argv.index("--request") + 1]).resolve()
    job_dir = request_path.parent
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(600)"])
    (job_dir / "grandchild.pid").write_text(str(child.pid), encoding="utf-8")
    child.wait()
    """
)

# 立即正常退出且不写任何协议文件的假 worker;host 侧随后放置伪造 result,
# 用于驱动 host 验证逻辑的负例(不依赖 torch)。
FAST_EXIT_STUB_SOURCE = (
    "# test-only stub: exit 0 immediately without writing protocol files\n"
    "import sys\n"
    "sys.exit(0)\n"
)


def _start_hello(
    tmp_path: Path,
    **runner_kwargs: Any,
) -> tuple[ExternalWorkerRunner, Any, str]:
    runner = ExternalWorkerRunner(RUNTIME_PYTHON, **runner_kwargs)
    job_id = uuid4()
    request, digest = build_request("hello", job_id=job_id)
    handle = runner.start(tmp_path / f"job-{job_id.hex}", request)
    return runner, handle, digest


def _wait_for_log_text(handle: Any, needle: str, timeout_s: float) -> str:
    """轮询 worker.log 直到出现 needle(确保 worker 已真正进入对应操作)。"""
    deadline = time.monotonic() + timeout_s
    log_text = ""
    while time.monotonic() < deadline:
        if handle.worker_log_path.is_file():
            log_text = handle.worker_log_path.read_text(encoding="utf-8", errors="replace")
            if needle in log_text:
                return log_text
        time.sleep(POLL_INTERVAL_S)
    raise AssertionError(f"worker.log never contained {needle!r}; log was: {log_text!r}")


def _pid_is_gone(pid: int, timeout_s: float = 5.0) -> bool:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return True
        time.sleep(POLL_INTERVAL_S)
    return False


def _forged_success_result(handle: Any, digest: str, operation: str) -> dict[str, Any]:
    """构造"身份全对、status=success"的伪造 result,用于迟到结果负例。"""
    now_iso = datetime.now(UTC).isoformat()
    return {
        "protocol_version": 1,
        "job_id": handle.job_id,
        "request_digest": digest,
        "operation": operation,
        "status": "success",
        "message": "external worker ready",
        "python": "3.11.0 (forged)",
        "executable": "/forged/python",
        "platform": "forged-platform",
        "machine": "forged-machine",
        "worker_frozen": False,
        "outputs": [],
        "started_at": now_iso,
        "finished_at": now_iso,
    }


def _write_forged_result(handle: Any, payload: dict[str, Any]) -> None:
    (handle.job_dir / "result.json").write_text(
        json.dumps(payload, indent=2), encoding="utf-8"
    )


def _mutate_result_file(handle: Any, mutate: Callable[[dict[str, Any]], None]) -> None:
    result_path = handle.job_dir / "result.json"
    result = json.loads(result_path.read_text(encoding="utf-8"))
    mutate(result)
    result_path.write_text(json.dumps(result, indent=2), encoding="utf-8")


# --- 1. hello 成功 ------------------------------------------------------------


def test_hello_success_returns_full_protocol_identity(tmp_path: Path) -> None:
    runner = ExternalWorkerRunner(RUNTIME_PYTHON)
    job_id = uuid4()
    request, digest = build_request("hello", job_id=job_id)
    handle = runner.start(tmp_path / f"job-{job_id.hex}", request)

    assert handle.is_alive()
    assert handle.join(timeout_s=JOIN_TIMEOUT_S)
    assert not handle.is_alive()
    assert handle.returncode == 0

    result = handle.read_result()
    assert result["status"] == "success"
    assert result["job_id"] == str(job_id)
    assert result["request_digest"] == digest
    assert result["operation"] == "hello"
    assert result["message"] == "external worker ready"
    for field in ("python", "executable", "platform", "machine"):
        assert isinstance(result[field], str) and result[field]
    # worker 确实跑在注入的 runtime python 里
    assert Path(result["executable"]).resolve() == Path(RUNTIME_PYTHON).resolve()

    log_text = (handle.job_dir / "worker.log").read_text(encoding="utf-8")
    assert "operation=hello" in log_text


# --- 2. fail 操作:合法 failed 结果 --------------------------------------------


def test_fail_operation_is_legal_failed_result(tmp_path: Path) -> None:
    runner = ExternalWorkerRunner(RUNTIME_PYTHON)
    job_id = uuid4()
    request, _ = build_request("fail", job_id=job_id)
    handle = runner.start(tmp_path / f"job-{job_id.hex}", request)

    assert handle.join(timeout_s=JOIN_TIMEOUT_S)
    assert handle.returncode == 1
    result = handle.read_result()  # failed 是合法终态,不是 ExternalWorkerError
    assert result["status"] == "failed"
    assert result["error"]["type"] == "RuntimeError"
    assert "Intentional failure" in result["error"]["message"]
    log_text = (handle.job_dir / "worker.log").read_text(encoding="utf-8")
    assert "RuntimeError" in log_text  # traceback 进入诊断日志


# --- 3. duplicate job 目录拒绝 -------------------------------------------------


def test_start_rejects_non_empty_job_directory(tmp_path: Path) -> None:
    runner = ExternalWorkerRunner(RUNTIME_PYTHON)
    occupied = tmp_path / "occupied"
    occupied.mkdir()
    (occupied / "stale.txt").write_text("stale", encoding="utf-8")
    request, _ = build_request("hello", job_id=uuid4())
    with pytest.raises(ExternalWorkerError, match="not empty"):
        runner.start(occupied, request)


# --- 4. cancel 协作 -----------------------------------------------------------


def test_wait_operation_cooperative_cancellation(tmp_path: Path) -> None:
    runner = ExternalWorkerRunner(RUNTIME_PYTHON, grace_s=10.0)
    job_id = uuid4()
    request, digest = build_request("wait", job_id=job_id)
    handle = runner.start(tmp_path / f"job-{job_id.hex}", request)

    try:
        _wait_for_log_text(handle, "operation=wait", timeout_s=JOIN_TIMEOUT_S)
        assert handle.join(timeout_s=0.05) is False  # wait 尚未退出,timeout 如实返回

        handle.cancel()
        assert not handle.is_alive()
        assert handle.forced_termination is False
        assert (handle.job_dir / "cancel.request").is_file()
        assert handle.returncode == 0

        result = handle.read_result()
        assert result["status"] == "cancelled"
        assert result["request_digest"] == digest
    finally:
        if handle.is_alive():
            handle.cancel()


# --- 5. 强制回收整组(POSIX)---------------------------------------------------


def _start_stubborn(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[Any, str]:
    stub_dir = tmp_path / "stub"
    stub_dir.mkdir()
    (stub_dir / "stubborn_worker_stub.py").write_text(STUBBORN_STUB_SOURCE, encoding="utf-8")
    monkeypatch.syspath_prepend(str(stub_dir))
    runner = ExternalWorkerRunner(
        RUNTIME_PYTHON,
        worker_module="stubborn_worker_stub",
        python_path_extra=(stub_dir,),
        grace_s=0.5,
    )
    job_id = uuid4()
    request, digest = build_request("wait", job_id=job_id, worker_module="stubborn_worker_stub")
    handle = runner.start(tmp_path / f"job-{job_id.hex}", request)
    return handle, digest


def _wait_for_grandchild_pid(handle: Any) -> int:
    pid_file = handle.job_dir / "grandchild.pid"
    deadline = time.monotonic() + JOIN_TIMEOUT_S
    while time.monotonic() < deadline:
        if pid_file.is_file():
            return int(pid_file.read_text(encoding="utf-8").strip())
        time.sleep(POLL_INTERVAL_S)
    raise AssertionError(f"stub never wrote {pid_file}")


@pytest.mark.skipif(
    sys.platform == "win32",
    reason="POSIX killpg group recovery; Windows taskkill branch awaits real-machine G4 gate (P6)",
)
def test_forced_cancellation_recovers_whole_process_group(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    handle, _ = _start_stubborn(tmp_path, monkeypatch)
    try:
        grandchild_pid = _wait_for_grandchild_pid(handle)
        assert handle.is_alive()

        handle.cancel()
        assert handle.forced_termination is True
        assert not handle.is_alive()
        # 孙子进程与 worker 同组,killpg 后必须一并回收
        assert _pid_is_gone(grandchild_pid), "grandchild survived group kill"
    finally:
        if handle.is_alive():
            handle.cancel()


# --- 6. 迟到结果拒绝 ----------------------------------------------------------


@pytest.mark.skipif(
    sys.platform == "win32",
    reason="depends on POSIX stubborn stub flow",
)
def test_late_success_after_forced_cancel_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    handle, digest = _start_stubborn(tmp_path, monkeypatch)
    try:
        _wait_for_grandchild_pid(handle)
        handle.cancel()
        assert handle.forced_termination is True
    finally:
        if handle.is_alive():
            handle.cancel()

    # 强制回收后 worker 才"写出"的 success(此处手动放置)一律不采
    forged = _forged_success_result(handle, digest, "wait")
    (handle.job_dir / "result.json").write_text(
        json.dumps(forged, indent=2), encoding="utf-8"
    )
    with pytest.raises(ExternalWorkerError, match="force-terminated"):
        handle.read_result()


def test_success_after_cooperative_cancel_is_rejected(tmp_path: Path) -> None:
    runner = ExternalWorkerRunner(RUNTIME_PYTHON, grace_s=10.0)
    job_id = uuid4()
    request, digest = build_request("wait", job_id=job_id)
    handle = runner.start(tmp_path / f"job-{job_id.hex}", request)
    try:
        _wait_for_log_text(handle, "operation=wait", timeout_s=JOIN_TIMEOUT_S)
        handle.cancel()
        assert handle.read_result()["status"] == "cancelled"

        # 取消终态判定后再出现的 success result 不得被采信
        _mutate_result_file(handle, lambda result: result.update(
            status="success", message="external worker ready", error=None,
            python="3.11.0 (forged)", executable="/forged/python",
            platform="forged-platform", machine="forged-machine",
        ))
        with pytest.raises(ExternalWorkerError, match="late success"):
            handle.read_result()
    finally:
        if handle.is_alive():
            handle.cancel()


# --- 7. result / request 篡改负例 ---------------------------------------------


def _completed_hello(tmp_path: Path) -> tuple[Any, str]:
    _, handle, digest = _start_hello(tmp_path)
    assert handle.join(timeout_s=JOIN_TIMEOUT_S)
    assert handle.read_result()["status"] == "success"
    return handle, digest


@pytest.mark.parametrize(
    "case",
    [
        "wrong_job_id",
        "wrong_request_digest",
        "missing_protocol_version",
        "invalid_status",
        "exit_code_status_conflict",
        "missing_runtime_field",
    ],
)
def test_read_result_rejects_tampered_result(tmp_path: Path, case: str) -> None:
    handle, _ = _completed_hello(tmp_path)

    def mutate(result: dict[str, Any]) -> None:
        if case == "wrong_job_id":
            result["job_id"] = str(uuid4())
        elif case == "wrong_request_digest":
            result["request_digest"] = "0" * 64
        elif case == "missing_protocol_version":
            del result["protocol_version"]
        elif case == "invalid_status":
            result["status"] = "running"
        elif case == "exit_code_status_conflict":
            # 实际 exit 0;声称 failed(应 exit 1)
            result["status"] = "failed"
            result["error"] = {"type": "RuntimeError", "message": "forged"}
        elif case == "missing_runtime_field":
            del result["python"]

    _mutate_result_file(handle, mutate)
    with pytest.raises(ExternalWorkerError):
        handle.read_result()


def test_read_result_rejects_tampered_request(tmp_path: Path) -> None:
    handle, _ = _completed_hello(tmp_path)
    request_path = handle.job_dir / "request.json"
    request_on_disk = json.loads(request_path.read_text(encoding="utf-8"))
    request_on_disk["device"] = "cuda"
    request_path.write_text(json.dumps(request_on_disk, indent=2), encoding="utf-8")
    with pytest.raises(ExternalWorkerError, match="digest"):
        handle.read_result()


# --- 7b. outputs 声明验证(路径逃逸 / size / SHA)--------------------------------


def _declare_outputs(handle: Any, entries: list[dict[str, Any]]) -> None:
    def mutate(result: dict[str, Any]) -> None:
        result["outputs"] = entries

    _mutate_result_file(handle, mutate)


@pytest.mark.parametrize(
    "case",
    ["relative_escape", "absolute_path", "symlink_escape", "size_mismatch", "sha256_mismatch"],
)
def test_read_result_rejects_invalid_output_declarations(
    tmp_path: Path, case: str
) -> None:
    handle, _ = _completed_hello(tmp_path)
    outside_bytes = b"outside-secret"
    outside = tmp_path / "outside.bin"
    outside.write_bytes(outside_bytes)
    outside_size = len(outside_bytes)
    outside_sha = hashlib.sha256(outside_bytes).hexdigest()

    if case == "relative_escape":
        entry = {"path": "../outside.bin", "size": outside_size, "sha256": outside_sha}
        expected = "escapes job directory"
    elif case == "absolute_path":
        entry = {"path": str(outside), "size": outside_size, "sha256": outside_sha}
        expected = "escapes job directory"
    elif case == "symlink_escape":
        link = handle.job_dir / "link.bin"
        try:
            link.symlink_to(outside)
        except OSError:
            pytest.skip("symlink creation not permitted on this platform")
        entry = {"path": "link.bin", "size": outside_size, "sha256": outside_sha}
        expected = "escapes job directory"
    elif case == "size_mismatch":
        inner = handle.job_dir / "inner.bin"
        inner.write_bytes(b"inside")
        entry = {"path": "inner.bin", "size": 999, "sha256": hashlib.sha256(b"inside").hexdigest()}
        expected = "size/sha256 mismatch"
    else:  # sha256_mismatch
        inner = handle.job_dir / "inner.bin"
        inner.write_bytes(b"inside")
        entry = {"path": "inner.bin", "size": 6, "sha256": "0" * 64}
        expected = "size/sha256 mismatch"

    _declare_outputs(handle, [entry])
    with pytest.raises(ExternalWorkerError, match=expected):
        handle.read_result()


def test_read_result_accepts_valid_declared_outputs(tmp_path: Path) -> None:
    handle, _ = _completed_hello(tmp_path)
    payload_bytes = b"declared-output"
    output_path = handle.job_dir / "artifacts" / "model.bin"
    output_path.parent.mkdir()
    output_path.write_bytes(payload_bytes)
    _declare_outputs(
        handle,
        [
            {
                "path": "artifacts/model.bin",
                "size": len(payload_bytes),
                "sha256": hashlib.sha256(payload_bytes).hexdigest(),
            }
        ],
    )
    result = handle.read_result()
    assert result["status"] == "success"


# --- 7c. 畸形 result.json ------------------------------------------------------


@pytest.mark.parametrize(
    "content",
    ["not-json{", "[]", '{"protocol_version": 1, "python": NaN}'],
    ids=["invalid-json", "not-an-object", "nan-value"],
)
def test_read_result_rejects_malformed_result_json(tmp_path: Path, content: str) -> None:
    handle, _ = _completed_hello(tmp_path)
    (handle.job_dir / "result.json").write_text(content, encoding="utf-8")
    with pytest.raises(ExternalWorkerError, match="canonical JSON"):
        handle.read_result()


# --- 7d. selftest device 不匹配 -------------------------------------------------


def test_selftest_actual_device_mismatch_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stub_dir = tmp_path / "fastexit_stub"
    stub_dir.mkdir()
    (stub_dir / "selftest_forge_stub.py").write_text(FAST_EXIT_STUB_SOURCE, encoding="utf-8")
    monkeypatch.syspath_prepend(str(stub_dir))
    runner = ExternalWorkerRunner(
        RUNTIME_PYTHON,
        worker_module="selftest_forge_stub",
        python_path_extra=(stub_dir,),
    )
    job_id = uuid4()
    request, digest = build_request(
        "selftest_runtime", job_id=job_id, device="cpu", worker_module="selftest_forge_stub"
    )
    handle = runner.start(tmp_path / f"job-{job_id.hex}", request)
    try:
        assert handle.join(timeout_s=JOIN_TIMEOUT_S)
        assert handle.returncode == 0

        forged = _forged_success_result(handle, digest, "selftest_runtime")
        forged["versions"] = {"torch": "0.0.0-forged"}
        forged["actual_device"] = "cuda:0"  # 请求 backend 是 cpu,不得被采信
        _write_forged_result(handle, forged)
        with pytest.raises(ExternalWorkerError, match="actual_device"):
            handle.read_result()
    finally:
        if handle.is_alive():
            handle.cancel()


# --- 8. canonical digest 稳定性 ------------------------------------------------


def test_request_digest_is_stable_and_canonical() -> None:
    job_id = uuid4()
    first, first_digest = build_request("hello", job_id=job_id)
    second, second_digest = build_request("hello", job_id=job_id)
    assert first_digest == second_digest

    # extra 字段顺序无关:canonical 表示只取决于内容
    _, digest_z_first = build_request("hello", job_id=job_id, extra={"z_first": 1, "a_second": 2})
    _, digest_a_first = build_request("hello", job_id=job_id, extra={"a_second": 2, "z_first": 1})
    assert digest_z_first == digest_a_first
    assert digest_z_first != first_digest

    canonical = json.dumps(
        first, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    )
    assert hashlib.sha256(canonical.encode("utf-8")).hexdigest() == first_digest


def test_build_request_rejects_invalid_device_and_reserved_extra() -> None:
    with pytest.raises(ValueError, match="device"):
        build_request("hello", job_id=uuid4(), device="cuda:0")
    with pytest.raises(ValueError, match="override"):
        build_request("hello", job_id=uuid4(), extra={"device": "mps"})


# --- 9. selftest_runtime -------------------------------------------------------


@pytest.mark.skipif(
    importlib.util.find_spec("torch") is None,
    reason="torch is not installed in the test runtime",
)
def test_selftest_runtime_reports_torch_identity(tmp_path: Path) -> None:
    runner = ExternalWorkerRunner(RUNTIME_PYTHON)
    job_id = uuid4()
    request, _ = build_request("selftest_runtime", job_id=job_id, device="cpu")
    handle = runner.start(tmp_path / f"job-{job_id.hex}", request)

    assert handle.join(timeout_s=120.0)
    result = handle.read_result()
    assert result["status"] == "success"
    assert result["actual_device"] == "cpu"
    assert result["versions"]["torch"]
    assert handle.returncode == 0


# --- 10. env 隔离 --------------------------------------------------------------


def test_polluted_host_environment_does_not_leak_to_worker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # frozen host 场景下典型的污染源:PYTHONHOME / PyInstaller 注入变量 / 旧 PYTHONPATH
    monkeypatch.setenv("PYTHONHOME", "/nonexistent/python-home")
    monkeypatch.setenv("_PYI_APPLICATION_HOME_DIR", "/nonexistent/frozen")
    monkeypatch.setenv("_PYI_HOMEPATH", "/nonexistent/frozen-home")
    monkeypatch.setenv("PYTHONPATH", "/nonexistent/old-python-path")

    _, handle, _ = _start_hello(tmp_path)
    assert handle.join(timeout_s=JOIN_TIMEOUT_S)
    result = handle.read_result()
    assert result["status"] == "success"


# --- 2026-09-28 S1–S3 review 回归(M1 host outputs 必填;B1 见下) -----------------


def test_success_result_without_outputs_key_rejected(tmp_path: Path) -> None:
    """M1:success result 缺 outputs 声明 → fail closed(空输出也须显式空列表)。"""

    runner = ExternalWorkerRunner(RUNTIME_PYTHON)
    job_id = uuid4()
    request, _digest = build_request("hello", job_id=job_id)
    handle = runner.start(tmp_path / f"job-{job_id.hex}", request)
    try:
        handle.join(timeout_s=10)
        assert handle.returncode == 0
        _mutate_result_file(handle, lambda result: result.pop("outputs"))
        with pytest.raises(ExternalWorkerError, match="misses the 'outputs'"):
            handle.read_result()
    finally:
        handle.cancel()
        handle.join(timeout_s=5)


def test_b1_model_snapshots_allows_four_bodyparts_for_training(monkeypatch) -> None:
    """B1:训练路径定位快照不限制 bodypart 集合;推理路径保持单点守卫。"""

    import types
    from ai_physics_tracker.infrastructure.dlc_adapter import _model_snapshots

    class _FakeSnapshot:
        path = Path("/fake/snapshot.pt")

    class _FakeLoader:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        @property
        def project_cfg(self):
            return {
                "multianimalproject": False,
                "cropping": False,
                "bodyparts": ["tip", "body_top", "body_bottom", "pivot"],
            }

        def snapshots(self):
            return [_FakeSnapshot()]

    fake_pkg = types.ModuleType("deeplabcut")
    pose_pkg = types.ModuleType("deeplabcut.pose_estimation_pytorch")
    data_pkg = types.ModuleType("deeplabcut.pose_estimation_pytorch.data")
    loader_pkg = types.ModuleType("deeplabcut.pose_estimation_pytorch.data.dlcloader")
    loader_pkg.DLCLoader = _FakeLoader
    fake_pkg.pose_estimation_pytorch = pose_pkg
    pose_pkg.data = data_pkg
    data_pkg.dlcloader = loader_pkg
    monkeypatch.setitem(sys.modules, "deeplabcut", fake_pkg)
    monkeypatch.setitem(sys.modules, "deeplabcut.pose_estimation_pytorch", pose_pkg)
    monkeypatch.setitem(sys.modules, "deeplabcut.pose_estimation_pytorch.data", data_pkg)
    monkeypatch.setitem(
        sys.modules, "deeplabcut.pose_estimation_pytorch.data.dlcloader", loader_pkg
    )

    # 训练路径(默认):四 bodypart 项目可定位快照(B1 修复前此处必 raise)
    snapshots = _model_snapshots(Path("/fake/config.yaml"), 1, 0)
    assert len(snapshots) == 1
    # 推理路径:保持单点守卫
    with pytest.raises(ValueError, match="Inference currently requires"):
        _model_snapshots(
            Path("/fake/config.yaml"), 1, 0, allowed_bodyparts=("target",)
        )
