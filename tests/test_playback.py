"""与 Qt 无关的 AsyncVideoSession 线程编排测试。

验证 phase2-requirements.md §2 R3：后台解码、latest-request coalescing、
过期请求丢弃。用 threading.Event 门控 fake reader，不依赖睡眠时序。
"""

import threading
import time
from pathlib import Path

import numpy as np
import pytest

from ai_physics_tracker.application.playback import AsyncVideoSession
from ai_physics_tracker.application.video import (
    DecodedFrame,
    VideoError,
    VideoOpenError,
    VideoStreamInfo,
)
from ai_physics_tracker.application.video_session import VideoSession


def wait_until(predicate, timeout: float = 5.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return False


class ControlledFakeReader:
    """可门控的 fake reader：manual_gate 开启后 read_frame 阻塞到 release。"""

    def __init__(self, frame_count: int = 6, fps_container: float = 2.0) -> None:
        self._is_open = False
        self._info = VideoStreamInfo(
            8, 6, fps_container, frame_count, "fake", "cfr"
        )
        self.manual_gate = False
        self.release = threading.Event()
        self.fail_open = False
        self.decoded_frames: list[int] = []
        self.close_calls = 0

    @property
    def is_open(self) -> bool:
        return self._is_open

    @property
    def info(self) -> VideoStreamInfo:
        return self._info

    def open(self, path: Path) -> VideoStreamInfo:
        if self.fail_open:
            raise VideoOpenError("cannot open")
        self._is_open = True
        return self._info

    def read_frame(self, frame_index: int) -> DecodedFrame:
        self.decoded_frames.append(frame_index)
        if self.manual_gate:
            assert self.release.wait(timeout=5.0), "decode gate never released"
        pixels = np.full((6, 8, 3), frame_index, dtype=np.uint8)
        return DecodedFrame(frame_index, pixels)

    def close(self) -> None:
        self.close_calls += 1
        self._is_open = False


class Callbacks:
    """线程安全的回调收集器；close() join 后读取即同步。"""

    def __init__(self) -> None:
        self.frames: list[int] = []
        self.errors: list[VideoError] = []
        self.lock = threading.Lock()

    def on_frame(self, frame: DecodedFrame) -> None:
        with self.lock:
            self.frames.append(frame.frame_index)

    def on_error(self, error: VideoError) -> None:
        with self.lock:
            self.errors.append(error)


def make_session(
    reader: ControlledFakeReader, callbacks: Callbacks
) -> AsyncVideoSession:
    return AsyncVideoSession(
        VideoSession(reader), callbacks.on_frame, callbacks.on_error
    )


def test_open_future_returns_first_frame_snapshot() -> None:
    reader = ControlledFakeReader()
    callbacks = Callbacks()
    session = make_session(reader, callbacks)

    snapshot = session.open(Path("video.fake")).result(timeout=5.0)

    assert snapshot.current_frame.frame_index == 0
    assert snapshot.info.frame_count == 6
    assert snapshot.timeline.fps_nominal == pytest.approx(2.0)
    assert session.snapshot() == snapshot
    assert callbacks.frames == []
    session.close()


def test_open_failure_surfaces_exception_in_future_only() -> None:
    reader = ControlledFakeReader()
    reader.fail_open = True
    callbacks = Callbacks()
    session = make_session(reader, callbacks)

    future = session.open(Path("bad.fake"))

    with pytest.raises(VideoOpenError):
        future.result(timeout=5.0)
    assert session.snapshot() is None
    assert callbacks.errors == []
    session.close()


def test_request_frame_decodes_and_reports_via_callback() -> None:
    reader = ControlledFakeReader()
    callbacks = Callbacks()
    session = make_session(reader, callbacks)
    session.open(Path("video.fake")).result(timeout=5.0)

    session.request_frame(3)
    assert wait_until(lambda: callbacks.frames == [3])

    assert session.snapshot() is not None
    assert session.snapshot().current_frame.frame_index == 3
    session.close()


def test_latest_wins_coalesces_pending_requests() -> None:
    reader = ControlledFakeReader()
    callbacks = Callbacks()
    session = make_session(reader, callbacks)
    session.open(Path("video.fake")).result(timeout=5.0)

    reader.manual_gate = True
    session.request_frame(1)
    assert wait_until(lambda: 1 in reader.decoded_frames)
    session.request_frame(2)
    session.request_frame(3)
    reader.release.set()

    assert wait_until(lambda: callbacks.frames == [1, 3])
    session.close()

    # 帧号 2 在解码开始前即被 3 覆盖（R3 latest-request coalescing）
    assert reader.decoded_frames == [0, 1, 3]


def test_request_without_open_reports_error_callback() -> None:
    reader = ControlledFakeReader()
    callbacks = Callbacks()
    session = make_session(reader, callbacks)

    session.request_frame(0)

    assert wait_until(lambda: len(callbacks.errors) == 1)
    assert isinstance(callbacks.errors[0], VideoError)
    assert callbacks.frames == []
    session.close()


def test_close_stops_worker_and_no_callbacks_after() -> None:
    reader = ControlledFakeReader()
    callbacks = Callbacks()
    session = make_session(reader, callbacks)
    session.open(Path("video.fake")).result(timeout=5.0)

    session.close()

    assert not session._worker.is_alive()
    session.request_frame(2)
    time.sleep(0.1)
    assert callbacks.frames == []
    # VideoSession.open 先预防性 close 一次，AsyncVideoSession.close 再一次
    assert reader.close_calls == 2
    assert session.snapshot() is None


def test_open_after_close_rejects_future() -> None:
    reader = ControlledFakeReader()
    callbacks = Callbacks()
    session = make_session(reader, callbacks)
    session.close()

    future = session.open(Path("video.fake"))

    with pytest.raises(VideoError):
        future.result(timeout=5.0)
