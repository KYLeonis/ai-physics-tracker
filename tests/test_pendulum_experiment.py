"""Pendulum publication 领域值对象与 v2 聚合不变量测试(P1.1-S1)。

覆盖契约 §1–§3:v1/v2 模式互斥、四 role 绑定、几何/物理/release 校验、
多成员 run 表达与 experiment-bound Track 删除防护。
"""

from dataclasses import replace
from uuid import uuid4

import pytest

from ai_physics_tracker.domain.pendulum import (
    PendulumExperiment,
    PendulumGeometry,
    PendulumRoles,
    PhysicalParameters,
    RoleBindingEditRecord,
    TrueVertical,
    create_pendulum_experiment,
    vertical_endpoint_digest,
)
from ai_physics_tracker.domain.project import (
    PUBLICATION_REQUIRED_CAPABILITIES,
    MigrationRecord,
    Project,
    delete_track,
    validate_project,
)
from ai_physics_tracker.domain.scientific_result import (
    ResultColumn,
    ResultPayload,
    ScientificResult,
)
from ai_physics_tracker.domain.timeline import Timeline
from ai_physics_tracker.domain.track import Track
from ai_physics_tracker.domain.tracking_run import TrackingRun, create_tracking_run
from ai_physics_tracker.domain.types import utc_now
from ai_physics_tracker.domain.video import Video
from ai_physics_tracker.infrastructure.project_serializer import (
    project_from_payload,
    project_to_payload,
)


