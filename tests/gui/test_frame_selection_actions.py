"""FrameSelectionActions 的 GUI offscreen 测试（Phase 5.1 AC-1）。

覆盖：建议帧请求→后台→结果展示、建议帧按钮状态、跳帧信号与标注模式恢复、
      context 切换清空与取消、错误消息传递、建议帧不生成 TrackPoint 严格不变式。
使用 MockEngineAdapter / FakeRunner，不依赖真实 DLC 引擎。
"""

from __future__ import annotations

import json
from pathlib import Path
from threading import Event
from typing import Any
from uuid import UUID, uuid4

import pytest
from PySide6.QtCore import QTimer, Qt
from PySide6.QtTest import QTest

from ai_physics_tracker.application.tracking_types import FrameSelectionResult
from ai_physics_tracker.application.video_session import VideoSession
from ai_physics_tracker.gui.main_window import MainWindow
from ai_physics_tracker.infrastructure.mock_engine_adapter import MockEngineAdapter
from ai_physics_tracker.infrastructure.opencv_video_reader import OpenCVVideoReader
from ai_physics_tracker.infrastructure.project_repository import ProjectRepository
from ai_physics_tracker.infrastructure.task_runner import TaskResult


# ---------------------------------------------------------------------------
# 基础设施 Stub
# ---------------------------------------------------------------------------

class _FakeHandle:
    """可控后台任务句柄。"""

    def __init__(self) -> None:
        self._alive = True
        self._messages: list[Any] = []
        self.exitcode = 0
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
    """控制 BackgroundTaskRunner 的假后端。"""

    def __init__(self, *handles: _FakeHandle) -> None:
        self.handles = list(handles)
        self.calls = 0
        self.started = Event()

    def start_task(self, run_id: UUID, target: Any, *args: Any, **kwargs: Any) -> _FakeHandle:
        del run_id, target, args, kwargs
        self.calls += 1
        self.started.set()
        if not self.handles:
            raise AssertionError("Fake runner ran out of handles")
        return self.handles.pop(0)


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


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def window(tmp_path, qapp):
    """打开裸 MainWindow 并注入 MockEngineAdapter。"""
    win = MainWindow(
        lambda: VideoSession(OpenCVVideoReader()),
        ProjectRepository(),
        _StaticTimingProbe(),
    )
    win.show()
    win.trackingActions.adapter = MockEngineAdapter()
    win.frameSelectionActions.adapter = MockEngineAdapter()
    yield win
    win.projectActions.close_allowed = True
    win.close()


@pytest.fixture
def opened_project(tmp_path, qtbot, synthetic_video_path: Path):
    """使用合成视频打开完整项目会话，返回 (window, session, track_id)。"""
    win = MainWindow(
        lambda: VideoSession(OpenCVVideoReader()),
        ProjectRepository(),
        _StaticTimingProbe(),
    )
    qtbot.addWidget(win)
    win.show()
    assert win.openVideo(synthetic_video_path, show_error=False)
    win.addTrackButton.click()
    track_id = win.selectedTrackId
    assert track_id is not None
    session = win.analysisSession
    assert session is not None
    # 打 3 个初始 manual 点 (帧 0, 1, 2)
    session.mark_point(track_id, 0, 10.0, 10.0)
    session.mark_point(track_id, 1, 12.0, 12.0)
    session.mark_point(track_id, 2, 14.0, 14.0)
    session.save_as(tmp_path / "project")
    win.projectActions.refresh()
    win.trackingActions.adapter = MockEngineAdapter()
    win.frameSelectionActions.adapter = MockEngineAdapter()
    win.frameSelectionActions._refreshEnabled()
    yield win, session, track_id
    win.projectActions.close_allowed = True
    win.close()


# ---------------------------------------------------------------------------
# TaskPanel 建议帧控件测试
# ---------------------------------------------------------------------------

