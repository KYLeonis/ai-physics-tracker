"""Pendulum setup GUI（P1.1-S5）的 Qt offscreen 测试。

覆盖 pendulum_setup.py（向导 / 物理参数对话框 / 侧栏 checklist）与
main_window / project_actions / video_view 的 pendulum 几何录入链路：
- 向导校验：role 缺口、重复 track、destination 已存在、合法提交
- 向导按构造只提供当前 video 的 track（跨 video 不可达）
- File 菜单 "Create Pendulum experiment…" → rootless v2 首存 + 几何写入
- true vertical 端点变化撤销既有确认（契约 §2）
- 物理参数对话框保存与本地校验（来源 provenance 必填）
- release 帧取自当前呈现帧；未呈现任何帧时拒绝写入
- checklist 面板随事实重建（incomplete → complete）
- v1 项目迁移：源目录字节不变、新目录 schema v2、undo 历史清空
- 任务卡动作路由到 pendulum 入口（pivot / vertical 点选模式）
"""

import json
from pathlib import Path
from uuid import UUID, uuid4

from PySide6.QtCore import QPointF
from PySide6.QtWidgets import QDialog, QFileDialog, QMessageBox
from pytestqt.qtbot import QtBot

from ai_physics_tracker.application.project_session import ProjectSession
from ai_physics_tracker.application.video import VideoStreamInfo
from ai_physics_tracker.application.video_session import VideoSession
from ai_physics_tracker.domain.pendulum import (
    ROLE_ORDER,
    PendulumRoles,
    PhysicalParameters,
)
from ai_physics_tracker.domain.track import Track
from ai_physics_tracker.domain.types import utc_now
from ai_physics_tracker.gui import project_actions
from ai_physics_tracker.gui.main_window import MainWindow
from ai_physics_tracker.gui.pendulum_setup import (
    PendulumWizardDialog,
    PhysicalParametersDialog,
)
from ai_physics_tracker.infrastructure.ffprobe_timing import FFprobeTimingProbe
from ai_physics_tracker.infrastructure.opencv_video_reader import OpenCVVideoReader
from ai_physics_tracker.infrastructure.project_repository import ProjectRepository


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


def _stub_track(name: str, video_id: UUID) -> Track:
    """直接构造 Track（不落 session），供向导的独立单测使用。"""

    return Track(
        track_id=uuid4(),
        video_id=video_id,
        name=name,
        color="#336699",
        created_at=utc_now(),
    )


def _four_tracks(session: ProjectSession, video_id: UUID) -> list[Track]:
    return [session.add_track(video_id, f"pendulum track {i + 1}") for i in range(4)]


def _roles_from(tracks: list[Track]) -> PendulumRoles:
    return PendulumRoles(
        tip=tracks[0].track_id,
        body_top=tracks[1].track_id,
        body_bottom=tracks[2].track_id,
        pivot=tracks[3].track_id,
    )


class _WizardStub:
    """以预设结论替代向导交互：exec 直接接受，roles/destination 返回预设值。

    记录构造参数（offered_tracks / require_destination），供测试断言
    createPendulumExperiment 传入了什么；不弹任何原生对话框。
    """

    DialogCode = QDialog.DialogCode
    roles: PendulumRoles
    destination_path: Path
    instances: "list[_WizardStub]" = []

    def __init__(
        self,
        offered_tracks: list[Track],
        *,
        require_destination: bool = True,
        default_destination: str = "",
        parent=None,
    ) -> None:
        self.offered_tracks = list(offered_tracks)
        self.require_destination = require_destination
        _WizardStub.instances.append(self)

    def exec(self) -> int:
        return 1

    def pendulum_roles(self) -> PendulumRoles:
        return _WizardStub.roles

    def destination(self) -> Path:
        return _WizardStub.destination_path


def _accept_wizard(monkeypatch, tracks: list[Track], destination: Path) -> type[_WizardStub]:
    """把 project_actions 命名空间中的向导类换成 stub 并返回 stub 类。"""

    _WizardStub.roles = _roles_from(tracks)
    _WizardStub.destination_path = destination
    _WizardStub.instances = []
    monkeypatch.setattr(project_actions, "PendulumWizardDialog", _WizardStub)
    return _WizardStub


