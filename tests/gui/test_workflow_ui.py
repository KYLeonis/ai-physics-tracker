"""Phase 5.7 — 工作区切换、常驻状态头与任务卡的 GUI 冒烟（offscreen）。

重点测状态与语义（卡片内容、工作区可见性、导航不改数据），不测像素布局。
"""

from pathlib import Path

from pytestqt.qtbot import QtBot

from ai_physics_tracker.application.video_session import VideoSession
from ai_physics_tracker.gui.main_window import MainWindow
from ai_physics_tracker.infrastructure.ffprobe_timing import FFprobeTimingProbe
from ai_physics_tracker.infrastructure.opencv_video_reader import OpenCVVideoReader
from ai_physics_tracker.infrastructure.project_repository import ProjectRepository


def _window() -> MainWindow:
    return MainWindow(
        lambda: VideoSession(OpenCVVideoReader()), ProjectRepository(), FFprobeTimingProbe()
    )


def test_three_workspaces_switch_without_touching_data(
    qtbot: QtBot, synthetic_video_path: Path
) -> None:
    window = _window()
    qtbot.addWidget(window)
    window.show()
    assert window.openVideo(synthetic_video_path, show_error=False)
    window.addTrackButton.click()
    session = window.analysisSession
    assert session is not None
    session.mark_point(session.tracks[0].track_id, 0, 10.0, 10.0)
    observations_before = session.project.observations

    assert window.currentWorkspace == "acquire"
    assert window.trackingActions.panel.isVisible()

    # 切到分析：视频参照重挂、任务面板隐藏、图表可见
    window.setWorkspace("analysis")
    assert window.currentWorkspace == "analysis"
    assert window.chartActions.panel.isVisible()
    assert not window.trackingActions.panel.isVisible()
    assert window.videoView.parent() is not None  # 仍存活，只是换了宿主

    # 切到实验设置：回到视频页，数据不变（导航只改视图）
    window.setWorkspace("setup")
    assert window.currentWorkspace == "setup"
    assert session.project.observations == observations_before

    # 切回获取轨迹：视频视图回到原列
    window.setWorkspace("acquire")
    assert window.trackingActions.panel.isVisible()


def test_header_shows_context_and_card_follows_projection(
    qtbot: QtBot, synthetic_video_path: Path, tmp_path: Path
) -> None:
    window = _window()
    qtbot.addWidget(window)
    window.show()

    # 无项目：卡片为空、状态头显示 No project
    assert window.workflowHeader.contextLabel.text() == "No project"
    assert not window.trackingActions.panel.cardPrimaryButton.isVisible()

    assert window.openVideo(synthetic_video_path, show_error=False)
    window.addTrackButton.click()
    session = window.analysisSession
    track = session.tracks[0]

    # 保存（选帧/学习前置）后：卡片进入标注模式（<3 帧）
    session.save_as(tmp_path / "proj")
    window.trackingActions._context_key = None
    window.trackingActions.refresh()
    card = window.trackingActions.panel
    assert "mark example positions" in card.cardTitleLabel.text()
    assert card.cardPrimaryButton.text() == "Pick representative frames"

    # 状态头显示项目/视频/目标/范围
    header_text = window.workflowHeader.contextLabel.text()
    assert "Project:" in header_text and "Object:" in header_text and "Range:" in header_text
    assert window.workflowHeader.trajectoryLabel.text().startswith("Current trajectory:")


def test_card_running_task_shows_cancel(qtbot: QtBot, synthetic_video_path: Path,
                                         tmp_path: Path) -> None:
    from tests.gui.test_tracking_actions import _FakeHandle, _FakeRunner, _opened_window

    window, session, track_id = _opened_window(qtbot, synthetic_video_path, tmp_path,
                                               _FakeRunner(_FakeHandle()))
    panel = window.trackingActions.panel

    # 该 fixture 已标 3 帧：卡片进入“可开始学习”（系统备好计划，用户显式启动）
    window.trackingActions._context_key = None
    window.trackingActions.refresh()
    assert panel.cardPrimaryButton.text() == "Start learning"
    assert "fixed-check" in panel.evidenceTextLabel.text()

    # 清空标注路径不可行（保存后），改用直接验证选帧运行卡片：手动触发选帧
    window.frameSelectionActions.requestSuggestion(n_frames=5, algorithm="kmeans")
    assert window.frameSelectionActions.busy
    qtbot.waitUntil(
        lambda: panel.cardTitleLabel.text().startswith("Current: picking"),
        timeout=3000)
    assert panel.cardPrimaryButton.text() == "Cancel"


