"""P1.3-S3 TeacherModelReference 域/序列化/注册/可用性测试(Qt-free)。

覆盖:域校验负例、serializer 双向(含旧 v2 payload 无 model_references 键)、
session 注册事务(undo/redo/save-reopen、重复注册拒绝、产物缺失拒绝)、
可用性检查(missing/modified → unavailable)。
"""

from __future__ import annotations

from pathlib import Path
from uuid import UUID, uuid4

import pytest

from ai_physics_tracker.application.experiment_training_job import (
    prepare_experiment_training,
    verify_experiment_training_result,
)
from ai_physics_tracker.application.project_session import (
    ProjectSession,
    ProjectSessionError,
)
from ai_physics_tracker.application.teacher_models import teacher_model_availability
from ai_physics_tracker.application.video import VideoStreamInfo
from ai_physics_tracker.domain.pendulum import ROLE_ORDER, PendulumRoles
from ai_physics_tracker.domain.project import create_project
from ai_physics_tracker.domain.teacher_model import (
    ModelManifestEntry,
    TeacherModelReference,
    build_manifest_hash,
)
from ai_physics_tracker.domain.types import utc_now
from ai_physics_tracker.infrastructure.project_repository import ProjectRepository

TRAIN_FRAMES = (1, 4, 7, 10)
CHECK_FRAMES = (2, 5, 8)
ALL_COMPLETE = tuple(sorted(TRAIN_FRAMES + CHECK_FRAMES))
RESULT_SECTION = "experiment_training"


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _completed_training(tmp_path: Path, synthetic_video_path: Path):
    """走到 completed 联合训练 run:session + 冻结 fixed check + prepare +
    伪造 job 产物 + verify。返回 (session, completed_run)。"""

    session = ProjectSession(ProjectRepository(), create_project("s3 models"))
    info = VideoStreamInfo(
        width_px=64, height_px=48, fps_container=10.0, frame_count=12,
        container_format="avi", timing_status="cfr",
    )
    video, _timeline = session.register_external_video(synthetic_video_path, info)
    tracks = {role: session.add_track(video.video_id, role) for role in ROLE_ORDER}
    session.save_as_publication(
        tmp_path / "publication",
        PendulumRoles(
            tip=tracks["tip"].track_id, body_top=tracks["body_top"].track_id,
            body_bottom=tracks["body_bottom"].track_id, pivot=tracks["pivot"].track_id,
        ),
    )
    experiment = session.pendulum_experiments()[0]
    for frame in ALL_COMPLETE:
        for role in ROLE_ORDER:
            session.mark_point(experiment.roles.track_id_for(role), frame, 10.0, 20.0)
    session.freeze_experiment_fixed_check(experiment.experiment_id, CHECK_FRAMES)
    run, request = prepare_experiment_training(
        session, experiment.experiment_id, run_id=uuid4()
    )

    job_dir = session.project_root / "data" / "engines" / str(run.run_id)
    job_dir.mkdir(parents=True, exist_ok=True)
    (job_dir / "config.yaml").write_text("bodyparts: four\n", encoding="utf-8")
    snapshot = job_dir / "dlc-project" / "snapshot.pt"
    snapshot.parent.mkdir(parents=True, exist_ok=True)
    snapshot.write_bytes(b"trained-weights-bytes")
    def _output(relative: str) -> dict:
        data = (job_dir / relative).read_bytes()
        return {
            "path": relative, "size": len(data),
            "sha256": __import__("hashlib").sha256(data).hexdigest(),
        }
    result = {
        "status": "success", "python": "3.12", "executable": "/usr/bin/python",
        "platform": "test", "machine": "arm64", "actual_device": "cpu",
        "outputs": [_output("config.yaml"), _output("dlc-project/snapshot.pt")],
        RESULT_SECTION: {
            "label_digest": request.label_digest,
            "video_sha256": request.video_sha256,
            "bodyparts": list(ROLE_ORDER), "engine_version": "3.0.1-test",
            "config_path": "config.yaml",
            "model_snapshot": "dlc-project/snapshot.pt",
            "epochs_completed": 3,
        },
    }
    completed = verify_experiment_training_result(session, run, request, result, job_dir)
    # verify 只返回 completed run;状态回写 session 是调用方(GUI/S6)职责
    session.update_tracking_run(completed)
    return session, completed


def _reference_fixture(**overrides) -> TeacherModelReference:
    entries = (
        ModelManifestEntry(
            relative_path="data/engines/x/config.yaml", size=20, sha256="a" * 64
        ),
        ModelManifestEntry(
            relative_path="data/engines/x/snap.pt", size=8, sha256="b" * 64
        ),
    )
    fields = dict(
        model_id=uuid4(), origin="trained", created_at=utc_now(),
        source_train_run_id=uuid4(), source_experiment_id=uuid4(),
        engine_version="3.0.1",
        bodypart_mapping=tuple((r, r) for r in ROLE_ORDER),
        config_path="data/engines/x/config.yaml",
        checkpoint_path="data/engines/x/snap.pt",
        manifest=entries, manifest_hash=build_manifest_hash(entries),
    )
    fields.update(overrides)
    return TeacherModelReference(**fields)


