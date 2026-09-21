"""Pendulum session 事务、legacy guard、stale 与 setup 动作测试(P1.1-S3/S4)。

覆盖契约 §2/§5/§6:四 role 一次提交、rebind 同事务清投影、bound Track 的
旧单轨 AI 写入口 fail closed、calibration 变化使科学结果 stale、
geometry/physical/release 动作 revision/stale/Undo 语义。
"""

from dataclasses import replace
from pathlib import Path
from uuid import uuid4

import pytest

from ai_physics_tracker.application.pendulum_setup import (
    experiment_dependency_digest,
    pendulum_setup_status,
)
from ai_physics_tracker.application.project_session import (
    ProjectSession,
    ProjectSessionError,
)
from ai_physics_tracker.domain.calibration import Calibration
from ai_physics_tracker.domain.pendulum import (
    PendulumRoles,
    PhysicalParameters,
    create_pendulum_experiment,
)
from ai_physics_tracker.domain.project import (
    PUBLICATION_REQUIRED_CAPABILITIES,
    Project,
)
from ai_physics_tracker.domain.scientific_result import ScientificResult
from ai_physics_tracker.domain.timeline import Timeline
from ai_physics_tracker.domain.track import Track, TrackPoint
from ai_physics_tracker.domain.tracking_run import TrackingRun
from ai_physics_tracker.domain.types import utc_now
from ai_physics_tracker.domain.video import Video
from ai_physics_tracker.infrastructure.project_repository import ProjectRepository
from test_pendulum_experiment import _timeline, _track, _video


def _engine_point(track_id, frame_index: int = 0) -> TrackPoint:
    now = utc_now()
    return TrackPoint(
        point_id=uuid4(),
        track_id=track_id,
        frame_index=frame_index,
        time_s=frame_index / 30.0,
        pixel_x=10.0,
        pixel_y=20.0,
        source="dlc",
        source_detail="dlc:infer:test",
        confidence=0.9,
        visibility="visible",
        status="active",
        created_at=now,
        modified_at=now,
    )


def _manual_point(track_id, frame_index: int = 0) -> TrackPoint:
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
        status="active",
        created_at=now,
        modified_at=now,
    )


def _bound_project_with_free_track(
    *, with_result: bool = False, with_active_run: bool = False
) -> tuple[Project, PendulumRoles, Track, TrackingRun | None]:
    """内存 v2 项目:四 bound track(部分带 AI/manual 点)+ 一个 free track。"""

    video = _video()
    bound = tuple(
        _track(video, name) for name in ("tip", "body top", "body bottom", "pivot")
    )
    free = _track(video, "free track")
    roles = PendulumRoles(
        tip=bound[0].track_id,
        body_top=bound[1].track_id,
        body_bottom=bound[2].track_id,
        pivot=bound[3].track_id,
    )
    experiment = create_pendulum_experiment(uuid4(), video.video_id, roles)
    observations = (
        _engine_point(bound[0].track_id),
        _manual_point(bound[0].track_id),
        _engine_point(free.track_id),
    )
    active_run = None
    runs: tuple[TrackingRun, ...] = ()
    if with_active_run:
        active_run = TrackingRun(
            run_id=uuid4(),
            video_id=video.video_id,
            member_track_ids=roles.track_ids(),
            engine="dlc",
            engine_version="3.0.1",
            task_type="infer",
            config={},
            source_detail="dlc:infer:joint",
            created_at=utc_now(),
            status="completed",
            completed_at=utc_now(),
            experiment_id=experiment.experiment_id,
            role_bindings=roles,
        )
        runs = (active_run,)
        experiment = replace(experiment, active_infer_run_id=active_run.run_id)
    results: tuple[ScientificResult, ...] = ()
    if with_result:
        results = (
            ScientificResult(
                result_id=uuid4(),
                experiment_id=experiment.experiment_id,
                kind="theta",
                created_at=utc_now(),
                input_digest="7" * 64,
                core_version="p2-core-1",
                execution_status="success",
            ),
        )
    project = Project(
        project_id=uuid4(),
        name="session fixture",
        created_at=utc_now(),
        modified_at=utc_now(),
        videos=(video,),
        timelines=(_timeline(video),),
        tracks=(*bound, free),
        observations=observations,
        required_capabilities=PUBLICATION_REQUIRED_CAPABILITIES,
        experiments=(experiment,),
        scientific_results=results,
        tracking_runs=runs,
    )
    return project, roles, free, active_run


