"""DifficultFrameReviewActions 的 GUI offscreen 测试（Phase 5.3 Slice 2）。

覆盖：
- AC-1: Mining 按钮可用性校验（项目保存、Track 匹配、completed infer run、产物完整性）；
- AC-2 / R3.1: 候选帧展示、AI prediction、score/reasons、跳帧定位与队列前后导航；
- AC-8: 同 run 排除已 Accept/Skip 帧；
- AC-9 / F4 / F6: 中性取消文案、取消按钮、算法 ComboBox itemData；
- 上下文切换守卫（R8）。
"""

from __future__ import annotations

import json
from pathlib import Path
from threading import Event
from typing import Any
from uuid import UUID, uuid4

import pytest
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtTest import QTest

from ai_physics_tracker.application.difficult_frame_job import (
    DifficultFrameJobRequest,
    DifficultFrameResult,
    DifficultFrameRunner,
)
from ai_physics_tracker.application.difficult_frames import MiningParams
from ai_physics_tracker.application.suggested_frame_review import (
    ActiveReviewBatch,
    ReviewCandidate,
    ReviewPredictionSnapshot,
)
from ai_physics_tracker.application.video_session import VideoSession
from ai_physics_tracker.domain.tracking_run import (
    create_tracking_run,
    mark_run_completed,
    mark_run_running,
)
from ai_physics_tracker.gui.main_window import MainWindow
from ai_physics_tracker.gui.suggested_frame_review_actions import DifficultFrameReviewActions
from ai_physics_tracker.infrastructure.opencv_video_reader import OpenCVVideoReader
from ai_physics_tracker.infrastructure.project_repository import ProjectRepository
from ai_physics_tracker.infrastructure.task_runner import TaskProgress, TaskResult


class _FakeHandle:
    def __init__(self) -> None:
        self._alive = True
        self._messages: list[Any] = []
        self.cancelled = False

    def poll_messages(self, limit: int | None = None) -> list[Any]:
        if limit is None:
            msgs, self._messages = self._messages, []
            return msgs
        msgs, self._messages = self._messages[:limit], self._messages[limit:]
        return msgs

    def is_alive(self) -> bool:
        return self._alive

    def cancel(self, timeout_s: float = 3.0) -> None:
        self.cancelled = True
        self._alive = False

    def die(self) -> None:
        self._alive = False

    def add_message(self, message: Any) -> None:
        self._messages.append(message)


class _FakeRunner:
    def __init__(self, *handles: _FakeHandle) -> None:
        self.handles = list(handles)
        self.calls = 0

    def start_task(self, run_id: UUID, target: Any, *args: Any, **kwargs: Any) -> _FakeHandle:
        del run_id, target, args, kwargs
        self.calls += 1
        if self.handles:
            return self.handles.pop(0)
        handle = _FakeHandle()
        handle.die()
        return handle

    def start(self, job_request: Any, request_id: UUID) -> _FakeHandle:
        return self.start_task(request_id, None, job_request)


class _StaticTimingProbe:
    def probe(self, path, cancel=None):
        del path, cancel
        from ai_physics_tracker.application.video_timing import TimingReport
        return TimingReport(
            status="cfr",
            reason="static GUI test timing",
            frame_count=5,
            fps_measured=10.0,
            fps_reference=10.0,
        )


@pytest.fixture
def test_window(tmp_path: Path, synthetic_video_path: Path, qtbot):
    """构建含单个 Video 与已保存项目的 MainWindow。"""
    from ai_physics_tracker.infrastructure.mock_engine_adapter import MockEngineAdapter

    window = MainWindow(
        lambda: VideoSession(OpenCVVideoReader()),
        ProjectRepository(),
        _StaticTimingProbe(),
    )
    qtbot.addWidget(window)
    window.show()
    window.trackingActions.adapter = MockEngineAdapter()
    window.frameSelectionActions.adapter = MockEngineAdapter()
    window.reviewActions.adapter = MockEngineAdapter()

    # 打开合成视频并建 Track
    assert window.openVideo(synthetic_video_path, show_error=False)
    window.addTrackButton.click()
    if not window.selectedTrackId and window.trackList.count() > 0:
        window.trackList.setCurrentRow(0)
    session = window.analysisSession
    assert session is not None
    if not window.selectedTrackId:
        track = session.add_track(window.activeVideoId)
        window._refreshTrackList()
        window.trackList.setCurrentRow(0)
    track_id = window.selectedTrackId
    assert track_id is not None
    session.mark_point(track_id, 0, 10.0, 10.0)
    session.mark_point(track_id, 1, 12.0, 12.0)
    session.mark_point(track_id, 2, 14.0, 14.0)

    # 保存项目以具备 project_root
    session.save_as(tmp_path / "project")
    window.projectActions.refresh()
    window.frameSelectionActions._refreshEnabled()
    window.reviewActions.refresh()
    QTest.qWait(50)

    yield window

    window.projectActions.close_allowed = True
    window.close()
    QTest.qWait(50)


