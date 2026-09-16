"""解码交付跨线程边界的回归（Windows CI 0xc0000374/c0000005 崩溃修复）。

根因：worker 线程直接 emit 携带 Python 对象的 queued signal，PySide6 6.11
在 Windows 特定调度时序下对参数对象的引用管理产生损坏。修复后交付对象
只走 _DecodeDeliveryBridge 的线程安全队列，Qt 信号仅做无参唤醒——
交付类信号必须且只能在 GUI 线程发出。
"""

import threading

from ai_physics_tracker.application.video_session import VideoSession
from ai_physics_tracker.gui.main_window import MainWindow, _DecodeDeliveryBridge
from ai_physics_tracker.infrastructure.opencv_video_reader import OpenCVVideoReader
from ai_physics_tracker.infrastructure.project_repository import ProjectRepository
from tests.gui.test_tracking_actions import _StaticTimingProbe


def test_bridge_drains_all_items_in_fifo_order() -> None:
    bridge = _DecodeDeliveryBridge(None)
    for index in range(5):
        bridge.enqueue(index)
    assert bridge.drain() == [0, 1, 2, 3, 4]
    assert bridge.drain() == []  # 取空后再次 drain 返回空列表


def test_bridge_delivers_items_queued_from_worker_thread(qtbot) -> None:
    """worker 线程 enqueue 期间主线程 drain 不得丢失交付（竞态回归）。"""

    bridge = _DecodeDeliveryBridge(None)
    seen: list[object] = []
    bridge.pending.connect(lambda: seen.extend(bridge.drain()))

    results = list(range(50))
    producer = threading.Thread(
        target=lambda: [bridge.enqueue(item) for item in results], daemon=True
    )
    producer.start()
    qtbot.waitUntil(lambda: len(seen) >= len(results), timeout=5000)
    producer.join(timeout=5)

    assert seen == results


def test_delivery_signals_emit_only_on_gui_thread(qtbot, synthetic_video_path) -> None:
    """端到端回归：解码交付信号必须只在 GUI 线程发出（根因约束）。"""

    window = MainWindow(
        lambda: VideoSession(OpenCVVideoReader()),
        ProjectRepository(),
        _StaticTimingProbe(),
    )
    qtbot.addWidget(window)
    assert window.openVideo(synthetic_video_path, show_error=False)

    emit_threads: list[threading.Thread] = []
    window.decodeCompleted.connect(
        lambda _result, _token: emit_threads.append(threading.current_thread()))
    window.frameDelivered.connect(
        lambda _frame, _token: emit_threads.append(threading.current_thread()))

    window._requestFrame(1)
    qtbot.waitUntil(lambda: window.presentedFrameIndex == 1, timeout=5000)
    window.nextButton.click()
    qtbot.waitUntil(lambda: window.presentedFrameIndex == 2, timeout=5000)

    assert emit_threads
    assert all(thread is threading.main_thread() for thread in emit_threads)


def test_close_leaves_no_decoder_or_executor_threads(qtbot, synthetic_video_path) -> None:
    """lifecycle：窗口 close 返回后，decoder 与项目 executor 线程均已退出。

    close() 返回后不得再有回调（application/playback.py 契约）；泄漏线程
    会在测试进程内长期持有 native 资源，是 CI 崩溃的温床。
    """

    window = MainWindow(
        lambda: VideoSession(OpenCVVideoReader()),
        ProjectRepository(),
        _StaticTimingProbe(),
    )
    qtbot.addWidget(window)
    assert window.openVideo(synthetic_video_path, show_error=False)

    window.projectActions.close_allowed = True
    assert window.close()

    names = [thread.name for thread in threading.enumerate()]
    assert not any(name.startswith("async-video-session") for name in names)
    assert not any(name.startswith("project-workflow") for name in names)
