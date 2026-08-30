"""ProjectMediaService 候选媒体准备与项目恢复回归测试。

核心成功路径使用运行时生成的 ``synthetic_video_path``、OpenCV reader 和
FFprobe 时序探测；失败路径只在 ``tmp_path`` 中构造候选路径，不接触用户媒体。
"""

from concurrent.futures import CancelledError, Future
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
import shutil
from threading import Event
from typing import Callable
from uuid import uuid4

import numpy as np
import pytest

from ai_physics_tracker.application.playback import (
    AsyncVideoSession,
    PlaybackSnapshot,
)
from ai_physics_tracker.application.project_media import ProjectMediaService
from ai_physics_tracker.application.project_session import (
    ProjectSession,
    ProjectSessionError,
)
from ai_physics_tracker.application.video import (
    DecodedFrame,
    VideoReader,
    VideoStreamInfo,
)
from ai_physics_tracker.application.video_session import VideoSession
from ai_physics_tracker.application.video_timing import (
    TimingReport,
    VideoTimingProbe,
)
from ai_physics_tracker.domain.timeline import Timeline
from ai_physics_tracker.domain.video import Video
from ai_physics_tracker.infrastructure.ffprobe_timing import FFprobeTimingProbe
from ai_physics_tracker.infrastructure.project_repository import ProjectRepository
from ai_physics_tracker.infrastructure.opencv_video_reader import OpenCVVideoReader


class _StaticTimingProbe:
    """返回固定结论的探测器，用于隔离时序边界分支。"""

    def __init__(self, report: TimingReport) -> None:
        self.report = report
        self.paths: list[Path] = []

    def probe(self, path: Path, cancel: Event | None = None) -> TimingReport:
        self.paths.append(path)
        return self.report


class _DecoderFactory:
    """创建真实异步 reader，并保留句柄供测试验证关闭语义。"""

    def __init__(
        self, reader_factory: Callable[[], VideoReader] = OpenCVVideoReader
    ) -> None:
        self._reader_factory = reader_factory
        self.readers: list[VideoReader] = []
        self.decoders: list[AsyncVideoSession] = []

    def __call__(self) -> AsyncVideoSession:
        reader = self._reader_factory()
        decoder = AsyncVideoSession(
            VideoSession(reader),
            lambda _frame: None,
            lambda _error: None,
        )
        self.readers.append(reader)
        self.decoders.append(decoder)
        return decoder


class _ImmediateDecoder:
    """立即完成 Future 的解码替身，用于精确构造错误元数据。"""

    def __init__(self, info: VideoStreamInfo) -> None:
        self.info = info
        self.closed = False

    def open(
        self,
        path: Path,
        timeline: Timeline | None = None,
        frame_index: int = 0,
    ) -> Future[PlaybackSnapshot]:
        del path
        active_timeline = timeline or Timeline(
            uuid4(), self.info.fps_container, (0, self.info.frame_count - 1)
        )
        frame = DecodedFrame(
            frame_index,
            np.zeros(
                (self.info.height_px, self.info.width_px, 3), dtype=np.uint8
            ),
        )
        future: Future[PlaybackSnapshot] = Future()
        future.set_result(PlaybackSnapshot(self.info, active_timeline, frame))
        return future

    def close(self) -> None:
        self.closed = True


class _ImmediateDecoderFactory:
    """为元数据失败测试创建可观察的立即完成 decoder。"""

    def __init__(self, info: VideoStreamInfo) -> None:
        self.info = info
        self.instances: list[_ImmediateDecoder] = []

    def __call__(self) -> _ImmediateDecoder:
        decoder = _ImmediateDecoder(self.info)
        self.instances.append(decoder)
        return decoder


def _cfr_report() -> TimingReport:
    """返回与 conftest 中五帧、10 FPS 合成视频一致的 CFR 结论。"""

    return TimingReport("cfr", "static CFR test result", frame_count=5, fps_measured=10.0)