def _experiment_via_menu(
    qtbot: QtBot,
    monkeypatch,
    window: MainWindow,
    tracks: list[Track],
    destination: Path,
):
    """走 File 菜单入口创建 experiment（stub 向导），等待后台迁移完成。"""

    _accept_wizard(monkeypatch, tracks, destination)
    window.projectActions.createPendulumExperiment()
    qtbot.waitUntil(lambda: not window.projectActions.busy, timeout=5000)
    experiment = window.currentPendulumExperiment()
    assert experiment is not None
    return experiment


def test_wizard_validation_rejects_missing_roles_duplicate_and_existing_destination(
    tmp_path: Path,
) -> None:
    video_id = uuid4()
    tracks = [
        _stub_track(name, video_id)
        for name in ("tip", "body top", "body bottom", "pivot")
    ]
    dialog = PendulumWizardDialog(tracks, require_destination=True)

    # role 未指派（combo 虽有缺省项，清空后模拟缺测）→ 提示补齐 role
    dialog.set_role_track("tip", tracks[0])
    dialog._role_combos["body_top"].setCurrentIndex(-1)
    error = dialog.validate()
    assert error is not None and "Select a track" in error

    # role 齐备但 destination 为空 → 提示 destination
    for role, track in zip(ROLE_ORDER[1:], tracks[1:]):
        dialog.set_role_track(role, track)
    dialog.destinationEdit.setText("")
    error = dialog.validate()
    assert error is not None and "destination" in error.lower()

    # 两个 role 选同一 track → 提示 different track（优先于 destination 校验）
    dialog.set_role_track("body_top", tracks[0])
    error = dialog.validate()
    assert error is not None and "different track" in error

    # destination 指向已存在路径 → 提示 already exists
    dialog.set_role_track("body_top", tracks[1])
    existing = tmp_path / "already-there"
    existing.mkdir()
    dialog.destinationEdit.setText(str(existing))
    error = dialog.validate()
    assert error is not None and "already exists" in error

    # 合法选择：四个不同 track + 不存在的 destination → 通过并返回四 UUID
    dialog.destinationEdit.setText(str(tmp_path / "fresh-publication"))
    assert dialog.validate() is None
    roles = dialog.pendulum_roles()
    assert {roles.tip, roles.body_top, roles.body_bottom, roles.pivot} == {
        track.track_id for track in tracks
    }
    assert all(isinstance(value, UUID) for value in roles.track_ids())


def test_wizard_rejects_cross_video_is_prevented_by_construction() -> None:
    """向导只接收当前 video 的 tracks：其他 video 的 track 不出现在选项中。"""

    current_video, other_video = uuid4(), uuid4()
    current_tracks = [
        _stub_track(f"current {i + 1}", current_video) for i in range(4)
    ]
    stranger = _stub_track("stranger", other_video)

    dialog = PendulumWizardDialog(current_tracks, require_destination=False)
    offered = {
        dialog._role_combos[role].itemData(index)
        for role in ROLE_ORDER
        for index in range(dialog._role_combos[role].count())
    }
    assert offered == {str(track.track_id) for track in current_tracks}
    assert str(stranger.track_id) not in offered
    # publication 项目路径不出现 destination 输入
    assert dialog.destinationEdit is None


