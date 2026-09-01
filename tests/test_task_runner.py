"""多进程后台任务框架 TaskRunner 的生命周期、IPC 通信与异常处理测试。"""

import time
from uuid import uuid4

from ai_physics_tracker.infrastructure.task_runner import (
    BackgroundTaskRunner,
    TaskLog,
    TaskProgress,
    TaskResult,
    send_log,
    send_progress,
)


def _dummy_successful_worker(run_id, queue, cancel_event, total_steps: int = 5):
    """模拟正常运行的工作函数，流式发送日志与进度。"""
    send_log(queue, run_id, "INFO", "Worker started")
    for step in range(1, total_steps + 1):
        if cancel_event.is_set():
            send_log(queue, run_id, "WARNING", "Worker cancelled early")
            return {"cancelled_at_step": step}
        send_progress(queue, run_id, step=step, total_steps=total_steps, loss=0.5 / step)
        time.sleep(0.02)
    send_log(queue, run_id, "INFO", "Worker finished successfully")
    return {"saved_model": "/path/to/model.pt", "final_loss": 0.1}


def _dummy_failing_worker(run_id, queue, cancel_event):
    """模拟抛出异常的工作函数。"""
    send_log(queue, run_id, "INFO", "Starting failing worker")
    time.sleep(0.02)
    raise RuntimeError("Synthetic worker failure: GPU out of memory")


def _dummy_hanging_worker(run_id, queue, cancel_event):
    """模拟忽略 cancel_event 持续死循环的工作函数。"""
    send_log(queue, run_id, "INFO", "Hanging worker running")
    while True:
        time.sleep(0.05)


def test_task_runner_success_flow() -> None:
    runner = BackgroundTaskRunner()
    run_id = uuid4()
    handle = runner.start_task(run_id, _dummy_successful_worker, total_steps=3)

    assert handle.run_id == run_id
    assert handle.is_alive()

    # 循环轮询消息直到进程结束
    all_messages = []
    start_time = time.time()
    while handle.is_alive() or (time.time() - start_time < 2.0):
        msgs = handle.poll_messages()
        all_messages.extend(msgs)
        if any(isinstance(m, TaskResult) for m in all_messages):
            break
        time.sleep(0.01)

    handle.join(timeout_s=1.0)
    assert not handle.is_alive()
    assert handle.exitcode == 0

    # 收集剩余消息
    all_messages.extend(handle.poll_messages())

    # 验证消息序列与内容
    logs = [m for m in all_messages if isinstance(m, TaskLog)]
    progresses = [m for m in all_messages if isinstance(m, TaskProgress)]
    results = [m for m in all_messages if isinstance(m, TaskResult)]

    assert len(logs) >= 2
    assert logs[0].message == "Worker started"
    assert logs[-1].message == "Worker finished successfully"

    assert len(progresses) == 3
    assert progresses[0].step == 1
    assert progresses[2].step == 3

    assert len(results) == 1
    assert results[0].success is True
    assert results[0].payload == {"saved_model": "/path/to/model.pt", "final_loss": 0.1}
    assert results[0].error is None


def test_task_runner_error_capture() -> None:
    runner = BackgroundTaskRunner()
    run_id = uuid4()
    handle = runner.start_task(run_id, _dummy_failing_worker)

    all_messages = []
    start_time = time.time()
    while handle.is_alive() or (time.time() - start_time < 2.0):
        msgs = handle.poll_messages()
        all_messages.extend(msgs)
        if any(isinstance(m, TaskResult) for m in all_messages):
            break
        time.sleep(0.01)

    handle.join(timeout_s=1.0)
    all_messages.extend(handle.poll_messages())

    results = [m for m in all_messages if isinstance(m, TaskResult)]
    assert len(results) == 1
    assert results[0].success is False
    assert "Synthetic worker failure: GPU out of memory" in str(results[0].error)


def test_task_runner_cooperative_cancellation() -> None:
    runner = BackgroundTaskRunner()
    run_id = uuid4()
    handle = runner.start_task(run_id, _dummy_successful_worker, total_steps=50)

    messages = []
    deadline = time.monotonic() + 3.0
    while time.monotonic() < deadline:
        messages.extend(handle.poll_messages())
        if any(isinstance(message, TaskLog) and message.message == "Worker started"
               for message in messages):
            break
        time.sleep(0.01)
    else:
        handle.cancel(timeout_s=0)
        raise AssertionError("worker did not report startup")

    handle.cancel(timeout_s=1.0)
    assert not handle.is_alive()

    messages.extend(handle.poll_messages())
    logs = [m for m in messages if isinstance(m, TaskLog)]
    assert any("cancelled" in log.message.lower() for log in logs)

    results = [m for m in messages if isinstance(m, TaskResult)]
    if results:
        assert results[0].success is False


def test_task_runner_forced_cancellation_of_hanging_worker() -> None:
    runner = BackgroundTaskRunner()
    run_id = uuid4()
    handle = runner.start_task(run_id, _dummy_hanging_worker)

    time.sleep(0.05)
    assert handle.is_alive()

    # 强制终止（worker 不响应 cancel_event，触发 terminate/kill）
    handle.cancel(timeout_s=0.1)
    assert not handle.is_alive()
    # 验证强杀后 poll_messages 不会因 EOFError 崩溃
    handle.poll_messages()