def test_deferred_preview_does_not_probe_or_mutate_session_during_validation(synthetic_video_path):
    probe = _StaticTimingProbe(_cfr_report())
    service = ProjectMediaService(ProjectRepository(), _DecoderFactory(), probe, defer_timing=True)
    prepared = service.open_video(synthetic_video_path, Event())
    try:
        assert prepared.snapshot.current_frame.frame_index == 0
        assert prepared.timing.status == "unknown"
        assert probe.paths == []
        before = prepared.session.project
        result = service.validate(prepared.validation, Event())
        assert result.timing.status == "cfr"
        assert result.sha256 is not None
        assert prepared.session.project == before
        assert prepared.session.project.videos[0].sha256 is None
    finally:
        prepared.close()


def test_background_validation_rejects_media_changed_after_preview(synthetic_video_path):
    service = ProjectMediaService(ProjectRepository(), _DecoderFactory(),
                                  _StaticTimingProbe(_cfr_report()), defer_timing=True)
    prepared = service.open_video(synthetic_video_path, Event())
    prepared.close()
    # 只改测试生成的视频，且先释放 reader，兼容 Windows 文件锁。
    with synthetic_video_path.open("ab") as stream:
        stream.write(b"changed")
    with pytest.raises(ProjectSessionError, match="changed during preparation"):
        service.validate(prepared.validation, Event())


def test_quantized_short_cfr_uses_verified_reference_rate_not_endpoint_estimate(tmp_path):
    path = tmp_path / "quantized.fake"
    path.touch()
    probe = _StaticTimingProbe(TimingReport("cfr", "quantized test", frame_count=2,
        fps_measured=1 / 0.042, fps_reference=24.0, max_grid_error_s=1 / 3000,
        max_interval_error_s=1 / 3000))
    factory = _ImmediateDecoderFactory(VideoStreamInfo(64, 48, 24.0, 2, "fake"))
    prepared = ProjectMediaService(ProjectRepository(), factory, probe).open_video(path, Event())
    try:
        assert prepared.timing.status == "cfr"
    finally:
        prepared.close()


def _probe_for_real_video(path: Path) -> VideoTimingProbe:
    """真实集成路径必须有 FFprobe，不能静默降级成替身。"""

    executable = shutil.which("ffprobe")
    if executable is not None:
        return FFprobeTimingProbe(executable=Path(executable))
    pytest.fail("FFprobe is required for the real project-media integration test")


def _cfr_info(path: Path) -> VideoStreamInfo:
    """读取真实媒体元数据，并把已由测试探测器确认的状态写入 fake info。"""

    reader = OpenCVVideoReader()
    try:
        info = reader.open(path)
    finally:
        reader.close()
    return replace(info, timing_status="cfr")


def _session_with_video(
    repository: ProjectRepository,
    path: Path,
    info: VideoStreamInfo,
    *,
    sha256: str | None = None,
) -> tuple[ProjectSession, Video]:
    """创建已确认 CFR 的项目会话；调用方负责保存。"""

    session = ProjectSession.start(repository, name="project media regression")
    video, _timeline = session.register_external_video(path, info, sha256=sha256)
    return session, video


def test_open_save_and_load_restores_identity_timeline_and_view_frame(
    tmp_path: Path, synthetic_video_path: Path
) -> None:
    repository = ProjectRepository()
    factory = _DecoderFactory()
    service = ProjectMediaService(
        repository, factory, _probe_for_real_video(synthetic_video_path)
    )

    prepared = service.open_video(synthetic_video_path, Event())
    try:
        assert prepared.video_id is not None
        video_id = prepared.video_id
        session = prepared.session
        timeline = session.project.timelines[0]
        session.update_view_state(
            {"version": 1, "video_id": str(video_id), "frame_index": 3}
        )
        root = tmp_path / "project"
        saved = session.save_as(root)
    finally:
        prepared.close()

    reopened = service.open_project(root, Event())
    try:
        assert reopened.snapshot is not None
        assert reopened.snapshot.current_frame.frame_index == 3
        assert reopened.session.project.project_id == saved.project_id
        assert reopened.session.project.videos[0].video_id == video_id
        restored_timeline = reopened.session.project.timelines[0]
        assert restored_timeline.video_id == video_id
        assert restored_timeline.fps_nominal == pytest.approx(
            timeline.fps_nominal, abs=1e-12
        )
        assert restored_timeline.working_zone == timeline.working_zone
        assert reopened.session.project.ui_state["workflow"]["frame_index"] == 3
        assert reopened.session.project.ui_state["workflow"]["video_id"] == str(
            video_id
        )
        assert not reopened.session.is_dirty
    finally:
        reopened.close()


