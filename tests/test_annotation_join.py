"""P1.2-S2:同帧四 role join 与 canonical label digest 的纯函数测试。

负例优先(契约 §3):AI 补点、superseded、partial、duplicate、non-finite
一律不计入 complete;digest 对标签语义敏感、对显示属性不敏感。
"""

from dataclasses import replace
from uuid import uuid4

import pytest

from ai_physics_tracker.application.annotation_join import (
    canonical_label_digest,
    join_complete_frames,
)
from ai_physics_tracker.domain.pendulum import (
    PendulumRoles,
    create_pendulum_experiment,
)
from ai_physics_tracker.domain.project import (
    PUBLICATION_REQUIRED_CAPABILITIES,
    Project,
    register_video_reference,
)
from ai_physics_tracker.domain.track import TrackPoint
from ai_physics_tracker.domain.types import utc_now
from test_pendulum_experiment import _timeline, _track, _video


def _make_point(
    track_id,
    frame_index,
    x=10.0,
    y=20.0,
    *,
    source="manual",
    status="active",
    superseded_by=None,
):
    now = utc_now()
    return TrackPoint(
        point_id=uuid4(),
        track_id=track_id,
        frame_index=frame_index,
        time_s=frame_index / 30.0,
        pixel_x=x,
        pixel_y=y,
        source=source,
        source_detail=None if source == "manual" else "dlc:infer:x",
        confidence=None if source == "manual" else 0.9,
        visibility="visible",
        status=status,
        superseded_by=superseded_by,
        created_at=now,
        modified_at=now,
    )


def _all_four(roles, frame_index):
    """frame_index 上的四个 active manual(每 role 一个,坐标随 role 偏移)。"""

    return [
        _make_point(track_id, frame_index, 10.0 + index, 20.0 + index)
        for index, track_id in enumerate(roles.track_ids())
    ]


def _build(extra_observations=()):
    """两段式构造:先建 roles,再由调用方造观测,最后落 Project。"""

    video = _video(frame_count=200)
    tracks = tuple(
        _track(video, name) for name in ("tip", "body top", "body bottom", "pivot")
    )
    roles = PendulumRoles(
        tip=tracks[0].track_id,
        body_top=tracks[1].track_id,
        body_bottom=tracks[2].track_id,
        pivot=tracks[3].track_id,
    )
    experiment = create_pendulum_experiment(uuid4(), video.video_id, roles)

    def project_with(observations):
        return (
            Project(
                project_id=uuid4(),
                name="join",
                created_at=utc_now(),
                modified_at=utc_now(),
                videos=(video,),
                timelines=(_timeline(video),),
                tracks=tracks,
                observations=tuple(observations),
                required_capabilities=PUBLICATION_REQUIRED_CAPABILITIES,
                experiments=(experiment,),
            ),
            experiment,
            roles,
        )

    return project_with, roles


class TestJoinCompleteness:
    def test_four_active_manuals_make_frame_complete_in_role_order(self):
        build, roles = _build()
        project, experiment, _ = build(_all_four(roles, 5))
        result = join_complete_frames(project, experiment)
        assert [label.frame_index for label in result.complete] == [5]
        label = result.complete[0]
        assert [point.track_id for point in label.points] == list(roles.track_ids())
        assert label.coordinates == (
            (10.0, 20.0), (11.0, 21.0), (12.0, 22.0), (13.0, 23.0)
        )
        assert not result.partial
        assert not result.ai_only_frames

    def test_frames_sorted_ascending_regardless_of_mark_order(self):
        build, roles = _build()
        project, experiment, _ = build(
            _all_four(roles, 30) + _all_four(roles, 4) + _all_four(roles, 17)
        )
        result = join_complete_frames(project, experiment)
        assert result.complete_frame_indices == (4, 17, 30)

    @pytest.mark.parametrize("missing_role_index", range(4))
    def test_three_of_four_is_partial_never_complete(self, missing_role_index):
        build, roles = _build()
        points = _all_four(roles, 8)
        points.pop(missing_role_index)
        project, experiment, _ = build(points)
        result = join_complete_frames(project, experiment)
        assert not result.complete
        assert result.partial == ((8, 3),)

    def test_engine_point_never_substitutes_missing_manual(self):
        build, roles = _build()
        points = _all_four(roles, 8)
        points.pop(2)  # body_bottom 缺 manual
        points.append(_make_point(roles.body_bottom, 8, source="dlc"))
        project, experiment, _ = build(points)
        result = join_complete_frames(project, experiment)
        assert not result.complete
        assert result.partial == ((8, 3),)

    def test_extra_superseded_manual_does_not_break_complete(self):
        build, roles = _build()
        actives = _all_four(roles, 8)
        shadowed = _make_point(
            roles.tip, 8, x=99.0, status="superseded",
            superseded_by=actives[0].point_id,
        )
        project, experiment, _ = build(actives + [shadowed])
        result = join_complete_frames(project, experiment)
        assert result.complete_frame_indices == (8,)
        assert not result.superseded_frames

    def test_partial_frame_with_one_manual_counts_role(self):
        build, roles = _build()
        project, experiment, _ = build([_make_point(roles.tip, 8)])
        result = join_complete_frames(project, experiment)
        assert not result.complete
        assert result.partial == ((8, 1),)

    def test_engine_only_frame_reported_as_ai_only(self):
        build, roles = _build()
        project, experiment, _ = build(
            [_make_point(track_id, 3, source="dlc") for track_id in roles.track_ids()]
        )
        result = join_complete_frames(project, experiment)
        assert not result.complete
        assert result.ai_only_frames == (3,)

    def test_nonfinite_active_coordinate_disqualifies_frame(self):
        build, roles = _build()
        points = _all_four(roles, 8)
        # TrackPoint 构造期拒绝 NaN;non-finite 只可能来自外部改写 manifest,
        # join 是最后一道防线——绕过构造校验模拟被改写的数据
        corrupted = replace(points[1], pixel_x=0.0)
        object.__setattr__(corrupted, "pixel_x", float("nan"))
        points[1] = corrupted
        project, experiment, _ = build(points)
        result = join_complete_frames(project, experiment)
        assert not result.complete
        assert result.nonfinite_frames == (8,)

    def test_duplicate_active_manual_same_role_frame_rejected(self):
        build, roles = _build()
        points = _all_four(roles, 8)
        points.append(_make_point(roles.tip, 8, x=99.0))
        project, experiment, _ = build(points)
        # add_manual_point 的 last-wins 在域层已防重;此处防御外部改写
        with pytest.raises(ValueError, match="duplicate active manual"):
            join_complete_frames(project, experiment)

    def test_unbound_track_points_ignored(self):
        build, roles = _build()
        project, experiment, _ = build(_all_four(roles, 8))
        free_video = _video(frame_count=200, suffix="-b")
        project = register_video_reference(project, free_video, _timeline(free_video))
        free = _track(free_video, "free")
        project = replace(
            project,
            tracks=(*project.tracks, free),
            observations=(*project.observations, _make_point(free.track_id, 8)),
        )
        result = join_complete_frames(project, experiment)
        assert result.complete_frame_indices == (8,)