def _setup_infer_run_with_prediction(window: MainWindow, tmp_path: Path):
    """辅助构造与当前 selectedTrackId 绑定的 completed infer run 和预测产物文件。"""
    session = window.analysisSession
    assert session is not None
    track_id = window.selectedTrackId
    if track_id is None and len(session.tracks) > 0:
        window.trackList.setCurrentRow(0)
        track_id = window.selectedTrackId
    assert track_id is not None
    video_id = window.activeVideoId
    assert video_id is not None

    run_id = uuid4()
    run_dir = session.project_root / "data" / "engines" / str(run_id)
    run_dir.mkdir(parents=True, exist_ok=True)
    pred_file = run_dir / "predictions.csv"
    pred_lines = [
        "scorer,MockDLC,MockDLC,MockDLC",
        "bodyparts,target,target,target",
        "coords,x,y,likelihood",
        "0,10.0,20.0,0.95",
        "1,12.0,22.0,0.40",
        "2,14.0,24.0,0.30",
    ]
    pred_file.write_text("\n".join(pred_lines) + "\n", encoding="utf-8")
    stat = pred_file.stat()

    model_file = run_dir / "model-snapshot.pt"
    model_file.write_bytes(b"dummy model")
    mstat = model_file.stat()

    run = mark_run_completed(
        mark_run_running(
            create_tracking_run(
                video_id=video_id,
                track_id=track_id,
                task_type="infer",
                engine="dlc",
                engine_version="3.0.1",
            )
        )
    )
    from dataclasses import replace
    run = replace(
        run,
        run_id=run_id,
        model_snapshot=f"data/engines/{run_id}/model-snapshot.pt",
        extra_fields={
            "prediction_path": f"data/engines/{run_id}/predictions.csv",
            "prediction_file_info": [stat.st_size, stat.st_mtime_ns],
            "model_file_info": [mstat.st_size, mstat.st_mtime_ns],
        },
    )
    session.record_tracking_run(run)
    window.trackingActions.panel.setRuns(session.tracking_runs(), track_id)
    return run


def test_mining_button_enablement_ac1(test_window: MainWindow, tmp_path: Path):
    """AC-1: 只有当前 Track 的 completed infer run 可启动 mining。"""
    window = test_window
    panel = window.trackingActions.panel
    actions = window.reviewActions

    # 1. 尚未选择 run -> 禁用
    actions.onRunSelected(None)
    assert not panel.mineButton.isEnabled()
    assert "Select a completed inference run" in panel.mineReasonLabel.text()

    # 构造合法的 completed infer run
    valid_run = _setup_infer_run_with_prediction(window, tmp_path)

    # 2. 选中 valid_run -> 启用
    actions.onRunSelected(valid_run.run_id)
    assert panel.mineButton.isEnabled()
    assert not panel.mineReasonLabel.isVisible()

    # 3. 未完成的 run (running) -> 禁用
    session = window.analysisSession
    from dataclasses import replace
    running_run = replace(valid_run, run_id=uuid4(), status="running")
    session.record_tracking_run(running_run)
    actions.onRunSelected(running_run.run_id)
    assert not panel.mineButton.isEnabled()
    assert "running, not completed" in panel.mineReasonLabel.text()

    # 4. 非 infer run (train) -> 禁用
    train_run = replace(valid_run, run_id=uuid4(), task_type="train")
    session.record_tracking_run(train_run)
    actions.onRunSelected(train_run.run_id)
    assert not panel.mineButton.isEnabled()
    assert "train, not infer" in panel.mineReasonLabel.text()

    # 5. 跨 Track 的 run -> 禁用
    other_track = session.add_track(window.activeVideoId)
    other_track_run = replace(valid_run, run_id=uuid4(), track_id=other_track.track_id)
    session.record_tracking_run(other_track_run)
    actions.onRunSelected(other_track_run.run_id)
    assert not panel.mineButton.isEnabled()
    assert "belongs to another track" in panel.mineReasonLabel.text()

    # 6. 切回 valid_run -> 重新可用
    actions.onRunSelected(valid_run.run_id)
    assert panel.mineButton.isEnabled()


def test_mining_cancellation_neutral_status_ac9(test_window: MainWindow, tmp_path: Path):
    """AC-9 / F4: 挖掘可被用户取消，取消态不显示为 Failed。"""
    window = test_window
    panel = window.trackingActions.panel
    valid_run = _setup_infer_run_with_prediction(window, tmp_path)

    fake_handle = _FakeHandle()
    fake_runner = _FakeRunner(fake_handle)
    window.reviewActions._runner = fake_runner

    window.reviewActions.onRunSelected(valid_run.run_id)
    assert panel.mineButton.isEnabled()

    # 点击挖掘
    panel.mineButton.click()
    QTest.qWait(50)
    assert window.reviewActions.busy
    assert panel.mineCancelButton.isVisible()
    assert panel.mineCancelButton.isEnabled()

    # 用户点击取消
    panel.mineCancelButton.click()
    QTest.qWait(50)

    assert not window.reviewActions.busy
    assert fake_handle.cancelled
    assert panel.mineStatusLabel.text() == "Mining cancelled"
    assert "Failed" not in panel.mineStatusLabel.text()


