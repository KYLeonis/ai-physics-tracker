"""应用层：分析源的可操作事实，供入口说明、按钮与实际准备共同使用。"""

from dataclasses import dataclass
from uuid import UUID

from ai_physics_tracker.application.angular_job import AngularJob
from ai_physics_tracker.application.kinematics_job import KinematicsJob
from ai_physics_tracker.application.project_session import ProjectSession, ProjectSessionError
from ai_physics_tracker.application.signal_analysis_job import SignalSelection, prepare_signal_source
from ai_physics_tracker.application.source_recipe import SmoothingParameters
from ai_physics_tracker.domain.angular import AngularReference


@dataclass(frozen=True)
class SignalSourceState:
    """基础可操作性、源问题与可执行准备分别保留，不合并为一个valid标记。"""

    availability_issue: str | None = None
    source_issue: str | None = None
    preparation: KinematicsJob | AngularJob | None = None

    @property
    def ready(self) -> bool:
        return not self.reason

    @property
    def reason(self) -> str:
        if self.availability_issue or self.source_issue:
            return self.availability_issue or self.source_issue
        return ("Source data need updating — Preview prepares them; retry Preview if cancelled."
                if self.preparation is not None else "")


def assess_signal_source(
    session: ProjectSession | None, video_id: UUID | None, selection: SignalSelection | None,
    parameters: SmoothingParameters | None, reference: AngularReference | None = None,
) -> SignalSourceState:
    """只采集准备事实，不执行计算、发布结果或修改工程；准备仍沿用原资格规则。"""
    if session is None or video_id is None:
        return SignalSourceState(availability_issue="Open a project and select a video.")
    if selection is None:
        return SignalSourceState(availability_issue="Add or select a track.")
    if not session.can_measure(video_id):
        return SignalSourceState(availability_issue="Timing detection is incomplete or unavailable; see the video timing status.")
    track = next((item for item in session.tracks if item.track_id == selection.track_id), None)
    if track is None or track.video_id != video_id:
        return SignalSourceState(availability_issue="Select an existing track in the current video.")
    try:
        return SignalSourceState(preparation=prepare_signal_source(session, selection, parameters, reference))
    except (ValueError, ProjectSessionError) as error:
        return SignalSourceState(source_issue=str(error))
