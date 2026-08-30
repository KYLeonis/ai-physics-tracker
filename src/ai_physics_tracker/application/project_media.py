"""项目候选加载：后台验证成功前不改写活动会话。"""

from concurrent.futures import CancelledError, TimeoutError, Future
from dataclasses import dataclass, replace
import hashlib
from math import isclose
from pathlib import Path
from threading import Event
from time import monotonic
from typing import Callable
from uuid import UUID

from ai_physics_tracker.application.playback import AsyncVideoSession, PlaybackSnapshot
from ai_physics_tracker.application.project_session import ProjectRepositoryPort, ProjectSession, ProjectSessionError
from ai_physics_tracker.application.video_timing import TimingReport, VideoTimingProbe
from ai_physics_tracker.domain.video import Video
from ai_physics_tracker.domain.types import JsonObject


@dataclass
class PreparedProject:
    """由后台准备、由 GUI 单次接管的候选资源；未接管时必须 close。"""

    session: ProjectSession
    video_id: UUID | None
    decoder: AsyncVideoSession | None
    snapshot: PlaybackSnapshot | None
    timing: TimingReport
    warning: str = ""

    def close(self) -> None:
        if self.decoder is not None:
            self.decoder.close()


def workflow_state(session: ProjectSession) -> JsonObject:
    """只解释自己的版本化命名空间，不消费未知版本。"""

    state = session.project.ui_state.get("workflow", {})
    if not isinstance(state, dict) or state.get("version", 1) != 1:
        return {}
    return state


class ProjectMediaService:
    """加载/重连的纯应用编排；decoder 与 probe 都通过端口注入。"""

    def __init__(self, repository: ProjectRepositoryPort,
                 decoder_factory: Callable[[], AsyncVideoSession], probe: VideoTimingProbe) -> None:
        self.repository = repository
        self.decoder_factory = decoder_factory
        self.probe = probe

    def open_video(self, path: Path, cancel: Event) -> PreparedProject:
        path = path.resolve()
        fingerprint = path.stat() if path.is_file() else None
        session = ProjectSession.start(self.repository, path.stem)
        decoder = self.decoder_factory()
        try:
            snapshot = self._wait_open(decoder.open(path), cancel)
            report = self._probe(path, snapshot, cancel)
            if report.status == "cfr":
                digest = self._hash(path, cancel)
                video, timeline = session.register_external_video(
                    path, replace(snapshot.info, timing_status="cfr"), sha256=digest
                )
            else:
                video, timeline = session.register_preview_video(
                    path, replace(snapshot.info, timing_status=report.status))
            video_id = video.video_id
            snapshot = self._wait_open(decoder.open(path, timeline), cancel)
            self._verify_unchanged(path, fingerprint)
            return PreparedProject(session, video_id, decoder, snapshot, report)
        except Exception:
            decoder.close()
            raise

    def open_project(self, root: Path, cancel: Event) -> PreparedProject:
        session = ProjectSession.load(self.repository, root)
        state = workflow_state(session)
        video = next((item for item in session.project.videos
                      if str(item.video_id) == state.get("video_id")), None)
        if video is None:
            video = next(iter(session.project.videos), None)
        return self.select_video(session, video.video_id if video else None, cancel)

    def select_video(self, session: ProjectSession, video_id: UUID | None,
                     cancel: Event) -> PreparedProject:
        if cancel.is_set():
            raise CancelledError()
        if video_id is None:
            return PreparedProject(session, None, None, None, TimingReport("unknown", "No video selected"))
        video = next(item for item in session.project.videos if item.video_id == video_id)
        path = session.video_path(video)
        if path is None:
            return PreparedProject(session, video_id, None, None,
                                   TimingReport("unknown", "Video is missing; use Relink Video"))
        timeline = next(item for item in session.project.timelines if item.video_id == video_id)
        fingerprint = path.stat()
        state = workflow_state(session)
        frame_index = state.get("frame_index", 0) if state.get("video_id") == str(video_id) else 0
        if isinstance(frame_index, bool) or not isinstance(frame_index, int):
            frame_index = 0
        decoder = self.decoder_factory()
        try:
            snapshot = self._wait_open(decoder.open(path, timeline, frame_index), cancel)
            self._validate_media(video, path, snapshot, cancel)
            report = self._probe(path, snapshot, cancel)
            self._verify_unchanged(path, fingerprint)
            session.confirm_video_timing(video_id, report)
            return PreparedProject(session, video_id, decoder, snapshot, report)
        except Exception:
            decoder.close()
            raise

    def relink(self, session: ProjectSession, video_id: UUID, path: Path,
               cancel: Event) -> PreparedProject:
        candidate = session.detached()
        candidate.relink(video_id, path)
        prepared = self.select_video(candidate, video_id, cancel)
        video = next(item for item in candidate.project.videos if item.video_id == video_id)
        if prepared.snapshot is None:
            raise ProjectSessionError("relinked video was not found")
        if video.sha256 is None:
            prepared.warning = "No saved file hash: matching metadata does not prove video identity. Confirm this is the original video."
        return prepared

    def _probe(self, path: Path, snapshot: PlaybackSnapshot, cancel: Event) -> TimingReport:
        report = self.probe.probe(path, cancel)
        if cancel.is_set():
            raise CancelledError()
        if report.status == "cfr" and (
            report.frame_count != snapshot.info.frame_count
            or report.fps_measured is None
            or not isclose(report.fps_measured, snapshot.info.fps_container,
                           rel_tol=1e-3, abs_tol=1e-6)
        ):
            return TimingReport("unknown", "FFprobe and decoder timing/count disagree")
        return report

    @staticmethod
    def _wait_open(future: Future[PlaybackSnapshot], cancel: Event) -> PlaybackSnapshot:
        deadline = monotonic() + 30.0
        while not cancel.is_set():
            try:
                return future.result(timeout=0.05)
            except TimeoutError:
                if monotonic() >= deadline:
                    raise ProjectSessionError("video preparation timed out")
        raise CancelledError()

    @staticmethod
    def _validate_media(video: Video, path: Path, snapshot: PlaybackSnapshot, cancel: Event) -> None:
        info = snapshot.info
        if ((info.width_px, info.height_px, info.frame_count) !=
                (video.width_px, video.height_px, video.frame_count)
                or not isclose(info.fps_container, video.fps_container, rel_tol=1e-4, abs_tol=1e-6)):
            raise ProjectSessionError("video metadata differs from the saved project; observations were not changed")
        if video.sha256 is not None and ProjectMediaService._hash(path, cancel) != video.sha256:
            raise ProjectSessionError("video SHA-256 differs from the saved project")

    @staticmethod
    def _hash(path: Path, cancel: Event) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            while block := stream.read(1024 * 1024):
                if cancel.is_set():
                    raise CancelledError()
                digest.update(block)
        return digest.hexdigest()

    @staticmethod
    def _verify_unchanged(path: Path, before) -> None:
        if before is None:
            return
        after = path.stat()
        if (before.st_size, before.st_mtime_ns, before.st_ino) != (after.st_size, after.st_mtime_ns, after.st_ino):
            raise ProjectSessionError("video changed during preparation; reopen and validate it again")