def test_frame_selection_cancellation_neutral_status_f4(test_window: MainWindow, qtbot):
    """F4 / AC-9: 代表帧选取可取消，且取消态不显示为 Failed。"""
    window = test_window
    panel = window.trackingActions.panel

    fake_handle = _FakeHandle()
    fake_runner = _FakeRunner(fake_handle)
    window.frameSelectionActions.runner = fake_runner

    assert panel.suggestButton.isEnabled()
    window.frameSelectionActions.requestSuggestion(n_frames=1, algorithm="uniform")
    qtbot.waitUntil(lambda: window.frameSelectionActions._handle is fake_handle, timeout=3000)

    assert window.frameSelectionActions.busy
    assert panel.suggestCancelButton.isVisible()
    assert panel.suggestCancelButton.isEnabled()

    # 点击取消
    panel.suggestCancelButton.click()
    qtbot.waitUntil(lambda: not window.frameSelectionActions.busy, timeout=3000)
    qtbot.waitUntil(lambda: fake_handle.cancelled, timeout=3000)

    assert panel.suggestStatusLabel.text() == "Frame selection cancelled"
    assert "Failed" not in panel.suggestStatusLabel.text()


def test_algorithm_combo_box_item_data_f6(test_window: MainWindow):
    """F6 / AC-9: 算法下拉框使用 itemData ("kmeans", "uniform")，不依赖显示文本。"""
    window = test_window
    panel = window.trackingActions.panel

    assert panel.algorithmComboBox.count() == 2
    assert panel.algorithmComboBox.itemData(0) == "kmeans"
    assert panel.algorithmComboBox.itemData(1) == "uniform"

    # 改变选中项
    panel.algorithmComboBox.setCurrentIndex(1)
    assert panel.algorithmComboBox.currentData() == "uniform"

    panel.algorithmComboBox.setCurrentIndex(0)
    assert panel.algorithmComboBox.currentData() == "kmeans"


def test_review_queue_navigation_and_seek_ac2(test_window: MainWindow, tmp_path: Path):
    """AC-2 / R3.1: 候选帧展示、跳帧定位 (seekFrame)、前后导航与 Accept/Skip 操作。"""
    window = test_window
    panel = window.trackingActions.panel
    valid_run = _setup_infer_run_with_prediction(window, tmp_path)

    # 准备一个已有 ActiveReviewBatch 的 run
    req_id = uuid4()
    c1 = ReviewCandidate(
        frame_index=1,
        prediction=ReviewPredictionSnapshot(12.0, 22.0, 0.40),
        components={"uncertainty": 0.6},
        raw_components={},
        reasons=("low_confidence",),
        total_score=0.75,
    )
    c2 = ReviewCandidate(
        frame_index=2,
        prediction=ReviewPredictionSnapshot(14.0, 24.0, 0.30),
        components={"jump": 0.8},
        raw_components={},
        reasons=("jump",),
        total_score=0.85,
    )
    batch = ActiveReviewBatch(request_id=req_id, params_snapshot={}, candidates=(c1, c2))
    session = window.analysisSession
    assert session is not None
    session.set_active_review_batch(valid_run.run_id, batch)

    # 记录 seekFrame 调用
    seek_calls: list[int] = []
    original_seek = window.seekFrame
    def _mock_seek(frame: int) -> None:
        seek_calls.append(frame)
        original_seek(frame)
    window.seekFrame = _mock_seek

    # 选中该 run
    window.reviewActions.onRunSelected(valid_run.run_id)

    # 验证 Review 控件已就绪
    ctrl = window.reviewActions.controller
    assert ctrl is not None
    assert ctrl.count == 2
    assert "Review: 0/2 reviewed" in panel.reviewProgressLabel.text()
    assert "Frame 1" in panel.candidateDetailsLabel.text()
    assert panel.reviewAcceptButton.isEnabled()
    assert panel.reviewSkipButton.isEnabled()
    assert panel.reviewNextButton.isEnabled()
    assert not panel.reviewPrevButton.isEnabled()

    # 候选列表渲染
    assert panel.reviewCandidatesList.count() == 2
    assert "Frame 1" in panel.reviewCandidatesList.item(0).text()

    # 双击候选列表第 2 项 -> 跳帧到帧 2
    item2 = panel.reviewCandidatesList.item(1)
    panel.reviewCandidatesList.itemDoubleClicked.emit(item2)
    QTest.qWait(20)
    assert 2 in seek_calls
    assert ctrl.current_index == 1
    assert "Frame 2" in panel.candidateDetailsLabel.text()

    # 点击 Accept 按钮 -> 接受当前候选帧并刷新统计，且 auto_advance 跳回首个未审项 (Frame 1)
    seek_calls.clear()
    panel.reviewAcceptButton.click()
    QTest.qWait(20)
    summary = ctrl.summary
    assert summary.accepted_count == 1
    assert "1/2 reviewed" in panel.reviewProgressLabel.text()
    assert ctrl.current_index == 0
    assert 1 in seek_calls
    assert "Frame 1" in panel.candidateDetailsLabel.text()

    # 点击 Next -> 移动到第 2 项并跳帧
    seek_calls.clear()
    panel.reviewNextButton.click()
    QTest.qWait(20)
    assert 2 in seek_calls
    assert ctrl.current_index == 1