class TestCreateAndMigrationSessionFlow:
    def _v1_session_on_disk(self, tmp_path: Path) -> ProjectSession:
        repository = ProjectRepository()
        root = tmp_path / "source"
        video = _video()
        project = Project(
            project_id=uuid4(),
            name="v1 flow",
            created_at=utc_now(),
            modified_at=utc_now(),
            videos=(video,),
            timelines=(_timeline(video),),
        )
        session = ProjectSession(repository, project)
        saved = session.save_as(root)
        assert saved is not None
        return ProjectSession.load(repository, root)

    def test_create_experiment_rejected_on_v1_session(self, tmp_path: Path):
        session = self._v1_session_on_disk(tmp_path)
        roles = PendulumRoles(*(uuid4() for _ in range(4)))
        with pytest.raises(ProjectSessionError, match="publication project"):
            session.create_pendulum_experiment(session.project.videos[0].video_id, roles)

    def test_save_as_publication_with_roles_switches_session(self, tmp_path: Path):
        repository = ProjectRepository()
        root = tmp_path / "source"
        video = _video()
        tracks = tuple(
            _track(video, name) for name in ("tip", "body top", "body bottom", "pivot")
        )
        from ai_physics_tracker.domain.project import add_calibration

        project = Project(
            project_id=uuid4(),
            name="migrate me",
            created_at=utc_now(),
            modified_at=utc_now(),
            videos=(video,),
            timelines=(_timeline(video),),
            tracks=tracks,
        )
        session = ProjectSession(repository, project)
        session.save_as(root)
        source_manifest = (root / "project.json").read_bytes()

        roles = PendulumRoles(
            tip=tracks[0].track_id,
            body_top=tracks[1].track_id,
            body_bottom=tracks[2].track_id,
            pivot=tracks[3].track_id,
        )
        destination = tmp_path / "publication"
        saved = session.save_as_publication(destination, roles)

        assert saved.required_capabilities == PUBLICATION_REQUIRED_CAPABILITIES
        assert session.project_root == destination.resolve()
        assert len(session.pendulum_experiments()) == 1
        assert not session._undo_stack  # 保存边界清空历史
        # 源目录保持 v1 可独立打开
        assert (root / "project.json").read_bytes() == source_manifest
        assert ProjectRepository().load(root).required_capabilities == ()

    def test_save_as_publication_rejects_v2_or_rootless(self, tmp_path: Path):
        session = self._v1_session_on_disk(tmp_path)
        migrated = session.save_as_publication(tmp_path / "v2-copy")
        migrated_session = ProjectSession(
            ProjectRepository(), migrated, tmp_path / "v2-copy"
        )
        with pytest.raises(ProjectSessionError, match="already a publication"):
            migrated_session.save_as_publication(tmp_path / "again")
        rootless = ProjectSession.start(ProjectRepository())
        with pytest.raises(ProjectSessionError, match="v1 root"):
            rootless.save_as_publication(tmp_path / "no-root")


