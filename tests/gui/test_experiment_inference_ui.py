"""P1.4-S4 联合推理/审核/激活 GUI 的 Qt offscreen 测试。

假 runner/handle 驱动推理收尾链(prepare→poll→verify→candidate),验证
workflow 卡片阶梯、审核队列(accept/skip/correct/finish)、四轨激活/
替换/清除与失败/取消路径。正确性守卫(session 层)已在
test_experiment_inference_job.py 覆盖,此处验证 GUI 编排。
"""

from __future__ import annotations

import csv
import hashlib
from pathlib import Path
from uuid import uuid4

import pytest

from ai_physics_tracker.application.experiment_inference_job import (
    RESULT_SECTION, prepare_experiment_inference,
)
from ai_physics_tracker.application.project_session import ProjectSession
from ai_physics_tracker.application.tracking_types import InferenceParams
from ai_physics_tracker.application.video import VideoStreamInfo
from ai_physics_tracker.application.workflow_projection import (
    select_task_card,
)
from ai_physics_tracker.domain.pendulum import ROLE_ORDER, PendulumRoles
from ai_physics_tracker.domain.project import create_project
from ai_physics_tracker.domain.teacher_model import (
    ModelManifestEntry, TeacherModelReference, build_manifest_hash,
)
from ai_physics_tracker.domain.types import utc_now
from ai_physics_tracker.infrastructure.hashing import file_sha256
from ai_physics_tracker.infrastructure.project_repository import ProjectRepository

pytestmark = pytest.mark.usefixtures("qapp")

_MIN_CONFIDENCE = 0.6


class _FakeHandle:
    def __init__(self, result: dict | None, *, alive_first_polls: int = 0):
        self._result = result
        self._alive_count = alive_first_polls
        self.cancelled = False
        self.elapsed_s_value = 21.0

    def is_alive(self) -> bool:
        if self._alive_count > 0:
            self._alive_count -= 1
            return True
        return False

    def cancel(self) -> None:
        self.cancelled = True
        self._alive_count = 0

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


def _write_model(root: Path) -> TeacherModelReference:
    """在项目内落一个静态 compatible 的 imported 模型(含自检证据)。"""

    model_id = uuid4()
    folder = root / "models" / str(model_id)
    folder.mkdir(parents=True)
    for name, data in (
        ("config.yaml", b"engine: pytorch\n"),
        ("snapshot-1.pt", b"checkpoint"),
        ("pytorch_config.yaml", b"pose"),
    ):
        (folder / name).write_bytes(data)
    manifest = tuple(ModelManifestEntry(
        f"models/{model_id}/{file.name}", file.stat().st_size, file_sha256(file)
    ) for file in sorted(folder.iterdir()))
    mapping = tuple((role, role) for role in ROLE_ORDER)
    return TeacherModelReference(
        model_id=model_id, origin="imported", created_at=utc_now(),
        bodypart_mapping=mapping,
        config_path=f"models/{model_id}/config.yaml",
        checkpoint_path=f"models/{model_id}/snapshot-1.pt",
        manifest=manifest, manifest_hash=build_manifest_hash(manifest),
        compatibility_state="compatible",
        self_test_evidence={
            "model_manifest_hash": build_manifest_hash(manifest),
            "bodypart_mapping": [list(pair) for pair in mapping],
            "pose_cfg_sha256": file_sha256(folder / "pytorch_config.yaml"),
            "runtime": {"device": "cpu", "versions": {
                "deeplabcut": "3.0.1", "torch": "2.13.0",
            }},
        },
    )


def _inject_model(session: ProjectSession, model: TeacherModelReference) -> None:
    from dataclasses import replace

    session._project = replace(
        session.project, model_references=(model,))


