"""外部 worker 协议的 host 侧(基础设施层):request 构造、受信子进程启动与 fail-closed 结果验证。

契约:publication/spec/runtime-boundary.md Protocol v1。本模块只提供机制
(进程、取消、验证);"何时/以何参数运行 worker"的策略属于 application 层
(S2 的 train_experiment)。
"""

import time
from datetime import datetime
import hashlib
import importlib.util
import json
import logging
import os
from pathlib import Path
import re
import signal
import subprocess
from typing import IO, Any, Sequence
from uuid import UUID

from ai_physics_tracker.domain.types import canonical_json_digest
from ai_physics_tracker.infrastructure.errors import ExternalWorkerError

# re-export:错误类型集中定义在 errors.py,此处重导出保持既有调用方兼容
__all__ = ["ExternalWorkerError", "ExternalWorkerRunner", "ExternalJobHandle", "build_request"]

logger = logging.getLogger(__name__)

PROTOCOL_VERSION = 1
WORKER_MODULE_DEFAULT = "ai_physics_tracker.worker"
# 跨进程协议字面量,与 worker/__main__.py 的 HELLO_MESSAGE 保持一致
HELLO_MESSAGE = "external worker ready"
DEVICE_BACKENDS = ("cpu", "mps", "cuda")
TERMINAL_STATUSES = ("success", "cancelled", "failed")
REQUEST_FILE_NAME = "request.json"
RESULT_FILE_NAME = "result.json"
CANCEL_MARKER_NAME = "cancel.request"
WORKER_LOG_NAME = "worker.log"
FORCED_REAP_TIMEOUT_S = 5.0

# 子进程最小环境白名单:只保留定位可执行文件 / 用户目录 / 编码 / 临时目录所需的系统
# 变量,其余一律不继承——PYTHONHOME、PYTHONPATH、PyInstaller 的 ``_PYI_*`` 等 frozen
# host 注入由此天然被清除(PyInstaller common-issues "external programs";spike 用
# "恢复式"清理 LD_LIBRARY_PATH,产品改用更严的白名单,不给 DLL 路径留继承通道)。
_ENV_ALLOWLIST: tuple[str, ...] = (
    "PATH",
    "HOME",
    "USER",
    "LOGNAME",
    "LANG",
    "LC_ALL",
    "LC_CTYPE",
    "TZ",
    "TMPDIR",
    "TEMP",
    "TMP",
    # Windows 缺失会导致 CRT 初始化 / 路径解析异常的必需变量
    "SYSTEMROOT",
    "SYSTEMDRIVE",
    "COMSPEC",
    "PATHEXT",
    "WINDIR",
    "USERNAME",
    "USERPROFILE",
    "APPDATA",
    "LOCALAPPDATA",
    "PROGRAMDATA",
    "HOMEDRIVE",
    "HOMEPATH",
    "OS",
)


def _default_package_root() -> Path:
    """默认 package_root = ai_physics_tracker 包的父目录(即 src 树)。"""
    return Path(__file__).resolve().parents[2]


def _canonical_dumps(payload: dict[str, Any]) -> str:
    """canonical JSON 文本;表示与 domain.types.canonical_json_digest 一致(可重算)。"""
    return (
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n"
    )


def _worker_source_path(package_root: Path, worker_module: str) -> Path:
    """从 package_root 按模块路径解析 worker 源文件。

    host 哈希的必须是子进程经 PYTHONPATH 实际导入的那份源,因此优先做文件系统解析:
    默认受信模块固定为包内 ``worker/__main__.py``;注入的模块名(测试缝)先按
    ``package_root/<module path>.py`` 与 ``package_root/<module path>/__main__.py``
    尝试;均不存在再回退 host 进程 find_spec——回退仅服务测试缝(stub 位于临时
    目录,不在 package_root 下)。
    """
    if worker_module == WORKER_MODULE_DEFAULT:
        return package_root / "ai_physics_tracker" / "worker" / "__main__.py"
    module_path = worker_module.replace(".", "/")
    module_file = package_root / (module_path + ".py")
    if module_file.is_file():
        return module_file
    package_main = package_root / module_path / "__main__.py"
    if package_main.is_file():
        return package_main
    try:
        spec = importlib.util.find_spec(worker_module)
    except (ImportError, ValueError):
        spec = None
    if spec is None:
        raise ExternalWorkerError(
            f"worker module {worker_module!r} not found under {package_root} or host sys.path"
        )
    if spec.submodule_search_locations:
        return Path(list(spec.submodule_search_locations)[0]) / "__main__.py"
    if spec.origin:
        return Path(spec.origin)
    raise ExternalWorkerError(f"worker module {worker_module!r} has no source file")


