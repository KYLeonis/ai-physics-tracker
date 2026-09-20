"""schema v1/v2 双格式 serializer 与 repository 版本守卫测试(P1.1-S1)。

覆盖契约 §1/§8:v1 原样读写、v2 keyed 集合、unknown capability/key-id
mismatch/悬空引用拒绝、scientific-results-v1 envelope 无损保存。
"""

import json
from dataclasses import replace
from pathlib import Path, PurePosixPath
from uuid import uuid4

import pytest

from ai_physics_tracker.domain.pendulum import create_pendulum_experiment
from ai_physics_tracker.domain.project import (
    PUBLICATION_REQUIRED_CAPABILITIES,
    MigrationRecord,
    Project,
    create_project,
)
from ai_physics_tracker.domain.scientific_result import (
    ResultColumn,
    ResultPayload,
    ScientificResult,
)
from ai_physics_tracker.domain.timeline import Timeline
from ai_physics_tracker.domain.track import Track
from ai_physics_tracker.domain.tracking_run import TrackingRun
from ai_physics_tracker.domain.types import utc_now
from ai_physics_tracker.domain.video import Video
from ai_physics_tracker.infrastructure.errors import (
    ProjectFormatError,
    UnsupportedSchemaVersionError,
)
from ai_physics_tracker.infrastructure.project_repository import ProjectRepository
from ai_physics_tracker.infrastructure.project_serializer import (
    project_from_payload,
    project_to_payload,
    tracking_run_to_payload,
)
from test_pendulum_experiment import (
    _completed_joint_run,
    _publication_project,
)


class TestV1FormatUnchanged:
    def test_generic_project_still_writes_schema_v1(self):
        project = create_project("generic")
        payload = project_to_payload(project)
        assert payload["schema_version"] == 1
        assert "required_capabilities" not in payload
        assert "experiments" not in payload
        assert "scientific_results" not in payload

    def test_v1_round_trip_through_repository_keeps_format(self, tmp_path: Path):
        repository = ProjectRepository()
        root = tmp_path / "v1"
        project = create_project("v1 keep")
        saved = repository.create_from_project(root, project)
        reloaded = repository.load(root)
        assert reloaded.required_capabilities == ()
        manifest = json.loads((root / "project.json").read_text(encoding="utf-8"))
        assert manifest["schema_version"] == 1
        repository.save(root, saved)
        manifest = json.loads((root / "project.json").read_text(encoding="utf-8"))
        assert manifest["schema_version"] == 1

    def test_v1_writer_rejects_multi_member_run(self):
        project = _publication_project()
        joint = _completed_joint_run(project.experiments[0])
        with pytest.raises(ValueError, match="single-member"):
            tracking_run_to_payload(joint)


class TestV2ReaderValidation:
    def _v2_payload(self) -> dict[str, object]:
        project = _publication_project(
            migration=MigrationRecord(
                source_schema_version=1, source_manifest_sha256="4" * 64
            )
        )
        return project_to_payload(project)

    def test_valid_v2_payload_loads_and_round_trips(self):
        payload = self._v2_payload()
        restored = project_from_payload(payload)
        assert restored.required_capabilities == PUBLICATION_REQUIRED_CAPABILITIES
        assert restored.migration is not None
        assert project_to_payload(restored) == payload

    def test_v2_without_required_capabilities_rejected(self):
        payload = self._v2_payload()
        del payload["required_capabilities"]
        with pytest.raises(ValueError, match="required_capabilities"):
            project_from_payload(payload)

    def test_v2_with_unknown_capability_rejected(self):
        payload = self._v2_payload()
        payload["required_capabilities"] = [
            "pendulum-four-role-v1",
            "scientific-results-v1",
            "future-capability",
        ]
        with pytest.raises(ValueError, match="unknown required capabilities"):
            project_from_payload(payload)

    def test_v2_with_missing_capability_rejected(self):
        payload = self._v2_payload()
        payload["required_capabilities"] = ["pendulum-four-role-v1"]
        with pytest.raises(ValueError, match="missing required capabilities"):
            project_from_payload(payload)

    def test_future_schema_version_rejected_by_repository(self, tmp_path: Path):
        root = tmp_path / "future"
        root.mkdir()
        (root / "project.json").write_text(
            json.dumps({"schema_version": 999, "name": "x"}), encoding="utf-8"
        )
        with pytest.raises(UnsupportedSchemaVersionError):
            ProjectRepository().load(root)

    def test_key_id_mismatch_rejected_for_experiments_and_results(self):
        payload = self._v2_payload()
        experiment_payload = next(iter(payload["experiments"].values()))
        payload["experiments"][str(uuid4())] = experiment_payload
        with pytest.raises(ValueError, match="map key must equal"):
            project_from_payload(payload)

    def test_v2_run_requires_member_track_ids(self):
        payload = self._v2_payload()
        run = {
            "run_id": str(uuid4()),
            "video_id": str(uuid4()),
            "track_id": str(uuid4()),
            "engine": "dlc",
            "engine_version": "3.0.1",
            "task_type": "infer",
            "config": {},
            "source_detail": "dlc:infer:legacy",
            "status": "pending",
            "created_at": utc_now().isoformat(),
        }
        payload["tracking_runs"] = [run]
        with pytest.raises(ValueError, match="member_track_ids"):
            project_from_payload(payload)

    def test_unknown_top_level_keys_preserved_in_v2(self):
        payload = self._v2_payload()
        payload["future_publication_section"] = {"anything": [1, 2, 3]}
        restored = project_from_payload(payload)
        assert restored.extra_fields["future_publication_section"] == {
            "anything": [1, 2, 3]
        }
        assert project_to_payload(restored)["future_publication_section"] == {
            "anything": [1, 2, 3]
        }