def test_pivot_and_vertical_clicks_write_experiment_geometry(
    qtbot: QtBot, synthetic_video_path: Path, tmp_path: Path, monkeypatch
) -> None:
    window = _opened_window(qtbot, synthetic_video_path)
    assert any(
        action.text() == "Create Pendulum experiment…"
        for action in window.projectActions.actions
    )
    session = window.analysisSession
    video_id = window.activeVideoId
    tracks = _four_tracks(session, video_id)
    destination = tmp_path / "publication-copy"

    stub = _accept_wizard(monkeypatch, tracks, destination)
    window.projectActions.createPendulumExperiment()
    qtbot.waitUntil(lambda: not window.projectActions.busy, timeout=5000)

    # rootless 新项目 → 向导要求 destination，走 v2 首存（无迁移记录）
    assert stub.instances[-1].require_destination is True
    assert stub.instances[-1].offered_tracks == tracks
    assert session.project_root == destination.resolve()
    experiment = window.currentPendulumExperiment()
    assert experiment is not None and experiment.video_id == video_id
    manifest = json.loads(
        (destination / "project.json").read_text(encoding="utf-8"))
    assert manifest["schema_version"] == 2
    assert "migration" not in manifest  # 首存路径没有 v1 源
    assert window.pendulumPanel.experimentId() == experiment.experiment_id
    assert "Setup incomplete" in window.pendulumPanel.statusLabel.text()

    # 固定 pivot：进入点选模式 → 点击写入几何事实并退出模式
    window.beginPivotPick()
    assert window.videoView.is_calibration_mode() == "pivot"
    window._onPivotClicked(QPointF(10.0, 20.0))
    experiment = window.currentPendulumExperiment()
    assert experiment.geometry.fixed_pivot_px == (10.0, 20.0)
    assert window.videoView.is_calibration_mode() is None
    assert "fixed pivot: (10.0, 20.0) px" in window.pendulumPanel.pivotLabel.text()

    # true vertical：top→bottom 两点写入；保存后方向未确认
    window.beginVerticalPick()
    assert window.videoView.is_calibration_mode() == "vertical"
    window._onVerticalLineDrawn(QPointF(5.0, 1.0), QPointF(5.5, 90.0))
    experiment = window.currentPendulumExperiment()
    vertical = experiment.geometry.true_vertical
    assert vertical is not None
    assert vertical.top_px == (5.0, 1.0)
    assert vertical.bottom_px == (5.5, 90.0)
    assert not vertical.direction_confirmed
    assert window.videoView.is_calibration_mode() is None
    assert "NOT confirmed" in window.pendulumPanel.verticalLabel.text()

    # 确认方向：top→bottom 即重力向下
    window._confirmVerticalDirection()
    experiment = window.currentPendulumExperiment()
    assert experiment.geometry.true_vertical.direction_confirmed
    assert not window.pendulumPanel.confirmVerticalButton.isEnabled()


def test_vertical_endpoint_change_revokes_confirmation(
    qtbot: QtBot, synthetic_video_path: Path, tmp_path: Path, monkeypatch
) -> None:
    window = _opened_window(qtbot, synthetic_video_path)
    session = window.analysisSession
    tracks = _four_tracks(session, window.activeVideoId)
    _experiment_via_menu(
        qtbot, monkeypatch, window, tracks, tmp_path / "publication-copy")

    window.beginVerticalPick()
    window._onVerticalLineDrawn(QPointF(5.0, 1.0), QPointF(5.5, 90.0))
    window._confirmVerticalDirection()
    assert window.currentPendulumExperiment().geometry.true_vertical.direction_confirmed

    # 端点再次变化（直接写入，不经模式）→ 确认被撤销，需重新 confirm
    window._onVerticalLineDrawn(QPointF(6.0, 2.0), QPointF(6.5, 80.0))
    vertical = window.currentPendulumExperiment().geometry.true_vertical
    assert vertical is not None
    assert not vertical.direction_confirmed
    assert vertical.top_px == (6.0, 2.0)
    assert vertical.bottom_px == (6.5, 80.0)
    assert window.pendulumPanel.confirmVerticalButton.isEnabled()