def test_missing_video_keeps_project_and_points_with_no_snapshot(tmp_path: Path) -> None:
    repository = ProjectRepository()
    missing_path = tmp_path / "missing-video.mp4"
    session, video = _session_with_video(
        repository,
        missing_path,
        VideoStreamInfo(64, 48, 10.0, 5, "fake", "cfr"),
    )
    track = session.add_track(video.video_id)
    point = session.mark_point(track.track_id, 2, 12.0, 13.0)
    root = tmp_path / "project"
    saved = session.save_as(root)
    service = ProjectMediaService(
        repository,
        _DecoderFactory(),
        _StaticTimingProbe(TimingReport("unknown", "missing media")),
    )

    prepared = service.open_project(root, Event())
    try:
        assert prepared.video_id == video.video_id
        assert prepared.snapshot is None
        assert prepared.decoder is None
        assert prepared.timing.status == "unknown"
        assert "missing" in prepared.timing.reason.lower()
        assert prepared.session.project == saved
        assert prepared.session.project.observations == (point,)
        assert not prepared.session.is_dirty
    finally:
        prepared.close()


def test_relink_wrong_dimensions_keeps_original_session_unchanged(
    tmp_path: Path, synthetic_video_path: Path
) -> None:
    repository = ProjectRepository()
    session, video = _session_with_video(
        repository, synthetic_video_path, _cfr_info(synthetic_video_path)
    )
    track = session.add_track(video.video_id)
    point = session.mark_point(track.track_id, 1, 8.0, 9.0)
    root = tmp_path / "project"
    session.save_as(root)
    before_relink = deepcopy(session.project)
    wrong_path = tmp_path / "wrong-size.mp4"
    wrong_path.write_bytes(b"temporary candidate path")
    factory = _ImmediateDecoderFactory(
        VideoStreamInfo(32, 24, 10.0, 5, "fake", "cfr")
    )
    service = ProjectMediaService(
        repository, factory, _StaticTimingProbe(_cfr_report())
    )

    with pytest.raises(ProjectSessionError, match="metadata differs"):
        service.relink(session, video.video_id, wrong_path, Event())

    assert factory.instances[0].closed
    assert session.project == before_relink
    assert session.project_root == root.resolve()
    assert session.project.observations == (point,)
    assert not session.is_dirty


def test_relink_hash_mismatch_keeps_original_session_unchanged(
    tmp_path: Path, synthetic_video_path: Path
) -> None:
    repository = ProjectRepository()
    session, video = _session_with_video(
        repository,
        synthetic_video_path,
        _cfr_info(synthetic_video_path),
        sha256="0" * 64,
    )
    track = session.add_track(video.video_id)
    point = session.mark_point(track.track_id, 1, 18.0, 19.0)
    root = tmp_path / "project"
    session.save_as(root)
    before_relink = deepcopy(session.project)
    factory = _DecoderFactory()
    service = ProjectMediaService(
        repository, factory, _StaticTimingProbe(_cfr_report())
    )

    with pytest.raises(ProjectSessionError, match="SHA-256"):
        service.relink(session, video.video_id, synthetic_video_path, Event())

    assert factory.readers
    assert not factory.readers[0].is_open
    assert session.project == before_relink
    assert session.project_root == root.resolve()
    assert session.project.observations == (point,)
    assert not session.is_dirty