def test_start_learning_card_confirms_fixed_check_then_trains(
    qtbot: QtBot, synthetic_video_path: Path, tmp_path: Path, monkeypatch
) -> None:
    """C1+C2：卡片“开始学习”→ 预选确认 → freeze → 以系统计划启动训练。"""
    from ai_physics_tracker.gui.fixed_check_dialog import (
        RESULT_KEEP,
        FixedCheckConfirmDialog,
    )
    from tests.gui.test_tracking_actions import _FakeHandle, _FakeRunner, _opened_window

    window, session, track_id = _opened_window(qtbot, synthetic_video_path, tmp_path,
                                               _FakeRunner(_FakeHandle()))
    session.mark_point(track_id, 3, 40.0, 50.0)  # 共 4 帧 → 预选 1 帧检查

    captured = {}

    def fake_exec(self):
        captured["frames"] = [
            self.frameList.item(i).data(0x0100) for i in range(self.frameList.count())
        ]
        captured["choice"] = self.result_choice = RESULT_KEEP
        return True

    monkeypatch.setattr(FixedCheckConfirmDialog, "exec", fake_exec)
    panel = window.trackingActions.panel
    window.trackingActions._context_key = None
    window.trackingActions.refresh()

    assert panel.cardPrimaryButton.text() == "Start learning"
    panel.cardPrimaryButton.click()

    # C1：预选集合经用户确认后才 freeze
    assert captured["frames"] == [1]  # 4 帧 [0,1,2,3] → 预选内部帧 1（floor 平局取早）
    state = session.get_refinement_state(track_id)
    assert state.active_series is not None
    assert tuple(state.active_series.frame_indices) == tuple(captured["frames"])

    # C2：系统计划写入表单（restart/50/8）并启动（同一执行入口）
    assert window.trackingActions.runner.calls == 1
    assert panel.trainingMode() == "restart"
    assert panel.epochsSpinBox.value() == 50
    train_runs = [r for r in session.tracking_runs() if r.task_type == "train"]
    assert len(train_runs) == 1 and train_runs[0].status in {"pending", "running"}


def test_generate_trajectory_binds_latest_completed_model(
    qtbot: QtBot, synthetic_video_path: Path, tmp_path: Path
) -> None:
    from tests.gui.test_tracking_actions import _FakeHandle, _FakeRunner, _opened_window

    window, session, track_id = _opened_window(qtbot, synthetic_video_path, tmp_path,
                                               _FakeRunner(_FakeHandle()))
    # 构造一个完成的训练 run（带 snapshot 文件）
    from ai_physics_tracker.domain.tracking_run import (
        create_tracking_run,
        mark_run_completed,
    )
    run = create_tracking_run(track_id.video_id if hasattr(track_id, "video_id")
                              else _video_id(session, window), track_id, "train",
                              engine_version="mock")
    snap_rel = f"data/engines/{run.run_id}/snap.pt"
    snap = session.project_root / snap_rel
    snap.parent.mkdir(parents=True, exist_ok=True)
    snap.write_bytes(b"w")
    run = mark_run_completed(run, model_snapshot=snap_rel)
    session.record_tracking_run(run)

    panel = window.trackingActions.panel
    window.trackingActions._context_key = None
    window.trackingActions.refresh()

    assert panel.cardPrimaryButton.text() == "Generate trajectory"
    panel.cardPrimaryButton.click()

    assert window.trackingActions.runner.calls == 1
    infer_runs = [r for r in session.tracking_runs() if r.task_type == "infer"]
    assert len(infer_runs) == 1
    assert infer_runs[0].config.get("training_run_id") == str(run.run_id)


def _video_id(session, window):
    track = next(t for t in session.tracks if t.track_id == window.selectedTrackId)
    return track.video_id