def _infer_result(request, job_dir: Path) -> dict:
    """四 role CSV artifact;frame 2 的 tip 低置信保证审核队列非空。"""

    job_dir.mkdir(parents=True, exist_ok=True)
    artifact = job_dir / "predictions.csv"
    with artifact.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(["scorer", *["DLC"] * 12])
        writer.writerow(["bodyparts", *[role for role in ROLE_ORDER for _ in range(3)]])
        writer.writerow(["coords", *[c for _ in ROLE_ORDER
                                      for c in ("x", "y", "likelihood")]])
        for frame in range(request.frame_count):
            values = []
            for _role in ROLE_ORDER:
                confidence = (
                    0.2 if (frame == 2 and _role == "tip") else 0.9)
                values.extend((1.0 + frame, 2.0 + frame, confidence))
            writer.writerow([frame, *values])

    def out(rel: str) -> dict:
        data = (job_dir / rel).read_bytes()
        return {"path": rel, "size": len(data),
                "sha256": hashlib.sha256(data).hexdigest()}

    return {
        "status": "success", "python": "3.12", "executable": "/usr/bin/python",
        "platform": "test", "machine": "arm64", "actual_device": "cpu",
        "outputs": [out(artifact.name)],
        RESULT_SECTION: {
            "input_digest": request.input_digest,
            "video_sha256": request.video_sha256,
            "model_manifest_hash": request.model_manifest_hash,
            "bodypart_mapping": [list(pair) for pair in request.bodypart_mapping],
            "frame_count": request.frame_count,
            "prediction_path": artifact.name,
            "scorer": "DLC", "engine_version": "3.0.1",
            "versions": request.expected_runtime_versions,
            "complete_count": request.frame_count,
            "missing_by_role": {role: 0 for role in ROLE_ORDER},
        },
    }


class _Runner:
    """假 ModelWorkerRunner:成功推理(fake artifact)。"""

    def __init__(self, result_factory=_infer_result):
        self.result_factory = result_factory

    def start_inference(self, project_root, request, *, device="cpu"):
        job_dir = Path(project_root) / "data" / "engines" / request.run_id
        return _FakeHandle(self.result_factory(request, job_dir))


class _FailRunner:
    def start_inference(self, project_root, request, *, device="cpu"):
        return _FakeHandle({
            "status": "failed",
            "error": {"type": "RuntimeError", "message": "boom"},
        })


def _install(window, runner):
    from ai_physics_tracker.gui.experiment_inference_actions import (
        ExperimentInferenceActions,
    )

    window.experimentInferenceActions.deleteLater()
    window.experimentInferenceActions = ExperimentInferenceActions(
        window, runner_factory=lambda: runner)
    return window.experimentInferenceActions


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
    session._verified_videos.add(window.activeVideoId)
    experiment = session.pendulum_experiments()[0]
    from ai_physics_tracker.domain.pendulum import PhysicalParameters

    session.set_fixed_pivot(experiment.experiment_id, (10.0, 12.0))
    session.set_true_vertical(experiment.experiment_id, (10.0, 2.0), (10.0, 40.0))
    session.confirm_true_vertical(experiment.experiment_id)
    session.set_physical(experiment.experiment_id, PhysicalParameters(
        length_m=1.2, g_m_s2=9.8, length_source="measured", g_source="assumed"))
    session.set_release_frame(experiment.experiment_id, 1)
    session.add_calibration(
        experiment.video_id, (0.0, 0.0), (10.0, 0.0), 2.0, "cm")
    model = _write_model(session.project_root)
    _inject_model(session, model)
    return window, session, session.pendulum_experiments()[0], model


def _run_inference(controller, session, experiment, model) -> object:
    """完整链 prepare→verify→update(activation/review 需要冻结身份)。"""

    from ai_physics_tracker.application.experiment_inference_job import (
        verify_experiment_inference_result,
    )
    from ai_physics_tracker.domain.tracking_run import mark_run_running

    run, request = prepare_experiment_inference(
        session, experiment.experiment_id, model.model_id,
        InferenceParams(min_confidence=_MIN_CONFIDENCE, batch_size=4, device="cpu"),
    )
    session.update_tracking_run(mark_run_running(run))
    job_dir = session.project_root / "data" / "engines" / str(run.run_id)
    result = _infer_result(request, job_dir)
    completed = verify_experiment_inference_result(
        session, run, request, result, job_dir)
    session.update_tracking_run(completed)
    return completed


