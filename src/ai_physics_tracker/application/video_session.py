"""与 Qt 无关的单视频浏览会话与 Timeline 导航。"""

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
    """持有一个读取器，并用领域 Timeline 协调当前帧。"""

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

    def open(
        self, path: Path, timeline: Timeline | None = None, frame_index: int = 0
    ) -> DecodedFrame:
        """打开视频并解码第 0 帧，要么全部成功、要么保持关闭状态。"""

        self.close()
        try:
            info = self._reader.open(path)
            timeline = timeline or Timeline(
                video_id=uuid4(),
                fps_nominal=info.fps_container,
                working_zone=(0, info.frame_count - 1),
            )
            if timeline.working_zone[1] >= info.frame_count:
                raise VideoError("saved working zone exceeds the video frame count")
            frame = self._read_frame(clamp_to_working_zone(frame_index, timeline))
        except Exception:
            self._reader.close()
            raise
        self._path = path
        self._info = info
        self._timeline = timeline
        self._current_frame = frame
        return frame

    def go_to_frame(self, frame_index: int) -> DecodedFrame:
        """先钳位到 working_zone，解码成功后再提交新当前帧。"""

        target = clamp_to_working_zone(frame_index, self.timeline)
        frame = self._read_frame(target)
        self._current_frame = frame
        return frame

    def step(self, delta: int) -> DecodedFrame:
        """按整数帧差步进并钳位到 working_zone。"""

        target = step_frame(self.current_frame.frame_index, delta, self.timeline)
        return self.go_to_frame(target)

    def close(self) -> None:
        """释放读取器并清空全部会话状态。"""

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