class TestTaskPanelSuggestControls:
    def test_suggest_button_exists(self, qtbot, window):
        panel = window.trackingActions.panel
        assert panel.suggestButton is not None

    def test_suggest_button_default_disabled(self, qtbot, window):
        panel = window.trackingActions.panel
        assert not panel.suggestButton.isEnabled()

    def test_n_frames_spinbox_range(self, qtbot, window):
        panel = window.trackingActions.panel
        assert panel.nFramesSpinBox.minimum() >= 1
        assert panel.nFramesSpinBox.maximum() >= 10
        assert panel.nFramesSpinBox.value() == 10

    def test_algorithm_combobox_has_items(self, qtbot, window):
        panel = window.trackingActions.panel
        assert panel.algorithmComboBox.count() >= 2

    def test_suggested_frames_list_initially_empty(self, qtbot, window):
        panel = window.trackingActions.panel
        assert panel.suggestedFramesList.count() == 0

    def test_set_suggest_result_populates_list(self, qtbot, window):
        panel = window.trackingActions.panel
        result = FrameSelectionResult(
            request_algorithm="uniform",
            suggested_frames=(5, 15, 25),
            actual_n=3,
            excluded_count=0,
            params_snapshot={},
        )
        panel.setSuggestResult(result)
        assert panel.suggestedFramesList.count() == 3

    def test_set_suggest_result_none_clears_list(self, qtbot, window):
        panel = window.trackingActions.panel
        result = FrameSelectionResult(
            request_algorithm="uniform",
            suggested_frames=(5,),
            actual_n=1,
            excluded_count=0,
            params_snapshot={},
        )
        panel.setSuggestResult(result)
        assert panel.suggestedFramesList.count() == 1
        panel.setSuggestResult(None)
        assert panel.suggestedFramesList.count() == 0

    def test_suggested_frame_double_click_emits_signal(self, qtbot, window):
        panel = window.trackingActions.panel
        result = FrameSelectionResult(
            request_algorithm="uniform",
            suggested_frames=(42,),
            actual_n=1,
            excluded_count=0,
            params_snapshot={},
        )
        panel.setSuggestResult(result)
        item = panel.suggestedFramesList.item(0)
        jumped: list[int] = []
        panel.suggestedFrameJumped.connect(jumped.append)
        panel.suggestedFramesList.itemDoubleClicked.emit(item)
        assert 42 in jumped

    def test_set_suggest_enabled_disables_button(self, qtbot, window):
        panel = window.trackingActions.panel
        panel.setSuggestEnabled(False, "Busy")
        assert not panel.suggestButton.isEnabled()

    def test_suggest_status_label_shows_message(self, qtbot, window):
        panel = window.trackingActions.panel
        panel.setSuggestStatus("Test status message")
        assert panel.suggestStatusLabel.isVisible()
        assert "Test status message" in panel.suggestStatusLabel.text()

    def test_suggest_status_label_hidden_on_empty(self, qtbot, window):
        panel = window.trackingActions.panel
        panel.setSuggestStatus("")
        assert not panel.suggestStatusLabel.isVisible()

    def test_unsaved_project_shows_visible_save_hint(self, qtbot, window):
        """未保存项目：禁用原因作为可见文案显示，保存后清除（HR 反馈）。"""
        panel = window.trackingActions.panel
        reason = "Save the project first — frame selection needs a saved project"
        panel.setSuggestEnabled(False, reason, hint=True)
        assert panel.suggestStatusLabel.text() == reason
        assert panel.suggestStatusLabel.isVisible()
        # 恢复可用：提示被清除，且不吞掉此后的结果状态
        panel.setSuggestEnabled(True)
        assert not panel.suggestStatusLabel.isVisible()
        result = FrameSelectionResult(
            request_algorithm="uniform", suggested_frames=(5,),
            actual_n=1, excluded_count=0, params_snapshot={},
        )
        panel.setSuggestResult(result)
        assert panel.suggestStatusLabel.isVisible()

    def test_suggest_frames_not_creating_track_points_invariant(self, qtbot, opened_project):
        """严格不变式：建议帧结果展示后，session 中 manual 点数严格不变，绝不自动打标。"""
        win, session, track_id = opened_project
        initial_points = tuple(session.manual_points(track_id))
        assert len(initial_points) == 3

        panel = win.trackingActions.panel
        result = FrameSelectionResult(
            request_algorithm="kmeans",
            suggested_frames=(5, 10, 20),
            actual_n=3,
            excluded_count=3,
            params_snapshot={"algorithm": "kmeans"},
        )
        panel.setSuggestResult(result)

        current_points = tuple(session.manual_points(track_id))
        assert len(current_points) == len(initial_points)
        assert current_points == initial_points

    def test_suggest_frames_requested_signal_emitted(self, qtbot, window):
        panel = window.trackingActions.panel
        panel.setSuggestEnabled(True)
        emitted: list[tuple] = []
        panel.suggestFramesRequested.connect(lambda n, a: emitted.append((n, a)))
        QTest.mouseClick(panel.suggestButton, Qt.MouseButton.LeftButton)
        assert len(emitted) == 1
        n, algo = emitted[0]
        assert isinstance(n, int) and n >= 1
        assert algo in ("kmeans", "uniform")