def test_physical_dialog_saves_and_validates(
    qtbot: QtBot, synthetic_video_path: Path, tmp_path: Path, monkeypatch
) -> None:
    window = _opened_window(qtbot, synthetic_video_path)
    session = window.analysisSession
    tracks = _four_tracks(session, window.activeVideoId)
    experiment = _experiment_via_menu(
        qtbot, monkeypatch, window, tracks, tmp_path / "publication-copy")
    assert experiment.physical is None

    # 对话框本地校验：来源 provenance 为空 → 拒绝（值本身合法）
    dialog = PhysicalParametersDialog()
    assert dialog.validate() is not None  # L source 缺省为空
    dialog.lengthSourceEdit.setText("ruler")
    dialog.gSourceEdit.setText("")
    assert dialog.validate() is not None
    dialog.gSourceEdit.setText("standard gravity")
    assert dialog.validate() is None
    dialog.lengthSpin.setValue(2.5)
    assert dialog.physical_parameters() == PhysicalParameters(
        length_m=2.5,
        g_m_s2=dialog.gSpin.value(),
        length_source="ruler",
        g_source="standard gravity",
    )

    # 窗口入口：对话框接受后经 session 落库并刷新面板
    parameters = PhysicalParameters(
        length_m=1.25,
        g_m_s2=9.81,
        length_source="ruler, pivot to bob centre",
        g_source="standard gravity",
    )
    monkeypatch.setattr(PhysicalParametersDialog, "exec", lambda self: 1)
    monkeypatch.setattr(
        PhysicalParametersDialog, "physical_parameters", lambda self: parameters)
    window.openPhysicalDialog()
    assert window.currentPendulumExperiment().physical == parameters
    assert "L = 1.250 m" in window.pendulumPanel.physicalLabel.text()


def test_release_uses_presented_frame(
    qtbot: QtBot, synthetic_video_path: Path, tmp_path: Path, monkeypatch
) -> None:
    window = _opened_window(qtbot, synthetic_video_path)
    session = window.analysisSession
    tracks = _four_tracks(session, window.activeVideoId)
    experiment = _experiment_via_menu(
        qtbot, monkeypatch, window, tracks, tmp_path / "publication-copy")
    assert experiment.release_frame_index is None

    # 尚未呈现任何帧（如视频只读占位）→ 拒绝写入并给出可操作提示
    window._presented_frame_index = None
    window._setReleaseToCurrentFrame()
    assert window.currentPendulumExperiment().release_frame_index is None
    assert "Navigate to the release frame" in window.statusBar().currentMessage()

    # 呈现第 3 帧后写入 → release 记录当前呈现帧（data-model.md §5.5）
    window._presented_frame_index = 3
    window._setReleaseToCurrentFrame()
    assert window.currentPendulumExperiment().release_frame_index == 3
    assert window.pendulumPanel.releaseLabel.text() == "release frame: 3"


def test_checklist_panel_refresh_reflects_status(
    qtbot: QtBot, synthetic_video_path: Path, tmp_path: Path, monkeypatch
) -> None:
    window = _opened_window(qtbot, synthetic_video_path)
    session = window.analysisSession
    video_id = window.activeVideoId
    tracks = _four_tracks(session, video_id)

    # 无 experiment → 面板隐藏
    window.pendulumPanel.refresh(session, video_id)
    assert not window.pendulumPanel.isVisible()

    experiment = _experiment_via_menu(
        qtbot, monkeypatch, window, tracks, tmp_path / "publication-copy")
    experiment_id = experiment.experiment_id
    assert window.pendulumPanel.isVisible()
    assert "Setup incomplete" in window.pendulumPanel.statusLabel.text()

    def status_text() -> str:
        window.pendulumPanel.refresh(session, video_id)
        return window.pendulumPanel.statusLabel.text()

    # scale：active calibration 落地后不再列为缺口
    session._verified_videos.add(video_id)  # openVideo 已验证 CFR；此处幂等
    session.add_calibration(
        video_id=video_id,
        scale_end_1_px=(0.0, 0.0),
        scale_end_2_px=(40.0, 0.0),
        known_length=1.0,
        unit="m",
    )
    text = status_text()
    assert "Setup incomplete" in text
    assert "active scale calibration" not in text
    assert window.pendulumPanel.scaleLabel.text().startswith("scale: set")

    # pivot + vertical（含确认）
    window.beginPivotPick()
    window._onPivotClicked(QPointF(12.0, 6.0))
    window.beginVerticalPick()
    window._onVerticalLineDrawn(QPointF(5.0, 1.0), QPointF(5.5, 90.0))
    window._confirmVerticalDirection()

    # physical
    session.set_physical(
        experiment_id,
        PhysicalParameters(
            length_m=0.98,
            g_m_s2=9.81,
            length_source="ruler",
            g_source="standard gravity",
        ),
    )
    text = status_text()
    assert "Setup incomplete" in text and "release frame" in text

    # release：最后一项补齐 → 分析就绪
    window._presented_frame_index = 2
    window._setReleaseToCurrentFrame()
    assert status_text() == "Setup complete — analysis enabled"