class TestExperimentTransactions:
    def test_rebind_clears_old_projection_and_records_history(self):
        project, roles, _, active_run = _bound_project_with_free_track(
            with_active_run=True
        )
        session = ProjectSession(ProjectRepository(), project)
        video = project.videos[0]
        replacement = session.add_track(video.video_id, "new tip")
        new_roles = PendulumRoles(
            tip=replacement.track_id,
            body_top=roles.body_top,
            body_bottom=roles.body_bottom,
            pivot=roles.pivot,
        )
        updated = session.rebind_pendulum_roles(
            project.experiments[0].experiment_id, new_roles
        )
        experiment = session.pendulum_experiment(project.experiments[0].experiment_id)
        assert experiment.roles == new_roles
        assert experiment.active_infer_run_id is None
        assert experiment.measurement_revision == updated.measurement_revision == 2
        history = experiment.binding_history()
        assert len(history) == 2
        assert history[1].old_roles == roles
        assert history[1].new_roles == new_roles
        # 旧 tip 的 AI 投影清除，manual 保留
        old_tip_points = [
            p
            for p in session.project.observations
            if p.track_id == roles.tip
        ]
        assert all(p.source == "manual" for p in old_tip_points)
        # undo 恢复 roles、AI 投影、revision 与 active 指针
        session.undo()
        restored = session.pendulum_experiment(project.experiments[0].experiment_id)
        assert restored.roles == roles
        assert restored.active_infer_run_id == active_run.run_id
        assert any(
            p.source == "dlc" and p.status == "active"
            for p in session.project.observations
            if p.track_id == roles.tip
        )

    def test_delete_experiment_blocked_by_run_or_result_references(self):
        project, _, _, _ = _bound_project_with_free_track(with_active_run=True)
        session = ProjectSession(ProjectRepository(), project)
        experiment_id = project.experiments[0].experiment_id
        with pytest.raises(ProjectSessionError, match="referenced by tracking runs"):
            session.delete_pendulum_experiment(experiment_id)

        clean, _, _, _ = _bound_project_with_free_track(with_result=True)
        clean_session = ProjectSession(ProjectRepository(), clean)
        with pytest.raises(ProjectSessionError, match="referenced by scientific results"):
            clean_session.delete_pendulum_experiment(
                clean.experiments[0].experiment_id
            )

    def test_delete_clean_experiment_unbinds_tracks(self):
        project, roles, _, _ = _bound_project_with_free_track()
        session = ProjectSession(ProjectRepository(), project)
        session.delete_pendulum_experiment(project.experiments[0].experiment_id)
        assert session.pendulum_experiments() == ()
        # 解绑后 track 不再被 experiment guard 保护
        assert session.experiment_for_track(roles.tip) is None
        session.undo()
        assert session.pendulum_experiments()[0].roles == roles


class TestLegacySingleTrackGuards:
    def test_bound_track_mutators_fail_closed_without_state_change(self):
        project, roles, free, _ = _bound_project_with_free_track()
        session = ProjectSession(ProjectRepository(), project)
        before_project = session.project
        before_store = session._store.tracks, session._store.observations
        before_undo = len(session._undo_stack)

        bound = roles.tip
        for action in (
            lambda: session.activate_infer_run(bound, uuid4()),
            lambda: session.replace_active_infer_run(bound, uuid4()),
            lambda: session.clear_active_ai_observations(bound),
            lambda: session.import_engine_points((), _completed_legacy_run(bound)),
        ):
            with pytest.raises(ProjectSessionError, match="pendulum experiment role"):
                action()
        assert session.project == before_project
        assert (session._store.tracks, session._store.observations) == before_store
        assert len(session._undo_stack) == before_undo

    def test_unbound_track_keeps_legacy_behavior(self):
        project, _, free, _ = _bound_project_with_free_track()
        session = ProjectSession(ProjectRepository(), project)
        record = session.clear_active_ai_observations(free.track_id)
        assert record.action == "clear"
        assert all(
            p.source == "manual"
            for p in session.project.observations
            if p.track_id == free.track_id
        )

    def test_prepare_paths_reject_bound_track(self):
        from ai_physics_tracker.application.tracking_job import prepare_tracking_request
        from ai_physics_tracker.application.training_job import TrainingParams

        project, roles, _, _ = _bound_project_with_free_track()
        session = ProjectSession(ProjectRepository(), project)
        with pytest.raises(ProjectSessionError, match="pendulum"):
            prepare_tracking_request(session, roles.body_top, TrainingParams())