def test_track_switch_cancels_active_mining_r8(test_window: MainWindow, tmp_path: Path, qtbot):
    """R8: 挖掘中切换 Track 触发取消，且迟到结果不污染项目。"""
    window = test_window
    session = window.analysisSession
    assert session is not None
    valid_run = _setup_infer_run_with_prediction(window, tmp_path)

    fake_handle = _FakeHandle()
    fake_runner = _FakeRunner(fake_handle)
    window.reviewActions._runner = fake_runner

    window.reviewActions.onRunSelected(valid_run.run_id)
    window.reviewActions.requestMining(valid_run.run_id)
    qtbot.waitUntil(lambda: window.reviewActions._handle is fake_handle, timeout=3000)
    assert window.reviewActions.busy

    # 切换 Track
    window._selected_track_id = None
    window.selectedTrackChanged.emit(None)
    assert not window.reviewActions.busy
    qtbot.waitUntil(lambda: fake_handle.cancelled, timeout=3000)


def _inside_point(window: MainWindow, pixel_x: float, pixel_y: float) -> QPoint:
    return window.videoView.mapFromScene(QPointF(pixel_x, pixel_y))


def test_accept_and_skip_gui_contract_ac3(test_window: MainWindow, tmp_path: Path):
    """AC-3: Accept 只记录 accepted，Skip 只记录 skipped；二者均不修改 TrackPoint。"""
    window = test_window
    session = window.analysisSession
    assert session is not None
    valid_run = _setup_infer_run_with_prediction(window, tmp_path)
    panel = window.trackingActions.panel

    req_id = uuid4()
    c1 = ReviewCandidate(
        frame_index=1,
        prediction=ReviewPredictionSnapshot(12.0, 22.0, 0.40),
        components={"uncertainty": 0.6},
        raw_components={},
        reasons=("low_confidence",),
        total_score=0.75,
    )
    c2 = ReviewCandidate(
        frame_index=2,
        prediction=ReviewPredictionSnapshot(14.0, 24.0, 0.30),
        components={"jump": 0.8},
        raw_components={},
        reasons=("jump",),
        total_score=0.85,
    )
    batch = ActiveReviewBatch(request_id=req_id, params_snapshot={}, candidates=(c1, c2))
    session.set_active_review_batch(valid_run.run_id, batch)
    window.reviewActions.onRunSelected(valid_run.run_id)

    initial_obs = session.project.observations
    ctrl = window.reviewActions.controller
    assert ctrl is not None

    # 点击 Accept 候选 1
    panel.reviewAcceptButton.click()
    QTest.qWait(20)
    assert session.project.observations == initial_obs
    assert ctrl.state.reviewed_frames[1].disposition == "accepted"

    # 点击 Skip 候选 2
    panel.reviewSkipButton.click()
    QTest.qWait(20)
    assert session.project.observations == initial_obs
    assert ctrl.state.reviewed_frames[2].disposition == "skipped"

    # 验证完成统计提示
    summary = ctrl.summary
    assert summary.pending_count == 0
    assert summary.accepted_count == 1
    assert summary.skipped_count == 1
    assert "Review Complete" in panel.reviewProgressLabel.text()


def test_correct_mode_toggle_and_esc_cancel_ac4(test_window: MainWindow, tmp_path: Path):
    """AC-4: Correct 进入一次性模式，Esc 取消不产生坐标，不弄脏 session。"""
    window = test_window
    session = window.analysisSession
    assert session is not None
    valid_run = _setup_infer_run_with_prediction(window, tmp_path)
    panel = window.trackingActions.panel

    req_id = uuid4()
    c1 = ReviewCandidate(
        frame_index=1,
        prediction=ReviewPredictionSnapshot(12.0, 22.0, 0.40),
        components={},
        raw_components={},
        reasons=(),
        total_score=0.5,
    )
    batch = ActiveReviewBatch(request_id=req_id, params_snapshot={}, candidates=(c1,))
    session.set_active_review_batch(valid_run.run_id, batch)
    session.save()
    assert not session.is_dirty

    window.reviewActions.onRunSelected(valid_run.run_id)
    assert not window.reviewActions.is_correcting

    # 进入 Correct 模式
    panel.reviewCorrectButton.click()
    assert window.reviewActions.is_correcting
    assert panel.reviewCorrectButton.text() == "Click Video..."
    assert not session.is_dirty  # 尚未落点，不应弄脏

    # Esc 取消
    window._exitAnnotationMode()
    assert not window.reviewActions.is_correcting
    assert panel.reviewCorrectButton.text() == "Correct (C)"
    assert not session.is_dirty
    assert 1 not in session.get_suggested_frame_review(valid_run.run_id).reviewed_frames


