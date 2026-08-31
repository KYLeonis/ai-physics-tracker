"""基于 multiprocessing spawn 模式的安全多进程后台任务框架。"""

from dataclasses import dataclass
from datetime import UTC, datetime
import multiprocessing as mp
from multiprocessing.context import BaseContext
from queue import Empty
import time
from typing import Any, Callable, TypeAlias
from uuid import UUID

from ai_physics_tracker.domain.types import JsonObject


@dataclass(frozen=True)
class TaskProgress:
    """任务执行进度消息。"""

    run_id: UUID
    step: int
    total_steps: int
    loss: float | None = None
    message: str = ""


@dataclass(frozen=True)
class TaskLog:
    """任务执行日志消息。"""

    run_id: UUID
    level: str
    message: str
    timestamp: str


@dataclass(frozen=True)
class TaskResult:
    """任务执行最终结果消息。"""

    run_id: UUID
    success: bool
    payload: JsonObject | None = None
    error: str | None = None


TaskMessage: TypeAlias = TaskProgress | TaskLog | TaskResult


def _worker_process_entry(
    target_fn: Callable[..., Any],
    run_id: UUID,
    queue: Any,
    cancel_event: Any,
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
) -> None:
    """顶层子进程入口包装器，负责未捕获异常的安全捕获与 IPC 返回。"""

    try:
        res = target_fn(run_id, queue, cancel_event, *args, **kwargs)
        is_cancelled = cancel_event.is_set() or (isinstance(res, dict) and res.get("status") == "cancelled")
        if isinstance(res, dict):
            queue.put(TaskResult(run_id=run_id, success=not is_cancelled, payload=res))
        elif res is True or res is None:
            queue.put(TaskResult(run_id=run_id, success=not is_cancelled))
    except Exception as exc:
        import traceback

        tb = traceback.format_exc()
        queue.put(
            TaskResult(
                run_id=run_id,
                success=False,
                error=f"{type(exc).__name__}: {exc}\n{tb}",
            )
        )


class TaskHandle:
    """单个后台任务的运行句柄，支持进度轮询、状态查询与安全取消。"""

    def __init__(
        self,
        run_id: UUID,
        process: Any,
        queue: Any,
        cancel_event: Any,
    ) -> None:
        self.run_id = run_id
        self._process = process
        self._queue = queue
        self._cancel_event = cancel_event

    def poll_messages(self) -> list[TaskMessage]:
        """非阻塞轮询读取子进程发来的所有最新消息。"""

        messages: list[TaskMessage] = []
        while True:
            try:
                msg = self._queue.get_nowait()
                messages.append(msg)
            except (Empty, OSError, ValueError, EOFError):
                break
        return messages

    def is_alive(self) -> bool:
        """检查子进程是否仍在存活运行。"""

        return bool(self._process.is_alive())

    @property
    def exitcode(self) -> int | None:
        """获取子进程退出码。"""

        return self._process.exitcode

    def cancel(self, timeout_s: float = 3.0) -> None:
        """向子进程发出取消信号；若超时未退出则强制 terminate/kill。"""

        self._cancel_event.set()
        self._process.join(timeout=timeout_s)
        if self._process.is_alive():
            self._process.terminate()
            self._process.join(timeout=1.0)
        if self._process.is_alive():
            self._process.kill()
            self._process.join(timeout=1.0)

    def join(self, timeout_s: float | None = None) -> None:
        """等待子进程结束。"""

        self._process.join(timeout=timeout_s)

    def emit_log(self, level: str, message: str) -> None:
        """辅助方法（供测试或宿主使用）。"""

        pass


class BackgroundTaskRunner:
    """使用 multiprocessing spawn 上下文启动和管理后台任务的执行器。"""

    def __init__(self, ctx: BaseContext | None = None) -> None:
        # 强制使用 spawn 模式，保证跨平台 (macOS/Windows) 及 CUDA 上下文安全性
        self._ctx = ctx or mp.get_context("spawn")

    def start_task(
        self,
        run_id: UUID,
        target_fn: Callable[..., Any],
        *args: Any,
        **kwargs: Any,
    ) -> TaskHandle:
        """启动一个后台工作进程并返回任务句柄。

        注意：禁用 daemon=True，以便子进程内 PyTorch DataLoader 能够正常创建多 worker 子进程。
        """

        queue = self._ctx.Queue()
        cancel_event = self._ctx.Event()

        process = self._ctx.Process(
            target=_worker_process_entry,
            args=(target_fn, run_id, queue, cancel_event, args, kwargs),
            daemon=False,
        )
        process.start()

        return TaskHandle(
            run_id=run_id,
            process=process,
            queue=queue,
            cancel_event=cancel_event,
        )


def send_progress(
    queue: Any,
    run_id: UUID,
    step: int,
    total_steps: int,
    loss: float | None = None,
    message: str = "",
) -> None:
    """子进程向队列发送进度的便捷工具函数。"""

    queue.put(
        TaskProgress(
            run_id=run_id,
            step=step,
            total_steps=total_steps,
            loss=loss,
            message=message,
        )
    )


def send_log(
    queue: Any,
    run_id: UUID,
    level: str,
    message: str,
) -> None:
    """子进程向队列发送日志的便捷工具函数。"""

    now_iso = datetime.now(UTC).isoformat()
    queue.put(
        TaskLog(
            run_id=run_id,
            level=level,
            message=message,
            timestamp=now_iso,
        )
    )