class TestCanonicalLabelDigest:
    def test_digest_changes_with_any_label_mutation(self):
        build, roles = _build()
        base_project, base_experiment, _ = build(_all_four(roles, 5))
        base = canonical_label_digest(
            join_complete_frames(base_project, base_experiment)
        )

        moved = _all_four(roles, 5)
        moved[0] = replace(moved[0], pixel_x=10.5)
        moved_project, moved_experiment, _ = build(moved)
        assert (
            canonical_label_digest(join_complete_frames(moved_project, moved_experiment))
            != base
        )

        reidentified = _all_four(roles, 5)
        reidentified[2] = replace(reidentified[2], point_id=uuid4())
        reid_project, reid_experiment, _ = build(reidentified)
        assert (
            canonical_label_digest(join_complete_frames(reid_project, reid_experiment))
            != base
        )

        added_project, added_experiment, _ = build(
            _all_four(roles, 5) + _all_four(roles, 6)
        )
        assert (
            canonical_label_digest(join_complete_frames(added_project, added_experiment))
            != base
        )

    def test_digest_stable_across_display_attribute_changes(self):
        build, roles = _build()
        base_project, base_experiment, _ = build(_all_four(roles, 5))
        base = canonical_label_digest(
            join_complete_frames(base_project, base_experiment)
        )
        renamed = replace(
            base_project,
            tracks=tuple(
                replace(track, name=f"display {index}", color="#abcdef")
                for index, track in enumerate(base_project.tracks)
            ),
        )
        assert (
            canonical_label_digest(join_complete_frames(renamed, base_experiment))
            == base
        )

    def test_role_rename_does_not_change_digest(self):
        """交换 Track 显示名不交换语义:digest 按 role UUID 对齐。"""

        build, roles = _build()
        base_project, base_experiment, _ = build(_all_four(roles, 5))
        base = canonical_label_digest(
            join_complete_frames(base_project, base_experiment)
        )
        swapped = (
            replace(base_project.tracks[0], name=base_project.tracks[1].name),
            replace(base_project.tracks[1], name=base_project.tracks[0].name),
            *base_project.tracks[2:],
        )
        assert canonical_label_digest(
            join_complete_frames(replace(base_project, tracks=swapped), base_experiment)
        ) == base


class TestIdentityReviewAdditions:
    """identity review ID5:补三类行为回归。"""

    def test_role_rebind_changes_digest(self):
        """重绑(swap 两 role 的 track)→ 同坐标点集 digest 变(role 身份变)。"""

        build, roles = _build()
        base_project, base_experiment, _ = build(_all_four(roles, 5))
        base = canonical_label_digest(
            join_complete_frames(base_project, base_experiment)
        )
        # role 互换:tip↔body_top 的 track 对调(重绑是一等域操作)
        swapped_roles = PendulumRoles(
            tip=roles.body_top,
            body_top=roles.tip,
            body_bottom=roles.body_bottom,
            pivot=roles.pivot,
        )
        rebound = replace(
            base_experiment, roles=swapped_roles
        )
        # 重绑后,同一物理点集的 role 归属变化必须体现为 digest 变化
        assert (
            canonical_label_digest(join_complete_frames(base_project, rebound))
            != base
        )

    def test_partial_count_ignores_shadowed_superseded_residual(self):
        """superseded 残留不影响 partial 计数(last-wins 语义的一致性)。"""

        build, roles = _build()
        actives = _all_four(roles, 8)
        actives.pop(1)  # body_top 缺 → 3/4
        shadowed = _make_point(
            roles.tip, 8, x=99.0, status="superseded",
            superseded_by=actives[0].point_id,
        )
        project, experiment, _ = build(actives + [shadowed])
        result = join_complete_frames(project, experiment)
        assert result.partial == ((8, 3),)
        assert not result.complete