def _worker_source_sha256(package_root: Path, worker_module: str) -> str:
    """定位 worker 模块将被 ``-m`` 执行的源文件并取字节 SHA256(包取其 __main__.py)。"""
    source = _worker_source_path(package_root, worker_module)
    if not source.is_file():
        raise ExternalWorkerError(f"worker source file missing: {source}")
    return hashlib.sha256(source.read_bytes()).hexdigest()


def build_request(
    operation: str,
    *,
    job_id: UUID,
    device: str = "cpu",
    inputs: dict[str, str] | None = None,
    extra: dict[str, Any] | None = None,
    worker_module: str = WORKER_MODULE_DEFAULT,
    package_root: Path | None = None,
) -> tuple[dict[str, Any], str]:
    """构造 Protocol v1 request payload 及其 canonical digest。

    - device 是 backend 级名称(runtime-boundary:cpu/mps/cuda,实际 cuda:0 等由
      result 的 actual_device 报告);
    - inputs:S2 起由具体操作声明(S1 操作均不需要),name → 路径;
    - extra:操作特定附加字段,不得覆盖协议保留字段;
    - worker_module:测试缝(注入 stub worker),产品恒为默认受信模块;
    - package_root:worker 源解析根,默认为 ai_physics_tracker 包的父目录。
    """
    if device not in DEVICE_BACKENDS:
        raise ValueError(f"device must be one of {DEVICE_BACKENDS}, got {device!r}")
    resolved_root = (
        package_root if package_root is not None else _default_package_root()
    ).resolve()
    request: dict[str, Any] = {
        "protocol_version": PROTOCOL_VERSION,
        "job_id": str(job_id),
        "operation": operation,
        "worker_sha256": _worker_source_sha256(resolved_root, worker_module),
        "device": device,
    }
    if inputs is not None:
        request["inputs"] = dict(inputs)
    if extra is not None:
        reserved = set(request)
        overlap = sorted(set(extra) & reserved)
        if overlap:
            raise ValueError(f"extra must not override protocol fields: {overlap}")
        request.update(extra)
    return request, canonical_json_digest(request)


def _validate_request(request: dict[str, Any]) -> None:
    """start 边界的 fail-fast 校验:缺少协议字段的 request 不允许进入 spawn。"""
    if request.get("protocol_version") != PROTOCOL_VERSION:
        raise ExternalWorkerError(
            f"request protocol_version must be {PROTOCOL_VERSION}, got {request.get('protocol_version')!r}"
        )
    for key in ("job_id", "operation", "worker_sha256", "device"):
        value = request.get(key)
        if not isinstance(value, str) or not value:
            raise ExternalWorkerError(f"request field {key!r} must be a non-empty string")


def _is_error_dict(value: Any) -> bool:
    return (
        isinstance(value, dict)
        and isinstance(value.get("type"), str)
        and bool(value["type"])
        and isinstance(value.get("message"), str)
    )


