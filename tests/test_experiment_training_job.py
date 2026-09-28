"""P1.3-S2 联合训练请求/结果的 Qt-free 测试。

覆盖:prepare 的唯一路径(EX4)与守卫、请求不可变身份(payload 往返)、
verifier 的 digest 回显/stale 复核/bodyparts/输出存在与逃逸负例。
真实 DLC 训练链路属 S6 smoke,本文件不依赖 torch/DLC。
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from uuid import uuid4

import pytest

from ai_physics_tracker.application.annotation_join import (
    canonical_label_digest,
    join_complete_frames,
)
from ai_physics_tracker.application.experiment_training_job import (
    RESULT_SECTION,
    ExperimentTrainingRequest,
    prepare_experiment_training,
    verify_experiment_training_result,
)
from ai_physics_tracker.application.project_session import (
    ProjectSession,
    ProjectSessionError,
)
from ai_physics_tracker.application.video import VideoStreamInfo
from ai_physics_tracker.domain.pendulum import ROLE_ORDER, PendulumRoles
from ai_physics_tracker.domain.project import create_project
from ai_physics_tracker.domain.tracking_run import create_tracking_run
from ai_physics_tracker.infrastructure.project_repository import ProjectRepository

TRAIN_FRAMES = (1, 4, 7, 10)
CHECK_FRAMES = (2, 5, 8)
ALL_COMPLETE = tuple(sorted(TRAIN_FRAMES + CHECK_FRAMES))


def _session_with_experiment(
    tmp_path: Path, synthetic_video_path: Path
) -> tuple[ProjectSession, object, object]:
    """带合成视频 + 四 role experiment 的 publication session,帧已 4/4。"""

    session = ProjectSession(ProjectRepository(), create_project("joint training"))
    info = VideoStreamInfo(
        width_px=64,
        height_px=48,
        fps_container=10.0,
        frame_count=12,
        container_format="avi",
        timing_status="cfr",
    )
    video, _timeline_obj = session.register_external_video(synthetic_video_path, info)
    tracks = {
        role: session.add_track(video.video_id, role) for role in ROLE_ORDER
    }
    roles = PendulumRoles(
        tip=tracks["tip"].track_id,
        body_top=tracks["body_top"].track_id,
        body_bottom=tracks["body_bottom"].track_id,
        pivot=tracks["pivot"].track_id,
    )
    session.save_as_publication(tmp_path / "publication", roles)
    experiment = session.pendulum_experiments()[0]
    for frame in ALL_COMPLETE:
        for role in ROLE_ORDER:
            session.mark_point(experiment.roles.track_id_for(role), frame, 10.0, 20.0)
    return session, video, experiment


def _prepared(tmp_path, synthetic_video_path):
    session, video, experiment = _session_with_experiment(
        tmp_path, synthetic_video_path
    )
    session.freeze_experiment_fixed_check(experiment.experiment_id, CHECK_FRAMES)
    run_id = uuid4()
    run, request = prepare_experiment_training(
        session, experiment.experiment_id, run_id=run_id
    )
    return session, video, experiment, run, request


def _fabricate_job_outputs(job_dir: Path) -> dict[str, str]:
    """在 job 目录伪造 config/snapshot 两份输出;返回相对路径。"""
    job_dir.mkdir(parents=True, exist_ok=True)
    (job_dir / "config.yaml").write_text("bodyparts: [tip]\n", encoding="utf-8")
    snapshot = job_dir / "dlc-project" / "snapshot.pt"
    snapshot.parent.mkdir(parents=True, exist_ok=True)
    snapshot.write_bytes(b"fake-snapshot-bytes")
    return {
        "config_path": "config.yaml",
        "model_snapshot": "dlc-project/snapshot.pt",
    }


def _success_result(request: ExperimentTrainingRequest, paths: dict[str, str]) -> dict:
    return {
        "status": "success",
        "python": "3.12",
        "executable": "/usr/bin/python",
        "platform": "test",
        "machine": "arm64",
        "outputs": [],
        RESULT_SECTION: {
            "label_digest": request.label_digest,
            "video_sha256": request.video_sha256,
            "bodyparts": list(ROLE_ORDER),
            "engine_version": "3.0.1-test",
            "config_path": paths["config_path"],
            "model_snapshot": paths["model_snapshot"],
            "epochs_completed": 3,
        },
    }


class TestPrepare:
    def test_request_built_from_unique_path(self, tmp_path, synthetic_video_path):
        session, _video, experiment, run, request = _prepared(
            tmp_path, synthetic_video_path
        )
        # run:四 role 成员、pending、config 冻结身份
        assert set(run.member_track_ids) == set(experiment.roles.track_ids())
        assert run.status == "pending"
        assert run.config["label_digest"] == request.label_digest
        assert run.config["experiment_id"] == str(experiment.experiment_id)
        assert run.config["request_kind"] == "experiment-joint-training-v1"
        assert run.experiment_id == experiment.experiment_id

        # rows:全部 complete 帧(升序),共同 split 与 plan 一致
        assert tuple(row.frame_index for row in request.rows) == ALL_COMPLETE
        assert request.train_indices == (0, 2, 4, 6)
        assert request.test_indices == (1, 3, 5)

        # digest 冻结 == 当前全量 complete labels 的 canonical digest
        join = join_complete_frames(session.project, experiment)
        assert request.label_digest == canonical_label_digest(join)

        # 视频身份 = 磁盘文件 sha256
        digest = hashlib.sha256(
            Path(synthetic_video_path).read_bytes()
        ).hexdigest()
        assert request.video_sha256 == digest

        # payload 往返不丢失语义
        restored = ExperimentTrainingRequest.from_payload(request.to_payload())
        assert restored.rows == request.rows
        assert restored.train_indices == request.train_indices
        assert restored.test_indices == request.test_indices
        assert restored.label_digest == request.label_digest
        assert restored.video_sha256 == request.video_sha256

    def test_rejects_without_valid_fixed_check(self, tmp_path, synthetic_video_path):
        session, _video, experiment = _session_with_experiment(
            tmp_path, synthetic_video_path
        )
        with pytest.raises(ProjectSessionError, match="fixed check"):
            prepare_experiment_training(session, experiment.experiment_id)

    def test_rejects_when_all_complete_frames_are_fixed_check(
        self, tmp_path, synthetic_video_path
    ):
        session, _video, experiment = _session_with_experiment(
            tmp_path, synthetic_video_path
        )
        session.freeze_experiment_fixed_check(
            experiment.experiment_id, ALL_COMPLETE
        )
        with pytest.raises(ProjectSessionError, match="training frame"):
            prepare_experiment_training(session, experiment.experiment_id)

    def test_rejects_active_member_task(self, tmp_path, synthetic_video_path):
        session, video, experiment, run, _request = _prepared(
            tmp_path, synthetic_video_path
        )
        # run 本身已登记(pending)→ 任何成员再发起即拒绝
        with pytest.raises(ProjectSessionError, match="active engine task"):
            prepare_experiment_training(session, experiment.experiment_id)

    def test_partial_frames_never_enter_request(self, tmp_path, synthetic_video_path):
        session, _video, experiment = _session_with_experiment(
            tmp_path, synthetic_video_path
        )
        session.freeze_experiment_fixed_check(
            experiment.experiment_id, CHECK_FRAMES
        )
        # 3/4 partial 帧(缺 pivot)不进入请求
        for role in ROLE_ORDER[:3]:
            session.mark_point(experiment.roles.track_id_for(role), 6, 1.0, 2.0)
        _run, request = prepare_experiment_training(
            session, experiment.experiment_id, run_id=uuid4()
        )
        assert 6 not in [row.frame_index for row in request.rows]
        assert [row.frame_index for row in request.rows] == list(ALL_COMPLETE)


class TestVerifyResult:
    def test_completes_run_with_snapshot(self, tmp_path, synthetic_video_path):
        session, _video, _experiment, run, request = _prepared(
            tmp_path, synthetic_video_path
        )
        job_dir = tmp_path / "engines" / str(run.run_id)
        paths = _fabricate_job_outputs(job_dir)
        result = _success_result(request, paths)

        completed = verify_experiment_training_result(
            session, run, request, result, job_dir
        )
        assert completed.status == "completed"
        assert completed.model_snapshot == paths["model_snapshot"]
        assert completed.engine_version == "3.0.1-test"
        assert completed.extra_fields["device"] == result[RESULT_SECTION].get(
            "actual_device"
        )
        assert completed.extra_fields["label_digest"] == request.label_digest

    def test_rejects_digest_echo_mismatch(self, tmp_path, synthetic_video_path):
        session, _video, _experiment, run, request = _prepared(
            tmp_path, synthetic_video_path
        )
        job_dir = tmp_path / "engines" / str(run.run_id)
        result = _success_result(request, _fabricate_job_outputs(job_dir))
        result[RESULT_SECTION]["label_digest"] = "0" * 64
        with pytest.raises(ProjectSessionError, match="label digest"):
            verify_experiment_training_result(session, run, request, result, job_dir)

    def test_rejects_stale_labels(self, tmp_path, synthetic_video_path):
        session, _video, experiment, run, request = _prepared(
            tmp_path, synthetic_video_path
        )
        job_dir = tmp_path / "engines" / str(run.run_id)
        result = _success_result(request, _fabricate_job_outputs(job_dir))
        # prepare 之后又补了一个 complete 帧 → 当前 digest 与冻结值不一致
        for role in ROLE_ORDER:
            session.mark_point(experiment.roles.track_id_for(role), 6, 3.0, 4.0)
        with pytest.raises(ProjectSessionError, match="stale"):
            verify_experiment_training_result(session, run, request, result, job_dir)

    def test_rejects_wrong_bodyparts(self, tmp_path, synthetic_video_path):
        session, _video, _experiment, run, request = _prepared(
            tmp_path, synthetic_video_path
        )
        job_dir = tmp_path / "engines" / str(run.run_id)
        result = _success_result(request, _fabricate_job_outputs(job_dir))
        result[RESULT_SECTION]["bodyparts"] = ["target"]
        with pytest.raises(ProjectSessionError, match="bodyparts"):
            verify_experiment_training_result(session, run, request, result, job_dir)

    def test_rejects_missing_snapshot_file(self, tmp_path, synthetic_video_path):
        session, _video, _experiment, run, request = _prepared(
            tmp_path, synthetic_video_path
        )
        job_dir = tmp_path / "engines" / str(run.run_id)
        result = _success_result(request, _fabricate_job_outputs(job_dir))
        (job_dir / "dlc-project" / "snapshot.pt").unlink()
        with pytest.raises(ProjectSessionError, match="missing or escapes"):
            verify_experiment_training_result(session, run, request, result, job_dir)

    def test_rejects_output_path_escape(self, tmp_path, synthetic_video_path):
        session, _video, _experiment, run, request = _prepared(
            tmp_path, synthetic_video_path
        )
        job_dir = tmp_path / "engines" / str(run.run_id)
        result = _success_result(request, _fabricate_job_outputs(job_dir))
        result[RESULT_SECTION]["model_snapshot"] = "../../etc/passwd"
        with pytest.raises(ProjectSessionError, match="missing or escapes"):
            verify_experiment_training_result(session, run, request, result, job_dir)

    def test_rejects_run_identity_mismatch(self, tmp_path, synthetic_video_path):
        session, _video, _experiment, run, request = _prepared(
            tmp_path, synthetic_video_path
        )
        job_dir = tmp_path / "engines" / str(run.run_id)
        result = _success_result(request, _fabricate_job_outputs(job_dir))
        other_run = create_tracking_run(
            video_id=run.video_id,
            member_track_ids=run.member_track_ids,
            task_type="train",
            run_id=uuid4(),
        )
        with pytest.raises(ProjectSessionError, match="identity mismatch"):
            verify_experiment_training_result(
                session, other_run, request, result, job_dir
            )
