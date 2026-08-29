"""Qt-free VideoSession navigation and cleanup tests."""

from pathlib import Path

import numpy as np
import pytest

from ai_physics_tracker.application.video import DecodedFrame, VideoStreamInfo
from ai_physics_tracker.application.video_session import VideoSession


class FakeVideoReader:
    def __init__(self, frame_count: int = 4, fps_container: float = 2.0) -> None:
        self._is_open = False
        self._info = VideoStreamInfo(8, 6, fps_container, frame_count, "fake", "cfr")
        self.close_calls = 0

    @property
    def is_open(self) -> bool:
        return self._is_open

    @property
    def info(self) -> VideoStreamInfo:
        return self._info

    def open(self, path: Path) -> VideoStreamInfo:
        self._is_open = True
        return self._info

    def read_frame(self, frame_index: int) -> DecodedFrame:
        if not self._is_open:
            raise RuntimeError("reader is closed")
        pixels = np.full((6, 8, 3), frame_index, dtype=np.uint8)
        return DecodedFrame(frame_index, pixels)

    def close(self) -> None:
        self.close_calls += 1
        self._is_open = False


def test_session_opens_frame_zero_and_uses_timeline_for_time() -> None:
    reader = FakeVideoReader()
    session = VideoSession(reader)

    frame = session.open(Path("video.fake"))

    assert frame.frame_index == 0
    assert session.current_time_s == pytest.approx(0.0, abs=1e-12)
    assert session.timeline.working_zone == (0, 3)


def test_session_step_and_jump_clamp_to_video_bounds() -> None:
    session = VideoSession(FakeVideoReader())
    session.open(Path("video.fake"))

    assert session.step(-1).frame_index == 0
    assert session.step(1).frame_index == 1
    assert session.current_time_s == pytest.approx(0.5, abs=1e-12)
    assert session.go_to_frame(99).frame_index == 3
    assert session.step(1).frame_index == 3


def test_session_switch_and_close_release_reader() -> None:
    reader = FakeVideoReader()
    session = VideoSession(reader)
    session.open(Path("first.fake"))

    session.open(Path("second.fake"))
    session.close()

    assert not session.is_open
    assert reader.close_calls == 3
