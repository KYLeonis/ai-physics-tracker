"""Phase 5.7 — 工作区切换、常驻状态头与任务卡的 GUI 冒烟（offscreen）。

重点测状态与语义，并覆盖小窗口下关键动作可达性；不做视觉像素比对。
"""

from pathlib import Path
from uuid import uuid4

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


def test_acquire_panel_fits_1024_by_640_without_horizontal_clipping(
    qtbot: QtBot, synthetic_video_path: Path, tmp_path: Path
) -> None:
    from tests.gui.test_tracking_actions import _FakeHandle, _FakeRunner, _opened_window

    window, _session, _track_id = _opened_window(
        qtbot, synthetic_video_path, tmp_path, _FakeRunner(_FakeHandle()))
    window.resize(1024, 640)
    window.show()
    panel = window.trackingActions.panel
    scroll = panel.widget()
    # resizeDocks 由 showEvent 的 singleShot 调度；Windows CI 的 Qt event loop
    # 可能超过固定 30 ms 才应用目标宽度，因此等待可观察布局事实。
    qtbot.waitUntil(lambda: panel.width() >= 280, timeout=1000)

    assert 280 <= panel.width() <= 430
    assert scroll.horizontalScrollBar().maximum() == 0
    assert panel.cardPrimaryButton.isVisible()

    panel.advancedToggleButton.click()
    qtbot.wait(20)
    assert scroll.horizontalScrollBar().maximum() == 0
    assert scroll.verticalScrollBar().maximum() > 0

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
    qtbot.waitUntil(lambda: window.trackingActions.runner.calls == 1, timeout=3000)
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




def _better_candidate_setup(qtbot, synthetic_video_path, tmp_path):
    """active v1 + 更好候选 v2（固定检查比较 better）的窗口。"""
    import dataclasses
    from uuid import uuid4 as _uuid

    from ai_physics_tracker.domain.tracking_run import (
        create_tracking_run,
        mark_run_completed,
    )
    from tests.gui.test_tracking_actions import _FakeHandle, _FakeRunner, _opened_window
    from tests.test_workflow_projection import (
        _completed_train_with_eval as _train_with_eval,
    )

    window, session, track_id = _opened_window(qtbot, synthetic_video_path,
                                               tmp_path, _FakeRunner(_FakeHandle()))
    for frame in (3, 4):
        session.mark_point(track_id, frame, 30.0 + frame, 40.0)
    series = session.create_validation_series(track_id, "fixed", [4])
    runs = session.tracking_runs()
    train1 = _train_with_eval(session, session.tracks[0], runs,
                              training_frames=[0, 1, 2],
                              series_id=series.series_id, val_rmse=5.0)
    train2 = _train_with_eval(session, session.tracks[0], runs + (train1,),
                              training_frames=[0, 1, 3],
                              series_id=series.series_id, val_rmse=4.0)

    def _infer(source):
        run = create_tracking_run(track_id.video_id if hasattr(track_id, "video_id")
                                  else _video_id(session, window), track_id, "infer",
                                  engine="dlc", engine_version="mock",
                                  source_detail=f"test:{_uuid()}",
                                  config={"training_run_id": str(source.run_id)})
        return run

    infer1 = _infer(train1)
    folder = session.project_root / "data" / "engines" / str(infer1.run_id)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "observations.json").write_text("[]", encoding="utf-8")
    session.record_tracking_run(mark_run_completed(infer1))
    session.activate_infer_run(track_id, infer1.run_id)
    infer2 = _infer(train2)
    folder2 = session.project_root / "data" / "engines" / str(infer2.run_id)
    folder2.mkdir(parents=True, exist_ok=True)
    (folder2 / "observations.json").write_text("[]", encoding="utf-8")
    session.record_tracking_run(mark_run_completed(infer2))
    return window, session, track_id, infer1, infer2


def test_adopt_card_replaces_after_confirmation_and_history_only_previews(
    qtbot, synthetic_video_path, tmp_path, monkeypatch
) -> None:
    from PySide6.QtWidgets import QMessageBox

    window, session, track_id, infer1, infer2 = _better_candidate_setup(
        qtbot, synthetic_video_path, tmp_path)
    panel = window.trackingActions.panel
    window.trackingActions._context_key = None
    window.trackingActions.refresh()

    # better 结论驱动主动作 = 采用；标题明示固定检查改善
    assert panel.cardPrimaryButton.text() == "Adopt for analysis"
    assert "looks better" in panel.cardTitleLabel.text()

    # conftest 把 question 桩化为 Discard：确认被拒 → 不采用
    panel.cardPrimaryButton.click()
    assert session.get_track_activation_status(track_id)[1] == infer1.run_id

    # 确认 Yes → 走既有 replace 原子事务
    monkeypatch.setattr(
        QMessageBox, "question",
        lambda *a, **k: QMessageBox.StandardButton.Yes)
    panel.cardPrimaryButton.click()
    assert session.get_track_activation_status(track_id)[1] == infer2.run_id

    # 采用后：无候选，卡片进入“图表待更新”；状态头显示当前版本
    window.trackingActions._context_key = None
    window.trackingActions.refresh()
    assert window.trackingActions.panel.cardPrimaryButton.text() == "Update charts"
    assert "Preview:" not in window.workflowHeader.trajectoryLabel.text()

    # history 选择旧行为只预览：不改变 active
    window.trackingActions.panel.resultsToggleButton.click()
    history = window.trackingActions.panel.historyList
    for i in range(history.count()):
        if history.item(i).data(0x0100) == infer1.run_id:
            history.setCurrentRow(i)
            break
    assert session.get_track_activation_status(track_id)[1] == infer2.run_id