def test_correct_mode_video_click_atomic_submission_ac4(test_window: MainWindow, tmp_path: Path, qtbot):
    """AC-4: 点击视频一次性提交 manual point + corrected disposition，并退出 Correct 模式。"""
    window = test_window
    session = window.analysisSession
    assert session is not None
    track_id = window.selectedTrackId
    assert track_id is not None
    valid_run = _setup_infer_run_with_prediction(window, tmp_path)
    panel = window.trackingActions.panel

    # 使用帧 3（此前无 manual point）
    assert session.effective_point(track_id, 3) is None
    req_id = uuid4()
    c1 = ReviewCandidate(
        frame_index=3,
        prediction=ReviewPredictionSnapshot(15.0, 25.0, 0.45),
        components={},
        raw_components={},
        reasons=("uncertainty",),
        total_score=0.6,
    )
    batch = ActiveReviewBatch(request_id=req_id, params_snapshot={}, candidates=(c1,))
    session.set_active_review_batch(valid_run.run_id, batch)
    window.reviewActions.onRunSelected(valid_run.run_id)

    # 启动 Correct 模式
    panel.reviewCorrectButton.click()
    assert window.reviewActions.is_correcting
    qtbot.waitUntil(lambda: not window._has_pending_request and window.presented_frame_index == 3, timeout=3000)

    # 模拟视频画面点击
    click_pos = _inside_point(window, 20.0, 30.0)
    window._onAnnotationClicked(click_pos)
    QTest.qWait(20)

    # 验证退出 Correct 模式
    assert not window.reviewActions.is_correcting
    assert panel.reviewCorrectButton.text() == "Correct (C)"

    # 验证 manual point 已原子创建
    pt = session.effective_point(track_id, 3)
    assert pt is not None
    assert pt.source == "manual"
    assert abs(pt.pixel_x - 20.0) <= 1.0
    assert abs(pt.pixel_y - 30.0) <= 1.0

    # 验证 review disposition 为 corrected
    st = session.get_suggested_frame_review(valid_run.run_id)
    assert st is not None
    rec = st.reviewed_frames[3]
    assert rec.disposition == "corrected"
    assert rec.manual_point_id == pt.point_id

    # 验证 dirty 与 undo
    assert session.is_dirty
    assert session.can_undo


def test_delete_manual_point_gui_interaction_and_revert_ac7(test_window: MainWindow, tmp_path: Path, qtbot):
    """AC-7: 当前帧有 manual 点时删除按钮使能，点击删除恢复 pending，Undo 可恢复。"""
    window = test_window
    session = window.analysisSession
    assert session is not None
    track_id = window.selectedTrackId
    assert track_id is not None
    valid_run = _setup_infer_run_with_prediction(window, tmp_path)
    panel = window.trackingActions.panel

    req_id = uuid4()
    c1 = ReviewCandidate(
        frame_index=3,
        prediction=ReviewPredictionSnapshot(15.0, 25.0, 0.45),
        components={},
        raw_components={},
        reasons=(),
        total_score=0.5,
    )
    batch = ActiveReviewBatch(request_id=req_id, params_snapshot={}, candidates=(c1,))
    session.set_active_review_batch(valid_run.run_id, batch)
    window.reviewActions.onRunSelected(valid_run.run_id)

    # 帧 3 当前无 manual point -> 删除按钮禁用
    window.seekFrame(3)
    qtbot.waitUntil(lambda: not window._has_pending_request and window.presented_frame_index == 3, timeout=3000)
    assert not window.deletePointButton.isEnabled()
    assert not panel.deleteManualPointButton.isEnabled()

    # 通过 Correct 在帧 3 添加 manual point
    panel.reviewCorrectButton.click()
    click_pos = _inside_point(window, 25.0, 35.0)
    window._onAnnotationClicked(click_pos)
    QTest.qWait(20)

    # 此时帧 3 具备 manual point -> 删除按钮使能
    qtbot.waitUntil(lambda: not window._has_pending_request and window.deletePointButton.isEnabled(), timeout=3000)
    assert panel.deleteManualPointButton.isEnabled()

    # 点击删除
    window.deletePointButton.click()
    QTest.qWait(20)

    # 验证 manual point 已被删除，且候选恢复为 pending
    assert session.effective_point(track_id, 3) is None
    summary = session.get_review_summary(valid_run.run_id)
    assert summary.corrected_count == 0
    assert summary.pending_count == 1
    assert not window.deletePointButton.isEnabled()
    assert not panel.deleteManualPointButton.isEnabled()

    # Undo 删除 -> 恢复 manual point 与 corrected disposition
    window.undoButton.click()
    QTest.qWait(20)
    assert session.effective_point(track_id, 3) is not None
    summary = session.get_review_summary(valid_run.run_id)
    assert summary.corrected_count == 1
    assert window.deletePointButton.isEnabled()
    assert panel.deleteManualPointButton.isEnabled()