class ExternalWorkerRunner:
    """以依赖注入的外部 Python 解释器启动受信 worker(host 侧机制)。

    dev 环境 runtime_python 指向当前 venv;frozen 发布指向未来的 managed runtime
    (installer 合同见 runtime-boundary.md,不在本 slice 范围)。
    """

    def __init__(
        self,
        runtime_python: str | Path,
        *,
        package_root: Path | None = None,
        grace_s: float = 5.0,
        worker_module: str = WORKER_MODULE_DEFAULT,
        python_path_extra: Sequence[Path] = (),
    ) -> None:
        # 注意不要 resolve():venv 的 bin/python 常是符号链接,解析到基础解释器会丢失
        # pyvenv.cfg 的 venv 归属,导致子进程 site-packages 指向错误环境。
        self._runtime_python = Path(runtime_python).expanduser().absolute()
        if not self._runtime_python.is_file():
            raise ExternalWorkerError(f"runtime python not found: {self._runtime_python}")
        self._package_root = (
            package_root if package_root is not None else _default_package_root()
        ).resolve()
        self._grace_s = grace_s
        # worker_module / python_path_extra 是测试缝:注入 stub worker 模块用,
        # 产品路径恒为默认受信模块 + 无额外搜索路径。
        self._worker_module = worker_module
        self._python_path_extra = [Path(entry).resolve() for entry in python_path_extra]

    def _build_environment(self) -> dict[str, str]:
        environment = {key: os.environ[key] for key in _ENV_ALLOWLIST if key in os.environ}
        python_path = os.pathsep.join(
            [str(self._package_root), *(str(entry) for entry in self._python_path_extra)]
        )
        environment["PYTHONPATH"] = python_path
        environment["PYTHONUTF8"] = "1"
        return environment

    def start(self, job_dir: Path, request: dict[str, Any]) -> "ExternalJobHandle":
        """在独占的 job 目录中落盘 request 并 spawn worker;非空目录视为 duplicate 拒绝。"""
        _validate_request(request)
        job_dir = Path(job_dir).resolve()
        try:
            occupied = job_dir.exists() and any(job_dir.iterdir())
        except OSError as error:
            raise ExternalWorkerError(
                f"job directory is not usable: {job_dir}: {error}"
            ) from error
        if occupied:
            raise ExternalWorkerError(f"job directory is not empty (duplicate job): {job_dir}")
        job_dir.mkdir(parents=True, exist_ok=True)
        request_path = job_dir / REQUEST_FILE_NAME
        request_path.write_text(_canonical_dumps(request), encoding="utf-8")

        log_file = (job_dir / WORKER_LOG_NAME).open("wb")
        argv = [
            str(self._runtime_python),
            "-m",
            self._worker_module,
            "--request",
            str(request_path),
        ]
        try:
            process = subprocess.Popen(
                argv,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                env=self._build_environment(),
                shell=False,
                # POSIX 独立 session,使 worker 及其子孙进程同组,可 killpg 整组回收
                start_new_session=os.name == "posix",
            )
        except Exception:
            log_file.close()
            raise
        return ExternalJobHandle(
            process=process,
            job_dir=job_dir,
            request=request,
            log_file=log_file,
            grace_s=self._grace_s,
        )