def test_analysis_source_bar_and_chip_reflect_projection(
    qtbot, synthetic_video_path, tmp_path
) -> None:
    window, session, track_id, infer1, _infer2 = _better_candidate_setup(
        qtbot, synthetic_video_path, tmp_path)
    window.setWorkspace("analysis")

    # 来源条：版本 + 人工点数 + 单位 + 时间依据
    source = window._analysisSourceLabel.text()
    assert "version 1 AI result" in source
    assert "manual position(s)" in source
    assert "px (no calibration)" in source
    assert "Timing:" in source

    # 状态头 chip：采用后待更新
    assert "charts need update" in window.workflowHeader.analysisChipLabel.text()


def test_candidate_preview_does_not_pollute_charts(
    qtbot, synthetic_video_path, tmp_path
) -> None:
    """候选只登记 run，不进入 effective 投影与图表输入（ADR-0014 隔离）。"""
    from dataclasses import replace
    from ai_physics_tracker.domain.tracking_run import (
        create_tracking_run,
        mark_run_completed,
    )
    from tests.gui.test_tracking_actions import _FakeHandle, _FakeRunner, _opened_window
    from tests.test_workflow_projection import _fake_observations

    window, session, track_id = _opened_window(qtbot, synthetic_video_path,
                                               tmp_path, _FakeRunner(_FakeHandle()))
    # manual-only 轨迹 + 已计算图表
    session.mark_point(track_id, 3, 30.0, 40.0)
    session.mark_point(track_id, 4, 35.0, 45.0)
    session.compute_kinematics(track_id)
    effective_before = session.effective_points(track_id)
    derived_before = session.project.derived

    # 新候选（未激活）登记：completed infer run
    candidate = create_tracking_run(
        _video_id(session, window), track_id, "infer",
        engine="dlc", engine_version="mock",
        config={"min_confidence": 0.6},
    )
    _fake_observations(session, candidate)
    run_dir = session.project_root / "data" / "engines" / str(candidate.run_id)
    prediction_path = run_dir / "predictions.csv"
    video = session.project.videos[0]
    rows = [
        "scorer,MockDLC,MockDLC,MockDLC",
        "bodyparts,target,target,target",
        "coords,x,y,likelihood",
    ]
    rows.extend(
        f"{frame_index},{20.0 + frame_index},{30.0 + frame_index},"
        f"{0.2 if frame_index < 2 else 0.9}"
        for frame_index in range(video.frame_count)
    )
    prediction_path.write_text("\n".join(rows) + "\n", encoding="utf-8")
    prediction_stat = prediction_path.stat()
    candidate = replace(candidate, extra_fields={
        "observations_path": (
            f"data/engines/{candidate.run_id}/observations.json"),
        "prediction_path": (
            f"data/engines/{candidate.run_id}/predictions.csv"),
        "prediction_file_info": [
            prediction_stat.st_size, prediction_stat.st_mtime_ns],
    })
    session.record_tracking_run(mark_run_completed(candidate))

    assert session.effective_points(track_id) == effective_before
    assert session.project.derived == derived_before

    window.trackingActions._context_key = None
    window.trackingActions.refresh()
    qtbot.waitUntil(
        lambda: len(window.videoView.preview_marker_views()) == video.frame_count,
        timeout=3000)
    # 卡片呈现候选采用结论；状态头标明 Preview 且分析 chip 不因候选变化
    assert "Preview: version 1 (not adopted)" in window.workflowHeader.trajectoryLabel.text()
    assert window.videoView._preview_legend.isVisible()
    assert "below confidence threshold" in window.videoView._preview_legend.text()
    assert sum(marker.color == "#ff6b6b"
               for marker in window.videoView.preview_marker_views()) == 2
    analysis_chip = window.workflowHeader.analysisChipLabel.text()
    assert "charts" in analysis_chip  # 只描述当前输入，不被候选覆盖


def test_inspect_binds_candidate_not_oldest_run(
    qtbot, synthetic_video_path, tmp_path, monkeypatch
) -> None:
    """R1 F1：检查对象 = 当前候选，不是注册序最旧的 completed infer run。"""
    window, session, track_id, infer1, infer2 = _better_candidate_setup(
        qtbot, synthetic_video_path, tmp_path)
    captured = {}
    monkeypatch.setattr(
        window.reviewActions, "requestMining",
        lambda run_id, params=None: captured.setdefault("run_id", run_id))

    window.trackingActions._context_key = None
    window.trackingActions.refresh()
    # 当前卡为 better→Adopt；次动作/inspect 路由直接调用
    window.trackingActions._onCardAction("inspect_trajectory")
    assert captured["run_id"] == infer2.run_id