def test_save_and_reopen_restores_review_state_ac5(test_window: MainWindow, tmp_path: Path, qtbot):
    """AC-5: 保存并重开后恢复 active batch、已提交 disposition 与 Correct 点。"""
    window = test_window
    session = window.analysisSession
    assert session is not None
    track_id = window.selectedTrackId
    assert track_id is not None
    valid_run = _setup_infer_run_with_prediction(window, tmp_path)
    panel = window.trackingActions.panel

    req_id = uuid4()
    c1 = ReviewCandidate(
        frame_index=1,
        prediction=ReviewPredictionSnapshot(12.0, 22.0, 0.40),
        components={},
        raw_components={},
        reasons=(),
        total_score=0.5,
    )
    c2 = ReviewCandidate(
        frame_index=2,
        prediction=ReviewPredictionSnapshot(14.0, 24.0, 0.30),
        components={},
        raw_components={},
        reasons=(),
        total_score=0.6,
    )
    batch = ActiveReviewBatch(request_id=req_id, params_snapshot={}, candidates=(c1, c2))
    session.set_active_review_batch(valid_run.run_id, batch)
    window.reviewActions.onRunSelected(valid_run.run_id)

    # Accept 候选 1
    panel.reviewAcceptButton.click()
    qtbot.waitUntil(lambda: not window._has_pending_request and window.presented_frame_index == 2, timeout=3000)

    # Correct 候选 2
    panel.reviewCorrectButton.click()
    click_pos = _inside_point(window, 18.0, 28.0)
    window._onAnnotationClicked(click_pos)
    QTest.qWait(20)

    # 保存
    session.save()
    proj_root = session.project_root

    # 重开项目
    window.projectActions._load(lambda service, cancel: service.open_project(proj_root, cancel))
    qtbot.waitUntil(lambda: window.analysisSession is not None, timeout=3000)
    new_session = window.analysisSession
    assert new_session is not None
    window.reviewActions.onRunSelected(valid_run.run_id)

    ctrl = window.reviewActions.controller
    assert ctrl is not None
    assert ctrl.count == 2
    summary = ctrl.summary
    assert summary.accepted_count == 1
    assert summary.corrected_count == 1
    assert summary.pending_count == 0


def test_shortcuts_and_focus_widget_guard_f04_f08(test_window: MainWindow, tmp_path: Path):
    """F-04 / F-08: 键盘快捷键 A/S 触发审核，但在输入框有焦点时被安全屏蔽。"""
    window = test_window
    session = window.analysisSession
    assert session is not None
    valid_run = _setup_infer_run_with_prediction(window, tmp_path)
    panel = window.trackingActions.panel

    req_id = uuid4()
    c1 = ReviewCandidate(
        frame_index=1,
        prediction=ReviewPredictionSnapshot(12.0, 22.0, 0.40),
        components={},
        raw_components={},
        reasons=(),
        total_score=0.5,
    )
    c2 = ReviewCandidate(
        frame_index=2,
        prediction=ReviewPredictionSnapshot(14.0, 24.0, 0.30),
        components={},
        raw_components={},
        reasons=(),
        total_score=0.6,
    )
    batch = ActiveReviewBatch(request_id=req_id, params_snapshot={}, candidates=(c1, c2))
    session.set_active_review_batch(valid_run.run_id, batch)
    window.reviewActions.onRunSelected(valid_run.run_id)

    ctrl = window.reviewActions.controller
    assert ctrl is not None
    assert ctrl.current_index == 0

    # 1. 无输入焦点时按 A -> 接受 candidate 1
    QTest.keyClick(window, Qt.Key.Key_A)
    QTest.qWait(20)
    assert ctrl.state.reviewed_frames[1].disposition == "accepted"

    # 2. 输入框获取焦点时按 S -> 快捷键被屏蔽，不会误跳过 candidate 2
    panel.mineTopNSpinBox.setFocus()
    assert window._isTypingInInputWidget()
    QTest.keyClick(panel.mineTopNSpinBox, Qt.Key.Key_S)
    QTest.qWait(20)
    assert 2 not in ctrl.state.reviewed_frames

    # 3. 清除焦点后按 S -> 成功跳过 candidate 2
    panel.mineTopNSpinBox.clearFocus()
    window.setFocus()
    assert not window._isTypingInInputWidget()
    QTest.keyClick(window, Qt.Key.Key_S)
    QTest.qWait(20)
    assert ctrl.state.reviewed_frames[2].disposition == "skipped"


