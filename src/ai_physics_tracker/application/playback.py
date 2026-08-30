"""与 Qt 无关的异步视频会话：后台线程串行解码，请求 latest-wins 合并。

application 层组件（ADR-0005 §4）：不 import Qt；内部组合同步
`VideoSession` 并将其全部变更操作（open / go_to_frame / close）转移到
单个工作线程串行执行——OpenCV `VideoCapture` 不保证线程安全，因此
reader 只允许被该线程访问（CODE_STANDARD.md §14：明确线程所有权）。

回调约定：`on_frame` / `on_error` 在工作线程中执行；GUI 侧必须自行
marshal 回自己的事件循环（Qt signal 天然跨线程排队）。`close()` 返回
后保证不再发生任何回调，可作为测试与关停的同步点。
"""

import logging
import threading
from concurrent.futures import Future
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from ai_physics_tracker.application.video import (
    DecodedFrame,
    VideoError,
    VideoStreamInfo,
)
from ai_physics_tracker.application.video_session import VideoSession
from ai_physics_tracker.domain.timeline import Timeline

logger = logging.getLogger(__name__)

FrameCallback = Callable[[DecodedFrame], None]
ErrorCallback = Callable[[VideoError], None]


@dataclass(frozen=True)
class PlaybackSnapshot:
    """一次读取的完整会话状态快照，避免 GUI 观察到撕裂的部分状态。"""

    info: VideoStreamInfo
    timeline: Timeline
    current_frame: DecodedFrame