def _current_card(window, session):
    from ai_physics_tracker.application.workflow_projection import (
        project_workflow_state,
    )

    experiment = window.currentPendulumExperiment()
    track_id = experiment.roles.tip if experiment is not None else window.selectedTrackId
    state = project_workflow_state(
        session, track_id, session.tracking_runs(), experiment=experiment,
    )
    return select_task_card(state), state


def _wait_presented(qtbot, window, frame):
    if frame is not None:
        qtbot.waitUntil(
            lambda: window.presented_frame_index == frame, timeout=3000)


# ---------------------------------------------------------------------------
# workflow 卡片阶梯(投影层)
# ---------------------------------------------------------------------------


class TestJointLadderCards:
    def _session(self, tmp_path, synthetic_video_path):
        from ai_physics_tracker.domain.pendulum import PhysicalParameters

        session = ProjectSession(ProjectRepository(), create_project("joint"))
        video, _ = session.register_external_video(synthetic_video_path, VideoStreamInfo(
            width_px=64, height_px=48, fps_container=10.0, frame_count=5,
            container_format="avi", timing_status="cfr",
        ))
        tracks = {role: session.add_track(video.video_id, role) for role in ROLE_ORDER}
        session.save_as_publication(
            tmp_path / "publication",
            PendulumRoles(*(tracks[role].track_id for role in ROLE_ORDER)),
        )
        experiment = session.pendulum_experiments()[0]
        # 补全 setup,否则卡片停在 1.5 checklist 而非 1.6 joint 阶梯
        session.set_fixed_pivot(experiment.experiment_id, (10.0, 12.0))
        session.set_true_vertical(experiment.experiment_id, (10.0, 2.0), (10.0, 40.0))
        session.confirm_true_vertical(experiment.experiment_id)
        session.set_physical(experiment.experiment_id, PhysicalParameters(
            length_m=1.2, g_m_s2=9.8, length_source="measured", g_source="assumed"))
        session.set_release_frame(experiment.experiment_id, 1)
        session.add_calibration(
            experiment.video_id, (0.0, 0.0), (10.0, 0.0), 2.0, "cm")
        return session, session.pendulum_experiments()[0]

    def _state(self, session, experiment):
        from ai_physics_tracker.application.workflow_projection import (
            project_workflow_state,
        )

        experiment_id = experiment.experiment_id
        track_id = experiment.roles.tip
        refreshed = session.pendulum_experiment(experiment_id)
        return project_workflow_state(
            session, track_id, session.tracking_runs(), experiment=refreshed,
        )

    def test_baseline_card_offers_inference_with_compatible_model(
        self, tmp_path, synthetic_video_path,
    ):
        session, experiment = self._session(tmp_path, synthetic_video_path)
        state = self._state(session, experiment)
        assert state.pendulum.missing == ("tip_radius_reference",)  # QC参考不能阻断训练/推理
        card = select_task_card(state)
        inference = next(
            a for a in card.secondary if a.action_id == "run_joint_inference")
        assert not inference.enabled
        assert "self-test" in (inference.reason or "")
        model = _write_model(session.project_root)
        _inject_model(session, model)
        card = select_task_card(self._state(session, experiment))
        inference = next(
            a for a in card.secondary if a.action_id == "run_joint_inference")
        assert inference.enabled

    def test_pending_run_shows_running_card_then_candidate_card(
        self, tmp_path, synthetic_video_path,
    ):
        session, experiment = self._session(tmp_path, synthetic_video_path)
        model = _write_model(session.project_root)
        _inject_model(session, model)
        run, _request = prepare_experiment_inference(
            session, experiment.experiment_id, model.model_id,
            InferenceParams(min_confidence=_MIN_CONFIDENCE, device="cpu"),
        )
        card = select_task_card(self._state(session, experiment))
        assert card.title.startswith("Current: joint inference running")
        assert card.primary is None

        # 完成→candidate 卡:审核主行 + 激活次行
        from dataclasses import replace as _replace
        from ai_physics_tracker.domain.tracking_run import mark_run_completed

        completed = mark_run_completed(run)
        completed = _replace(
            completed,
            extra_fields={
                **completed.extra_fields,
                "prediction_path": "data/engines/x/predictions.csv",
                "prediction_sha256": "0" * 64,
                "input_digest": completed.config["input_digest"],
                "video_sha256": "0" * 64,
                "verified_min_confidence": _MIN_CONFIDENCE,
                "scorer": "DLC", "complete_count": 5,
                "missing_by_role": {role: 0 for role in ROLE_ORDER},
            },
        )
        session.update_tracking_run(completed)
        from ai_physics_tracker.application.workflow_projection import (
            select_task_card as _select,
        )

        state = self._state(session, experiment)
        card = _select(state)
        assert card.title.startswith("Current: joint candidate ready")
        assert card.primary.action_id == "review_joint_candidate"
        assert card.secondary[0].action_id == "activate_experiment"

        # 激活后:active + candidate(新推理)→ Replace/Clear;无 candidate → 测量卡
        from ai_physics_tracker.domain.pendulum import (
            PendulumExperiment,
        )
        activated = _replace(
            session.pendulum_experiment(experiment.experiment_id),
            active_infer_run_id=run.run_id,
        )
        from dataclasses import replace as _r

        session._project = _r(
            session.project,
            experiments=(activated,) if not session.project.experiments else tuple(
                activated if e.experiment_id == activated.experiment_id else e
                for e in session.project.experiments),
        )
        state = self._state(session, experiment)
        card = _select(state)
        assert card.mode == "analyze"
        assert card.title.startswith("Current: experiment measurement active")
        ids = [a.action_id for a in card.secondary]
        assert {"review_joint_candidate", "run_joint_inference",
                "clear_experiment"} <= set(ids)


