"""Qt-free single-video browsing session and Timeline navigation."""

from pathlib import Path
from uuid import uuid4

from ai_physics_tracker.application.video import (
    DecodedFrame,
    VideoError,
    VideoFrameError,
    VideoReader,
    VideoStreamInfo,
)
from ai_physics_tracker.domain.timeline import (
    Timeline,
    clamp_to_working_zone,
    frame_to_time,
    step_frame,
)


class VideoSession:
    """Own one reader and coordinate current frame with a domain Timeline."""

    def __init__(self, reader: VideoReader) -> None:
        self._reader = reader
        self._path: Path | None = None
        self._info: VideoStreamInfo | None = None
        self._timeline: Timeline | None = None
        self._current_frame: DecodedFrame | None = None

    @property
    def is_open(self) -> bool:
        return self._current_frame is not None

    @property
    def path(self) -> Path:
        if self._path is None:
            raise VideoError("no video is open")
        return self._path

    @property
    def info(self) -> VideoStreamInfo:
        if self._info is None:
            raise VideoError("no video is open")
        return self._info

    @property
    def timeline(self) -> Timeline:
        if self._timeline is None:
            raise VideoError("no video is open")
        return self._timeline

    @property
    def current_frame(self) -> DecodedFrame:
        if self._current_frame is None:
            raise VideoError("no video is open")
        return self._current_frame

    @property
    def current_time_s(self) -> float:
        return frame_to_time(self.current_frame.frame_index, self.timeline)

    def open(self, path: Path) -> DecodedFrame:
        """Open a video and decode frame 0 as one all-or-closed operation."""

        self.close()
        try:
            info = self._reader.open(path)
            timeline = Timeline(
                video_id=uuid4(),
                fps_nominal=info.fps_container,
                working_zone=(0, info.frame_count - 1),
            )
            frame = self._read_frame(0)
        except Exception:
            self._reader.close()
            raise
        self._path = path
        self._info = info
        self._timeline = timeline
        self._current_frame = frame
        return frame

    def go_to_frame(self, frame_index: int) -> DecodedFrame:
        """Clamp to the working zone, decode, then commit the new current frame."""

        target = clamp_to_working_zone(frame_index, self.timeline)
        frame = self._read_frame(target)
        self._current_frame = frame
        return frame

    def step(self, delta: int) -> DecodedFrame:
        """Move by an integer frame delta and clamp to the working zone."""

        target = step_frame(self.current_frame.frame_index, delta, self.timeline)
        return self.go_to_frame(target)

    def close(self) -> None:
        """Release the reader and clear all session state."""

        self._reader.close()
        self._path = None
        self._info = None
        self._timeline = None
        self._current_frame = None

    def _read_frame(self, frame_index: int) -> DecodedFrame:
        frame = self._reader.read_frame(frame_index)
        if frame.frame_index != frame_index:
            raise VideoFrameError(
                f"reader returned frame {frame.frame_index} for requested frame {frame_index}"
            )
        return frame