def _completed_legacy_run(track_id) -> TrackingRun:
    return TrackingRun(
        run_id=uuid4(),
        video_id=uuid4(),
        member_track_ids=(track_id,),
        engine="dlc",
        engine_version="3.0.1",
        task_type="infer",
        config={},
        source_detail="dlc:infer:legacy",
        created_at=utc_now(),
        status="completed",
        completed_at=utc_now(),
    )


class TestCalibrationStale:
    def _calibration(self, video_id) -> Calibration:
        return Calibration(
            calibration_id=uuid4(),
            video_id=video_id,
            name="ruler",
            scale_end_1_px=(0.0, 0.0),
            scale_end_2_px=(100.0, 0.0),
            known_length=1.0,
            unit="m",
            created_at=utc_now(),
        )

    def test_calibration_changes_mark_experiment_results_stale(self):
        project, _, _, _ = _bound_project_with_free_track(with_result=True)
        experiment = project.experiments[0]
        video_id = experiment.video_id
        session = ProjectSession(ProjectRepository(), project)
        session._verified_videos.add(video_id)

        result_id = project.scientific_results[0].result_id
        assert session.project.scientific_results[0].freshness == "valid"

        calibration = self._calibration(video_id)
        session.add_calibration(calibration, set_active=True)
        assert session.project.scientific_results[0].freshness == "stale"

    def test_switch_and_delete_active_calibration_stale_without_resubstitution(self):
        project, _, _, _ = _bound_project_with_free_track(with_result=True)
        experiment = project.experiments[0]
        video_id = experiment.video_id
        first = self._calibration(video_id)
        second = replace(self._calibration(video_id), name="second")
        project = replace(
            project,
            calibrations=(first, second),
            active_calibration_by_video={video_id: first.calibration_id},
            scientific_results=tuple(
                replace(r, freshness="valid")
                for r in project.scientific_results
            ),
        )
        session = ProjectSession(ProjectRepository(), project)
        session.set_active_calibration(video_id, second.calibration_id)
        assert session.project.scientific_results[0].freshness == "stale"

        # 删除 active：解析为 None，不偷选另一条
        session.set_active_calibration(video_id, first.calibration_id)
        session.remove_calibration(first.calibration_id)
        from ai_physics_tracker.application.pendulum_setup import (
            resolve_scale_calibration,
        )

        assert (
            resolve_scale_calibration(session.project, session.pendulum_experiments()[0])
            is None
        )
        assert (
            session.project.active_calibration_by_video.get(video_id)
            != second.calibration_id
        )


class TestGeometryAndReleaseActions:
    def _session(self):
        project, _, _, _ = _bound_project_with_free_track()
        session = ProjectSession(ProjectRepository(), project)
        return session, session.pendulum_experiments()[0]

    def test_setup_actions_bump_revision_and_undo_restores(self):
        session, experiment = self._session()
        experiment_id = experiment.experiment_id
        session.set_fixed_pivot(experiment_id, (50.0, 60.0))
        session.set_true_vertical(experiment_id, (50.0, 10.0), (52.0, 95.0))
        session.confirm_true_vertical(experiment_id)
        session.set_physical(
            experiment_id,
            PhysicalParameters(
                length_m=0.98, g_m_s2=9.81, length_source="ruler", g_source="standard"
            ),
        )
        session.set_release_frame(experiment_id, 12)
        current = session.pendulum_experiment(experiment_id)
        assert current.geometry.fixed_pivot_px == (50.0, 60.0)
        assert current.geometry.true_vertical.direction_confirmed
        assert current.physical.length_m == 0.98
        assert current.release_frame_index == 12
        assert current.measurement_revision == experiment.measurement_revision + 5

        session.undo()
        restored = session.pendulum_experiment(experiment_id)
        assert restored.release_frame_index is None
        assert restored.measurement_revision == current.measurement_revision - 1

    def test_changing_endpoints_revokes_confirmation(self):
        session, experiment = self._session()
        experiment_id = experiment.experiment_id
        session.set_true_vertical(experiment_id, (50.0, 10.0), (52.0, 95.0))
        session.confirm_true_vertical(experiment_id)
        assert session.pendulum_experiment(experiment_id).geometry.true_vertical.direction_confirmed
        session.set_true_vertical(experiment_id, (50.0, 12.0), (52.0, 95.0))
        vertical = session.pendulum_experiment(experiment_id).geometry.true_vertical
        assert not vertical.direction_confirmed

    def test_release_bounds_and_confirm_without_vertical_rejected(self):
        session, experiment = self._session()
        experiment_id = experiment.experiment_id
        with pytest.raises(ProjectSessionError, match="frame range"):
            session.set_release_frame(experiment_id, 10_000)
        with pytest.raises(ProjectSessionError, match="before confirming"):
            session.confirm_true_vertical(experiment_id)