class AsyncVideoSession:
    """把同步 VideoSession 包成 latest-wins 的异步帧服务。

    - `open()` 在工作线程执行并返回 Future（含首帧解码，见 VideoSession.open）；
    - `request_frame()` 只保留最新未处理的帧号（覆盖旧请求）：播放与 scrub
      高频提交时，中间帧在解码开始前即被丢弃，这正是 phase2-requirements.md
      §2 R3 的"latest-request coalescing / 过期解码请求可丢弃"；
    - `snapshot()` 提供当前状态的最终一致读取（见其 docstring）；
    - 会话已停止或正在关闭时 `request_frame()` 静默丢弃请求且**不产生
      任何回调**——调用方不得依赖回调来清自身的在途标志。
    """

    def __init__(
        self,
        session: VideoSession,
        on_frame: FrameCallback,
        on_error: ErrorCallback,
    ) -> None:
        self._session = session
        self._on_frame = on_frame
        self._on_error = on_error
        self._lock = threading.Lock()
        self._wakeup = threading.Condition(self._lock)
        self._pending_frame: int | None = None
        self._pending_open: Path | None = None
        self._pending_timeline: Timeline | None = None
        self._pending_initial_frame = 0
        self._pending_open_future: Future[PlaybackSnapshot] | None = None
        self._pending_close = False
        self._stopped = False
        self._worker = threading.Thread(
            target=self._run, name="async-video-session", daemon=True
        )
        self._worker.start()

    def open(
        self, path: Path, timeline: Timeline | None = None, frame_index: int = 0
    ) -> "Future[PlaybackSnapshot]":
        """请求在工作线程打开视频；Future 完成时带回首帧快照或异常。"""

        future: Future[PlaybackSnapshot] = Future()
        with self._wakeup:
            if self._stopped:
                future.set_exception(VideoError("session is closed"))
                return future
            if self._pending_open is not None or self._pending_close:
                future.set_exception(VideoError("another open/close is pending"))
                return future
            self._pending_open = path
            self._pending_timeline = timeline
            self._pending_initial_frame = frame_index
            self._pending_open_future = future
            self._wakeup.notify_all()
        return future

    def request_frame(self, frame_index: int) -> None:
        """提交解码请求；覆盖尚未开始的旧请求（latest-wins）。

        会话已停止或正在关闭时请求被静默丢弃，不产生回调。
        """

        with self._wakeup:
            if self._stopped or self._pending_close:
                return
            self._pending_frame = frame_index
            self._wakeup.notify_all()

    def snapshot(self) -> PlaybackSnapshot | None:
        """当前会话状态；未打开或已关闭时返回 None。

        worker 是 session 的唯一写者，这里不加锁直接读：`go_to_frame`
        只写 `_current_frame` 单字段（不可变对象），无撕裂组合；open 的
        字段按序发布且 `_current_frame` 最后赋值，读到半开状态时
        `is_open` 仍为 False。读到 open/close 的中间态（属性抛
        VideoError）按"暂无有效快照"处理返回 None。
        """

        try:
            if not self._session.is_open:
                return None
            return PlaybackSnapshot(
                info=self._session.info,
                timeline=self._session.timeline,
                current_frame=self._session.current_frame,
            )
        except VideoError:
            return None

    def close(self) -> None:
        """请求关闭并等待工作线程退出；返回后保证不再有回调。"""

        with self._wakeup:
            if self._stopped:
                return
            self._pending_close = True
            self._pending_frame = None
            self._wakeup.notify_all()
        self._worker.join(timeout=10.0)
        if self._worker.is_alive():
            logger.error("async video session worker did not exit within timeout")

    def _run(self) -> None:
        while True:
            path: Path | None
            frame_index: int | None
            closing: bool
            open_future: Future[PlaybackSnapshot] | None
            with self._wakeup:
                while (
                    self._pending_open is None
                    and self._pending_frame is None
                    and not self._pending_close
                ):
                    self._wakeup.wait()
                path = self._pending_open
                timeline = self._pending_timeline
                initial_frame = self._pending_initial_frame
                self._pending_open = None
                open_future = self._pending_open_future
                self._pending_open_future = None
                frame_index = self._pending_frame
                self._pending_frame = None
                closing = self._pending_close
            if closing:
                if open_future is not None and not open_future.done():
                    open_future.set_exception(VideoError("session closed before open"))
                self._session.close()
                self._stopped = True
                self._pending_close = False
                return
            if path is not None:
                self._handle_open(path, open_future, timeline, initial_frame)
            elif frame_index is not None:
                self._decode(frame_index)

    def _handle_open(
        self, path: Path, future: Future[PlaybackSnapshot] | None,
        timeline: Timeline | None = None, frame_index: int = 0,
    ) -> None:
        # open 走 Future 请求-响应通道；on_frame/on_error 只服务 request_frame
        # 的异步事件，避免 GUI 对同一操作收到双重通知。
        try:
            if timeline is None and frame_index == 0:
                self._session.open(path)
            else:
                self._session.open(path, timeline, frame_index)
            snapshot = PlaybackSnapshot(
                info=self._session.info,
                timeline=self._session.timeline,
                current_frame=self._session.current_frame,
            )
        except Exception as error:
            logger.warning("async video open failed: %s", path, exc_info=True)
            if future is not None:
                future.set_exception(error)
            return
        if future is not None:
            future.set_result(snapshot)

    def _decode(self, frame_index: int) -> None:
        # 不在解码期间持有任何锁：request_frame 必须能在慢速解码进行中
        # 覆盖 pending 槽，否则 latest-wins 退化为排队（见
        # test_latest_wins_coalesces_pending_requests）。worker 是唯一写者。
        try:
            if not self._session.is_open:
                raise VideoError("no video is open")
            frame = self._session.go_to_frame(frame_index)
        except VideoError as error:
            self._emit_error(error)
            return
        except Exception as error:
            self._emit_error(VideoError(str(error)))
            return
        try:
            if not self._pending_close and not self._stopped:
                self._on_frame(frame)
        except Exception:
            logger.exception("on_frame callback raised for frame %d", frame.frame_index)

    def _emit_error(self, error: Exception) -> None:
        if not isinstance(error, VideoError):
            error = VideoError(str(error))
        try:
            if not self._pending_close and not self._stopped:
                self._on_error(error)
        except Exception:
            logger.exception("on_error callback raised")