def test_empty_queue_shortcut_stability_f04(test_window: MainWindow, tmp_path: Path):
    """F-04: 候选队列为空时触发快捷键不引发未捕获异常。"""
    window = test_window
    session = window.analysisSession
    assert session is not None
    valid_run = _setup_infer_run_with_prediction(window, tmp_path)

    req_id = uuid4()
    batch = ActiveReviewBatch(request_id=req_id, params_snapshot={}, candidates=())
    session.set_active_review_batch(valid_run.run_id, batch)
    window.reviewActions.onRunSelected(valid_run.run_id)

    # 队列为空时按 A 和 S 不崩溃
    QTest.keyClick(window, Qt.Key.Key_A)
    QTest.keyClick(window, Qt.Key.Key_S)
    QTest.keyClick(window, Qt.Key.Key_C)


def test_cross_track_selection_guard_f01(test_window: MainWindow, tmp_path: Path):
    """F-01: 选中属于其他 Track 的 run 时，不激活审核控制器，防止跨 Track 错标。"""
    window = test_window
    session = window.analysisSession
    assert session is not None

    # Track 1
    run_track1 = _setup_infer_run_with_prediction(window, tmp_path)
    req_id = uuid4()
    c1 = ReviewCandidate(
        frame_index=1,
        prediction=ReviewPredictionSnapshot(12.0, 22.0, 0.40),
        components={},
        raw_components={},
        reasons=(),
        total_score=0.5,
    )
    batch = ActiveReviewBatch(request_id=req_id, params_snapshot={}, candidates=(c1,))
    session.set_active_review_batch(run_track1.run_id, batch)

    # 新建 Track 2 并切换为当前选中
    track2 = session.add_track(window.activeVideoId)
    window._refreshTrackList()
    for row in range(window.trackList.count()):
        if window.trackList.item(row).data(Qt.ItemDataRole.UserRole) == track2.track_id:
            window.trackList.setCurrentRow(row)
            break
    assert window.selectedTrackId == track2.track_id

    # 尝试选择属于 Track 1 的 run
    window.reviewActions.onRunSelected(run_track1.run_id)
    assert window.reviewActions.controller is None
    assert "No active review batch" in window.trackingActions.panel.reviewProgressLabel.text()


def test_in_flight_frame_guard_on_delete_manual_point_f02(test_window: MainWindow):
    """F-02: 在途解码帧未交付时屏蔽删除人工点，防止竞态误删旧帧点。"""
    window = test_window
    window._has_pending_request = True
    window._deleteCurrentManualPoint()
    assert "Waiting for frame; delete ignored" in window.statusBar().currentMessage()


def test_cannot_accept_or_skip_already_corrected_frame(test_window: MainWindow, tmp_path: Path):
    """Subagent 1 [P1]: 对已人工修正的帧禁止直接 Accept/Skip，防止产生孤立人工点。"""
    from ai_physics_tracker.application.project_session import ProjectSessionError
    window = test_window
    session = window.analysisSession
    assert session is not None
    valid_run = _setup_infer_run_with_prediction(window, tmp_path)

    req_id = uuid4()
    c1 = ReviewCandidate(
        frame_index=1,
        prediction=ReviewPredictionSnapshot(12.0, 22.0, 0.40),
        components={},
        raw_components={},
        reasons=(),
        total_score=0.5,
    )
    batch = ActiveReviewBatch(request_id=req_id, params_snapshot={}, candidates=(c1,))
    session.set_active_review_batch(valid_run.run_id, batch)

    # 修正帧 1
    session.correct_suggested_frame(valid_run.run_id, 1, 10.0, 20.0)

    # 1. 领域层抛出 ProjectSessionError
    with pytest.raises(ProjectSessionError, match="already been corrected"):
        session.accept_suggested_frame(valid_run.run_id, 1)

    with pytest.raises(ProjectSessionError, match="already been corrected"):
        session.skip_suggested_frame(valid_run.run_id, 1)

    # 2. GUI 层按钮被禁用且具备提示（Reviewer [P1]）
    window.reviewActions.onRunSelected(valid_run.run_id)
    panel = window.trackingActions.panel
    assert not panel.reviewAcceptButton.isEnabled()
    assert not panel.reviewSkipButton.isEnabled()
    assert "delete it first" in panel.reviewAcceptButton.toolTip()

    # 3. GUI action 方法具备异常屏障，不向事件循环抛异常
    window.reviewActions.acceptCurrent()
    assert "Accept failed" in window.statusBar().currentMessage()
    window.reviewActions.skipCurrent()
    assert "Skip failed" in window.statusBar().currentMessage()