class ExternalJobHandle:
    """单个外部 worker job 的 host 侧句柄:存活查询、协作/强制取消、fail-closed 结果读取。"""

    def __init__(
        self,
        *,
        process: subprocess.Popen[bytes],
        job_dir: Path,
        request: dict[str, Any],
        log_file: IO[bytes],
        grace_s: float,
    ) -> None:
        self._process = process
        self._job_dir = job_dir
        self._grace_s = grace_s
        self._expected_digest = canonical_json_digest(request)
        self._job_id = request["job_id"]
        self._operation = request["operation"]
        self._device = request.get("device")
        self._log_file = log_file
        self._cancel_requested = False
        self._started_monotonic = time.monotonic()   # elapsed_s 记录(i3②)
        self._finished_monotonic: float | None = None
        self._forced_termination = False

    @property
    def job_dir(self) -> Path:
        return self._job_dir

    @property
    def job_id(self) -> str:
        return self._job_id

    @property
    def worker_log_path(self) -> Path:
        return self._job_dir / WORKER_LOG_NAME

    @property
    def cancel_requested(self) -> bool:
        return self._cancel_requested

    @property
    def forced_termination(self) -> bool:
        return self._forced_termination

    @property
    def returncode(self) -> int | None:
        return self._process.returncode

    @property
    def elapsed_s(self) -> float:
        """worker 启动至今的耗时(秒);进程退出后冻结(i3②,runtime-boundary)。"""

        if self._process.returncode is None:
            return time.monotonic() - self._started_monotonic
        if self._finished_monotonic is None:
            self._finished_monotonic = time.monotonic()
        return self._finished_monotonic - self._started_monotonic

    def is_alive(self) -> bool:
        return self._process.poll() is None

    def join(self, timeout_s: float | None = None) -> bool:
        """等待 worker 退出;返回是否已退出(timeout 到期返回 False,不抛异常)。"""
        try:
            self._process.wait(timeout=timeout_s)
        except subprocess.TimeoutExpired:
            return False
        self._close_log()
        return True

    def cancel(self) -> None:
        """取消:写 cancel.request marker → 等 grace → 仍存活则强制回收整组进程树。

        runtime-boundary §取消:child 被留下即取消失败,不能只杀 worker parent;
        强制回收后仍无法收尸时抛 ExternalWorkerError,不静默放弃。
        """
        if not self.is_alive():
            self._close_log()
            return
        self._cancel_requested = True
        try:
            (self._job_dir / CANCEL_MARKER_NAME).write_text("", encoding="utf-8")
        except OSError as error:
            # marker 写失败不放弃回收(fail-open 仅限协作路径):最终回收不依赖
            # marker,继续走 grace → 强制回收
            logger.warning(
                "failed to write cancel marker %s: %s; proceeding with grace/forced recovery",
                self._job_dir / CANCEL_MARKER_NAME,
                error,
            )
        if self.join(self._grace_s):
            return
        self._forced_termination = True
        logger.warning(
            "worker pid=%s unresponsive after %.3fs grace; forcing process-tree termination",
            self._process.pid,
            self._grace_s,
        )
        if self._process.poll() is None:
            if os.name == "nt":
                # Windows 真机 G4 门禁未验证(P6 前补);/T 连同子进程树、/F 强制终止
                kill_result = subprocess.run(
                    ["taskkill", "/PID", str(self._process.pid), "/T", "/F"],
                    capture_output=True,
                    check=False,
                )
                logger.info(
                    "taskkill pid=%s returncode=%s stdout=%r stderr=%r",
                    self._process.pid,
                    kill_result.returncode,
                    kill_result.stdout.decode("utf-8", errors="replace"),
                    kill_result.stderr.decode("utf-8", errors="replace"),
                )
            else:
                try:
                    # start_new_session ⇒ pgid == pid;getpgid 在进程刚退出时会抛
                    # ProcessLookupError,交由下方 wait 收尸
                    os.killpg(os.getpgid(self._process.pid), signal.SIGKILL)
                except ProcessLookupError as error:
                    logger.warning(
                        "killpg on pid=%s raced with worker exit: %s",
                        self._process.pid,
                        error,
                    )
        if not self.join(timeout_s=FORCED_REAP_TIMEOUT_S):
            self._close_log()
            raise ExternalWorkerError(
                "forced termination failed to reap the worker process tree; "
                f"pid={self._process.pid} (log: {self.worker_log_path})"
            )
        self._close_log()

    def _close_log(self) -> None:
        if not self._log_file.closed:
            self._log_file.close()

    def read_result(self) -> dict[str, Any]:
        """进程退出后读取并 fail-closed 验证 result(runtime-boundary §Host 校验)。

        status=failed 是合法终态,正常返回;任何验证失败抛 ExternalWorkerError
        (消息含具体字段与 worker.log 路径)。host 已判定 cancelled / forced 后,
        绝不采信 success(迟到结果拒绝)。
        """
        self._process.poll()
        returncode = self._process.returncode
        if returncode is None:
            raise ExternalWorkerError(
                f"worker still running; join before read_result (log: {self.worker_log_path})"
            )
        if self._forced_termination:
            raise ExternalWorkerError(
                f"worker was force-terminated; late result is rejected (log: {self.worker_log_path})"
            )
        self._read_request_as_written()
        result = self._read_result_file()
        self._validate_identity(result)
        self._validate_status_and_exit(result, returncode)
        if result["status"] == "success":
            self._validate_success_payload(result)
        elif result["status"] == "failed" and not _is_error_dict(result.get("error")):
            raise ExternalWorkerError(
                f"failed result misses error diagnostics (log: {self.worker_log_path})"
            )
        self._close_log()
        return result

    def _read_request_as_written(self) -> dict[str, Any]:
        """复核落盘 request 与启动时捕获的 digest 一致(job 目录可能被篡改)。"""
        request_path = self._job_dir / REQUEST_FILE_NAME
        if not request_path.is_file():
            raise ExternalWorkerError(
                f"request.json missing from job directory (log: {self.worker_log_path})"
            )
        try:
            written = json.loads(request_path.read_text(encoding="utf-8"))
            if not isinstance(written, dict):
                raise ValueError("request.json is not a JSON object")
            digest = canonical_json_digest(written)
        except (OSError, ValueError, json.JSONDecodeError) as error:
            raise ExternalWorkerError(
                f"request.json unreadable: {error} (log: {self.worker_log_path})"
            ) from error
        if digest != self._expected_digest:
            raise ExternalWorkerError(
                f"request.json no longer matches the digest captured at start (log: {self.worker_log_path})"
            )
        return written

    def _read_result_file(self) -> dict[str, Any]:
        result_path = self._job_dir / RESULT_FILE_NAME
        if not result_path.is_file():
            raise ExternalWorkerError(
                f"result.json missing after worker exit (log: {self.worker_log_path})"
            )
        try:
            result = json.loads(result_path.read_text(encoding="utf-8"))
            if not isinstance(result, dict):
                raise ValueError("result.json is not a JSON object")
            # canonical 解析约束:非有限浮点(NaN/Inf)不允许进入协议 payload
            json.dumps(result, allow_nan=False)
        except (OSError, ValueError, json.JSONDecodeError) as error:
            raise ExternalWorkerError(
                f"result.json is not valid canonical JSON: {error} (log: {self.worker_log_path})"
            ) from error
        return result

    def _validate_identity(self, result: dict[str, Any]) -> None:
        expectations: list[tuple[str, Any]] = [
            ("protocol_version", PROTOCOL_VERSION),
            ("job_id", self._job_id),
            ("request_digest", self._expected_digest),
            ("operation", self._operation),
        ]
        for field, expected in expectations:
            actual = result.get(field)
            if actual != expected:
                raise ExternalWorkerError(
                    f"result field {field!r} mismatch: expected {expected!r}, "
                    f"got {actual!r} (log: {self.worker_log_path})"
                )

    def _validate_status_and_exit(self, result: dict[str, Any], returncode: int) -> None:
        status = result.get("status")
        if status not in TERMINAL_STATUSES:
            raise ExternalWorkerError(
                f"invalid terminal status {status!r} (log: {self.worker_log_path})"
            )
        expected_code = 1 if status == "failed" else 0
        if returncode != expected_code:
            raise ExternalWorkerError(
                f"result status={status!r} conflicts with exit code {returncode} "
                f"(log: {self.worker_log_path})"
            )
        if status == "success" and self._cancel_requested:
            # runtime-boundary:取消之后迟到的 success 不采信,以 host lifecycle 为准
            raise ExternalWorkerError(
                "late success after cancellation is rejected; host lifecycle is "
                f"authoritative (log: {self.worker_log_path})"
            )

    def _validate_success_payload(self, result: dict[str, Any]) -> None:
        for field in ("python", "executable", "platform", "machine"):
            value = result.get(field)
            if not isinstance(value, str) or not value:
                raise ExternalWorkerError(
                    f"success result missing runtime identity field {field!r} "
                    f"(log: {self.worker_log_path})"
                )
        self._validate_timestamps(result)
        if self._operation == "hello" and result.get("message") != HELLO_MESSAGE:
            raise ExternalWorkerError(
                f"hello result message mismatch: {result.get('message')!r} "
                f"(log: {self.worker_log_path})"
            )
        if self._operation == "selftest_runtime":
            self._validate_selftest_payload(result)
        if self._operation == "infer_experiment" and not result.get("actual_device"):
            raise ExternalWorkerError(
                f"joint inference result misses actual_device (log: {self.worker_log_path})"
            )
        if self._operation in {"train_experiment", "infer_experiment"} and result.get("actual_device"):
            actual = str(result["actual_device"])
            requested = str(self._device)
            # auto 由 worker 解析后如实上报;显式 backend 必须匹配(带索引可)
            if requested != "auto" and not re.fullmatch(
                re.escape(requested) + r"(?::[0-9]+)?", actual
            ):
                raise ExternalWorkerError(
                    f"worker actual_device {actual!r} does not match the "
                    f"requested backend {requested!r} (log: {self.worker_log_path})"
                )
        self._validate_outputs(result)

    def _validate_timestamps(self, result: dict[str, Any]) -> None:
        """success 必须携带可解析的 ISO8601 起止时间(worker 侧由 utc_now 写入)。"""
        for field in ("started_at", "finished_at"):
            value = result.get(field)
            if not isinstance(value, str) or not value:
                raise ExternalWorkerError(
                    f"success result missing timestamp field {field!r} "
                    f"(log: {self.worker_log_path})"
                )
            try:
                datetime.fromisoformat(value)
            except ValueError as error:
                raise ExternalWorkerError(
                    f"success result field {field!r} is not ISO8601: {value!r} "
                    f"(log: {self.worker_log_path})"
                ) from error

    def _validate_selftest_payload(self, result: dict[str, Any]) -> None:
        versions = result.get("versions")
        if (
            not isinstance(versions, dict)
            or not isinstance(versions.get("torch"), str)
            or not versions["torch"]
        ):
            raise ExternalWorkerError(
                f"selftest_runtime result misses versions['torch'] (log: {self.worker_log_path})"
            )
        actual_device = result.get("actual_device")
        # runtime-boundary:请求的是 backend;cuda:0/mps:0 等带索引的 actual_device
        # 必须与 backend 匹配,不得用字符串相等错误拒绝
        if not isinstance(actual_device, str) or not re.fullmatch(
            re.escape(str(self._device)) + r"(?::[0-9]+)?", actual_device
        ):
            raise ExternalWorkerError(
                f"selftest_runtime actual_device {actual_device!r} does not match "
                f"requested backend {self._device!r} (log: {self.worker_log_path})"
            )

    def _validate_outputs(self, result: dict[str, Any]) -> None:
        """声明的 outputs 必须落在 job 目录内且 size / SHA256 一致。

        S1 操作恒声明空列表;本函数即 S2(train_experiment 声明 checkpoint/config)
        复用的输出校验接口。
        """
        outputs = result.get("outputs")
        if outputs is None:
            # M1(2026-09-28 review):success 缺 outputs 键 = 输出完整性链旁路,
            # fail closed(空输出也必须显式声明为空列表)
            raise ExternalWorkerError(
                f"success result misses the 'outputs' declaration (log: {self.worker_log_path})"
            )
        if not isinstance(outputs, list):
            raise ExternalWorkerError(
                f"declared outputs must be a list (log: {self.worker_log_path})"
            )
        for item in outputs:
            if not isinstance(item, dict):
                raise ExternalWorkerError(
                    f"output declaration must be an object: {item!r} (log: {self.worker_log_path})"
                )
            relative = item.get("path")
            if not isinstance(relative, str) or not relative:
                raise ExternalWorkerError(
                    f"output declaration misses 'path': {item!r} (log: {self.worker_log_path})"
                )
            candidate = self._job_dir / relative
            if candidate.is_symlink() or not candidate.resolve().is_relative_to(self._job_dir):
                raise ExternalWorkerError(
                    f"output path escapes job directory: {relative!r} (log: {self.worker_log_path})"
                )
            try:
                from ai_physics_tracker.infrastructure.hashing import file_sha256

                size = candidate.stat().st_size
                sha256 = file_sha256(candidate)
            except OSError as error:
                raise ExternalWorkerError(
                    f"declared output unreadable: {relative!r}: {error} "
                    f"(log: {self.worker_log_path})"
                ) from error
            if item.get("size") != size or item.get("sha256") != sha256:
                raise ExternalWorkerError(
                    f"declared output size/sha256 mismatch: {relative!r} (log: {self.worker_log_path})"
                )