def test_successful_relink_preserves_raw_ids_and_marks_candidate_dirty(
    tmp_path: Path, synthetic_video_path: Path
) -> None:
    repository = ProjectRepository()
    factory = _DecoderFactory()
    service = ProjectMediaService(
        repository, factory, _probe_for_real_video(synthetic_video_path)
    )
    opened = service.open_video(synthetic_video_path, Event())
    try:
        assert opened.video_id is not None
        video_id = opened.video_id
        session = opened.session
        track = session.add_track(video_id)
        point = session.mark_point(track.track_id, 2, 22.0, 23.0)
        root = tmp_path / "project"
        session.save_as(root)
    finally:
        opened.close()

    before_relink = deepcopy(session.project)
    relocated_path = tmp_path / "relocated-video.mp4"
    shutil.copyfile(synthetic_video_path, relocated_path)
    prepared = service.relink(session, video_id, relocated_path, Event())
    try:
        candidate_video = prepared.session.project.videos[0]
        assert prepared.snapshot is not None
        assert prepared.timing.status == "cfr"
        assert prepared.session.project.project_id == before_relink.project_id
        assert candidate_video.video_id == video_id
        assert candidate_video.original_path == str(relocated_path.resolve())
        assert prepared.session.project.timelines == before_relink.timelines
        assert prepared.session.project.tracks == before_relink.tracks
        assert prepared.session.project.observations == (point,)
        assert prepared.session.project.observations == before_relink.observations
        assert prepared.session.is_dirty
    finally:
        prepared.close()

    assert session.project == before_relink
    assert session.project_root == root.resolve()
    assert not session.is_dirty


@pytest.mark.parametrize("timing_status", ["unknown", "vfr_suspected"])
def test_unknown_open_preserves_browsing_reference_without_measurement_permission(
    synthetic_video_path: Path, tmp_path: Path, timing_status: str,
) -> None:
    repository = ProjectRepository()
    factory = _DecoderFactory()
    probe = _StaticTimingProbe(TimingReport(timing_status, "browsing only"))
    service = ProjectMediaService(repository, factory, probe)

    prepared = service.open_video(synthetic_video_path, Event())
    try:
        assert prepared.video_id is not None
        assert prepared.timing.status == timing_status
        assert prepared.snapshot is not None
        assert prepared.snapshot.current_frame.frame_index == 0
        assert len(prepared.session.project.videos) == 1
        track = prepared.session.add_track(prepared.video_id)
        with pytest.raises(ProjectSessionError, match="not verified CFR"):
            prepared.session.mark_point(track.track_id, 1, 2.0, 3.0)
        root = tmp_path / "unknown-project"
        prepared.session.save_as(root)
        reopened = service.open_project(root, Event())
        try:
            assert reopened.video_id == prepared.video_id
            assert reopened.snapshot is not None
            assert reopened.timing.status == timing_status
        finally:
            reopened.close()
        assert len(prepared.session.project.timelines) == 1
        assert not prepared.session.is_dirty
        assert probe.paths == [synthetic_video_path.resolve(), synthetic_video_path.resolve()]
    finally:
        prepared.close()


def test_pre_cancelled_open_rejects_and_closes_reader(
    synthetic_video_path: Path,
) -> None:
    repository = ProjectRepository()
    factory = _DecoderFactory()
    service = ProjectMediaService(repository, factory, _StaticTimingProbe(_cfr_report()))
    cancel = Event()
    cancel.set()

    with pytest.raises(CancelledError):
        service.open_video(synthetic_video_path, cancel)

    assert len(factory.readers) == 1
    assert not factory.readers[0].is_open
    assert factory.decoders[0].snapshot() is None


def test_existing_project_with_unknown_timing_cannot_mark_point(
    tmp_path: Path, synthetic_video_path: Path
) -> None:
    repository = ProjectRepository()
    session, video = _session_with_video(
        repository, synthetic_video_path, _cfr_info(synthetic_video_path)
    )
    track = session.add_track(video.video_id)
    root = tmp_path / "project"
    session.save_as(root)
    service = ProjectMediaService(
        repository,
        _DecoderFactory(),
        _StaticTimingProbe(TimingReport("unknown", "timing not verified")),
    )

    prepared = service.open_project(root, Event())
    try:
        assert prepared.snapshot is not None
        assert prepared.timing.status == "unknown"
        with pytest.raises(ProjectSessionError, match="new measurements disabled"):
            prepared.session.mark_point(track.track_id, 0, 4.0, 5.0)
        assert prepared.session.project.observations == ()
    finally:
        prepared.close()