# ---------------------------------------------------------------------------
# GUI 控制器:推理/取消/失败
# ---------------------------------------------------------------------------


class TestInferenceController:
    def test_success_creates_candidate_and_card(self, qtbot, tmp_path, synthetic_video_path):
        window, session, experiment, model = _experiment_window(
            qtbot, tmp_path, synthetic_video_path)
        controller = _install(window, _Runner())
        controller.runJointInference(
            model.model_id,
            InferenceParams(min_confidence=_MIN_CONFIDENCE, batch_size=4, device="cpu"))
        assert controller.busy
        controller._poll()
        assert not controller.busy
        runs = [r for r in session.tracking_runs()
                if r.task_type == "infer" and r.status == "completed"]
        assert len(runs) == 1
        assert runs[0].extra_fields["elapsed_s"] == 21.0
        assert experiment.active_infer_run_id is None   # candidate 不自动生效
        card, _state = _current_card(window, session)
        assert card.title.startswith("Current: joint candidate ready")

    def test_failure_marks_run_failed(self, qtbot, tmp_path, synthetic_video_path):
        window, session, experiment, model = _experiment_window(
            qtbot, tmp_path, synthetic_video_path)
        controller = _install(window, _FailRunner())
        controller.runJointInference(
            model.model_id,
            InferenceParams(min_confidence=_MIN_CONFIDENCE, device="cpu"))
        controller._poll()
        runs = [r for r in session.tracking_runs() if r.task_type == "infer"]
        assert runs and runs[0].status == "failed"
        assert not controller.busy

    def test_cancel_marks_run_cancelled(self, qtbot, tmp_path, synthetic_video_path):
        window, session, experiment, model = _experiment_window(
            qtbot, tmp_path, synthetic_video_path)
        controller = _install(window, _Runner())
        controller.runJointInference(
            model.model_id,
            InferenceParams(min_confidence=_MIN_CONFIDENCE, device="cpu"))
        controller.cancel()
        controller._user_cancel = True
        # read_result 协议错误时按取消收尾(M1 语义:强杀=取消)
        controller._handle._result = None
        controller._poll()
        runs = [r for r in session.tracking_runs() if r.task_type == "infer"]
        assert runs and runs[0].status == "cancelled"