class TestSetupProjectionAndDigest:
    def test_status_projection_and_analysis_gate(self):
        project, _, _, _ = _bound_project_with_free_track()
        experiment = project.experiments[0]
        status = pendulum_setup_status(project, experiment)
        assert status.can_annotate
        assert not status.can_analyze
        assert status.missing_for_analysis == (
            "fixed_pivot",
            "true_vertical",
            "active_calibration",
            "physical_parameters",
            "release_frame",
        )
        from ai_physics_tracker.domain.pendulum import PendulumGeometry, TrueVertical

        filled = replace(
            experiment,
            geometry=PendulumGeometry(
                fixed_pivot_px=(1.0, 2.0),
                true_vertical=TrueVertical((1.0, 2.0), (1.5, 90.0)).confirmed(),
            ),
            physical=PhysicalParameters(
                length_m=1.0, g_m_s2=9.8, length_source="s", g_source="s"
            ),
            release_frame_index=3,
        )
        calibration = Calibration(
            calibration_id=uuid4(),
            video_id=experiment.video_id,
            name="ruler",
            scale_end_1_px=(0.0, 0.0),
            scale_end_2_px=(10.0, 0.0),
            known_length=0.1,
            unit="m",
            created_at=utc_now(),
        )
        complete = replace(
            project,
            experiments=(filled,),
            calibrations=(calibration,),
            active_calibration_by_video={
                experiment.video_id: calibration.calibration_id
            },
        )
        ready = pendulum_setup_status(complete, filled)
        assert ready.can_analyze
        assert ready.missing_for_analysis == ()

    def test_digest_tracks_dependencies_not_display_names(self):
        project, _, _, _ = _bound_project_with_free_track()
        experiment = project.experiments[0]
        base = experiment_dependency_digest(project, experiment)
        # 显示名变化不改变 digest（identity 只看 UUID）
        renamed = replace(
            project,
            tracks=tuple(
                replace(track, name=f"display {index}")
                for index, track in enumerate(project.tracks)
            ),
        )
        assert experiment_dependency_digest(renamed, experiment) == base
        # 几何变化改变 digest
        from ai_physics_tracker.domain.pendulum import PendulumGeometry

        moved = replace(
            project,
            experiments=(
                replace(experiment, geometry=PendulumGeometry(fixed_pivot_px=(5.0, 5.0))),
            ),
        )
        assert experiment_dependency_digest(moved, moved.experiments[0]) != base


