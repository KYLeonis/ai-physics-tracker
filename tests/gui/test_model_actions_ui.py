"""P1.3-S6 模型动作控制器与导入向导的 Qt offscreen 测试。

假 runner/handle 驱动联合训练与自检的完整收尾链(prepare→poll→verify→
register / apply),验证 i3①②(取消经 handle.cancel、elapsed_s 入 extras)、
失败/取消路径的 run 状态、向导映射与导入事务。
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from uuid import uuid4

import pytest

from ai_physics_tracker.application.video import VideoStreamInfo
from ai_physics_tracker.domain.pendulum import ROLE_ORDER, PendulumRoles
from ai_physics_tracker.domain.project import create_project
from ai_physics_tracker.gui.model_actions import ModelActions
from ai_physics_tracker.gui.teacher_import_dialog import propose_identity_mapping
from ai_physics_tracker.infrastructure.project_repository import ProjectRepository

pytestmark = pytest.mark.usefixtures("qapp")

RESULT_SECTION = "experiment_training"
TRAIN_FRAMES = (1, 4, 7, 10)
CHECK_FRAMES = (2, 5, 8)
ALL_COMPLETE = tuple(sorted(TRAIN_FRAMES + CHECK_FRAMES))


class _FakeHandle:
    def __init__(self, result: dict | None = None, *, alive_first_polls: int = 0):
        self._result = result
        self._alive_count = alive_first_polls
        self.cancelled = False
        self.elapsed_s_value = 12.5

    def is_alive(self) -> bool:
        if self._alive_count > 0:
            self._alive_count -= 1
            return True
        return False

    def join(self, timeout_s=None) -> bool:
        return True

    def cancel(self) -> None:
        self.cancelled = True
        self._alive_count = 0   # 取消后 join 收尸,is_alive 即 False

    def read_result(self) -> dict:
        if self._result is None:
            from ai_physics_tracker.infrastructure.external_worker import (
                ExternalWorkerError,
            )
            raise ExternalWorkerError("protocol broken (fake)")
        return self._result

    @property
    def elapsed_s(self) -> float:
        return self.elapsed_s_value


class _FakeRunnerFactory:
    """按 ModelWorkerRunner 接口(request 对象直入)提供假实现。"""

    def __init__(self, result: dict | None = None, *, alive_first_polls: int = 0):
        self.result = result
        self.alive_first_polls = alive_first_polls

    def __call__(self):
        factory = self

        class _Runner:
            def start_training(self, project_root, request, *, device="cpu"):
                job_dir = Path(project_root) / "data" / "engines" / request.run_id
                result = (
                    _train_success_result(request, job_dir)
                    if factory.result is None and factory._train_mode
                    else factory.result
                )
                return _FakeHandle(result, alive_first_polls=factory.alive_first_polls)

            def start_selftest(self, project_root, model_id, fields, *, device="cpu"):
                return _FakeHandle(
                    factory.result, alive_first_polls=factory.alive_first_polls
                )

        factory._train_mode = False
        return _Runner()

    _train_mode = False


@pytest.fixture
def long_video_path(tmp_path):
    """12 帧 CFR 视频(共享 fixture 只有 5 帧,不够本文件的帧号)。"""
    import cv2
    import numpy as np

    path = tmp_path / "synthetic12.avi"
    writer = cv2.VideoWriter(
        str(path), cv2.VideoWriter_fourcc(*"MJPG"), 10.0, (64, 48)
    )
    if not writer.isOpened():
        raise RuntimeError("OpenCV MJPEG writer unavailable")
    for index in range(12):
        writer.write(
            np.full((48, 64, 3), 40 * index % 255, dtype=np.uint8)
        )
    writer.release()
    return path


def _experiment_window(qtbot, tmp_path, synthetic_video_path):
    from ai_physics_tracker.gui.main_window import MainWindow
    from ai_physics_tracker.infrastructure.ffprobe_timing import FFprobeTimingProbe
    from ai_physics_tracker.application.video_session import VideoSession
    from ai_physics_tracker.infrastructure.opencv_video_reader import OpenCVVideoReader

    window = MainWindow(
        lambda: VideoSession(OpenCVVideoReader()), ProjectRepository(),
        FFprobeTimingProbe(),
    )
    qtbot.addWidget(window)
    window.show()
    assert window.openVideo(synthetic_video_path, show_error=False)
    session = window.analysisSession
    tracks = {role: session.add_track(window.activeVideoId, role) for role in ROLE_ORDER}
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
    session._verified_videos.add(window.activeVideoId)
    return window, session, experiment


def _train_success_result(request, job_dir: Path) -> dict:
    config_file = job_dir / "config.yaml"
    config_file.parent.mkdir(parents=True, exist_ok=True)
    config_file.write_text("bodyparts: four\n", encoding="utf-8")
    snapshot = job_dir / "dlc-project" / "snapshot.pt"
    snapshot.parent.mkdir(parents=True, exist_ok=True)
    snapshot.write_bytes(b"weights")

    def out(rel: str) -> dict:
        data = (job_dir / rel).read_bytes()
        return {"path": rel, "size": len(data),
                "sha256": hashlib.sha256(data).hexdigest()}

    return {
        "status": "success", "python": "3.12", "executable": "/usr/bin/python",
        "platform": "test", "machine": "arm64", "actual_device": "cpu",
        "outputs": [out("config.yaml"), out("dlc-project/snapshot.pt")],
        RESULT_SECTION: {
            "label_digest": request.label_digest,
            "video_sha256": request.video_sha256,
            "check_frames": list(request.check_frames),
            "bodyparts": list(ROLE_ORDER), "engine_version": "3.0.1-test",
            "config_path": "config.yaml",
            "model_snapshot": "dlc-project/snapshot.pt",
            "epochs_completed": 1,
        },
    }


class TestJointTrainingFlow:
    def test_success_registers_model_with_elapsed(
        self, qtbot, tmp_path, long_video_path
    ):
        window, session, experiment = _experiment_window(qtbot, tmp_path, long_video_path)
        window.modelActions.deleteLater()
        from ai_physics_tracker.gui.model_actions import ModelActions

        class _Runner:
            def start_training(self, project_root, request, *, device="cpu"):
                job_dir = Path(project_root) / "data" / "engines" / request.run_id
                result = _train_success_result(request, job_dir)
                pose = job_dir / "dlc-project/dlc-models-pytorch/iteration-0/test/train/pytorch_config.yaml"
                pose.parent.mkdir(parents=True)
                pose.write_text("net: resnet_50\n", encoding="utf-8")
                return _FakeHandle(result)

            def start_selftest(self, project_root, model_id, fields, *, device="cpu"):
                return _FakeHandle({
                    "status": "success", "actual_device": "cpu", "model_selftest": {
                        "config_sha256": fields["config_sha256"],
                        "checkpoint_sha256": fields["checkpoint_sha256"],
                        "pose_cfg_sha256": fields["pose_cfg_sha256"],
                        "frame_sha256": "f" * 64, "frame_index": 0,
                        "bodyparts_found": list(ROLE_ORDER),
                        "versions": {"deeplabcut": "3.0.1"},
                    },
                })

        window.modelActions = ModelActions(window, runner_factory=_Runner)
        window.modelActions.runJointTraining()
        assert window.modelActions.busy
        window.modelActions._poll()
        assert window.modelActions.busy
        assert window.modelActions._job_kind == "selftest"
        window.modelActions._poll()
        assert not window.modelActions.busy
        references = session.project.model_references
        assert len(references) == 1
        assert references[0].origin == "trained"
        assert references[0].compatibility_state == "compatible"
        run = next(
            r for r in session.project.tracking_runs
            if r.run_id == references[0].source_train_run_id
        )
        assert run.status == "completed"
        assert run.extra_fields["elapsed_s"] == 12.5   # i3②
        assert "compatible" in window.statusBar().currentMessage()

    def test_failure_marks_run_failed(self, qtbot, tmp_path, long_video_path):
        window, session, experiment = _experiment_window(qtbot, tmp_path, long_video_path)
        from ai_physics_tracker.gui.model_actions import ModelActions

        window.modelActions.deleteLater()
        window.modelActions = ModelActions(
            window, runner_factory=_FakeRunnerFactory({
                "status": "failed", "error": {"type": "RuntimeError", "message": "boom"},
            })
        )
        window.modelActions.runJointTraining()
        window.modelActions._poll()
        runs = [r for r in session.project.tracking_runs if r.task_type == "train"]
        assert runs and runs[0].status == "failed"
        assert "boom" in window.statusBar().currentMessage()

    def test_cancel_routes_through_handle_cancel(self, qtbot, tmp_path, long_video_path):
        """i3①:取消必须经 handle.cancel(迟到 success 拒绝的唯一入口)。"""
        window, session, experiment = _experiment_window(qtbot, tmp_path, long_video_path)
        from ai_physics_tracker.gui.model_actions import ModelActions

        window.modelActions.deleteLater()
        factory = _FakeRunnerFactory(alive_first_polls=100)
        window.modelActions = ModelActions(window, runner_factory=factory)
        window.modelActions.runJointTraining()
        assert window.modelActions.busy
        window.modelActions.cancel()
        # fake handle cancel 后 join 即返回;下一次 poll 读 cancelled result
        handle = window.modelActions._handle
        handle._result = {"status": "cancelled"}
        window.modelActions._poll()
        assert not window.modelActions.busy
        assert handle.cancelled
        runs = [r for r in session.project.tracking_runs if r.task_type == "train"]
        assert runs and runs[0].status == "cancelled"


class TestSelftestFlow:
    @pytest.mark.parametrize("outcome", ["success", "failed", "cancelled", "late_cancel", "session_swap", "rejected"])
    def test_selftest_success_applies_compatible(self, qtbot, tmp_path, long_video_path, outcome):
        import yaml

        window, session, experiment = _experiment_window(qtbot, tmp_path, long_video_path)
        bundle = tmp_path / "bundle"
        bundle.mkdir()
        (bundle / "config.yaml").write_text(yaml.safe_dump({
            "Task": "t", "multianimalproject": False, "identity": False,
            "project_path": str(bundle), "bodyparts": list(ROLE_ORDER),
            "cropping": False, "engine": "pytorch",
        }), encoding="utf-8")
        (bundle / "snapshot-1.pt").write_bytes(b"w")
        (bundle / "pose_cfg.yaml").write_text("net: resnet_50\n", encoding="utf-8")
        reference = session.import_teacher_model(
            bundle, "config.yaml", "snapshot-1.pt",
            tuple((r, r) for r in ROLE_ORDER), extra_files=("pose_cfg.yaml",),
        )
        pose_bytes = (bundle / "pose_cfg.yaml").read_bytes()
        by_name = {Path(e.relative_path).name: e for e in reference.manifest}

        result = {
            "status": "success", "python": "3.12", "executable": "/x",
            "platform": "test", "machine": "arm64", "actual_device": "cpu",
            "outputs": [],
            "model_selftest": {
                "config_sha256": by_name["config.yaml"].sha256,
                "checkpoint_sha256": by_name["snapshot-1.pt"].sha256,
                "pose_cfg_sha256": hashlib.sha256(pose_bytes).hexdigest(),
                "frame_sha256": "f" * 64, "frame_index": 0,
                "bodyparts_found": sorted(ROLE_ORDER),
                "versions": {"torch": "2", "deeplabcut": "3.0.1"},
            },
        }
        from ai_physics_tracker.gui.model_actions import ModelActions

        window.modelActions.deleteLater()
        window.modelActions = ModelActions(
            window, runner_factory=_FakeRunnerFactory(result)
        )
        if outcome in ("failed", "cancelled"):
            result["status"] = outcome
        elif outcome == "rejected":
            result["model_selftest"]["config_sha256"] = "0" * 64
        continued = []
        window.modelActions.runSelftest(reference.model_id, on_success=lambda: continued.append(True))
        if outcome == "late_cancel":
            window.modelActions.cancel()
        elif outcome == "session_swap":
            window._annotation_session = None
        window.modelActions._poll()
        updated = session.project.model_references[0]
        assert updated.compatibility_state == ("compatible" if outcome == "success" else "unverified")
        assert continued == ([True] if outcome == "success" else [])
        assert not window.modelActions.busy
        assert window.modelActions._selftest_on_success is None
        assert not window.trackingActions.panel.cancelButton.isEnabled()


class TestImportDialogLogic:
    def test_propose_identity_mapping(self):
        mapping = propose_identity_mapping(list(ROLE_ORDER))
        assert mapping["tip"] == "tip" and mapping["pivot"] == "pivot"
        mapping2 = propose_identity_mapping(["bob", "top", "bottom", "axis"])
        assert all(v is None for v in mapping2.values())

    def test_dialog_load_and_mapping_validation(self, qtbot, tmp_path):
        import yaml

        from ai_physics_tracker.gui.teacher_import_dialog import TeacherImportDialog

        bundle = tmp_path / "b"
        bundle.mkdir()
        renamed = ["bob", "top", "bottom", "axis"]
        (bundle / "config.yaml").write_text(yaml.safe_dump({
            "multianimalproject": False, "identity": False,
            "project_path": str(bundle), "bodyparts": renamed,
            "cropping": False, "engine": "pytorch",
        }), encoding="utf-8")
        (bundle / "snap.pt").write_bytes(b"w")

        class _Win:
            statusBar = lambda self: None
            projectActions = None
            analysisSession = None

        dialog = TeacherImportDialog(_Win())
        qtbot.addWidget(dialog)
        assert dialog.load_bundle(bundle)
        assert [dialog.role_boxes[r].count() for r in ROLE_ORDER] == [4] * 4
        # 未选择完整映射 → collect 拒绝
        assert dialog.collect_mapping() is None
        for role, target in zip(ROLE_ORDER, renamed):
            dialog.role_boxes[role].setCurrentText(target)
        assert dialog.collect_mapping() == tuple(zip(ROLE_ORDER, renamed))
        # 同名冲突拒绝
        dialog.role_boxes["body_bottom"].setCurrentText("bob")
        assert dialog.collect_mapping() is None


class TestS6ReviewRegressions:
    def test_m2_start_failure_marks_run_failed(self, qtbot, tmp_path, long_video_path):
        """启动失败不得留下孤儿 pending run(否则 experiment 被永久锁死)。"""
        from ai_physics_tracker.application.model_worker import ModelWorkerError

        window, session, experiment = _experiment_window(qtbot, tmp_path, long_video_path)
        from ai_physics_tracker.gui.model_actions import ModelActions

        window.modelActions.deleteLater()

        class _BrokenRunner:
            def start_training(self, project_root, request, *, device="cpu"):
                raise ModelWorkerError("runtime python not found")

            def start_selftest(self, *a, **k):
                raise ModelWorkerError("broken")

        window.modelActions = ModelActions(window, runner_factory=_BrokenRunner)
        window.modelActions.runJointTraining()
        runs = [r for r in session.project.tracking_runs if r.task_type == "train"]
        assert runs and runs[0].status == "failed"
        assert not window.modelActions.busy
        # 实验不再被 active-run 守卫锁死:可再次 prepare
        from ai_physics_tracker.application.experiment_training_job import (
            prepare_experiment_training,
        )
        run2, _req = prepare_experiment_training(
            session, experiment.experiment_id, run_id=uuid4()
        )
        assert run2.status == "pending"

    def test_b1_session_swap_discards_result(self, qtbot, tmp_path, long_video_path):
        """session 被替换后完成的 job 结果必须被丢弃,且 UI 不永久 busy。"""
        window, session, experiment = _experiment_window(qtbot, tmp_path, long_video_path)
        from ai_physics_tracker.gui.model_actions import ModelActions

        window.modelActions.deleteLater()

        class _Runner:
            def __init__(self):
                self.handle = None

            def start_training(self, project_root, request, *, device="cpu"):
                job_dir = Path(project_root) / "data" / "engines" / request.run_id
                self.handle = _FakeHandle(_train_success_result(request, job_dir))
                return self.handle

            def start_selftest(self, *a, **k):
                return _FakeHandle(None)

        runner = _Runner()
        window.modelActions = ModelActions(window, runner_factory=lambda: runner)
        window.modelActions.runJointTraining()
        assert window.modelActions.busy
        # 模拟项目被替换(guarded 阻断生产路径,这里直接构造异常态验证兜底)
        window._annotation_session = None
        window.modelActions._poll()
        assert not window.modelActions.busy
        assert runner.handle.cancelled

    def test_m1_user_cancel_after_force_kill_is_cancelled(
        self, qtbot, tmp_path, long_video_path
    ):
        """真实训练取消路径:worker 不响应 → 强杀 → read_result 抛错 → cancelled。"""
        from ai_physics_tracker.gui.model_actions import ModelActions
        from ai_physics_tracker.infrastructure.external_worker import (
            ExternalWorkerError,
        )

        window, session, experiment = _experiment_window(qtbot, tmp_path, long_video_path)
        window.modelActions.deleteLater()

        class _StubbornHandle(_FakeHandle):
            def read_result(self):
                raise ExternalWorkerError(
                    "worker was force-terminated; late result is rejected")

        class _Runner:
            def start_training(self, project_root, request, *, device="cpu"):
                return _StubbornHandle()

            def start_selftest(self, *a, **k):
                return _StubbornHandle()

        window.modelActions = ModelActions(window, runner_factory=_Runner)
        window.modelActions.runJointTraining()
        window.modelActions.cancel()
        window.modelActions._poll()
        runs = [r for r in session.project.tracking_runs if r.task_type == "train"]
        assert runs and runs[0].status == "cancelled"
        assert "cancelled" in window.statusBar().currentMessage()

    def test_shutdown_cancels_inflight(self, qtbot, tmp_path, long_video_path):
        window, session, experiment = _experiment_window(qtbot, tmp_path, long_video_path)
        handle_holder = {}

        class _Runner:
            def start_training(self, project_root, request, *, device="cpu"):
                job_dir = Path(project_root) / "data" / "engines" / request.run_id
                handle = _FakeHandle(None, alive_first_polls=1000)
                handle_holder["h"] = handle
                return handle

            def start_selftest(self, *a, **k):
                return _FakeHandle(None)

        from ai_physics_tracker.gui.model_actions import ModelActions

        window.modelActions.deleteLater()
        window.modelActions = ModelActions(window, runner_factory=_Runner)
        window.modelActions.runJointTraining()
        assert window.modelActions.busy
        window.modelActions.shutdown()
        assert handle_holder["h"].cancelled

    def test_m3_unmapped_role_rejected(self, qtbot, tmp_path):
        import yaml

        from ai_physics_tracker.gui.teacher_import_dialog import TeacherImportDialog

        bundle = tmp_path / "m3"
        bundle.mkdir()
        renamed = ["bob", "top", "bottom", "axis"]
        (bundle / "config.yaml").write_text(yaml.safe_dump({
            "multianimalproject": False, "identity": False,
            "project_path": str(bundle), "bodyparts": renamed,
            "cropping": False, "engine": "pytorch",
        }), encoding="utf-8")
        (bundle / "snap.pt").write_bytes(b"w")

        class _Win:
            statusBar = lambda self: None

        dialog = TeacherImportDialog(_Win())
        qtbot.addWidget(dialog)
        assert dialog.load_bundle(bundle)
        # 只显式映射三个 role,第四个保持未选 → collect 拒绝(修复前会静默
        # 落到第 0 项通过)
        for role, target in zip(list(ROLE_ORDER)[:3], renamed[1:4]):
            dialog.role_boxes[role].setCurrentText(target)
        assert dialog.collect_mapping() is None


class TestFreezeFixedCheck:
    def test_freeze_via_confirmation(self, qtbot, tmp_path, long_video_path, monkeypatch):
        from PySide6.QtWidgets import QMessageBox

        window, session, experiment = _experiment_window(qtbot, tmp_path, long_video_path)
        monkeypatch.setattr(
            QMessageBox, "question",
            staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes),
        )
        window.modelActions.freezeFixedCheck()
        updated = session.pendulum_experiments()[0]
        assert updated.fixed_check is not None
        assert updated.fixed_check.frames  # 预选非空
        assert "frozen" in window.statusBar().currentMessage()

    def test_decline_keeps_state(self, qtbot, tmp_path, long_video_path, monkeypatch):
        from PySide6.QtWidgets import QMessageBox

        window, session, experiment = _experiment_window(qtbot, tmp_path, long_video_path)
        session.clear_experiment_fixed_check(experiment.experiment_id)  # 从未冻结态起步
        monkeypatch.setattr(
            QMessageBox, "question",
            staticmethod(lambda *a, **k: QMessageBox.StandardButton.No),
        )
        window.modelActions.freezeFixedCheck()
        assert session.pendulum_experiments()[0].fixed_check is None


class TestHrFeedback:
    """HR 2026-09-28 三条反馈的回归。"""

    def test_model_task_drives_activity_and_cancel(
        self, qtbot, tmp_path, long_video_path
    ):
        """反馈①:模型任务必须有 Activity 文案 + Cancel 可用。"""
        window, session, experiment = _experiment_window(qtbot, tmp_path, long_video_path)
        window.modelActions.deleteLater()
        from ai_physics_tracker.gui.model_actions import ModelActions

        class _Runner:
            def start_training(self, project_root, request, *, device="cpu"):
                job_dir = Path(project_root) / "data" / "engines" / request.run_id
                return _FakeHandle(_train_success_result(request, job_dir))

            def start_selftest(self, *a, **k):
                return _FakeHandle(None)

        window.modelActions = ModelActions(window, runner_factory=_Runner)
        window.modelActions.runJointTraining()
        panel = window.trackingActions.panel
        assert panel.stageLabel.text() == "Training (external worker)"
        assert panel.cancelButton.isEnabled()
        window.modelActions._poll()
        assert panel.stageLabel.text() == "Completed"
        assert not panel.cancelButton.isEnabled()

    def test_cancel_button_routes_to_model(self, qtbot, tmp_path, long_video_path):
        window, session, experiment = _experiment_window(qtbot, tmp_path, long_video_path)
        window.modelActions.deleteLater()
        from ai_physics_tracker.gui.model_actions import ModelActions

        class _Runner:
            def start_training(self, project_root, request, *, device="cpu"):
                return _FakeHandle(None, alive_first_polls=1000)

            def start_selftest(self, *a, **k):
                return _FakeHandle(None)

        window.modelActions = ModelActions(window, runner_factory=_Runner)
        window.modelActions.runJointTraining()
        handle = window.modelActions._handle
        handle._result = {"status": "cancelled"}
        window.trackingActions.panel.cancelButton.click()   # → modelActions.cancel
        assert handle.cancelled

    def test_guided_context_not_no_track(self, qtbot, tmp_path, long_video_path, monkeypatch):
        """反馈②:引导模式头部不得显示 "No track" 无提示。"""
        window, session, experiment = _experiment_window(qtbot, tmp_path, long_video_path)
        window._guide_experiment_id = experiment.experiment_id
        window.trackingActions.refresh()
        context = window.trackingActions.panel.contextLabel.text()
        assert "Guided marking" in context
        assert "No track" not in context

    def test_history_label_has_local_time(self, qtbot, tmp_path, long_video_path):
        """反馈③:history 条目带本地时间。"""
        from ai_physics_tracker.domain.tracking_run import create_tracking_run

        window, session, experiment = _experiment_window(qtbot, tmp_path, long_video_path)
        free_track = session.add_track(window.activeVideoId, "free track")
        session.record_tracking_run(create_tracking_run(
            video_id=window.activeVideoId,
            member_track_ids=free_track.track_id,
            task_type="train",
        ))
        window.trackingActions.refresh()
        labels = [window.trackingActions.panel.historyList.item(i).text()
                  for i in range(window.trackingActions.panel.historyList.count())]
        import re as _re
        assert labels and all(
            _re.match(r"^\d{4}-\d\d-\d\d \d\d:\d\d:\d\d · ", label) for label in labels
        ), labels[:3]
