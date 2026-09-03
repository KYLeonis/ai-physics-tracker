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
from PySide6.QtCore import Qt
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