# ---------------------------------------------------------------------------
# GUI 控制器:审核队列
# ---------------------------------------------------------------------------


class TestReviewQueue:
    def test_suggestions_allow_one_point_correction_without_forced_progress(
        self, qtbot, tmp_path, synthetic_video_path,
    ):
        window, session, experiment, model = _experiment_window(
            qtbot, tmp_path, synthetic_video_path)
        controller = _install(window, _Runner())
        run = _run_inference(controller, session, experiment, model)
        controller.openReviewQueue(run.run_id)
        assert controller.review_open
        assert controller._review_frames
        assert not hasattr(controller._dialog, "acceptAllButton")
        assert "small batches" in controller._dialog.infoLabel.text()
        _wait_presented(qtbot, window, controller._review_current)

        current = controller._review_current
        controller.startCorrect("tip")
        assert controller.is_correcting
        assert window.videoView.is_annotation_mode()
        assert controller.handleCorrectClick(6.5, 7.5)
        assert not controller.is_correcting
        assert controller._review_current == current
        point = session.effective_point(experiment.roles.tip, current)
        assert point is not None and point.source == "manual"
        assert point.pixel_x == 6.5 and point.pixel_y == 7.5
        record = controller._records()[current]
        assert record["disposition"] == "corrected"
        assert "tip" in record["manual_point_ids"]

        controller.finishReviewing()
        assert not controller.review_open
        assert window.videoView.preview_marker_views() == []
        # 重开恢复进度
        controller.openReviewQueue(run.run_id)
        assert controller.review_open
        assert controller._records()[current]["disposition"] == "corrected"

    def test_correct_click_rejected_on_frame_mismatch(
        self, qtbot, tmp_path, synthetic_video_path,
    ):
        window, session, experiment, model = _experiment_window(
            qtbot, tmp_path, synthetic_video_path)
        controller = _install(window, _Runner())
        run = _run_inference(controller, session, experiment, model)
        controller.openReviewQueue(run.run_id)
        controller.startCorrect("pivot")
        # 用户跳到别的帧后点击:拒绝,不写点(等帧真正呈现再点)
        away = 0 if controller._review_current != 0 else 1
        window.seekFrame(away)
        _wait_presented(qtbot, window, away)
        assert "Waiting for frame" in controller._dialog.progressLabel.text()
        assert not window.videoView.is_annotation_mode()
        assert not controller.handleCorrectClick(1.0, 1.0)
        assert session.project.observations == ()

    def test_selected_batch_continuously_marks_four_roles_and_only_selected_frames(
        self, qtbot, tmp_path, synthetic_video_path,
    ):
        from PySide6.QtCore import QPoint, Qt

        window, session, experiment, model = _experiment_window(
            qtbot, tmp_path, synthetic_video_path)
        controller = _install(window, _Runner())
        run = _run_inference(controller, session, experiment, model)
        controller.openReviewQueue(run.run_id)
        frames = controller._review_frames[::2][:2]
        assert len(frames) == 2
        for row in range(controller._dialog.frameList.count()):
            item = controller._dialog.frameList.item(row)
            item.setCheckState(Qt.CheckState.Checked if item.data(Qt.ItemDataRole.UserRole)
                               in frames else Qt.CheckState.Unchecked)
        before = (experiment.frame_set.frames
                  if experiment.frame_set is not None else ())
        controller._dialog.trainButton.click()
        merged = session.pendulum_experiment(
            experiment.experiment_id).frame_set.frames
        assert set(frames) | set(before) == set(merged)
        assert not window.experiment_guide_active
        assert controller.review_open and controller.is_correcting
        assert session.project.observations == ()
        for frame in frames:
            _wait_presented(qtbot, window, frame)
            qtbot.waitUntil(lambda: not window._has_pending_request)
            for index, role in enumerate(ROLE_ORDER):
                assert controller._correcting_role == role
                assert role in window.calibrationGuideLabel.text()
                window.videoView.mapScreenToPixel = lambda _pos, i=index: (6.0 + i, 7.0)
                window.videoView.annotationClicked.emit(QPoint(10, 10))
                point = session.effective_point(experiment.roles.track_id_for(role), frame)
                assert point is not None and point.pixel_x == 6.0 + index
                if index < 3:
                    assert controller._review_current == frame
                    assert any(p.source == "manual" and p.pixel_x == 6.0 + index
                               for p in window.videoView.preview_marker_views())
        assert not controller.is_correcting
        assert "2 relabeled" in controller._dialog.progressLabel.text()
        assert {p.frame_index for p in session.project.observations} == set(frames)
        qtbot.waitUntil(lambda: not window.projectActions.busy)
        reopened = ProjectSession.load(ProjectRepository(), session.project_root)
        assert len(reopened.project.observations) == 8

    def test_batch_loop_refresh_and_pool(
        self, qtbot, tmp_path, synthetic_video_path,
    ):
        """用户决策(2026-09-30):总困难池作为信息展示;每批 Suggest N 帧,
        标完自动推荐下一批;随时可 Done-labeling 直接走训练准备。"""

        window, session, experiment, model = _experiment_window(
            qtbot, tmp_path, synthetic_video_path)
        controller = _install(window, _Runner())
        run = _run_inference(controller, session, experiment, model)
        controller.openReviewQueue(run.run_id)
        dialog = controller._dialog
        # 池信息 + 默认每批 15(≤ 视频帧数时全部推荐且默认全选)
        assert "Difficulty pool" in dialog.poolLabel.text()
        assert dialog.suggestSpin.value() == 15
        assert dialog.checkedFrames() == controller._review_frames
        # Refresh 用新 N 重算并保持全选
        controller.refreshSuggestions(3)
        assert controller._suggest_count == 3
        assert dialog.suggestion_count() == 3
        assert len(controller._review_frames) <= 3
        assert dialog.checkedFrames() == controller._review_frames
        # 无勾选 Start 有提示,不静默
        controller._dialog.frameList.item(0).setCheckState(
            __import__("PySide6.QtCore", fromlist=["Qt"]).Qt.CheckState.Unchecked)
        for row in range(1, controller._dialog.frameList.count()):
            controller._dialog.frameList.item(row).setCheckState(
                __import__("PySide6.QtCore", fromlist=["Qt"]).Qt.CheckState.Unchecked)
        controller.startRelabelSelected()
        assert "Check at least one" in window.statusBar().currentMessage()
        for row in range(controller._dialog.frameList.count()):
            item = controller._dialog.frameList.item(row)
            item.setCheckState(
                __import__("PySide6.QtCore", fromlist=["Qt"]).Qt.CheckState.Checked
                if row == 0 else
                __import__("PySide6.QtCore", fromlist=["Qt"]).Qt.CheckState.Unchecked)
        # 标完第一批(1 帧)后自动推荐下一批(排除已 complete 帧)
        from PySide6.QtCore import QPoint, Qt

        first = controller._dialog.checkedFrames()
        assert len(first) == 1
        controller.startRelabelSelected()
        _wait_presented(qtbot, window, first[0])
        qtbot.waitUntil(lambda: not window._has_pending_request)
        for index, role in enumerate(ROLE_ORDER):
            window.videoView.mapScreenToPixel = lambda _pos, i=index: (6.0 + i, 7.0)
            window.videoView.annotationClicked.emit(QPoint(10, 10))
        assert not controller.is_correcting
        qtbot.waitUntil(
            lambda: controller._relabel_message.startswith("Next batch")
            or controller._relabel_message.startswith("No more"),
            timeout=4000)
        message = controller._relabel_message
        # 引导条只保留一句方向,长文案/按钮字样留在推荐窗(HR 第六轮反馈)
        guide_text = window.calibrationGuideLabel.text()
        assert "Batch finished" in guide_text
        assert "Done labeling" not in guide_text
        assert "Done labeling" in controller._dialog.progressLabel.text() or \
            message.startswith("No more") or message.startswith("Next batch")
        if controller._review_frames:
            assert message.startswith("Next batch")
            # 已标帧被排除:新一批不含 first
            assert first[0] not in controller._review_frames
            assert dialog.checkedFrames() == controller._review_frames
        else:
            assert message.startswith("No more")
        # Done labeling → fixed-check 失效 → freeze 流程
        frozen = []
        models = window.modelActions
        original_freeze = models.freezeFixedCheck
        models.freezeFixedCheck = lambda: frozen.append(True)
        try:
            controller.doneLabelingTrain()
        finally:
            models.freezeFixedCheck = original_freeze
        assert frozen == [True]
        assert not controller.review_open

    def test_pause_resumes_same_role_and_skip_moves_to_next_selected_frame(
        self, qtbot, tmp_path, synthetic_video_path,
    ):
        window, session, experiment, model = _experiment_window(
            qtbot, tmp_path, synthetic_video_path)
        controller = _install(window, _Runner())
        run = _run_inference(controller, session, experiment, model)
        controller.openReviewQueue(run.run_id)
        frames = controller._dialog.checkedFrames()
        controller.startRelabelSelected()
        _wait_presented(qtbot, window, frames[0])
        assert controller.handleCorrectClick(5.0, 6.0)
        controller.cancelCorrect()
        assert not controller.is_correcting
        qtbot.waitUntil(lambda: not window.projectActions.busy)
        controller.startRelabelSelected()
        assert controller._review_current == frames[0]
        assert controller._correcting_role == "body_top"
        controller.skipRelabelFrame()
        assert controller._review_current == frames[1]
        assert controller._correcting_role == "tip"
        assert len(session.manual_points(experiment.roles.body_top)) == 0

    def test_correct_click_via_video_signal_without_selected_track(
        self, qtbot, tmp_path, synthetic_video_path,
    ):
        """HR 反馈(2026-09-29):joint 审核不选 track 时点击被吞——钉住真实链路。"""

        from PySide6.QtCore import QPoint

        window, session, experiment, model = _experiment_window(
            qtbot, tmp_path, synthetic_video_path)
        controller = _install(window, _Runner())
        run = _run_inference(controller, session, experiment, model)
        controller.openReviewQueue(run.run_id)
        frame = controller._review_current
        _wait_presented(qtbot, window, frame)
        # joint 审核是 experiment 级:track 列表无选中(甚至中途取消选中)
        # 时,Correct 点击仍必须写点且不丢十字光标模式
        window.trackList.clearSelection()
        assert window.selectedTrackId is None
        controller.startCorrect("tip")
        assert window.videoView.is_annotation_mode()
        # startCorrect 内的 seekFrame 会再触发一次帧请求,等它落地再点击
        qtbot.waitUntil(lambda: not window._has_pending_request, timeout=3000)
        window.videoView.mapScreenToPixel = lambda _pos: (6.5, 7.5)
        window.videoView.annotationClicked.emit(QPoint(10, 10))
        point = session.effective_point(experiment.roles.tip, frame)
        assert point is not None and point.source == "manual"
        assert point.pixel_x == 6.5 and point.pixel_y == 7.5


