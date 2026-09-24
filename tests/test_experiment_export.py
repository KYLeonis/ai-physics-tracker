"""P1.2-S5:四 bodypart 导出计划与 DLC 行结构的测试。

golden structure:行数=complete 帧、每行 8 坐标按规范 role 序、
fixed-check 帧进 test 行且 split 索引与导出行序一致、
计划在 fixed-check 缺失/失效时整体拒绝。
"""

from dataclasses import replace
from uuid import uuid4

import pytest

from ai_physics_tracker.application.annotation_join import canonical_label_digest
from ai_physics_tracker.application.experiment_export import (
    build_experiment_export_plan,
)
from ai_physics_tracker.application.project_session import ProjectSession
from ai_physics_tracker.infrastructure.project_repository import ProjectRepository
from test_annotation_join import _all_four, _build, _make_point


def _frozen_session(tmp_path, frames=(5, 9, 12)):
    """建 experiment、标齐 frames、冻结 frames[1:] 为 fixed-check。"""

    build, roles = _build()
    points = []
    for frame in frames:
        points.extend(_all_four(roles, frame))
    project, experiment, _ = build(points)
    session = ProjectSession(ProjectRepository(), project)
    session._verified_videos.add(project.videos[0].video_id)
    session.save_as(tmp_path / "proj")
    session.freeze_experiment_fixed_check(
        experiment.experiment_id, tuple(frames[1:])
    )
    return session, session.pendulum_experiments()[0], roles


class TestExportPlan:
    def test_plan_splits_train_and_fixed_check_rows(self, tmp_path):
        session, experiment, _ = _frozen_session(tmp_path)
        plan = build_experiment_export_plan(session.project, experiment)
        assert [row.frame_index for row in plan.train_rows] == [5]
        assert [row.frame_index for row in plan.test_rows] == [9, 12]
        assert plan.total_rows == 3
        # 每行恰四组坐标,按规范 role 序(坐标随 role 偏移)
        row = plan.train_rows[0]
        assert row.coordinates == (
            (10.0, 20.0), (11.0, 21.0), (12.0, 22.0), (13.0, 23.0)
        )

    def test_split_indices_align_with_merged_frame_order(self, tmp_path):
        session, experiment, _ = _frozen_session(tmp_path, frames=(5, 9, 12))
        plan = build_experiment_export_plan(session.project, experiment)
        train_idx, test_idx = plan.split_indices()
        # 合并帧序 5,9,12 → 行号 0,1,2;9/12 是 test
        assert train_idx == (0,)
        assert test_idx == (1, 2)

    def test_plan_rejected_without_frozen_check(self, tmp_path):
        session, experiment, _ = _frozen_session(tmp_path)
        session.clear_experiment_fixed_check(experiment.experiment_id)
        # 用 session 当前状态(固定检查已清空),不是旧快照
        with pytest.raises(ValueError, match="fixed check is not valid"):
            build_experiment_export_plan(
                session.project, session.pendulum_experiments()[0]
            )

    def test_plan_rejected_when_labels_drift(self, tmp_path):
        session, experiment, roles = _frozen_session(tmp_path)
        session.mark_point(roles.tip, 9, 55.0, 66.0)  # 检查帧上的点被改
        with pytest.raises(ValueError, match="not valid"):
            build_experiment_export_plan(
                session.project, session.pendulum_experiments()[0]
            )

    def test_partial_frames_never_enter_plan(self, tmp_path):
        session, experiment, roles = _frozen_session(tmp_path)
        # 标一个 3/4 帧:join 为 partial,不应出现在任何行
        partial_points = [_make_point(roles.tip, 30)]
        from ai_physics_tracker.domain.project import Project

        project = replace(
            session.project,
            observations=(*session.project.observations, *partial_points),
        )
        plan = build_experiment_export_plan(project, experiment)
        assert all(row.frame_index != 30 for row in (*plan.train_rows, *plan.test_rows))