# ---------------------------------------------------------------------------
# FrameSelectionActions 状态机与生命周期测试
# ---------------------------------------------------------------------------

class TestFrameSelectionActions:
    def test_actions_created_with_window(self, qtbot, window):
        assert window.frameSelectionActions is not None

    def test_busy_initially_false(self, qtbot, window):
        assert not window.frameSelectionActions.busy

    def test_context_changed_clears_result(self, qtbot, window):
        panel = window.trackingActions.panel
        result = FrameSelectionResult(
            request_algorithm="uniform",
            suggested_frames=(5, 10),
            actual_n=2,
            excluded_count=0,
            params_snapshot={},
        )
        panel.setSuggestResult(result)
        assert panel.suggestedFramesList.count() == 2
        window.projectChanged.emit()
        assert panel.suggestedFramesList.count() == 0

    def _run_selection_to_success(self, qtbot, opened_project):
        win, session, track_id = opened_project
        actions = win.frameSelectionActions
        panel = win.trackingActions.panel
        handle = _FakeHandle()
        actions.runner = _FakeRunner(handle)
        actions.requestSuggestion(n_frames=3, algorithm="uniform")
        qtbot.waitUntil(lambda: actions._handle is handle, timeout=3000)
        req_id = actions._request_id
        out_dir = session.project_root / "data" / "engines" / str(req_id)
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "frame-selection-result.json").write_text(json.dumps({
            "request_id": str(req_id),
            "algorithm": "uniform",
            "suggested_frames": [1, 3, 4],
            "actual_n": 3,
            "excluded_count": 3,
            "params_snapshot": {"algorithm": "uniform"},
        }), encoding="utf-8")
        handle.die()
        handle.add_message(TaskResult(run_id=req_id, success=True,
                                      payload={"status": "completed"}))
        qtbot.waitUntil(lambda: not actions.busy, timeout=3000)
        assert panel.suggestedFramesList.count() == 3
        return win, session, track_id

    def test_same_track_reselection_keeps_results(self, qtbot, opened_project):
        """Track 列表对同一 track 的重复点击不得清空建议帧（用户实测 bug）。"""
        win, _session, track_id = self._run_selection_to_success(qtbot, opened_project)
        panel = win.trackingActions.panel
        # itemClicked 会重发 selectedTrackChanged（selectedTrackId 未变）
        win._onTrackSelectionChanged()
        assert panel.suggestedFramesList.count() == 3
        assert win.frameSelectionActions._result_track_id == track_id

    def test_different_track_selection_clears_results(self, qtbot, opened_project):
        win, session, track_id = self._run_selection_to_success(qtbot, opened_project)
        panel = win.trackingActions.panel
        video = session.project.videos[0]
        other = session.add_track(video.video_id, "TrackB")
        win._selected_track_id = other.track_id
        win.selectedTrackChanged.emit(other.track_id)
        assert panel.suggestedFramesList.count() == 0
        # 切回原 track：缓存恢复显示（HR 反馈：重新选中后保留推荐帧）
        win._selected_track_id = track_id
        win.selectedTrackChanged.emit(track_id)
        assert panel.suggestedFramesList.count() == 3

    def test_deselect_then_reselect_restores_results(self, qtbot, opened_project):
        """取消选择 Track 再选回：列表清空但缓存恢复（HR 反馈场景）。"""
        win, session, track_id = self._run_selection_to_success(qtbot, opened_project)
        panel = win.trackingActions.panel
        assert panel.suggestedFramesList.count() == 3
        win._selected_track_id = None
        win.selectedTrackChanged.emit(None)
        assert panel.suggestedFramesList.count() == 0
        win._selected_track_id = track_id
        win.selectedTrackChanged.emit(track_id)
        assert panel.suggestedFramesList.count() == 3
        assert "Suggested 3 frame(s)" in panel.suggestStatusLabel.text()

    def test_same_track_click_does_not_cancel_running_task(self, qtbot, opened_project):
        win, _session, track_id = self._run_selection_to_success(qtbot, opened_project)
        del track_id
        actions = win.frameSelectionActions
        handle = _FakeHandle()
        actions.runner = _FakeRunner(handle)
        actions.requestSuggestion(n_frames=2, algorithm="uniform")
        qtbot.waitUntil(lambda: actions._handle is handle, timeout=3000)
        win._onTrackSelectionChanged()  # 同一 track 重复点击
        assert actions.busy
        assert not handle.cancelled
        actions._cancel_active_task()  # 清理
        actions._reset()

    def test_async_workflow_success(self, qtbot, opened_project):
        """测试 requestSuggestion -> 后台执行写入结果 -> _poll -> TaskPanel 渲染成功。"""
        win, session, track_id = opened_project
        actions = win.frameSelectionActions
        panel = win.trackingActions.panel

        assert panel.suggestButton.isEnabled()
        handle = _FakeHandle()
        runner = _FakeRunner(handle)
        actions.runner = runner

        actions.requestSuggestion(n_frames=3, algorithm="uniform")
        assert actions.busy

        # 等待后台 worker 启动
        qtbot.waitUntil(lambda: actions._handle is handle, timeout=3000)

        # 模拟后台 worker 完成并写入结果 JSON
        req_id = actions._request_id
        out_dir = session.project_root / "data" / "engines" / str(req_id)
        out_dir.mkdir(parents=True, exist_ok=True)
        res_file = out_dir / "frame-selection-result.json"
        res_file.write_text(json.dumps({
            "request_id": str(req_id),
            "algorithm": "uniform",
            "suggested_frames": [1, 3, 4],
            "actual_n": 3,
            "excluded_count": 3,
            "params_snapshot": {"algorithm": "uniform"},
        }), encoding="utf-8")

        # 模拟子进程退出
        handle.die()
        handle.add_message(TaskResult(run_id=req_id, success=True, payload={"status": "completed"}))

        # 轮询直到完成
        qtbot.waitUntil(lambda: not actions.busy, timeout=3000)
        assert panel.suggestedFramesList.count() == 3
        assert "Suggested 3 frame(s)" in panel.suggestStatusLabel.text()
        assert panel.suggestButton.isEnabled()

    def test_async_workflow_failure_shows_error(self, qtbot, opened_project):
        """测试 worker 失败时正确通过 poll_messages 捕获真实错误。"""
        win, session, track_id = opened_project
        actions = win.frameSelectionActions
        panel = win.trackingActions.panel

        handle = _FakeHandle()
        actions.runner = _FakeRunner(handle)
        actions.requestSuggestion(n_frames=3, algorithm="uniform")

        qtbot.waitUntil(lambda: actions._handle is handle, timeout=3000)

        # 模拟 worker 报错退出
        handle.die()
        handle.add_message(TaskResult(
            run_id=actions._request_id,
            success=False,
            error="Video file is corrupted",
        ))

        qtbot.waitUntil(lambda: not actions.busy, timeout=3000)
        assert "Failed: Video file is corrupted" in panel.suggestStatusLabel.text()
        assert panel.suggestButton.isEnabled()

    def test_context_change_cancels_running_task(self, qtbot, opened_project):
        """测试在任务运行中切换 track/project 时触发 handle.cancel()。"""
        win, session, track_id = opened_project
        actions = win.frameSelectionActions

        handle = _FakeHandle()
        actions.runner = _FakeRunner(handle)
        actions.requestSuggestion(n_frames=3, algorithm="uniform")

        qtbot.waitUntil(lambda: actions._handle is handle, timeout=3000)
        assert actions.busy

        # 触发 track 切换（真实路径先更新 selectedTrackId 再发信号）
        win._selected_track_id = None
        win.selectedTrackChanged.emit(None)
        assert not actions.busy
        qtbot.waitUntil(lambda: handle.cancelled, timeout=3000)

    def test_jump_to_frame_restores_annotation_mode(self, qtbot, opened_project):
        """测试 jumpToFrame 在有选中 track 时成功跳转并保持 annotation mode。"""
        win, session, track_id = opened_project
        win.videoView.set_annotation_mode(False)
        assert not win.videoView.is_annotation_mode()

        assert win.jumpToFrame(3)
        assert win.videoView.is_annotation_mode()
        assert "Click video to annotate" in win.statusBar().currentMessage()