# ---------------------------------------------------------------------------
# GUI 控制器:四轨激活/替换/清除
# ---------------------------------------------------------------------------


class TestActivation:
    def _confirmed(self, controller):
        controller._confirm = lambda *args, **kwargs: True
        return controller

    def test_activate_replace_clear(self, qtbot, tmp_path, synthetic_video_path):
        window, session, experiment, model = _experiment_window(
            qtbot, tmp_path, synthetic_video_path)
        controller = self._confirmed(_install(window, _Runner()))
        baseline_revision = session.pendulum_experiment(
            experiment.experiment_id).measurement_revision
        first = _run_inference(controller, session, experiment, model)
        controller.activateCandidate(first.run_id)
        assert session.pendulum_experiment(
            experiment.experiment_id).active_infer_run_id == first.run_id
        # 4 role × 5 帧 − 1:frame2 tip 置信 0.2 低于阈值 0.6 被激活筛选剔除
        assert len(session.project.observations) == 4 * 5 - 1
        controller.openReviewQueue()
        assert controller.review_open and controller._review_run_id == first.run_id
        controller.finishReviewing()

        second = _run_inference(controller, session, experiment, model)
        card, _state = _current_card(window, session)
        ids = [a.action_id for a in card.secondary]
        assert "replace_experiment" in ids and "clear_experiment" in ids
        controller.replaceCandidate(second.run_id)
        assert session.pendulum_experiment(
            experiment.experiment_id).active_infer_run_id == second.run_id
        controller.openReviewQueue()
        assert controller._review_run_id == second.run_id
        card, _state = _current_card(window, session)
        assert card.title.startswith("Current: experiment measurement active")
        controller.finishReviewing()

        controller.clearMeasurement()
        assert session.pendulum_experiment(
            experiment.experiment_id).active_infer_run_id is None
        assert session.project.observations == ()

        # 激活历史与 revision 留痕
        refreshed = session.pendulum_experiment(experiment.experiment_id)
        # setup 期也可能留 history 记录(如 role binding edit),只看末三条
        assert [r.action for r in refreshed.activation_history[-3:]] == [
            "activate", "replace", "clear"]
        # setup 动作同样递增 revision,断言相对增量
        assert refreshed.measurement_revision == baseline_revision + 3

    def test_confirm_declined_keeps_state(self, qtbot, tmp_path, synthetic_video_path):
        window, session, experiment, model = _experiment_window(
            qtbot, tmp_path, synthetic_video_path)
        controller = _install(window, _Runner())
        controller._confirm = lambda *args, **kwargs: False
        run = _run_inference(controller, session, experiment, model)
        controller.activateCandidate(run.run_id)
        assert session.pendulum_experiment(
            experiment.experiment_id).active_infer_run_id is None
        assert session.project.observations == ()