# ---------------------------------------------------------------------------
# domain
# ---------------------------------------------------------------------------


class TestTeacherModelDomain:
    def test_imported_must_not_carry_source_run(self):
        with pytest.raises(ValueError, match="source_train_run_id"):
            _reference_fixture(
                origin="imported", source_train_run_id=uuid4(),
                source_experiment_id=None,
            )

    def test_manifest_hash_mismatch_rejected(self):
        entries = _reference_fixture().manifest
        with pytest.raises(ValueError, match="manifest_hash"):
            _reference_fixture(
                manifest=entries, manifest_hash="0" * 64,
                config_path=entries[0].relative_path,
                checkpoint_path=entries[1].relative_path,
            )

    def test_manifest_path_escape_rejected(self):
        with pytest.raises(ValueError, match="'..'"):
            ModelManifestEntry(
                relative_path="../escape.pt", size=1, sha256="c" * 64
            )

    def test_config_must_be_manifest_member(self):
        with pytest.raises(ValueError, match="manifest entries"):
            _reference_fixture(config_path="data/other/config.yaml")

    def test_compatible_requires_evidence(self):
        with pytest.raises(ValueError, match="self-test evidence"):
            _reference_fixture(compatibility_state="compatible")

    def test_duplicate_bodypart_targets_rejected(self):
        with pytest.raises(ValueError, match="unique"):
            _reference_fixture(
                bodypart_mapping=(("tip", "a"), ("body_top", "a"),
                                  ("body_bottom", "c"), ("pivot", "d"))
            )


# ---------------------------------------------------------------------------
# serializer
# ---------------------------------------------------------------------------


class TestTeacherModelSerializer:
    def test_round_trip(self, tmp_path, synthetic_video_path):
        from ai_physics_tracker.infrastructure.publication_serializer import (
            teacher_model_from_payload,
            teacher_model_to_payload,
        )

        session, completed = _completed_training(tmp_path, synthetic_video_path)
        reference = session.register_trained_model_reference(completed.run_id)
        restored = teacher_model_from_payload(teacher_model_to_payload(reference))
        assert restored == reference

    def test_project_payload_round_trip_and_unknown_optional(
        self, tmp_path, synthetic_video_path
    ):
        session, completed = _completed_training(tmp_path, synthetic_video_path)
        session.register_trained_model_reference(completed.run_id)
        session.save()
        reopened = ProjectSession.load(
            ProjectRepository(), session.project_root
        )
        references = reopened.project.model_references
        assert len(references) == 1
        assert references[0].source_train_run_id == completed.run_id
        assert references[0].origin == "trained"
        assert references[0].compatibility_state == "unverified"

        # 旧 v2 payload(无 model_references 键)读为空集合
        import json as json_module

        payload = json_module.loads(
            (session.project_root / "project.json").read_text(encoding="utf-8")
        )
        del payload["model_references"]
        legacy_root = tmp_path / "legacy"
        legacy_root.mkdir()
        (legacy_root / "project.json").write_text(
            json_module.dumps(payload, ensure_ascii=False), encoding="utf-8"
        )
        legacy = ProjectSession.load(ProjectRepository(), legacy_root)
        assert legacy.project.model_references == ()


# ---------------------------------------------------------------------------
# session registration
# ---------------------------------------------------------------------------


class TestRegisterTrainedModel:
    def test_register_creates_reference_with_frozen_manifest(
        self, tmp_path, synthetic_video_path
    ):
        session, completed = _completed_training(tmp_path, synthetic_video_path)
        reference = session.register_trained_model_reference(completed.run_id)
        assert reference.origin == "trained"
        assert reference.source_experiment_id == completed.experiment_id
        assert reference.bodypart_mapping == tuple((r, r) for r in ROLE_ORDER)
        assert len(reference.manifest) == 2
        for entry in reference.manifest:
            file_path = session.project_root / entry.relative_path
            assert file_path.is_file()
            assert entry.size == file_path.stat().st_size

    def test_register_is_undoable(self, tmp_path, synthetic_video_path):
        session, completed = _completed_training(tmp_path, synthetic_video_path)
        session.register_trained_model_reference(completed.run_id)
        assert len(session.project.model_references) == 1
        assert session.undo()
        assert session.project.model_references == ()
        assert session.redo()
        assert len(session.project.model_references) == 1

    def test_duplicate_registration_rejected(self, tmp_path, synthetic_video_path):
        session, completed = _completed_training(tmp_path, synthetic_video_path)
        session.register_trained_model_reference(completed.run_id)
        with pytest.raises(ProjectSessionError, match="already has"):
            session.register_trained_model_reference(completed.run_id)

    def test_missing_snapshot_rejected(self, tmp_path, synthetic_video_path):
        session, completed = _completed_training(tmp_path, synthetic_video_path)
        snapshot_rel = completed.model_snapshot
        (session.project_root / "data" / "engines" / str(completed.run_id)
         / snapshot_rel).unlink()
        with pytest.raises(ProjectSessionError, match="missing"):
            session.register_trained_model_reference(completed.run_id)

    def test_non_joint_run_rejected(self, tmp_path, synthetic_video_path):
        session, completed = _completed_training(tmp_path, synthetic_video_path)
        from dataclasses import replace

        plain = replace(completed, run_id=uuid4(), config={"request_kind": "other"})
        session.record_tracking_run(plain)
        with pytest.raises(ProjectSessionError, match="joint training"):
            session.register_trained_model_reference(plain.run_id)


