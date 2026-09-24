"""引导标注（P1.2-S3）GUI 链路的 Qt offscreen 测试。

覆盖 main_window 的 experiment 四 role 引导：
- beginExperimentAnnotation 生命周期与 Esc（_exitAnnotationMode）退出
- 引导点击路由到当前待标 role 的 track（无第二落点路径），4/4 后拒绝再点
- guide_skip 跳过当前 role，帧保持 partial（join 事实断言）
- frame_set worklist：进入引导跳到第一个未完成帧、guide_next/guide_finish
- 引导模式四 role marker 全显示（不依赖 track 选中）
- frame_set 持久化：session.set_experiment_frame_set → 保存重开完整往返
- FrameSelectionActions：experiment 存在时走共享帧集路径并回写
  experiment.frame_set（状态栏 "Saved as shared frame set"）

向导 stub 与窗口 helper 复制自 tests/gui/test_pendulum_setup_ui.py；
Fake runner 模式复制自 tests/gui/test_frame_selection_actions.py。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from PySide6.QtWidgets import QDialog, QFileDialog
from pytestqt.qtbot import QtBot

from ai_physics_tracker.application.annotation_join import join_complete_frames
from ai_physics_tracker.application.experiment_annotation import (
    annotation_guide_state,
    frame_set_worklist,
)
from ai_physics_tracker.application.video_session import VideoSession
from ai_physics_tracker.domain.pendulum import (
    ROLE_ORDER,
    ExperimentFrameSet,
)
from ai_physics_tracker.domain.types import utc_now
from ai_physics_tracker.gui import project_actions
from ai_physics_tracker.gui.main_window import MainWindow
from ai_physics_tracker.infrastructure.ffprobe_timing import FFprobeTimingProbe
from ai_physics_tracker.infrastructure.opencv_video_reader import OpenCVVideoReader
from ai_physics_tracker.infrastructure.project_repository import ProjectRepository
from ai_physics_tracker.infrastructure.task_runner import TaskResult


# ---------------------------------------------------------------------------
# 窗口与向导 helpers（复制自 tests/gui/test_pendulum_setup_ui.py）
# ---------------------------------------------------------------------------

def _window() -> MainWindow:
    return MainWindow(
        lambda: VideoSession(OpenCVVideoReader()), ProjectRepository(), FFprobeTimingProbe()
    )


def _opened_window(qtbot: QtBot, synthetic_video_path: Path) -> MainWindow:
    window = _window()
    qtbot.addWidget(window)
    window.show()
    assert window.openVideo(synthetic_video_path, show_error=False)
    return window


def _wait_presented(qtbot: QtBot, window: MainWindow) -> None:
    """等待首帧解码呈现（_presented_frame_index 就绪后再驱动引导）。"""

    qtbot.waitUntil(lambda: window._presented_frame_index is not None, timeout=5000)


def _four_tracks(session, video_id: UUID) -> list:
    return [session.add_track(video_id, f"pendulum track {i + 1}") for i in range(4)]


def _roles_from(tracks: list):
    from ai_physics_tracker.domain.pendulum import PendulumRoles

    return PendulumRoles(
        tip=tracks[0].track_id,
        body_top=tracks[1].track_id,
        body_bottom=tracks[2].track_id,
        pivot=tracks[3].track_id,
    )


class _WizardStub:
    """以预设结论替代向导交互：exec 直接接受，roles/destination 返回预设值。"""

    DialogCode = QDialog.DialogCode
    roles = None
    destination_path: Path | None = None
    instances: "list[_WizardStub]" = []

    def __init__(self, offered_tracks, *, require_destination: bool = True,
                 first_save: bool = False, default_destination: str = "",
                 create_track=None, parent=None) -> None:
        self.offered_tracks = list(offered_tracks)
        self.require_destination = require_destination
        _WizardStub.instances.append(self)

    def exec(self) -> int:
        return 1

    def pendulum_roles(self):
        return _WizardStub.roles

    def destination(self) -> Path:
        return _WizardStub.destination_path


def _accept_wizard(monkeypatch, tracks: list, destination: Path) -> type[_WizardStub]:
    _WizardStub.roles = _roles_from(tracks)
    _WizardStub.destination_path = destination
    _WizardStub.instances = []
    monkeypatch.setattr(project_actions, "PendulumWizardDialog", _WizardStub)
    return _WizardStub


def _experiment_via_menu(qtbot: QtBot, monkeypatch, window: MainWindow,
                         tracks: list, destination: Path):
    """走 File 菜单入口创建 experiment（stub 向导），等待后台迁移完成。"""

    _accept_wizard(monkeypatch, tracks, destination)
    window.projectActions.createPendulumExperiment()
    qtbot.waitUntil(lambda: not window.projectActions.busy, timeout=5000)
    experiment = window.currentPendulumExperiment()
    assert experiment is not None
    return experiment


def _guided_window(qtbot: QtBot, synthetic_video_path: Path, tmp_path: Path,
                   monkeypatch):
    """打开视频 → 向导建 experiment → 进入引导模式；返回 (window, session)。"""

    window = _opened_window(qtbot, synthetic_video_path)
    _wait_presented(qtbot, window)
    tracks = _four_tracks(window.analysisSession, window.activeVideoId)
    _experiment_via_menu(
        qtbot, monkeypatch, window, tracks, tmp_path / "publication-copy")
    assert window._measurement_allowed
    window.beginExperimentAnnotation()
    assert window.experiment_guide_active
    return window, window.analysisSession


# ---------------------------------------------------------------------------
# Fake 后端（复制自 tests/gui/test_frame_selection_actions.py）
# ---------------------------------------------------------------------------

class _FakeHandle:
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
    def __init__(self, *handles: _FakeHandle) -> None:
        self.handles = list(handles)
        self.calls = 0

    def start_task(self, run_id: UUID, target: Any, *args: Any, **kwargs: Any) -> _FakeHandle:
        del run_id, target, args, kwargs
        self.calls += 1
        if not self.handles:
            raise AssertionError("Fake runner ran out of handles")
        return self.handles.pop(0)


# ---------------------------------------------------------------------------
# 引导生命周期
# ---------------------------------------------------------------------------


def test_guide_lifecycle_enter_and_escape(
    qtbot: QtBot, synthetic_video_path: Path, tmp_path: Path, monkeypatch
) -> None:
    window = _opened_window(qtbot, synthetic_video_path)
    _wait_presented(qtbot, window)
    assert window.calibrationGuideLabel.isHidden()
    assert not window.experiment_guide_active

    tracks = _four_tracks(window.analysisSession, window.activeVideoId)
    _experiment_via_menu(
        qtbot, monkeypatch, window, tracks, tmp_path / "publication-copy")

    window.beginExperimentAnnotation()

    # 引导激活：标注模式开启、无需选中 track、引导条给出第一个待标 role
    assert window.experiment_guide_active
    assert window.videoView.is_annotation_mode()
    assert not window.trackList.selectedItems()
    assert not window.calibrationGuideLabel.isHidden()
    assert "click the tip" in window.calibrationGuideLabel.text()
    assert "0/4 done" in window.calibrationGuideLabel.text()

    # Esc（_exitAnnotationMode）退出引导：引导态清空、引导条隐藏
    window._exitAnnotationMode()
    assert not window.experiment_guide_active
    assert window.calibrationGuideLabel.isHidden()
    assert "Browse mode" in window.statusBar().currentMessage()

    # 退出后可重新进入（annotate 按钮入口与 beginExperimentAnnotation 等价）
    window.beginExperimentAnnotation()
    assert window.experiment_guide_active


def test_guided_click_writes_current_role_track(
    qtbot: QtBot, synthetic_video_path: Path, tmp_path: Path, monkeypatch
) -> None:
    window, session = _guided_window(qtbot, synthetic_video_path, tmp_path, monkeypatch)
    roles = window.currentPendulumExperiment().roles

    # 呈现帧 2 后经引导点击：落点写到当前待标 role（tip）的 track
    window._presented_frame_index = 2
    window._onGuidedAnnotationClicked((10.0, 20.0))
    tip_points = session.manual_points(roles.tip)
    assert [(p.frame_index, p.pixel_x, p.pixel_y) for p in tip_points] == [
        (2, 10.0, 20.0)
    ]
    for role in ("body_top", "body_bottom", "pivot"):
        assert session.manual_points(roles.track_id_for(role)) == ()

    # 继续点击三次：依次落到 body_top / body_bottom / pivot → 4/4
    window._onGuidedAnnotationClicked((11.0, 21.0))
    window._onGuidedAnnotationClicked((12.0, 22.0))
    window._onGuidedAnnotationClicked((13.0, 23.0))
    state = annotation_guide_state(session.project, window.currentPendulumExperiment(), 2)
    assert state.frame_complete is True
    assert state.done_roles == ROLE_ORDER
    for role in ROLE_ORDER:
        points = session.manual_points(roles.track_id_for(role))
        assert len(points) == 1 and points[0].frame_index == 2

    # 帧已完整：再点击只提示，不新增任何观测
    before = len(session.project.observations)
    window._onGuidedAnnotationClicked((14.0, 24.0))
    assert len(session.project.observations) == before
    assert "complete (4/4)" in window.statusBar().currentMessage()
    # 无 frame_set → 完成后引导条给出 finish 出口
    assert window.calibrationGuideButton.text() == "Finish guided marking"


def test_skip_role_keeps_frame_partial(
    qtbot: QtBot, synthetic_video_path: Path, tmp_path: Path, monkeypatch
) -> None:
    window, session = _guided_window(qtbot, synthetic_video_path, tmp_path, monkeypatch)
    experiment = window.currentPendulumExperiment()
    roles = experiment.roles

    window._presented_frame_index = 2
    window._onGuidedAnnotationClicked((10.0, 20.0))  # tip
    window._onGuidedAnnotationClicked((11.0, 21.0))  # body_top

    # skip 当前待标 role（body_bottom）→ 引导推进到 pivot
    window._onAnnotationGuideAction("guide_skip")
    label = window.calibrationGuideLabel.text()
    assert "click the pivot" in label
    assert "skipping: body_bottom" in label

    # 再点一次：落到 pivot；被 skip 的 role 不落点
    window._onGuidedAnnotationClicked((12.0, 22.0))
    assert session.manual_points(roles.body_bottom) == ()
    assert len(session.manual_points(roles.pivot)) == 1

    # 帧保持 partial（3 个 role 的 manual，不足 4）：join 是唯一真值
    result = join_complete_frames(session.project, window.currentPendulumExperiment())
    assert result.partial == ((2, 3),)
    assert result.complete == ()

    # skip 后本帧无待点 role：再点击只提示，不写点
    before = len(session.project.observations)
    window._onGuidedAnnotationClicked((14.0, 24.0))
    assert len(session.project.observations) == before
    assert "skipped" in window.statusBar().currentMessage()


# ---------------------------------------------------------------------------
# frame_set worklist：进入帧、guide_next / guide_finish
# ---------------------------------------------------------------------------


def test_frame_set_guided_start_next_and_finish(
    qtbot: QtBot, synthetic_video_path: Path, tmp_path: Path, monkeypatch
) -> None:
    window = _opened_window(qtbot, synthetic_video_path)
    _wait_presented(qtbot, window)
    tracks = _four_tracks(window.analysisSession, window.activeVideoId)
    experiment = _experiment_via_menu(
        qtbot, monkeypatch, window, tracks, tmp_path / "publication-copy")
    session = window.analysisSession
    roles = experiment.roles

    # 帧集 (0, 4)：帧 4 预先标满 → 引导应跳到第一个未完成帧 0
    session.set_experiment_frame_set(
        experiment.experiment_id,
        ExperimentFrameSet(frames=(0, 4), algorithm="uniform", created_at=utc_now()),
    )
    for role, (x, y) in zip(ROLE_ORDER, ((1.0, 1.0), (2.0, 2.0), (3.0, 3.0), (4.0, 4.0))):
        session.mark_point(roles.track_id_for(role), 4, x, y)

    window.beginExperimentAnnotation()
    assert window.experiment_guide_active
    _wait_presented(qtbot, window)
    assert window._presented_frame_index == 0
    assert "click the tip" in window.calibrationGuideLabel.text()

    # 帧内四次引导点击 → 4/4 → 提示推进到帧集中的下一帧
    window._presented_frame_index = 0
    for x in (11.0, 12.0, 13.0, 14.0):
        window._onGuidedAnnotationClicked((x, 20.0))
    assert "Frame 0 complete (4/4)" in window.calibrationGuideLabel.text()
    assert "Continue to frame 4." in window.calibrationGuideLabel.text()
    assert window.calibrationGuideButton.text() == "Next frame (4)"

    # guide_next：跳到帧集的下一帧（异步解码）
    window._onAnnotationGuideAction("guide_next")
    qtbot.waitUntil(lambda: window._presented_frame_index == 4, timeout=5000)
    # 帧 4 已预先标满 → 提示完成、给出 finish 出口
    assert "Frame 4 complete (4/4)." in window.calibrationGuideLabel.text()
    assert window.calibrationGuideButton.text() == "Finish guided marking"

    # guide_finish：退出引导
    window._onAnnotationGuideAction("guide_finish")
    assert not window.experiment_guide_active
    assert window.calibrationGuideLabel.isHidden()


def test_guide_entry_jump_retries_after_transient_seek_rejection(
    qtbot: QtBot, synthetic_video_path: Path, tmp_path: Path, monkeypatch
) -> None:
    """F1(2026-09-24 HR)：加载窗口期内 seekFrame 被拒时入口跳帧不得静默丢失。

    真机观察到项目加载后第一次进入引导偶发不跳帧（呈现帧停在原处，
    重新进入才生效）。入口路径对单次 seekFrame 失败改为有界重试：
    本测试拒绝首次 seek 并断言定时器重试最终呈现帧集目标帧。
    """

    window = _opened_window(qtbot, synthetic_video_path)
    _wait_presented(qtbot, window)
    tracks = _four_tracks(window.analysisSession, window.activeVideoId)
    experiment = _experiment_via_menu(
        qtbot, monkeypatch, window, tracks, tmp_path / "publication-copy")
    session = window.analysisSession

    # 帧集只含帧 4（无任何标注）→ 入口目标 4 ≠ 当前呈现帧
    session.set_experiment_frame_set(
        experiment.experiment_id,
        ExperimentFrameSet(frames=(4,), algorithm="uniform", created_at=utc_now()),
    )
    assert window._presented_frame_index != 4

    real_seek = window.seekFrame
    state = {"rejected_first": False}

    def flaky_seek(frame_index: int) -> bool:
        if not state["rejected_first"]:
            state["rejected_first"] = True
            return False
        return real_seek(frame_index)

    monkeypatch.setattr(window, "seekFrame", flaky_seek)
    window.beginExperimentAnnotation()
    assert window.experiment_guide_active

    qtbot.waitUntil(lambda: window._presented_frame_index == 4, timeout=5000)
    assert "click the tip" in window.calibrationGuideLabel.text()


# ---------------------------------------------------------------------------
# 引导 marker：四 role 全显示
# ---------------------------------------------------------------------------


def test_guided_markers_show_all_four_roles(
    qtbot: QtBot, synthetic_video_path: Path, tmp_path: Path, monkeypatch
) -> None:
    window, session = _guided_window(qtbot, synthetic_video_path, tmp_path, monkeypatch)
    experiment = window.currentPendulumExperiment()
    roles = experiment.roles
    tracks = list(session.tracks)
    color_by_role = {
        role: next(t.color for t in tracks if t.track_id == member)
        for role, member in roles.by_role().items()
    }

    window._presented_frame_index = 2
    for x in (11.0, 12.0, 13.0, 14.0):
        window._onGuidedAnnotationClicked((x, 20.0))

    # 四 role 各 1 点：引导模式不依赖选中，全部显示为 marker
    assert window.videoView.marker_count() == 4
    views = window.videoView.marker_views()
    assert {view.frame_index for view in views} == {2}
    assert all(view.source == "manual" for view in views)
    view_colors = {view.color for view in views}
    for role in ROLE_ORDER:
        assert color_by_role[role] in view_colors


# ---------------------------------------------------------------------------
# frame_set 持久化：保存 → 重开完整往返
# ---------------------------------------------------------------------------


def test_frame_set_persists_across_project_reopen(
    qtbot: QtBot, synthetic_video_path: Path, tmp_path: Path, monkeypatch
) -> None:
    window = _opened_window(qtbot, synthetic_video_path)
    session = window.analysisSession
    tracks = _four_tracks(session, window.activeVideoId)
    experiment = _experiment_via_menu(
        qtbot, monkeypatch, window, tracks, tmp_path / "v2")
    session.set_experiment_frame_set(
        experiment.experiment_id,
        ExperimentFrameSet(frames=(1, 2, 3), algorithm="uniform", created_at=utc_now()),
    )
    session.save()

    # 重开：走 openProject 的文件对话框路径
    monkeypatch.setattr(
        QFileDialog,
        "getOpenFileName",
        staticmethod(lambda *a, **k: (str(tmp_path / "v2" / "project.json"), "")),
    )
    window.projectActions.openProject()
    qtbot.waitUntil(lambda: not window.projectActions.busy, timeout=5000)

    reopened = window.analysisSession
    assert reopened is not session
    assert reopened.project_root == (tmp_path / "v2").resolve()
    restored = reopened.pendulum_experiments()[0]
    assert restored.experiment_id == experiment.experiment_id
    assert restored.roles == experiment.roles
    # 共享帧集完整往返（契约 §3：帧号只存一次）
    assert restored.frame_set is not None
    assert restored.frame_set.frames == (1, 2, 3)
    assert restored.frame_set.algorithm == "uniform"
    assert frame_set_worklist(restored) == (1, 2, 3)

    # pendulum 面板与四 role pins 正常
    qtbot.waitUntil(
        lambda: window.pendulumPanel.experimentId() == restored.experiment_id,
        timeout=5000,
    )
    assert not window.pendulumPanel.isHidden()
    assert window.trackList.count() == 4
    assert window.currentPendulumExperiment() is not None


# ---------------------------------------------------------------------------
# FrameSelectionActions：experiment 存在时写共享帧集
# ---------------------------------------------------------------------------


def test_frame_selection_actions_persist_shared_frame_set(
    qtbot: QtBot, synthetic_video_path: Path, tmp_path: Path, monkeypatch
) -> None:
    window, session = _guided_window(qtbot, synthetic_video_path, tmp_path, monkeypatch)
    experiment = window.currentPendulumExperiment()
    roles = experiment.roles
    # 四 role 中两个 role 各标帧 0（重叠）→ 排除集应为并集 {0}
    session.mark_point(roles.tip, 0, 10.0, 10.0)
    session.mark_point(roles.pivot, 0, 5.0, 5.0)

    actions = window.frameSelectionActions
    panel = window.trackingActions.panel
    handle = _FakeHandle()
    actions.runner = _FakeRunner(handle)

    actions.requestSuggestion(n_frames=2, algorithm="uniform")
    qtbot.waitUntil(lambda: actions._handle is handle, timeout=3000)

    # experiment 存在 → 请求归属 experiment，排除集为四 role manual 并集
    assert actions._running_experiment_id == experiment.experiment_id
    assert actions._job_request.selection_request.experiment_id == experiment.experiment_id
    assert actions._job_request.selection_request.excluded_frames == frozenset({0})

    # 模拟 worker 写结果并退出
    req_id = actions._request_id
    out_dir = session.project_root / "data" / "engines" / str(req_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "frame-selection-result.json").write_text(json.dumps({
        "request_id": str(req_id),
        "algorithm": "uniform",
        "suggested_frames": [2, 4],
        "actual_n": 2,
        "excluded_count": 1,
        "params_snapshot": {"algorithm": "uniform"},
    }), encoding="utf-8")
    handle.die()
    handle.add_message(TaskResult(run_id=req_id, success=True,
                                  payload={"status": "completed"}))
    qtbot.waitUntil(lambda: not actions.busy, timeout=3000)

    # 结果回写为 experiment 共享帧集（可撤销事务），状态栏明示
    saved = window.currentPendulumExperiment()
    assert saved.frame_set is not None
    assert saved.frame_set.frames == (2, 4)
    assert saved.frame_set.algorithm == "uniform"
    assert "Saved as shared frame set" in panel.suggestStatusLabel.text()