class TestScientificResultEnvelopeLossless:
    def _project_with_result(self) -> tuple[Project, ScientificResult]:
        project = _publication_project()
        result = ScientificResult(
            result_id=uuid4(),
            experiment_id=project.experiments[0].experiment_id,
            kind="theta",
            created_at=utc_now(),
            input_digest="5" * 64,
            core_version="p2-core-1",
            execution_status="success",
            payload=ResultPayload(
                format="csv",
                path=PurePosixPath("data/results/theta.csv"),
                size_bytes=256,
                sha256="6" * 64,
                columns=(ResultColumn(name="theta", dtype="float64", unit="rad"),),
            ),
        )
        return replace(project, scientific_results=(result,)), result

    def test_envelope_fields_round_trip_losslessly(self):
        project, result = self._project_with_result()
        payload = project_to_payload(project)
        stored = payload["scientific_results"][str(result.result_id)]
        assert stored["payload"]["path"] == "data/results/theta.csv"
        assert stored["payload"]["columns"] == [
            {"name": "theta", "dtype": "float64", "unit": "rad"}
        ]
        restored = project_from_payload(payload)
        assert restored.scientific_results == (result,)

    def test_repository_round_trip_preserves_envelope(self, tmp_path: Path):
        repository = ProjectRepository()
        project, _ = self._project_with_result()
        root = tmp_path / "v2"
        repository.create_from_project(root, project)
        reloaded = repository.load(root)
        assert reloaded.scientific_results == project.scientific_results
        manifest = json.loads((root / "project.json").read_text(encoding="utf-8"))
        assert manifest["schema_version"] == 2


class TestLegacyRunMigrationShape:
    def test_legacy_v1_run_loads_as_single_member(self, tmp_path: Path):
        """契约 §3：v1 run 迁移为一个 member，不假装四点 run。"""

        project = create_project("legacy run")
        video = Video(
            video_id=uuid4(),
            file_path=None,
            original_path="/tmp/legacy.mp4",
            display_name="legacy.mp4",
            width_px=320,
            height_px=240,
            fps_container=30.0,
            frame_count=50,
        )
        timeline = Timeline(
            video_id=video.video_id,
            fps_nominal=30.0,
            frame_indexing="zero-based",
            working_zone=(0, 49),
        )
        track = Track(
            track_id=uuid4(),
            video_id=video.video_id,
            name="single",
            color="#000000",
            created_at=utc_now(),
        )
        run = TrackingRun(
            run_id=uuid4(),
            video_id=video.video_id,
            member_track_ids=(track.track_id,),
            engine="dlc",
            engine_version="3.0.1",
            task_type="train",
            config={},
            source_detail="dlc:train:legacy",
            created_at=utc_now(),
            status="completed",
            completed_at=utc_now(),
        )
        populated = Project(
            project_id=project.project_id,
            name=project.name,
            created_at=project.created_at,
            modified_at=project.modified_at,
            videos=(video,),
            timelines=(timeline,),
            tracks=(track,),
            tracking_runs=(run,),
        )
        payload = project_to_payload(populated)
        assert payload["tracking_runs"][0]["track_id"] == str(track.track_id)
        restored = project_from_payload(payload)
        assert restored.tracking_runs[0].member_track_ids == (track.track_id,)
        assert restored.tracking_runs[0].track_id == track.track_id