def test_empty_screening_card_reruns_candidate_with_force(
    qtbot, synthetic_video_path, tmp_path, monkeypatch
) -> None:
    from ai_physics_tracker.application.suggested_frame_review import ActiveReviewBatch

    window, session, _track_id, _infer1, infer2 = _better_candidate_setup(
        qtbot, synthetic_video_path, tmp_path)
    session.set_active_review_batch(infer2.run_id, ActiveReviewBatch(
        request_id=uuid4(), params_snapshot={"top_n": 10}, candidates=()))
    captured = {}

    def _capture(run_id, params=None, *, force=False):
        captured.update(run_id=run_id, params=params, force=force)

    monkeypatch.setattr(window.reviewActions, "requestMining", _capture)
    window.trackingActions._context_key = None
    window.trackingActions.refresh()

    assert "screening complete" in window.trackingActions.panel.cardTitleLabel.text()
    window.trackingActions._onCardAction("recheck_trajectory")
    assert captured["run_id"] == infer2.run_id
    assert captured["force"] is True


def test_invalid_series_rebuild_flow_via_card(
    qtbot, synthetic_video_path, tmp_path, monkeypatch
) -> None:
    """R1 F2：集合失效 → 卡片给重建主动作；确认后停用旧集并 freeze 新预选。"""
    from ai_physics_tracker.gui.fixed_check_dialog import (
        RESULT_KEEP,
        FixedCheckConfirmDialog,
    )
    from tests.gui.test_tracking_actions import _FakeHandle, _FakeRunner, _opened_window

    window, session, track_id = _opened_window(qtbot, synthetic_video_path, tmp_path,
                                               _FakeRunner(_FakeHandle()))
    for frame in (3, 4):
        session.mark_point(track_id, frame, 30.0 + frame, 40.0)
    series = session.create_validation_series(track_id, "old", [4])
    session.mark_point(track_id, 4, 99.0, 99.0)  # 使集合失效
    assert not session.validate_active_validation_series(track_id)[0]

    monkeypatch.setattr(
        FixedCheckConfirmDialog, "exec",
        lambda self: (setattr(self, "result_choice", RESULT_KEEP), True)[1])

    window.trackingActions._context_key = None
    window.trackingActions.refresh()
    panel = window.trackingActions.panel
    assert panel.cardPrimaryButton.text() == "Review suggested check frames"
    panel.cardPrimaryButton.click()

    state = session.get_refinement_state(track_id)
    assert state.active_series is not None
    assert state.active_series.series_id != series.series_id  # 旧集被替换（停用+新建）
    assert session.validate_active_validation_series(track_id)[0]
    # P6R-03：被引用旧集不可删除，仅停用——仍保留在 series 列表中
    assert state.get_series(series.series_id) is not None


def test_activation_failure_dialog_uses_three_question_copy(
    qtbot, synthetic_video_path, tmp_path, monkeypatch
) -> None:
    """R2 N1：激活失败路径不再 NameError，对话框带三问文案。"""
    from PySide6.QtWidgets import QMessageBox

    window, session, track_id, infer1, _infer2 = _better_candidate_setup(
        qtbot, synthetic_video_path, tmp_path)
    captured = {}
    monkeypatch.setattr(
        QMessageBox, "critical",
        lambda parent, title, text, *a, **k: captured.update(
            title=title, text=text) or QMessageBox.StandardButton.Ok)
    # 确认问题桩为 Yes（conftest 默认 Discard 会提前退出）
    monkeypatch.setattr(
        QMessageBox, "question",
        lambda *a, **k: QMessageBox.StandardButton.Yes)

    # 已激活的 run 再走 activate → session 抛错 → critical 路径
    window.trackingActions.activateRun(infer1.run_id)
    assert captured["title"] == "Activation Failed"
    assert "No new trajectory was adopted" in captured["text"]
    assert "Next:" in captured["text"]


def test_header_shows_analysis_limitations(
    qtbot, synthetic_video_path, tmp_path
) -> None:
    """R2 O2：limitations 行真实渲染（缺测数量可见）。"""
    from tests.gui.test_tracking_actions import _FakeHandle, _FakeRunner, _opened_window

    window, session, track_id = _opened_window(qtbot, synthetic_video_path, tmp_path,
                                               _FakeRunner(_FakeHandle()))
    # 视频共 5 帧，fixture 只标了 0/1/2 → 2 帧缺测
    window.trackingActions._context_key = None
    window.trackingActions.refresh()
    limitations = window.workflowHeader.limitationsLabel
    assert limitations.isVisible() or not limitations.isHidden()
    assert "2 of 5 frames" in limitations.text()
    assert "no effective observation" in limitations.text()