def _video(frame_count: int = 100, suffix: str = "") -> Video:
    return Video(
        video_id=uuid4(),
        file_path=None,
        original_path=f"/tmp/pendulum{suffix}.mp4",
        display_name=f"pendulum{suffix}.mp4",
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


def _roles(video: Video) -> PendulumRoles:
    return PendulumRoles(
        tip=_track(video, "tip").track_id,
        body_top=_track(video, "body top").track_id,
        body_bottom=_track(video, "body bottom").track_id,
        pivot=_track(video, "pivot").track_id,
    )


def _publication_project(
    *,
    video: Video | None = None,
    extra_videos: tuple[Video, ...] = (),
    tracks: tuple[Track, ...] | None = None,
    roles: PendulumRoles | None = None,
    experiment: PendulumExperiment | None = None,
    runs: tuple[TrackingRun, ...] = (),
    results: tuple[ScientificResult, ...] = (),
    migration: MigrationRecord | None = None,
) -> Project:
    video = video or _video()
    tracks = tracks or tuple(
        _track(video, name) for name in ("tip", "body top", "body bottom", "pivot")
    )
    roles = roles or PendulumRoles(
        tip=tracks[0].track_id,
        body_top=tracks[1].track_id,
        body_bottom=tracks[2].track_id,
        pivot=tracks[3].track_id,
    )
    experiment = experiment or create_pendulum_experiment(
        uuid4(), video.video_id, roles
    )
    return Project(
        project_id=uuid4(),
        name="publication",
        created_at=utc_now(),
        modified_at=utc_now(),
        videos=(video, *extra_videos),
        timelines=(_timeline(video), *(_timeline(item) for item in extra_videos)),
        tracks=tracks,
        required_capabilities=PUBLICATION_REQUIRED_CAPABILITIES,
        migration=migration,
        experiments=(experiment,),
        scientific_results=results,
        tracking_runs=runs,
    )


def _completed_joint_run(
    experiment: PendulumExperiment, *, status: str = "completed"
) -> TrackingRun:
    return TrackingRun(
        run_id=uuid4(),
        video_id=experiment.video_id,
        member_track_ids=experiment.roles.track_ids(),
        engine="dlc",
        engine_version="3.0.1",
        task_type="infer",
        config={},
        source_detail="dlc:infer:joint",
        created_at=utc_now(),
        status=status,
        completed_at=utc_now() if status == "completed" else None,
        experiment_id=experiment.experiment_id,
        role_bindings=experiment.roles,
    )


class TestPendulumRoles:
    def test_roles_must_bind_four_distinct_tracks(self):
        shared = uuid4()
        with pytest.raises(ValueError, match="four distinct tracks"):
            PendulumRoles(tip=shared, body_top=shared, body_bottom=uuid4(), pivot=uuid4())

    def test_track_ids_follow_canonical_role_order(self):
        ids = tuple(uuid4() for _ in range(4))
        roles = PendulumRoles(tip=ids[0], body_top=ids[1], body_bottom=ids[2], pivot=ids[3])
        assert roles.track_ids() == ids
        assert roles.by_role() == {
            "tip": ids[0],
            "body_top": ids[1],
            "body_bottom": ids[2],
            "pivot": ids[3],
        }


class TestTrueVertical:
    def test_rejects_coincident_and_non_finite_endpoints(self):
        with pytest.raises(ValueError, match="must be two finite coordinates"):
            TrueVertical(top_px=(1.0, float("nan")), bottom_px=(2.0, 3.0))
        with pytest.raises(ValueError, match="must not coincide"):
            TrueVertical(top_px=(1.0, 2.0), bottom_px=(1.0, 2.0))

    def test_unconfirmed_vertical_rejects_stale_digest(self):
        with pytest.raises(ValueError, match="must not carry a digest"):
            TrueVertical(
                top_px=(0.0, 0.0),
                bottom_px=(0.0, 10.0),
                direction_confirmed=False,
                confirmed_digest="0" * 64,
            )

    def test_confirmed_digest_must_match_endpoints(self):
        confirmed = TrueVertical(top_px=(0.0, 0.0), bottom_px=(0.0, 10.0)).confirmed()
        assert confirmed.direction_confirmed
        assert confirmed.confirmed_digest == vertical_endpoint_digest(
            (0.0, 0.0), (0.0, 10.0)
        )
        with pytest.raises(ValueError, match="does not match"):
            TrueVertical(
                top_px=(0.0, 0.0),
                bottom_px=(5.0, 10.0),
                direction_confirmed=True,
                confirmed_digest=confirmed.confirmed_digest,
            )


class TestGeometryAndPhysical:
    def test_geometry_defaults_allow_stepwise_setup(self):
        geometry = PendulumGeometry()
        assert geometry.fixed_pivot_px is None
        assert geometry.true_vertical is None
        assert geometry.tip_radius_reference_px is None

    def test_geometry_rejects_degenerate_values(self):
        with pytest.raises(ValueError, match="two finite coordinates"):
            PendulumGeometry(fixed_pivot_px=(float("inf"), 1.0))
        with pytest.raises(ValueError, match="positive finite"):
            PendulumGeometry(tip_radius_reference_px=0.0)

    def test_physical_requires_positive_finite_with_provenance(self):
        ok = PhysicalParameters(
            length_m=1.23, g_m_s2=9.81, length_source="ruler", g_source="profile"
        )
        assert ok.length_m == 1.23
        for bad in (
            {"length_m": 0.0},
            {"length_m": -1.0},
            {"length_m": float("nan")},
        ):
            with pytest.raises(ValueError, match="length_m"):
                PhysicalParameters(g_m_s2=9.81, length_source="s", g_source="s", **bad)
        with pytest.raises(ValueError, match="g_m_s2"):
            PhysicalParameters(length_m=1.0, g_m_s2=0.0, length_source="s", g_source="s")
        with pytest.raises(ValueError, match="provenance"):
            PhysicalParameters(length_m=1.0, g_m_s2=9.81, length_source=" ", g_source="s")


class TestExperimentRecord:
    def test_creation_commits_first_binding_history_at_revision_one(self):
        roles = _roles(_video())
        experiment = create_pendulum_experiment(uuid4(), uuid4(), roles)
        assert experiment.measurement_revision == 1
        history = experiment.binding_history()
        assert len(history) == 1
        assert history[0].old_roles is None
        assert history[0].new_roles == roles
        assert history[0].revision == 1

    def test_rejects_negative_revision_and_release_frame(self):
        roles = _roles(_video())
        with pytest.raises(ValueError, match="measurement_revision"):
            PendulumExperiment(
                experiment_id=uuid4(),
                video_id=uuid4(),
                roles=roles,
                created_at=utc_now(),
                measurement_revision=-1,
            )
        with pytest.raises(ValueError, match="release_frame_index"):
            PendulumExperiment(
                experiment_id=uuid4(),
                video_id=uuid4(),
                roles=roles,
                created_at=utc_now(),
                release_frame_index=-5,
            )


class TestFormatModeInvariants:
    def test_v1_project_rejects_publication_facts(self):
        project = _publication_project()
        with pytest.raises(ValueError, match="v1 project must not carry"):
            validate_project(replace(project, required_capabilities=()))
        with pytest.raises(ValueError, match="v1 project must not carry"):
            validate_project(
                replace(
                    project,
                    required_capabilities=(),
                    experiments=(),
                    migration=MigrationRecord(
                        source_schema_version=1, source_manifest_sha256="0" * 64
                    ),
                )
            )

    def test_unknown_and_missing_capabilities_rejected(self):
        project = _publication_project()
        with pytest.raises(ValueError, match="unknown required capabilities"):
            validate_project(
                replace(project, required_capabilities=("pendulum-four-role-v1", "future-cap"))
            )
        with pytest.raises(ValueError, match="missing required capabilities"):
            validate_project(
                replace(project, required_capabilities=("pendulum-four-role-v1",))
            )

    def test_v1_project_rejects_multi_member_run(self):
        project = _publication_project()
        joint = _completed_joint_run(project.experiments[0])
        with pytest.raises(ValueError, match="single-member"):
            # replace 触发构造期聚合校验，非法组合在此即被拒绝
            replace(
                project,
                required_capabilities=(),
                experiments=(),
                tracking_runs=(joint,),
            )


class TestPublicationCollectionValidation:
    def test_roles_must_reference_same_video_tracks(self):
        video = _video()
        second_video = _video(suffix="-b")
        same_video_tracks = tuple(
            _track(video, name) for name in ("tip", "body top", "body bottom")
        )
        foreign = _track(second_video, "other video pivot")
        roles = PendulumRoles(
            tip=same_video_tracks[0].track_id,
            body_top=same_video_tracks[1].track_id,
            body_bottom=same_video_tracks[2].track_id,
            pivot=foreign.track_id,
        )
        with pytest.raises(ValueError, match="same video"):
            # Project 构造期即执行聚合校验，跨 video 绑定在此被拒绝
            _publication_project(
                video=video,
                extra_videos=(second_video,),
                tracks=(*same_video_tracks, foreign),
                roles=roles,
                experiment=create_pendulum_experiment(uuid4(), video.video_id, roles),
            )

    def test_second_experiment_on_same_video_rejected(self):
        project = _publication_project()
        video = project.videos[0]
        extra_tracks = tuple(
            _track(video, name) for name in ("tip2", "body top2", "body bottom2", "pivot2")
        )
        second_roles = PendulumRoles(
            tip=extra_tracks[0].track_id,
            body_top=extra_tracks[1].track_id,
            body_bottom=extra_tracks[2].track_id,
            pivot=extra_tracks[3].track_id,
        )
        second = create_pendulum_experiment(uuid4(), video.video_id, second_roles)
        with pytest.raises(ValueError, match="at most one pendulum experiment"):
            validate_project(
                replace(
                    project,
                    tracks=(*project.tracks, *extra_tracks),
                    experiments=(*project.experiments, second),
                )
            )

    def test_release_frame_bounds_use_video_frame_count(self):
        project = _publication_project()
        experiment = project.experiments[0]
        with pytest.raises(ValueError, match="frame_count"):
            validate_project(
                replace(
                    project,
                    experiments=(
                        replace(experiment, release_frame_index=1000),
                    ),
                )
            )

    def test_active_run_must_be_completed_joint_inference_of_this_experiment(self):
        project = _publication_project()
        experiment = project.experiments[0]
        completed = _completed_joint_run(experiment)
        # 非 completed / 非 infer / 成员不一致均拒绝
        for mutated in (
            replace(completed, status="failed", completed_at=None),
            replace(completed, task_type="train"),
            replace(
                completed,
                member_track_ids=(*completed.member_track_ids[:3], uuid4()),
                role_bindings=PendulumRoles(
                    tip=completed.member_track_ids[0],
                    body_top=completed.member_track_ids[1],
                    body_bottom=completed.member_track_ids[2],
                    pivot=uuid4(),
                ),
            ),
        ):
            with pytest.raises(ValueError):
                validate_project(
                    replace(
                        project,
                        tracking_runs=(mutated,),
                        experiments=(replace(experiment, active_infer_run_id=mutated.run_id),),
                    )
                )
        validate_project(
            replace(
                project,
                tracking_runs=(completed,),
                experiments=(replace(experiment, active_infer_run_id=completed.run_id),),
            )
        )

    def test_pendulum_run_members_follow_canonical_role_order(self):
        project = _publication_project()
        experiment = project.experiments[0]
        shuffled = TrackingRun(
            run_id=uuid4(),
            video_id=experiment.video_id,
            member_track_ids=tuple(reversed(experiment.roles.track_ids())),
            engine="dlc",
            engine_version="3.0.1",
            task_type="infer",
            config={},
            source_detail="dlc:infer:joint",
            created_at=utc_now(),
            status="completed",
            completed_at=utc_now(),
            experiment_id=experiment.experiment_id,
            role_bindings=experiment.roles,
        )
        with pytest.raises(ValueError, match="canonical role order"):
            validate_project(replace(project, tracking_runs=(shuffled,)))

    def test_generic_run_in_v2_project_must_stay_single_member(self):
        project = _publication_project()
        generic = create_tracking_run(
            project.videos[0].video_id,
            (project.tracks[0].track_id, project.tracks[1].track_id),
            "train",
        )
        with pytest.raises(ValueError, match="exactly one member"):
            validate_project(replace(project, tracking_runs=(generic,)))


class TestDeleteTrackGuard:
    def test_experiment_bound_track_deletion_rejected(self):
        project = _publication_project()
        bound = project.experiments[0].roles.tip
        with pytest.raises(ValueError, match="bound to pendulum experiment"):
            delete_track(project, bound)

    def test_unbound_track_deletion_still_works(self):
        project = _publication_project()
        extra = _track(project.videos[0], "free track")
        updated = replace(project, tracks=(*project.tracks, extra))
        after = delete_track(updated, extra.track_id)
        assert all(track.track_id != extra.track_id for track in after.tracks)


class TestScientificResultEnvelope:
    def test_envelope_validates_digest_path_and_columns(self):
        experiment_id = uuid4()
        with pytest.raises(ValueError, match="input_digest"):
            ScientificResult(
                result_id=uuid4(),
                experiment_id=experiment_id,
                kind="theta",
                created_at=utc_now(),
                input_digest="short",
                core_version="1",
                execution_status="success",
            )
        with pytest.raises(ValueError, match="unknown execution status"):
            ScientificResult(
                result_id=uuid4(),
                experiment_id=experiment_id,
                kind="theta",
                created_at=utc_now(),
                input_digest="0" * 64,
                core_version="1",
                execution_status="excellent",
            )
        with pytest.raises(ValueError, match="payload path"):
            ResultPayload(
                format="csv",
                path=__import__("pathlib").PurePosixPath("../escape.csv"),
                size_bytes=1,
                sha256="0" * 64,
                columns=(ResultColumn(name="theta", dtype="float64", unit="rad"),),
            )
        with pytest.raises(ValueError, match="at least one column"):
            ResultPayload(
                format="csv",
                path=__import__("pathlib").PurePosixPath("data/results/a.csv"),
                size_bytes=1,
                sha256="0" * 64,
                columns=(),
            )

    def test_result_must_reference_registered_experiment(self):
        project = _publication_project()
        orphan = ScientificResult(
            result_id=uuid4(),
            experiment_id=uuid4(),
            kind="theta",
            created_at=utc_now(),
            input_digest="0" * 64,
            core_version="1",
            execution_status="success",
        )
        with pytest.raises(ValueError, match="registered experiment"):
            validate_project(replace(project, scientific_results=(orphan,)))


class TestMigrationRecord:
    def test_migration_record_requires_valid_sha256(self):
        MigrationRecord(source_schema_version=1, source_manifest_sha256="0" * 64)
        with pytest.raises(ValueError, match="64-hex"):
            MigrationRecord(source_schema_version=1, source_manifest_sha256="zz")


class TestV2RoundTrip:
    def test_full_publication_project_survives_payload_round_trip(self):
        project = _publication_project(
            migration=MigrationRecord(
                source_schema_version=1, source_manifest_sha256="1" * 64
            )
        )
        experiment = project.experiments[0]
        vertical = TrueVertical(top_px=(10.0, 5.0), bottom_px=(12.0, 95.0)).confirmed()
        experiment = replace(
            experiment,
            geometry=PendulumGeometry(
                fixed_pivot_px=(10.0, 5.0), true_vertical=vertical
            ),
            physical=PhysicalParameters(
                length_m=0.98, g_m_s2=9.81, length_source="ruler", g_source="standard"
            ),
            release_frame_index=12,
        )
        run = _completed_joint_run(experiment)
        experiment = replace(experiment, active_infer_run_id=run.run_id)
        result = ScientificResult(
            result_id=uuid4(),
            experiment_id=experiment.experiment_id,
            kind="theta",
            created_at=utc_now(),
            input_digest="2" * 64,
            core_version="p2-core-1",
            execution_status="success",
            payload=ResultPayload(
                format="csv",
                path=__import__("pathlib").PurePosixPath("data/results/theta.csv"),
                size_bytes=128,
                sha256="3" * 64,
                columns=(
                    ResultColumn(name="theta", dtype="float64", unit="rad"),
                    ResultColumn(name="time_s", dtype="float64", unit="s"),
                ),
            ),
        )
        project = replace(
            project,
            experiments=(experiment,),
            tracking_runs=(run,),
            scientific_results=(result,),
        )
        payload = project_to_payload(project)
        assert payload["schema_version"] == 2
        assert payload["experiments"][str(experiment.experiment_id)]["roles"] == {
            "tip": str(experiment.roles.tip),
            "body_top": str(experiment.roles.body_top),
            "body_bottom": str(experiment.roles.body_bottom),
            "pivot": str(experiment.roles.pivot),
        }
        restored = project_from_payload(payload)
        assert restored == project
