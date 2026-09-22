"""同帧四 role 引导标注的应用层测试（P1.2-S3，Qt-free）。

覆盖：
- experiment_annotation.annotation_guide_state：pending/done 排序、
  current_role、progress、hint 文案、frame_set 的 next/in 标志
- experiment_annotation.frame_set_worklist：有/无 frame_set
- tracking_job.prepare_experiment_frame_selection：四 role manual 帧并集
  去重、experiment_id 透传、unknown experiment 报错；并与单轨版
  prepare_frame_selection_request 对照（排除集只算给定 track）。

GUI 链路见 tests/gui/test_experiment_annotation_ui.py。
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from ai_physics_tracker.application.experiment_annotation import (
    annotation_guide_state,
    frame_set_worklist,
)
from ai_physics_tracker.application.project_session import (
    ProjectSession,
    ProjectSessionError,
)
from ai_physics_tracker.application.tracking_job import (
    prepare_experiment_frame_selection,
    prepare_frame_selection_request,
)
from ai_physics_tracker.application.video import VideoStreamInfo
from ai_physics_tracker.domain.pendulum import (
    ROLE_ORDER,
    ExperimentFrameSet,
    PendulumRoles,
    create_pendulum_experiment,
)
from ai_physics_tracker.domain.project import Project, create_project
from ai_physics_tracker.domain.timeline import Timeline
from ai_physics_tracker.domain.track import Track, TrackPoint
from ai_physics_tracker.domain.types import utc_now
from ai_physics_tracker.domain.video import Video
from ai_physics_tracker.infrastructure.project_repository import ProjectRepository


# ---------------------------------------------------------------------------
# 辅助工厂（内存 Project，不落盘、不依赖 Qt）
# ---------------------------------------------------------------------------

def _video(frame_count: int = 20) -> Video:
    return Video(
        video_id=uuid4(),
        file_path=None,
        original_path=f"/tmp/guide-{uuid4().hex[:6]}.mp4",
        display_name="guide.mp4",
        width_px=320,
        height_px=240,
        fps_container=30.0,
        frame_count=frame_count,
    )


def _timeline(video: Video) -> Timeline:
    return Timeline(
        video_id=video.video_id,
        fps_nominal=30.0,
        frame_indexing="zero-based",
        working_zone=(0, video.frame_count - 1),
    )


def _track(video: Video, name: str) -> Track:
    return Track(
        track_id=uuid4(),
        video_id=video.video_id,
        name=name,
        color="#123456",
        created_at=utc_now(),
    )


def _manual_point(
    track_id: UUID, frame_index: int, *, status: str = "active"
) -> TrackPoint:
    now = utc_now()
    return TrackPoint(
        point_id=uuid4(),
        track_id=track_id,
        frame_index=frame_index,
        time_s=frame_index / 30.0,
        pixel_x=11.0,
        pixel_y=21.0,
        source="manual",
        visibility="visible",
        status=status,
        created_at=now,
        modified_at=now,
    )


def _roles_and_tracks(
    video: Video,
) -> tuple[PendulumRoles, dict[str, Track], Track]:
    """四 role track（键为 role 名）+ 一个未绑定的 free track。"""

    display = {
        "tip": "tip",
        "body_top": "body top",
        "body_bottom": "body bottom",
        "pivot": "pivot",
    }
    tracks = {role: _track(video, display[role]) for role in ROLE_ORDER}
    roles = PendulumRoles(
        tip=tracks["tip"].track_id,
        body_top=tracks["body_top"].track_id,
        body_bottom=tracks["body_bottom"].track_id,
        pivot=tracks["pivot"].track_id,
    )
    return roles, tracks, _track(video, "free track")


def _experiment_project(
    marks: dict[str, tuple[int, ...]] | None = None,
    *,
    frame_set: tuple[int, ...] | None = None,
    extra_observations: tuple[TrackPoint, ...] = (),
    with_free_track: bool = False,
) -> tuple[Project, PendulumExperiment, dict[str, Track]]:
    """构造带四 role experiment 的内存项目；marks 按 role 给帧号。"""

    video = _video()
    roles, tracks, free = _roles_and_tracks(video)
    experiment = create_pendulum_experiment(uuid4(), video.video_id, roles)
    if frame_set is not None:
        experiment = replace(
            experiment,
            frame_set=ExperimentFrameSet(
                frames=frame_set, algorithm="kmeans", created_at=utc_now()
            ),
        )
    observations = tuple(
        _manual_point(tracks[role].track_id, frame)
        for role, frames in (marks or {}).items()
        for frame in frames
    ) + extra_observations
    project_tracks: tuple[Track, ...] = tuple(tracks.values())
    if with_free_track:
        project_tracks = (*project_tracks, free)
    project = Project(
        project_id=uuid4(),
        name="guide fixture",
        created_at=utc_now(),
        modified_at=utc_now(),
        videos=(video,),
        timelines=(_timeline(video),),
        tracks=project_tracks,
        observations=observations,
        experiments=(experiment,),
    )
    return project, experiment, tracks


# ---------------------------------------------------------------------------
# annotation_guide_state
# ---------------------------------------------------------------------------


class TestAnnotationGuideState:
    def test_empty_frame_lists_all_roles_pending(self) -> None:
        project, experiment, _tracks = _experiment_project()

        state = annotation_guide_state(project, experiment, 0)

        assert state.frame_index == 0
        assert state.pending_roles == ROLE_ORDER
        assert state.done_roles == ()
        assert state.current_role == "tip"
        assert state.progress_label == "0/4 landmark roles marked"
        assert state.frame_complete is False
        assert state.frame_in_frame_set is False
        assert state.next_frame_set_index is None
        assert "click the tip" in state.hint()

    def test_partial_frame_orders_done_and_pending_by_role_order(self) -> None:
        # ROLE_ORDER = (tip, body_top, body_bottom, pivot)；故意乱序给 marks
        project, experiment, _tracks = _experiment_project(
            {"body_top": (4,), "tip": (4,)}
        )

        state = annotation_guide_state(project, experiment, 4)

        assert state.done_roles == ("body_top", "tip")
        assert state.pending_roles == ("body_bottom", "pivot")
        assert state.current_role == "body_bottom"
        assert state.progress_label == "2/4 landmark roles marked"
        assert state.frame_complete is False
        hint = state.hint()
        assert "click the body_bottom" in hint
        assert "(2/4 done; remaining: body_bottom → pivot)" in hint

    def test_complete_frame_reports_completion_and_next_frame(self) -> None:
        full = {role: (2, 4) for role in ROLE_ORDER}
        project, experiment, _tracks = _experiment_project(
            full, frame_set=(2, 7, 11)
        )

        in_set = annotation_guide_state(project, experiment, 2)
        assert in_set.frame_complete is True
        assert in_set.frame_in_frame_set is True
        assert in_set.done_roles == ROLE_ORDER
        assert in_set.pending_roles == ()
        assert in_set.current_role is None
        assert in_set.next_frame_set_index == 7
        assert "complete (4/4)" in in_set.hint()
        assert "Continue to frame 7." in in_set.hint()

        out_of_set = annotation_guide_state(project, experiment, 4)
        assert out_of_set.frame_complete is True
        assert out_of_set.frame_in_frame_set is False
        assert out_of_set.next_frame_set_index == 7

    def test_complete_last_frame_hint_has_no_continue(self) -> None:
        project, experiment, _tracks = _experiment_project(
            {role: (11,) for role in ROLE_ORDER}, frame_set=(2, 7, 11)
        )

        state = annotation_guide_state(project, experiment, 11)

        assert state.frame_complete is True
        assert state.frame_in_frame_set is True
        assert state.next_frame_set_index is None
        assert state.hint() == "Frame 11 complete (4/4)."
        assert "Continue" not in state.hint()

    def test_next_frame_set_index_first_frame_after_current(self) -> None:
        project, experiment, _tracks = _experiment_project(frame_set=(2, 7, 11))

        assert annotation_guide_state(
            project, experiment, 0
        ).next_frame_set_index == 2
        assert annotation_guide_state(
            project, experiment, 2
        ).next_frame_set_index == 7
        assert annotation_guide_state(
            project, experiment, 7
        ).next_frame_set_index == 11
        assert annotation_guide_state(
            project, experiment, 11
        ).next_frame_set_index is None
        assert annotation_guide_state(
            project, experiment, 15
        ).next_frame_set_index is None

    def test_ignores_superseded_and_non_role_manual_points(self) -> None:
        video = _video()
        roles, tracks, free = _roles_and_tracks(video)
        experiment = create_pendulum_experiment(uuid4(), video.video_id, roles)
        project = Project(
            project_id=uuid4(),
            name="guide fixture",
            created_at=utc_now(),
            modified_at=utc_now(),
            videos=(video,),
            timelines=(_timeline(video),),
            tracks=(*tracks.values(), free),
            observations=(
                # superseded manual 不算已标（历史点不补位）
                _manual_point(tracks["tip"].track_id, 4, status="superseded"),
                # 未绑定 role 的 track 上的 manual 不算
                _manual_point(free.track_id, 4),
            ),
            experiments=(experiment,),
        )

        state = annotation_guide_state(project, experiment, 4)

        assert state.done_roles == ()
        assert state.pending_roles == ROLE_ORDER
        assert state.frame_complete is False

    def test_partial_hint_mentions_never_used_for_training(self) -> None:
        project, experiment, _tracks = _experiment_project({"pivot": (3,)})

        hint = annotation_guide_state(project, experiment, 3).hint()

        assert "click the tip" in hint  # current_role 仍是第一个待标
        assert "(1/4 done" in hint
        assert "never used for training" in hint


# ---------------------------------------------------------------------------
# frame_set_worklist
# ---------------------------------------------------------------------------


class TestFrameSetWorklist:
    def test_worklist_returns_frame_set_frames(self) -> None:
        _project, experiment, _tracks = _experiment_project(frame_set=(2, 7, 11))

        assert frame_set_worklist(experiment) == (2, 7, 11)

    def test_worklist_empty_without_frame_set(self) -> None:
        _project, experiment, _tracks = _experiment_project()

        assert frame_set_worklist(experiment) == ()


# ---------------------------------------------------------------------------
# prepare_experiment_frame_selection
# ---------------------------------------------------------------------------


def _publication_session(
    tmp_path: Path, synthetic_video_path: Path
) -> tuple[ProjectSession, object, object, dict[str, Track]]:
    """带合成视频与四 role experiment 的已保存 publication session。"""

    session = ProjectSession(ProjectRepository(), create_project("exp selection"))
    info = VideoStreamInfo(
        width_px=64,
        height_px=48,
        fps_container=10.0,
        frame_count=10,
        container_format="avi",
        timing_status="cfr",
    )
    video, _timeline_obj = session.register_external_video(synthetic_video_path, info)
    plain_tracks = {
        role: session.add_track(video.video_id, role) for role in ROLE_ORDER
    }
    roles = PendulumRoles(
        tip=plain_tracks["tip"].track_id,
        body_top=plain_tracks["body_top"].track_id,
        body_bottom=plain_tracks["body_bottom"].track_id,
        pivot=plain_tracks["pivot"].track_id,
    )
    saved = session.save_as_publication(tmp_path / "publication", roles)
    experiment = saved.experiments[0]
    return session, video, experiment, plain_tracks


class TestPrepareExperimentFrameSelection:
    def test_excluded_frames_are_union_of_four_roles(
        self, tmp_path: Path, synthetic_video_path: Path
    ) -> None:
        session, video, experiment, tracks = _publication_session(
            tmp_path, synthetic_video_path
        )
        # 四 role 各标 2 帧，其中帧 3 被 tip/body_top 重叠（一处重叠）
        marks = {
            "tip": (2, 3),
            "body_top": (3, 5),
            "body_bottom": (7, 9),
            "pivot": (1, 8),
        }
        for role, frames in marks.items():
            for frame in frames:
                session.mark_point(tracks[role].track_id, frame, 10.0, 20.0)

        job = prepare_experiment_frame_selection(
            session, experiment.experiment_id, n_frames=3,
            algorithm="uniform", seed=7,
        )

        sel = job.selection_request
        assert sel.experiment_id == experiment.experiment_id
        assert isinstance(sel.experiment_id, UUID)
        assert sel.video_id == video.video_id
        assert sel.track_id == experiment.roles.tip  # 兼容必填位
        assert sel.n_frames == 3
        assert sel.algorithm == "uniform"
        assert sel.seed == 7
        # 并集去重：8 次标注 → 7 个唯一帧
        assert sel.excluded_frames == frozenset({1, 2, 3, 5, 7, 8, 9})
        assert sel.frame_count == 10
        assert sel.zone_start == 0
        assert sel.zone_end == 9

    def test_unknown_experiment_raises(
        self, tmp_path: Path, synthetic_video_path: Path
    ) -> None:
        session, _video, _experiment, _tracks = _publication_session(
            tmp_path, synthetic_video_path
        )

        with pytest.raises(ProjectSessionError, match="unknown experiment_id"):
            prepare_experiment_frame_selection(session, uuid4(), n_frames=3)

    def test_experiment_union_contrasts_with_single_track_scope(
        self, tmp_path: Path, synthetic_video_path: Path
    ) -> None:
        """experiment 版排除集为四 role 并集；单轨版只算给定 track。"""

        # experiment 会话：tip 标 (2, 4)、body_top 标 (6, 8)，其余 role 未标
        session, _video, experiment, tracks = _publication_session(
            tmp_path, synthetic_video_path
        )
        for frame in (2, 4):
            session.mark_point(tracks["tip"].track_id, frame, 10.0, 20.0)
        for frame in (6, 8):
            session.mark_point(tracks["body_top"].track_id, frame, 10.0, 20.0)

        experiment_sel = prepare_experiment_frame_selection(
            session, experiment.experiment_id, n_frames=3, algorithm="uniform"
        ).selection_request
        assert experiment_sel.excluded_frames == frozenset({2, 4, 6, 8})

        # 对照：单轨会话，track A 标同样的 (2, 4)，另一 track 标 (6, 8)
        plain = ProjectSession(ProjectRepository(), create_project("plain"))
        info = VideoStreamInfo(
            width_px=64,
            height_px=48,
            fps_container=10.0,
            frame_count=10,
            container_format="avi",
            timing_status="cfr",
        )
        plain_video, _ = plain.register_external_video(synthetic_video_path, info)
        track_a = plain.add_track(plain_video.video_id, "A")
        track_b = plain.add_track(plain_video.video_id, "B")
        for frame in (2, 4):
            plain.mark_point(track_a.track_id, frame, 10.0, 20.0)
        for frame in (6, 8):
            plain.mark_point(track_b.track_id, frame, 10.0, 20.0)

        single_sel = prepare_frame_selection_request(
            plain, track_a.track_id, n_frames=3, algorithm="uniform"
        ).selection_request
        # 只排除 track A 自己的帧；track B 的帧不影响该 track 的建议集
        assert single_sel.excluded_frames == frozenset({2, 4})
