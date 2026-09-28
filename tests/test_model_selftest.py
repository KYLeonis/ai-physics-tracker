"""P1.3-S5 runtime self-test 测试(Qt-free,不依赖 torch/DLC)。

覆盖:pose_cfg 解析(imported/trained)、payload 构造 fail-closed、result
验证(digest 回显/版本/bodyparts/帧摘要)、unverified→compatible 状态机
(undo、文件篡改阻断、证据失效回落)、incompatible 显式标记、save/reopen。
真实 DLC 推理链路属 S6 smoke。
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from uuid import uuid4

import pytest

from ai_physics_tracker.application.project_session import (
    ProjectSession,
    ProjectSessionError,
)
from ai_physics_tracker.application.teacher_models import (
    build_model_selftest_payload,
    effective_compatibility_state,
    resolve_pose_cfg_path,
    verify_model_selftest_result,
)
from ai_physics_tracker.application.teacher_import import TeacherImportError
from ai_physics_tracker.application.video import VideoStreamInfo
from ai_physics_tracker.domain.pendulum import ROLE_ORDER, PendulumRoles
from ai_physics_tracker.domain.project import create_project
from ai_physics_tracker.infrastructure.project_repository import ProjectRepository

IDENTITY = tuple((role, role) for role in ROLE_ORDER)


def _session_with_imported_model(
    tmp_path: Path, synthetic_video_path: Path, *, with_pose_cfg: bool = True
):
    session = ProjectSession(ProjectRepository(), create_project("s5 selftest"))
    info = VideoStreamInfo(
        width_px=64, height_px=48, fps_container=10.0, frame_count=8,
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
    import yaml

    bundle = tmp_path / "bundle"
    bundle.mkdir()
    (bundle / "config.yaml").write_text(
        yaml.safe_dump({
            "Task": "t", "multianimalproject": False, "identity": False,
            "project_path": str(bundle), "bodyparts": list(ROLE_ORDER),
            "cropping": False, "engine": "pytorch",
        }),
        encoding="utf-8",
    )
    (bundle / "snapshot-50.pt").write_bytes(b"weights")
    extra = ()
    if with_pose_cfg:
        (bundle / "pose_cfg.yaml").write_text("net_type: resnet_50\n", encoding="utf-8")
        extra = ("pose_cfg.yaml",)
    reference = session.import_teacher_model(
        bundle, "config.yaml", "snapshot-50.pt", IDENTITY, extra_files=extra
    )
    return session, video, reference


def _selftest_success_result(
    session: ProjectSession, reference, *, frame_sha: str = "f" * 64
) -> dict:
    by_name = {Path(e.relative_path).name: e for e in reference.manifest}
    return {
        "status": "success", "python": "3.12", "executable": "/usr/bin/python",
        "platform": "test", "machine": "arm64", "actual_device": "cpu",
        "outputs": [],
        "model_selftest": {
            "config_sha256": by_name["config.yaml"].sha256,
            "checkpoint_sha256": by_name["snapshot-50.pt"].sha256,
            "pose_cfg_sha256": "e" * 64,
            "frame_sha256": frame_sha,
            "frame_index": 0,
            "bodyparts_found": sorted(ROLE_ORDER),
            "versions": {"torch": "2.x", "deeplabcut": "3.0.1"},
        },
    }


class TestResolvePoseCfg:
    def test_imported_with_pose_cfg(self, tmp_path, synthetic_video_path):
        session, _video, reference = _session_with_imported_model(tmp_path, synthetic_video_path)
        pose_cfg = resolve_pose_cfg_path(session.project_root, reference)
        assert pose_cfg is not None and pose_cfg.is_file()

    def test_imported_without_pose_cfg_is_none(self, tmp_path, synthetic_video_path):
        session, _video, reference = _session_with_imported_model(
            tmp_path, synthetic_video_path, with_pose_cfg=False
        )
        assert resolve_pose_cfg_path(session.project_root, reference) is None


class TestBuildPayload:
    def test_payload_carries_identity(self, tmp_path, synthetic_video_path):
        session, video, reference = _session_with_imported_model(tmp_path, synthetic_video_path)
        video_path = Path(session.video_path(video))
        payload = build_model_selftest_payload(
            session.project_root, reference, video_path
        )
        by_name = {Path(e.relative_path).name: e for e in reference.manifest}
        assert payload["config_sha256"] == by_name["config.yaml"].sha256
        assert payload["checkpoint_sha256"] == by_name["snapshot-50.pt"].sha256
        assert payload["expected_bodyparts"] == list(ROLE_ORDER)
        assert Path(payload["pose_cfg_path"]).is_file()

    def test_missing_pose_cfg_rejects(self, tmp_path, synthetic_video_path):
        session, video, reference = _session_with_imported_model(
            tmp_path, synthetic_video_path, with_pose_cfg=False
        )
        with pytest.raises(ValueError, match="pose_cfg"):
            build_model_selftest_payload(
                session.project_root, reference, Path(session.video_path(video))
            )

    def test_tampered_model_rejects(self, tmp_path, synthetic_video_path):
        session, video, reference = _session_with_imported_model(tmp_path, synthetic_video_path)
        (session.project_root / reference.checkpoint_path).write_bytes(b"tampered")
        with pytest.raises(ValueError, match="unavailable"):
            build_model_selftest_payload(
                session.project_root, reference, Path(session.video_path(video))
            )


class TestVerifyResult:
    def test_happy_path_builds_evidence(self, tmp_path, synthetic_video_path):
        session, _video, reference = _session_with_imported_model(tmp_path, synthetic_video_path)
        result = _selftest_success_result(session, reference)
        evidence = verify_model_selftest_result(reference, result)
        assert evidence["kind"] == "runtime-selftest-v1"
        assert evidence["model_manifest_hash"] == reference.manifest_hash
        assert evidence["runtime"]["device"] == "cpu"
        assert evidence["runtime"]["versions"]["deeplabcut"] == "3.0.1"

    def test_wrong_checkpoint_echo_rejected(self, tmp_path, synthetic_video_path):
        session, _video, reference = _session_with_imported_model(tmp_path, synthetic_video_path)
        result = _selftest_success_result(session, reference)
        result["model_selftest"]["checkpoint_sha256"] = "0" * 64
        with pytest.raises(ValueError, match="checkpoint digest"):
            verify_model_selftest_result(reference, result)

    def test_bodypart_mismatch_rejected(self, tmp_path, synthetic_video_path):
        session, _video, reference = _session_with_imported_model(tmp_path, synthetic_video_path)
        result = _selftest_success_result(session, reference)
        result["model_selftest"]["bodyparts_found"] = ["target"]
        with pytest.raises(ValueError, match="mapping"):
            verify_model_selftest_result(reference, result)

    def test_missing_versions_rejected(self, tmp_path, synthetic_video_path):
        session, _video, reference = _session_with_imported_model(tmp_path, synthetic_video_path)
        result = _selftest_success_result(session, reference)
        result["model_selftest"]["versions"] = {}
        with pytest.raises(ValueError, match="versions"):
            verify_model_selftest_result(reference, result)


class TestStateMachine:
    def test_unverified_to_compatible_undoable(self, tmp_path, synthetic_video_path):
        session, _video, reference = _session_with_imported_model(tmp_path, synthetic_video_path)
        assert reference.compatibility_state == "unverified"
        result = _selftest_success_result(session, reference)
        updated = session.apply_model_selftest(reference.model_id, result)
        assert updated.compatibility_state == "compatible"
        assert updated.self_test_evidence["runtime"]["device"] == "cpu"
        assert session.undo()
        assert session.project.model_references[0].compatibility_state == "unverified"

    def test_apply_blocked_when_files_tampered(self, tmp_path, synthetic_video_path):
        session, _video, reference = _session_with_imported_model(tmp_path, synthetic_video_path)
        (session.project_root / reference.config_path).write_text("x: 1\n", encoding="utf-8")
        result = _selftest_success_result(session, reference)
        with pytest.raises(ProjectSessionError, match="unavailable|changed"):
            session.apply_model_selftest(reference.model_id, result)

    def test_stale_manifest_invalidates_evidence(self, tmp_path, synthetic_video_path):
        session, _video, reference = _session_with_imported_model(tmp_path, synthetic_video_path)
        result = _selftest_success_result(session, reference)
        session.apply_model_selftest(reference.model_id, result)
        compatible = session.project.model_references[0]
        assert effective_compatibility_state(compatible) == "compatible"
        # 证据过期路径:模型登记后 manifest 又变(新引用)而旧 compatible
        # 证据被带到新 manifest 上——用 evidence 侧 manifest_hash 不一致模拟
        from dataclasses import replace as _replace

        stale = _replace(
            compatible,
            self_test_evidence={
                **compatible.self_test_evidence,
                "model_manifest_hash": "0" * 64,
            },
        )
        assert effective_compatibility_state(stale) == "unverified"

    def test_mark_incompatible_requires_reason(self, tmp_path, synthetic_video_path):
        session, _video, reference = _session_with_imported_model(tmp_path, synthetic_video_path)
        with pytest.raises(ProjectSessionError, match="reason"):
            session.mark_model_incompatible(reference.model_id, "  ")
        marked = session.mark_model_incompatible(reference.model_id, "selftest failed on mps")
        assert marked.compatibility_state == "incompatible"
        assert marked.self_test_evidence["reason"] == "selftest failed on mps"

    def test_save_reopen_preserves_evidence(self, tmp_path, synthetic_video_path):
        session, _video, reference = _session_with_imported_model(tmp_path, synthetic_video_path)
        result = _selftest_success_result(session, reference)
        session.apply_model_selftest(reference.model_id, result)
        session.save()
        reopened = ProjectSession.load(ProjectRepository(), session.project_root)
        restored = reopened.project.model_references[0]
        assert restored.compatibility_state == "compatible"
        assert effective_compatibility_state(restored) == "compatible"


# ---------------------------------------------------------------------------
# S5 review 回归(B1 真实布局 / M2 组合入口 / m3 状态转移 / m4 协议级)
# ---------------------------------------------------------------------------


class TestReviewRegressions:
    def test_b1_trained_layout_resolves_pytorch_config(
        self, tmp_path, synthetic_video_path
    ):
        session, video, reference = _session_with_imported_model(tmp_path, synthetic_video_path)
        # 构造 trained 模型:借用 register 路径太重;直接验证 resolve 的 trained 分支
        from dataclasses import replace as _replace

        run_id = uuid4()
        real_layout = (
            session.project_root / "data" / "engines" / str(run_id)
            / "dlc-project" / "dlc-models-pytorch" / "iteration-0"
            / "task-trainset95shuffle1" / "train" / "pytorch_config.yaml"
        )
        real_layout.parent.mkdir(parents=True, exist_ok=True)
        real_layout.write_text("net_type: resnet_50\n", encoding="utf-8")
        trained = _replace(
            reference, model_id=uuid4(), origin="trained",
            source_train_run_id=run_id, source_experiment_id=uuid4(),
            bodypart_mapping=IDENTITY,
        )
        resolved = resolve_pose_cfg_path(session.project_root, trained)
        assert resolved == real_layout

    def test_m2_combined_state_precedence_and_pose_drift(
        self, tmp_path, synthetic_video_path
    ):
        from ai_physics_tracker.application.teacher_models import model_effective_state

        session, _video, reference = _session_with_imported_model(tmp_path, synthetic_video_path)
        pose_file = session.project_root / [
            e.relative_path for e in reference.manifest
            if Path(e.relative_path).name == "pose_cfg.yaml"
        ][0]
        # 证据冻结的 pose sha 与磁盘实际不符(manifest 完好)→ unverified+原因
        result = _selftest_success_result(session, reference)
        result["model_selftest"]["pose_cfg_sha256"] = "f" * 64
        session.apply_model_selftest(reference.model_id, result)
        compatible = session.project.model_references[0]
        state, reason = model_effective_state(session.project_root, compatible)
        assert state == "unverified"
        assert "pose config" in reason
        # 真实 sha 冻结 → compatible;再篡改文件(imported 的 pose 属 manifest)
        # → availability 先裁决 unavailable(优先级高于证据失效)
        result2 = _selftest_success_result(session, reference)
        result2["model_selftest"]["pose_cfg_sha256"] = hashlib.sha256(
            pose_file.read_bytes()
        ).hexdigest()
        session.apply_model_selftest(reference.model_id, result2)
        assert model_effective_state(
            session.project_root, session.project.model_references[0]
        ) == ("compatible", None)
        pose_file.write_text("net_type: resnet_152\n", encoding="utf-8")
        state, reason = model_effective_state(
            session.project_root, session.project.model_references[0]
        )
        assert state == "unavailable"
        assert "changed" in reason

    def test_m3_incompatible_back_to_compatible(self, tmp_path, synthetic_video_path):
        session, _video, reference = _session_with_imported_model(tmp_path, synthetic_video_path)
        session.mark_model_incompatible(reference.model_id, "mps run failed")
        result = _selftest_success_result(session, reference)
        restored = session.apply_model_selftest(reference.model_id, result)
        assert restored.compatibility_state == "compatible"

    def test_m3_mark_incompatible_undo_restores_evidence(
        self, tmp_path, synthetic_video_path
    ):
        session, _video, reference = _session_with_imported_model(tmp_path, synthetic_video_path)
        result = _selftest_success_result(session, reference)
        session.apply_model_selftest(reference.model_id, result)
        session.mark_model_incompatible(reference.model_id, "manual veto")
        assert session.project.model_references[0].compatibility_state == "incompatible"
        assert session.undo()
        assert session.project.model_references[0].compatibility_state == "compatible"

    def test_m4_protocol_level_selftest_via_real_worker(
        self, tmp_path, synthetic_video_path
    ):
        """真实 worker 进程 + 假 deeplabcut/torch(python_path_extra 注入):
        覆盖 sha 复核、帧解码、结构校验、result section 形状。"""

        import sys as _sys

        from ai_physics_tracker.infrastructure.external_worker import (
            ExternalWorkerRunner,
            build_request,
        )

        session, video, reference = _session_with_imported_model(tmp_path, synthetic_video_path)
        payload = build_model_selftest_payload(
            session.project_root, reference, Path(session.video_path(video))
        )

        fakes = tmp_path / "fakes"
        (fakes / "deeplabcut" / "pose_estimation_pytorch").mkdir(parents=True)
        (fakes / "deeplabcut" / "__init__.py").write_text(
            "__version__ = '3.0.1-fake'\n", encoding="utf-8"
        )
        (fakes / "deeplabcut" / "pose_estimation_pytorch" / "__init__.py").write_text(
            "class _Runner:\n"
            "    def inference(self, frames):\n"
            "        import numpy as np\n"
            "        return [{'bodyparts': np.zeros((1, 4, 3)), 'bbox': None}]\n"
            "def get_pose_inference_runner(**_kwargs):\n"
            "    return _Runner()\n",
            encoding="utf-8",
        )
        (fakes / "torch.py").write_text(
            "__version__ = '2.9.0-fake'\n"
            "class _cuda: pass\n"
            "class _backends: pass\n"
            "cuda = _cuda(); backends = _backends()\n"
            "cuda.is_available = lambda: False\n"
            "backends.mps = type('mps', (), {'is_available': staticmethod(lambda: False)})()\n",
            encoding="utf-8",
        )

        runner = ExternalWorkerRunner(
            _sys.executable, python_path_extra=[fakes]
        )
        job_id = uuid4()
        request, _digest = build_request(
            "selftest_model", job_id=job_id, device="cpu", extra=payload
        )
        job_dir = tmp_path / "engines" / str(job_id)
        handle = runner.start(job_dir, request)
        try:
            assert handle.join(timeout_s=60)
            result = handle.read_result()
            assert result["status"] == "success"
            section = result["model_selftest"]
            assert section["versions"]["deeplabcut"] == "3.0.1-fake"
            assert sorted(section["bodyparts_found"]) == sorted(ROLE_ORDER)
            assert len(section["frame_sha256"]) == 64
            assert section["pose_cfg_sha256"] == payload["pose_cfg_sha256"]
        finally:
            handle.cancel()
            handle.join(timeout_s=5)

    def test_m4_worker_rejects_tampered_checkpoint_echo(
        self, tmp_path, synthetic_video_path
    ):
        import sys as _sys

        from ai_physics_tracker.infrastructure.external_worker import (
            ExternalWorkerError,
            ExternalWorkerRunner,
            build_request,
        )

        session, video, reference = _session_with_imported_model(tmp_path, synthetic_video_path)
        payload = build_model_selftest_payload(
            session.project_root, reference, Path(session.video_path(video))
        )
        payload["checkpoint_sha256"] = "0" * 64  # 伪造回显 → worker sha 复核失败
        runner = ExternalWorkerRunner(_sys.executable)
        job_id = uuid4()
        request, _digest = build_request(
            "selftest_model", job_id=job_id, device="cpu", extra=payload
        )
        handle = runner.start(tmp_path / "engines" / str(job_id), request)
        try:
            assert handle.join(timeout_s=60)
            result = handle.read_result()
            assert result["status"] == "failed"
            assert "checkpoint changed" in result["error"]["message"]
        finally:
            handle.cancel()
            handle.join(timeout_s=5)