def test_correct_mode_mismatch_does_not_fallthrough_to_mark_point(test_window: MainWindow, tmp_path: Path, qtbot):
    """Reviewer [P1]: Correct 模式下若校验失败或帧不匹配，绝不穿透到普通 mark_point。"""
    window = test_window
    session = window.analysisSession
    assert session is not None
    valid_run = _setup_infer_run_with_prediction(window, tmp_path)
    track_id = window.selectedTrackId
    assert track_id is not None

    req_id = uuid4()
    c1 = ReviewCandidate(1, ReviewPredictionSnapshot(12.0, 22.0, 0.40), {}, {}, (), 0.5)
    batch = ActiveReviewBatch(request_id=req_id, params_snapshot={}, candidates=(c1,))
    session.set_active_review_batch(valid_run.run_id, batch)
    window.reviewActions.onRunSelected(valid_run.run_id)

    # 启动 Correct 模式（目标是帧 1）
    window.reviewActions.startCorrectCurrent()
    assert window.reviewActions.is_correcting
    qtbot.waitUntil(lambda: not window._has_pending_request and window.presented_frame_index == 1, timeout=3000)

    # 模拟外部导致 presented_frame_index 与目标 candidate 不一致（例如 0）
    window._presented_frame_index = 0
    obs_before = len(session.manual_points(track_id))

    # 在图像区域点击（视频分辨率 64x48，使用有效内部坐标）
    click_pos = _inside_point(window, 20.0, 20.0)
    window._onAnnotationClicked(click_pos)

    # 校验：由于帧不匹配，Correct 被拒绝，且绝不穿透执行 mark_point
    assert len(session.manual_points(track_id)) == obs_before
    assert "does not match candidate frame" in window.statusBar().currentMessage()


def test_mining_params_spinbox_wiring_ac9(test_window: MainWindow, tmp_path: Path):
    """Reviewer [P2]: AC-9 参数微调框 (Top N, Min Gap) 传参准确连通。"""
    window = test_window
    session = window.analysisSession
    assert session is not None
    valid_run = _setup_infer_run_with_prediction(window, tmp_path)
    panel = window.trackingActions.panel

    runner = _FakeRunner()
    window.reviewActions._runner = runner
    window.reviewActions.onRunSelected(valid_run.run_id)

    # 调整 spinbox 参数
    panel.mineTopNSpinBox.setValue(15)
    panel.mineMinGapSpinBox.setValue(0.75)

    # 启动挖掘
    panel.mineButton.click()
    assert window.reviewActions.busy

    # 校验传入 job_request 的 MiningParams 准确匹配
    job_req = window.reviewActions._job_request
    assert job_req is not None
    assert job_req.mining_request.params.top_n == 15
    assert job_req.mining_request.params.min_gap_s == 0.75


def test_ai_tasks_mutual_exclusion_gui(test_window: MainWindow, tmp_path: Path):
    """Reviewer [P1]: 挖掘进行中，训练/推理与选帧均互斥禁用。"""
    window = test_window
    session = window.analysisSession
    assert session is not None
    valid_run = _setup_infer_run_with_prediction(window, tmp_path)
    panel = window.trackingActions.panel

    runner = _FakeRunner()
    window.reviewActions._runner = runner
    window.reviewActions.onRunSelected(valid_run.run_id)

    # 启动挖掘
    panel.mineButton.click()
    assert window.reviewActions.busy

    # 刷新状态并校验互斥
    window.trackingActions.refresh()
    window.frameSelectionActions._refreshEnabled()
    assert not panel.trainButton.isEnabled()
    assert not panel.inferButton.isEnabled()
    assert not panel.suggestButton.isEnabled()

    # 尝试在挖掘中启动选帧 -> 被直接阻止
    window.frameSelectionActions.requestSuggestion(5, "uncertainty")
    assert not window.frameSelectionActions.busy


def test_seek_frame_cancels_active_correct_mode(test_window: MainWindow, tmp_path: Path):
    """Reviewer [P2]: seekFrame() 导航操作必须自动退出 Correct 模式。"""
    window = test_window
    session = window.analysisSession
    assert session is not None
    valid_run = _setup_infer_run_with_prediction(window, tmp_path)

    req_id = uuid4()
    c1 = ReviewCandidate(1, ReviewPredictionSnapshot(12.0, 22.0, 0.40), {}, {}, (), 0.5)
    batch = ActiveReviewBatch(request_id=req_id, params_snapshot={}, candidates=(c1,))
    session.set_active_review_batch(valid_run.run_id, batch)
    window.reviewActions.onRunSelected(valid_run.run_id)

    window.reviewActions.startCorrectCurrent()
    assert window.reviewActions.is_correcting

    # 调用 seekFrame
    window.seekFrame(0)
    assert not window.reviewActions.is_correcting
    assert window.trackingActions.panel.reviewCorrectButton.text() == "Correct (C)"