@pytest.mark.parametrize("changed", [False, True])
def test_unverified_model_checks_before_inference(qtbot, tmp_path, synthetic_video_path, monkeypatch, changed):
    from dataclasses import replace

    window, session, experiment, model = _experiment_window(qtbot, tmp_path, synthetic_video_path)
    _inject_model(session, replace(model, compatibility_state="unverified", self_test_evidence=None))
    controller = _install(window, _Runner())
    callbacks = []
    monkeypatch.setattr(window.modelActions, "runSelftest",
                        lambda model_id, *, on_success: callbacks.append(on_success))
    controller.runJointInference(model.model_id, InferenceParams(min_confidence=0.6))
    assert len(callbacks) == 1
    assert not controller.busy
    assert not session.tracking_runs()
    _inject_model(session, model)
    if changed:
        monkeypatch.setattr(window, "currentPendulumExperiment", lambda: None)
    callbacks[0]()
    assert controller.busy is (not changed)
    if not changed:
        controller._poll()
        assert len(session.tracking_runs()) == 1


def test_model_chooser_dates_and_verify_action(qtbot, tmp_path, synthetic_video_path):
    from dataclasses import replace
    from datetime import timedelta
    from types import SimpleNamespace
    from ai_physics_tracker.gui.joint_inference_dialog import JointInferenceDialog

    window, session, experiment, model = _experiment_window(qtbot, tmp_path, synthetic_video_path)
    started = model.created_at - timedelta(minutes=30)
    trained = replace(model, model_id=uuid4(), origin="trained", source_train_run_id=uuid4(),
                      source_experiment_id=experiment.experiment_id,
                      compatibility_state="unverified", self_test_evidence=None,
                      created_at=model.created_at + timedelta(minutes=1))
    dialog = JointInferenceDialog([model, trained], training_runs=[
        SimpleNamespace(run_id=trained.source_train_run_id, created_at=started)])
    qtbot.addWidget(dialog)
    assert dialog.selected_model_id() == trained.model_id
    assert dialog.modelList.item(0).text().startswith(started.astimezone().strftime("%Y-%m-%d %H:%M:%S"))
    assert dialog._ok_button.isEnabled() and dialog._ok_button.text() == "Verify & run"
    dialog.modelList.setCurrentRow(1)
    assert dialog._ok_button.text() == "Run inference"