class TestReviewFindings:
    """S3 Independent Review findings 的回归测试(G1–G4)。"""

    def test_migration_strips_legacy_active_pointer_from_bound_tracks(self, tmp_path):
        from ai_physics_tracker.application.refinement_history import (
            ActivationRecord,
            RefinementState,
            attach_refinement_state,
            extract_refinement_state,
        )

        repository = ProjectRepository()
        video = _video()
        tracks = tuple(
            _track(video, name) for name in ("tip", "body top", "body bottom", "pivot")
        )
        legacy_run = TrackingRun(
            run_id=uuid4(),
            video_id=video.video_id,
            member_track_ids=(tracks[0].track_id,),
            engine="dlc",
            engine_version="3.0.1",
            task_type="infer",
            config={},
            source_detail="dlc:infer:legacy",
            created_at=utc_now(),
            status="completed",
            completed_at=utc_now(),
        )
        state = RefinementState(
            active_infer_run_id=legacy_run.run_id,
            activation_history=(
                ActivationRecord(
                    record_id=uuid4(),
                    timestamp="2026-01-01T00:00:00+00:00",
                    action="activate",
                    from_run_id=None,
                    to_run_id=legacy_run.run_id,
                    point_count=3,
                    manual_preserved_count=0,
                ),
            ),
        )
        archived_track = attach_refinement_state(tracks[0], state)
        tracks = (archived_track, *tracks[1:])
        project = Project(
            project_id=uuid4(),
            name="legacy pointer",
            created_at=utc_now(),
            modified_at=utc_now(),
            videos=(video,),
            timelines=(_timeline(video),),
            tracks=tracks,
            tracking_runs=(legacy_run,),
        )
        session = ProjectSession(repository, project)
        root = tmp_path / "source"
        session.save_as(root)
        session = ProjectSession.load(repository, root)
        assert extract_refinement_state(
            next(t for t in session.tracks if t.track_id == tracks[0].track_id)
        ).active_infer_run_id == legacy_run.run_id

        roles = PendulumRoles(
            tip=tracks[0].track_id,
            body_top=tracks[1].track_id,
            body_bottom=tracks[2].track_id,
            pivot=tracks[3].track_id,
        )
        session.save_as_publication(tmp_path / "publication", roles)
        restored = extract_refinement_state(
            next(
                t for t in session.tracks if t.track_id == tracks[0].track_id
            )
        )
        # 指针清除,activation history 归档保留(契约 §2)
        assert restored.active_infer_run_id is None
        assert len(restored.activation_history) == 1

    def test_delete_track_blocked_by_experiment_joint_run_membership(self):
        project, roles, _, _ = _bound_project_with_free_track(with_active_run=True)
        session = ProjectSession(ProjectRepository(), project)
        video = project.videos[0]
        replacement = session.add_track(video.video_id, "new tip")
        new_roles = PendulumRoles(
            tip=replacement.track_id,
            body_top=roles.body_top,
            body_bottom=roles.body_bottom,
            pivot=roles.pivot,
        )
        session.rebind_pendulum_roles(
            project.experiments[0].experiment_id, new_roles
        )
        # 旧 tip 已解除 role 绑定,但仍被 joint run 引用:删除必须被阻止
        from ai_physics_tracker.application.project_session import ProjectSessionError

        with pytest.raises(ProjectSessionError, match="joint run"):
            session.remove_track(roles.tip)
        # run 记录未被级联删除
        assert any(
            run.experiment_id == project.experiments[0].experiment_id
            for run in session.project.tracking_runs
        )

    def test_new_generic_run_registration_rejected_on_bound_track(self):
        project, roles, _, _ = _bound_project_with_free_track()
        session = ProjectSession(ProjectRepository(), project)
        bound_run = TrackingRun(
            run_id=uuid4(),
            video_id=project.videos[0].video_id,
            member_track_ids=(roles.tip,),
            engine="dlc",
            engine_version="3.0.1",
            task_type="infer",
            config={},
            source_detail="dlc:infer:single",
            created_at=utc_now(),
            status="pending",
        )
        with pytest.raises(ProjectSessionError, match="pendulum experiment role"):
            session.record_tracking_run(bound_run)
        assert session.project.tracking_runs == ()

    def test_manual_point_on_bound_track_bumps_revision_and_stales(self):
        project, roles, _, _ = _bound_project_with_free_track(with_result=True)
        session = ProjectSession(ProjectRepository(), project)
        session._verified_videos.add(project.videos[0].video_id)
        before = session.pendulum_experiments()[0]
        session.mark_point(roles.body_top, 5, 30.0, 40.0)
        after = session.pendulum_experiments()[0]
        assert after.measurement_revision == before.measurement_revision + 1
        assert session.project.scientific_results[0].freshness == "stale"