# ---------------------------------------------------------------------------
# availability
# ---------------------------------------------------------------------------


class TestAvailability:
    def test_intact_files_keep_reference_state(
        self, tmp_path, synthetic_video_path
    ):
        session, completed = _completed_training(tmp_path, synthetic_video_path)
        reference = session.register_trained_model_reference(completed.run_id)
        state, reason = teacher_model_availability(session.project_root, reference)
        assert state == "unverified"
        assert reason is None

    def test_modified_file_becomes_unavailable(
        self, tmp_path, synthetic_video_path
    ):
        session, completed = _completed_training(tmp_path, synthetic_video_path)
        reference = session.register_trained_model_reference(completed.run_id)
        snapshot_file = session.project_root / reference.checkpoint_path
        snapshot_file.write_bytes(b"tampered")  # size 变化,先触发 size 检查
        state, reason = teacher_model_availability(session.project_root, reference)
        assert state == "unavailable"
        assert "size changed" in reason

    def test_same_size_tamper_caught_by_sha(
        self, tmp_path, synthetic_video_path
    ):
        session, completed = _completed_training(tmp_path, synthetic_video_path)
        reference = session.register_trained_model_reference(completed.run_id)
        config_file = session.project_root / reference.config_path
        original = config_file.read_bytes()
        config_file.write_bytes(b"x" * len(original))  # 等 size 内容篡改
        state, reason = teacher_model_availability(session.project_root, reference)
        assert state == "unavailable"
        assert "content changed" in reason

    def test_missing_file_becomes_unavailable(self, tmp_path, synthetic_video_path):
        session, completed = _completed_training(tmp_path, synthetic_video_path)
        reference = session.register_trained_model_reference(completed.run_id)
        (session.project_root / reference.checkpoint_path).unlink()
        state, reason = teacher_model_availability(session.project_root, reference)
        assert state == "unavailable"
        assert "missing" in reason


# ---------------------------------------------------------------------------
# 2026-09-28 S1–S3 review 回归(M3/m1/m2)
# ---------------------------------------------------------------------------


class TestReviewRegressions:
    def test_m3_project_validation_rejects_dangling_reference(self):
        from dataclasses import replace as _replace

        from ai_physics_tracker.domain.project import Project

        # 引用不存在的 run → 聚合校验拒绝(经 serialize/load 路径)
        reference = _reference_fixture()
        base = Project(project_id=uuid4(), name="m3", created_at=utc_now(),
                       modified_at=utc_now())
        # Project 构造期(__post_init__ → validate_project)即拒绝悬空引用
        with pytest.raises(ValueError, match="registered train run"):
            _replace(base, model_references=(reference,),
                     required_capabilities=("pendulum-four-role-v1",
                                            "scientific-results-v1"))

    def test_m3_v1_project_rejects_model_references(self):
        from dataclasses import replace as _replace

        from ai_physics_tracker.domain.project import Project

        reference = _reference_fixture(origin="imported",
                                       source_train_run_id=None,
                                       source_experiment_id=None)
        base = Project(project_id=uuid4(), name="m3-v1", created_at=utc_now(),
                       modified_at=utc_now())
        with pytest.raises(ValueError, match="publication collections"):
            _replace(base, model_references=(reference,)).validate()

    def test_m1_serializer_rejects_non_object_manifest_entry(self):
        from ai_physics_tracker.infrastructure.publication_serializer import (
            teacher_model_from_payload,
            teacher_model_to_payload,
        )

        payload = teacher_model_to_payload(_reference_fixture())
        payload["manifest"] = ["not-an-object"] + payload["manifest"]
        with pytest.raises(ValueError, match="manifest entries must be objects"):
            teacher_model_from_payload(payload)

    def test_m2_register_rejects_run_without_verified_digest(
        self, tmp_path, synthetic_video_path
    ):
        session, completed = _completed_training(tmp_path, synthetic_video_path)
        from dataclasses import replace as _replace

        stripped = _replace(
            completed,
            extra_fields={
                k: v for k, v in completed.extra_fields.items()
                if k != "label_digest"
            },
        )
        session.update_tracking_run(stripped)
        with pytest.raises(ProjectSessionError, match="verified label digest"):
            session.register_trained_model_reference(stripped.run_id)