def test_migration_from_saved_v1_project_preserves_source(
    qtbot: QtBot, synthetic_video_path: Path, tmp_path: Path, monkeypatch
) -> None:
    # 先以 v1 形态落一个已保存项目：外部 video 引用 + 四个 track
    source = tmp_path / "v1-source"
    builder = ProjectSession.start(ProjectRepository(), "v1 source project")
    info = VideoStreamInfo(
        width_px=64,
        height_px=48,
        fps_container=10.0,
        frame_count=5,
        container_format="avi",
        timing_status="cfr",
    )
    video, _timeline = builder.register_external_video(synthetic_video_path, info)
    for index in range(4):
        builder.add_track(video.video_id, f"Track {index + 1}")
    builder.save_as(source)
    source_manifest = (source / "project.json").read_bytes()
    assert json.loads(source_manifest)["schema_version"] == 1

    # 经 File → Open project… 打开 v1 目录（QFileDialog 桩掉）
    window = _window()
    qtbot.addWidget(window)
    window.show()
    monkeypatch.setattr(
        QFileDialog, "getOpenFileName",
        lambda *args: (str(source / "project.json"), ""))
    window.projectActions.openProject()
    qtbot.waitUntil(lambda: not window.projectActions.busy, timeout=5000)

    session = window.analysisSession
    video_id = window.activeVideoId
    assert video_id == video.video_id
    tracks = list(session.tracks)
    assert len(tracks) == 4

    destination = tmp_path / "publication-copy"
    _accept_wizard(monkeypatch, tracks, destination)
    window.projectActions.createPendulumExperiment()
    qtbot.waitUntil(lambda: not window.projectActions.busy, timeout=5000)

    # 源目录字节不变；新目录是 schema v2 且带迁移记录
    assert (source / "project.json").read_bytes() == source_manifest
    manifest = json.loads(
        (destination / "project.json").read_text(encoding="utf-8"))
    assert manifest["schema_version"] == 2
    assert manifest["migration"]["source_schema_version"] == 1

    # 会话整体切到新目录，experiment 存在，保存边界语义清空 undo
    experiment = window.currentPendulumExperiment()
    assert experiment is not None and experiment.video_id == video_id
    assert session.project_root == destination.resolve()
    assert session.can_undo is False
    assert window.pendulumPanel.isVisible()


def test_card_actions_route_to_pendulum_entries(
    qtbot: QtBot, synthetic_video_path: Path, tmp_path: Path, monkeypatch
) -> None:
    window = _opened_window(qtbot, synthetic_video_path)
    session = window.analysisSession
    tracks = _four_tracks(session, window.activeVideoId)
    _experiment_via_menu(
        qtbot, monkeypatch, window, tracks, tmp_path / "publication-copy")
    assert window._measurement_allowed

    window.trackingActions._onCardAction("setup_fixed_pivot")
    assert window.videoView.is_calibration_mode() == "pivot"
    window._exitAnnotationMode()

    window.trackingActions._onCardAction("setup_true_vertical")
    assert window.videoView.is_calibration_mode() == "vertical"
    window._exitAnnotationMode()


