"""基于 multiprocessing spawn 模式的安全多进程后台任务框架。"""

from datetime import UTC, datetime
import multiprocessing as mp
from multiprocessing.context import BaseContext
from queue import Empty
import time
from typing import Any, Callable
from uuid import UUID

from ai_physics_tracker.domain.types import JsonObject


from ai_physics_tracker.application.tracking_types import TaskProgress, TaskLog, TaskResult, TaskMessage


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
        is_failed = isinstance(res, dict) and res.get("status") == "failed"
        error_msg = res.get("error_message") if isinstance(res, dict) and is_failed else None
        if isinstance(res, dict):
            queue.put(TaskResult(run_id=run_id, success=not (is_cancelled or is_failed), payload=res, error=error_msg))
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

    def poll_messages(self, limit: int | None = None) -> list[TaskMessage]:
        """非阻塞轮询读取子进程发来的所有最新消息。"""

        messages: list[TaskMessage] = []
        while limit is None or len(messages) < limit:
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
        try:
            process.start()
        except Exception:
            if process.pid is not None and process.is_alive():
                process.terminate()
                process.join(timeout=1.0)
            queue.close()
            raise

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
    learning_rate: float | None = None,
) -> None:
    """子进程向队列发送进度的便捷工具函数。"""

    queue.put(
        TaskProgress(
            run_id=run_id,
            step=step,
            total_steps=total_steps,
            loss=loss,
            message=message,
            learning_rate=learning_rate,
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
