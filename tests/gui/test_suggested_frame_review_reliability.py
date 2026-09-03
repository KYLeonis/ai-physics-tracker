"""Phase 5.3 Slice 4 — Reliability Matrix tests.

覆盖：
1. 保存重开、中途退出恢复与继续审核
2. Scoped review 与普通打点交错 Undo/Redo 状态机
3. 后台挖掘取消、迟到到达与上下文切换隔离
4. 后台挖掘失败处理与干净恢复
5. Correct 模式在全部时间轴导航与播放矢量下的自动注销
6. 预存人工点与纠偏覆盖冲突处理
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtTest import QTest

from ai_physics_tracker.application.difficult_frame_job import DifficultFrameResult
from ai_physics_tracker.application.suggested_frame_review import (
    ActiveReviewBatch,
    ReviewCandidate,
    ReviewPredictionSnapshot,
)
from ai_physics_tracker.application.tracking_types import TaskProgress, TaskResult
from ai_physics_tracker.application.video_session import VideoSession
from ai_physics_tracker.domain.tracking_run import (
    create_tracking_run,
    mark_run_completed,
    mark_run_running,
)
from ai_physics_tracker.gui.main_window import MainWindow
from ai_physics_tracker.infrastructure.opencv_video_reader import OpenCVVideoReader
from ai_physics_tracker.infrastructure.project_repository import ProjectRepository


class _ControllableHandle:
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
        del timeout_s
        self.cancelled = True
        self._alive = False

    def die(self) -> None:
        self._alive = False

    def push(self, msg: Any) -> None:
        self._messages.append(msg)


class _ControllableRunner:
    def __init__(self) -> None:
        self.handles: list[_ControllableHandle] = []
        self.calls = 0

    def start_task(self, run_id: UUID, target: Any, args: Any = (), kwargs: Any = None) -> _ControllableHandle:
        del run_id, target, args, kwargs
        self.calls += 1
        if self.handles:
            return self.handles.pop(0)
        handle = _ControllableHandle()
        handle.die()
        return handle

    def start(self, job_request: Any, request_id: UUID) -> _ControllableHandle:
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
def rel_window(tmp_path: Path, synthetic_video_path: Path, qtbot):
    """构建用于可靠性测试的 MainWindow。"""
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

    session.save_as(tmp_path / "project")
    window.projectActions.refresh()
    window.reviewActions.refresh()
    QTest.qWait(50)

    yield window

    window.projectActions.close_allowed = True
    window.close()
    QTest.qWait(50)


def _setup_run(window: MainWindow):
    session = window.analysisSession
    assert session is not None
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
        "3,16.0,26.0,0.20",
    ]
    pred_file.write_text("\n".join(pred_lines) + "\n", encoding="utf-8")
    stat = pred_file.stat()

    model_file = run_dir / "model-snapshot.pt"
    model_file.write_bytes(b"dummy")
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


def _inside_point(window: MainWindow, px: float, py: float) -> QPoint:
    return window.videoView.mapFromScene(QPointF(px, py))


def test_save_reopen_and_resume_review_matrix(rel_window: MainWindow, qtbot):
    """可靠性测试 1：保存、重开后恢复审核进度并继续完成剩余审核。"""
    window = rel_window
    session = window.analysisSession
    assert session is not None
    run = _setup_run(window)
    panel = window.trackingActions.panel

    # 构造 3 个候选帧
    req_id = uuid4()
    c1 = ReviewCandidate(1, ReviewPredictionSnapshot(12.0, 22.0, 0.40), {}, {}, (), 0.5)
    c2 = ReviewCandidate(2, ReviewPredictionSnapshot(14.0, 24.0, 0.30), {}, {}, (), 0.6)
    c3 = ReviewCandidate(3, ReviewPredictionSnapshot(16.0, 26.0, 0.20), {}, {}, (), 0.7)
    batch = ActiveReviewBatch(req_id, {}, (c1, c2, c3))
    session.set_active_review_batch(run.run_id, batch)
    window.reviewActions.onRunSelected(run.run_id)

    # 1. 接受候选 1
    panel.reviewAcceptButton.click()
    qtbot.waitUntil(lambda: not window._has_pending_request and window.presented_frame_index == 2, timeout=3000)

    # 2. 修正候选 2
    panel.reviewCorrectButton.click()
    click_pos = _inside_point(window, 18.0, 28.0)
    window._onAnnotationClicked(click_pos)
    qtbot.waitUntil(lambda: not window._has_pending_request and window.presented_frame_index == 3, timeout=3000)

    # 保存并重开
    session.save()
    proj_root = session.project_root
    window.projectActions._load(lambda service, cancel: service.open_project(proj_root, cancel))
    qtbot.waitUntil(lambda: window.analysisSession is not None, timeout=3000)

    # 验证重开后恢复
    new_session = window.analysisSession
    assert new_session is not None
    window.reviewActions.onRunSelected(run.run_id)
    ctrl = window.reviewActions.controller
    assert ctrl is not None
    assert ctrl.summary.accepted_count == 1
    assert ctrl.summary.corrected_count == 1
    assert ctrl.summary.pending_count == 1
    assert ctrl.current_candidate is not None
    assert ctrl.current_candidate.frame_index == 1
    assert ctrl.current_disposition == "accepted"

    # 校验人工修正点在重开后坐标与属性完全恢复（AC-5）
    track_id = run.track_id
    pt2 = new_session.effective_point(track_id, 2)
    assert pt2 is not None
    assert pt2.source == "manual"
    assert pt2.pixel_x == pytest.approx(18.0, abs=0.5)
    assert pt2.pixel_y == pytest.approx(28.0, abs=0.5)

    # 跳到首个待审候选（候选 3）
    ctrl.first_pending()
    assert ctrl.current_candidate.frame_index == 3
    assert ctrl.current_disposition == "pending"

    # 继续完成候选 3 (Skip)
    panel.reviewSkipButton.click()
    QTest.qWait(30)
    assert ctrl.summary.pending_count == 0
    assert ctrl.summary.skipped_count == 1
    assert "Review Complete" in panel.reviewProgressLabel.text()


def test_interleaved_undo_redo_matrix(rel_window: MainWindow, qtbot):
    """可靠性测试 2：普通人工打点、Accept、Correct 与删除点交错时的 Scoped Undo/Redo。"""
    window = rel_window
    session = window.analysisSession
    assert session is not None
    track_id = window.selectedTrackId
    assert track_id is not None
    run = _setup_run(window)
    panel = window.trackingActions.panel

    req_id = uuid4()
    c1 = ReviewCandidate(1, ReviewPredictionSnapshot(12.0, 22.0, 0.40), {}, {}, (), 0.5)
    c2 = ReviewCandidate(2, ReviewPredictionSnapshot(14.0, 24.0, 0.30), {}, {}, (), 0.6)
    batch = ActiveReviewBatch(req_id, {}, (c1, c2))
    session.set_active_review_batch(run.run_id, batch)
    window.reviewActions.onRunSelected(run.run_id)

    # 1. 普通 mark_point 在帧 0
    p0 = session.mark_point(track_id, 0, 10.0, 10.0)
    assert p0 is not None

    # 2. Accept candidate 1 (帧 1)
    panel.reviewAcceptButton.click()
    qtbot.waitUntil(lambda: not window._has_pending_request and window.presented_frame_index == 2, timeout=3000)

    # 3. Correct candidate 2 (帧 2)
    panel.reviewCorrectButton.click()
    click_pos = _inside_point(window, 22.0, 32.0)
    window._onAnnotationClicked(click_pos)
    qtbot.waitUntil(lambda: not window._has_pending_request, timeout=3000)

    summary = session.get_review_summary(run.run_id)
    assert summary.accepted_count == 1
    assert summary.corrected_count == 1

    # 4. 连续 Undo
    # Undo 1 -> 回滚 Correct candidate 2
    window.undoButton.click()
    QTest.qWait(20)
    summary = session.get_review_summary(run.run_id)
    assert summary.corrected_count == 0
    assert session.effective_point(track_id, 2) is None

    # Undo 2 -> 回滚 Accept candidate 1
    window.undoButton.click()
    QTest.qWait(20)
    summary = session.get_review_summary(run.run_id)
    assert summary.accepted_count == 0

    # Undo 3 -> 回滚普通 mark_point (帧 0)
    window.undoButton.click()
    QTest.qWait(20)
    assert session.effective_point(track_id, 0) is None

    # 5. 连续 Redo
    window.redoButton.click()
    QTest.qWait(20)
    assert session.effective_point(track_id, 0) is not None

    window.redoButton.click()
    QTest.qWait(20)
    summary = session.get_review_summary(run.run_id)
    assert summary.accepted_count == 1

    window.redoButton.click()
    QTest.qWait(20)
    summary = session.get_review_summary(run.run_id)
    assert summary.corrected_count == 1
    assert session.effective_point(track_id, 2) is not None


def test_background_mining_cancellation_and_late_result_guard(rel_window: MainWindow, qtbot):
    """可靠性测试 3：任务运行中切换 Track 或关闭，迟到的 worker 结果被安全丢弃。"""
    window = rel_window
    session = window.analysisSession
    assert session is not None
    run = _setup_run(window)
    panel = window.trackingActions.panel

    runner = _ControllableRunner()
    handle = _ControllableHandle()
    runner.handles.append(handle)
    window.reviewActions._runner = runner
    window.reviewActions.onRunSelected(run.run_id)

    # 启动挖掘
    panel.mineButton.click()
    assert window.reviewActions.busy
    assert not panel.mineButton.isEnabled()

    # 在任务运行中切换 Track (新建 Track 2 并切换)
    track2 = session.add_track(window.activeVideoId)
    window._refreshTrackList()
    for row in range(window.trackList.count()):
        if window.trackList.item(row).data(Qt.ItemDataRole.UserRole) == track2.track_id:
            window.trackList.setCurrentRow(row)
            break
    assert window.selectedTrackId == track2.track_id

    # 此时原挖掘任务已被取消
    qtbot.waitUntil(lambda: handle.cancelled, timeout=2000)
    assert not window.reviewActions.busy

    # 模拟迟到交付的结果
    handle.push(TaskResult(run_id=run.run_id, success=True, payload={"status": "completed"}))
    window.reviewActions._poll()

    # 迟到结果未附加到当前 track2
    assert window.reviewActions.controller is None
    assert "No active review batch" in panel.reviewProgressLabel.text()


def test_background_mining_failure_cleanup(rel_window: MainWindow):
    """可靠性测试 4：挖掘任务失败时状态干净恢复，按钮重新使能。"""
    window = rel_window
    run = _setup_run(window)
    panel = window.trackingActions.panel

    runner = _ControllableRunner()
    handle = _ControllableHandle()
    runner.handles.append(handle)
    window.reviewActions._runner = runner
    window.reviewActions.onRunSelected(run.run_id)

    # 启动挖掘
    panel.mineButton.click()
    assert window.reviewActions.busy

    # 任务失败
    handle.die()
    handle.push(TaskResult(run_id=run.run_id, success=False, error="Engine runtime out of memory"))
    window.reviewActions._poll()

    assert not window.reviewActions.busy
    assert panel.mineButton.isEnabled()
    assert "failed" in panel.mineStatusLabel.text().lower() or "out of memory" in panel.mineStatusLabel.text().lower()


def test_correct_mode_cancelled_on_all_navigation_vectors(rel_window: MainWindow):
    """可靠性测试 5：Correct 模式在全部导航矢量（步进、跳帧、拖动、播放、切轨）下均自动注销。"""
    window = rel_window
    session = window.analysisSession
    assert session is not None
    run = _setup_run(window)

    req_id = uuid4()
    c1 = ReviewCandidate(1, ReviewPredictionSnapshot(12.0, 22.0, 0.40), {}, {}, (), 0.5)
    batch = ActiveReviewBatch(req_id, {}, (c1,))
    session.set_active_review_batch(run.run_id, batch)
    window.reviewActions.onRunSelected(run.run_id)

    # 1. 步进 delta 取消
    window.reviewActions.startCorrectCurrent()
    assert window.reviewActions.is_correcting
    window._step(1)
    assert not window.reviewActions.is_correcting
    assert not window.videoView.is_annotation_mode()

    # 2. _goToFrame 取消
    window.reviewActions.startCorrectCurrent()
    assert window.reviewActions.is_correcting
    window._goToFrame(0)
    assert not window.reviewActions.is_correcting

    # 3. _scrubStarted 取消
    window.reviewActions.startCorrectCurrent()
    assert window.reviewActions.is_correcting
    window._scrubStarted()
    assert not window.reviewActions.is_correcting

    # 4. startPlayback 取消
    window.reviewActions.startCorrectCurrent()
    assert window.reviewActions.is_correcting
    window.startPlayback()
    assert not window.reviewActions.is_correcting
    window.stopPlayback()

    # 5. 切 Track 取消
    window.reviewActions.startCorrectCurrent()
    assert window.reviewActions.is_correcting
    track2 = session.add_track(window.activeVideoId)
    window._refreshTrackList()
    for row in range(window.trackList.count()):
        if window.trackList.item(row).data(Qt.ItemDataRole.UserRole) == track2.track_id:
            window.trackList.setCurrentRow(row)
            break
    assert not window.reviewActions.is_correcting


def test_candidate_with_preexisting_manual_point(rel_window: MainWindow, qtbot):
    """可靠性测试 6：帧上已有 manual 点时的纠偏重标与删除。"""
    window = rel_window
    session = window.analysisSession
    assert session is not None
    track_id = window.selectedTrackId
    assert track_id is not None
    run = _setup_run(window)
    panel = window.trackingActions.panel

    # 预先在帧 1 放置普通 manual 点
    p_pre = session.mark_point(track_id, 1, 10.0, 15.0)
    assert p_pre is not None

    req_id = uuid4()
    c1 = ReviewCandidate(1, ReviewPredictionSnapshot(12.0, 22.0, 0.40), {}, {}, (), 0.5)
    batch = ActiveReviewBatch(req_id, {}, (c1,))
    session.set_active_review_batch(run.run_id, batch)
    window.reviewActions.onRunSelected(run.run_id)

    # 触发 Correct 重标
    panel.reviewCorrectButton.click()
    qtbot.waitUntil(lambda: not window._has_pending_request and window.presented_frame_index == 1, timeout=3000)
    click_pos = _inside_point(window, 30.0, 40.0)
    window._onAnnotationClicked(click_pos)
    qtbot.waitUntil(lambda: not window._has_pending_request, timeout=3000)

    # 新 manual 点覆盖旧 manual 点
    pt = session.effective_point(track_id, 1)
    assert pt is not None
    assert abs(pt.pixel_x - 30.0) <= 1.0
    assert abs(pt.pixel_y - 40.0) <= 1.0
    summary = session.get_review_summary(run.run_id)
    assert summary.corrected_count == 1

    # 删除该 manual 点 -> 恢复为 pending
    window.deletePointButton.click()
    QTest.qWait(20)
    summary = session.get_review_summary(run.run_id)
    assert summary.corrected_count == 0
    assert summary.pending_count == 1