class TestPublicationFailureAndReopen:
    """P1.1-S6:迁移失败探针与 setup 事实的保存重开。"""

    def test_migration_failure_shows_three_question_message_and_keeps_session(
        self, qtbot, synthetic_video_path, tmp_path, monkeypatch
    ):
        window = _window()
        qtbot.addWidget(window)
        assert window.openVideo(synthetic_video_path, show_error=False)
        session = window.analysisSession
        session.save_as(tmp_path / "v1")
        tracks = [session.add_track(window.activeVideoId) for _ in range(4)]
        destination = tmp_path / "broken-copy"

        shown: list[str] = []

        def critical(parent, title, text, *args, **kwargs):
            shown.append(f"{title}\n{text}")

        monkeypatch.setattr(QMessageBox, "critical", staticmethod(critical))

        def failing_save_as_publication(self_repo, source, dest, project):
            raise RuntimeError("simulated disk failure; recovery staging: /tmp/x")

        monkeypatch.setattr(
            ProjectRepository, "save_as_publication", failing_save_as_publication
        )
        _accept_wizard(monkeypatch, tracks, destination)
        window.projectActions.createPendulumExperiment()
        qtbot.waitUntil(lambda: not window.projectActions.busy, timeout=5000)

        assert shown, "failure dialog must be shown"
        joined = "\n".join(shown)
        assert "not created" in joined          # 发生了什么
        assert "unchanged" in joined            # 数据是否还在
        assert "Next:" in joined                # 下一步
        # 失败后 v1 会话原样保留:根目录与 schema 都不变
        assert window.analysisSession is session
        assert session.project_root == (tmp_path / "v1").resolve()
        assert session.project.required_capabilities == ()
        assert not destination.exists()

    def test_setup_facts_survive_save_and_reopen(
        self, qtbot, synthetic_video_path, tmp_path, monkeypatch
    ):
        from ai_physics_tracker.domain.calibration import Calibration
        from ai_physics_tracker.domain.pendulum import PhysicalParameters
        from ai_physics_tracker.domain.types import utc_now

        window = _window()
        qtbot.addWidget(window)
        assert window.openVideo(synthetic_video_path, show_error=False)
        session = window.analysisSession
        session.save_as(tmp_path / "v1")
        tracks = [session.add_track(window.activeVideoId) for _ in range(4)]
        _accept_wizard(monkeypatch, tracks, tmp_path / "v2")
        window.projectActions.createPendulumExperiment()
        qtbot.waitUntil(lambda: not window.projectActions.busy, timeout=5000)

        experiment = window.analysisSession.pendulum_experiments()[0]
        session = window.analysisSession
        session._verified_videos.add(window.activeVideoId)
        session.add_calibration(
            Calibration(
                calibration_id=uuid4(),
                video_id=window.activeVideoId,
                name="ruler",
                scale_end_1_px=(0.0, 0.0),
                scale_end_2_px=(10.0, 0.0),
                known_length=0.1,
                unit="m",
                created_at=utc_now(),
            )
        )
        session.set_fixed_pivot(experiment.experiment_id, (12.0, 34.0))
        session.set_true_vertical(experiment.experiment_id, (12.0, 2.0), (13.0, 44.0))
        session.confirm_true_vertical(experiment.experiment_id)
        session.set_physical(
            experiment.experiment_id,
            PhysicalParameters(
                length_m=0.5, g_m_s2=9.81, length_source="ruler", g_source="standard"
            ),
        )
        window._presented_frame_index = 2
        session.set_release_frame(experiment.experiment_id, 2)
        before = session.pendulum_experiments()[0]
        session.save()

        # 重开:走 openProject 的文件对话框路径
        monkeypatch.setattr(
            QFileDialog,
            "getOpenFileName",
            staticmethod(
                lambda *a, **k: (str(tmp_path / "v2" / "project.json"), "")
            ),
        )
        window.projectActions.openProject()
        qtbot.waitUntil(lambda: not window.projectActions.busy, timeout=5000)

        reopened = window.analysisSession
        assert reopened is not session
        assert reopened.project_root == (tmp_path / "v2").resolve()
        restored = reopened.pendulum_experiments()[0]
        assert restored == before  # frozen 事实完整往返(含 revision/history)
        assert restored.geometry.fixed_pivot_px == (12.0, 34.0)
        assert restored.geometry.true_vertical.direction_confirmed
        assert restored.physical is not None and restored.physical.length_m == 0.5
        assert restored.release_frame_index == 2
        qtbot.waitUntil(
            lambda: "Setup complete" in window.pendulumPanel.statusLabel.text(),
            timeout=5000,
        )
