"""P6.1 launch_context（frozen/dev 解析）与 AI 入口 runtime 守卫的测试。

frozen 形态用 ``sys.frozen``/``sys._MEIPASS`` monkeypatch 模拟；worker 指针、
env 覆盖与占位提示逐分支验证。dev 行为必须与 P6.1 之前完全一致
（runtime python = 当前解释器、FFprobe 走 PATH、无文件日志）。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# 复用联合训练测试的 12 帧视频 fixture 与完整 experiment window 装配
from test_model_actions_ui import _experiment_window, long_video_path  # noqa: F401

from ai_physics_tracker.gui import launch_context
from ai_physics_tracker.gui.launch_context import (
    APP_NAME,
    app_data_dir,
    bundled_ffprobe,
    configure_file_logging,
    resource_root,
    runtime_python,
)

pytestmark = pytest.mark.usefixtures("qapp")


@pytest.fixture
def dev_environment(monkeypatch):
    """强制 dev 形态：清除 frozen 痕迹与两个 env 覆盖。"""

    monkeypatch.delattr(sys, "frozen", raising=False)
    monkeypatch.delattr(sys, "_MEIPASS", raising=False)
    monkeypatch.delenv("AI_PHYSICS_RUNTIME_PYTHON", raising=False)
    monkeypatch.delenv("AI_PHYSICS_FFPROBE", raising=False)


@pytest.fixture
def frozen_environment(monkeypatch, tmp_path):
    """强制 frozen 形态：_MEIPASS 指向临时目录，其下 resources/ 为资源根。"""

    resources = tmp_path / "contents" / "resources"
    resources.mkdir(parents=True)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(resources.parent), raising=False)
    monkeypatch.delenv("AI_PHYSICS_RUNTIME_PYTHON", raising=False)
    return resources


class TestDevBehaviour:
    def test_runtime_python_is_current_interpreter(self, dev_environment):
        assert runtime_python() == sys.executable

    def test_resource_root_is_none(self, dev_environment):
        assert resource_root() is None

    def test_bundled_ffprobe_is_none(self, dev_environment):
        assert bundled_ffprobe() is None

    def test_file_logging_is_noop(self, dev_environment):
        import logging

        before = list(logging.getLogger().handlers)
        assert configure_file_logging() is None
        assert logging.getLogger().handlers == before


class TestFrozenResolution:
    def test_no_pointer_and_no_override_returns_none(self, frozen_environment, monkeypatch):
        monkeypatch.setattr(
            launch_context, "app_data_dir", lambda: Path("/nonexistent-apt")
        )
        assert runtime_python() is None

    def test_pointer_with_existing_interpreter_wins(self, frozen_environment, monkeypatch, tmp_path):
        data_dir = tmp_path / "appdata"
        (data_dir / "runtimes").mkdir(parents=True)
        (data_dir / "runtimes" / "active.txt").write_text(
            f"{sys.executable}\n", encoding="utf-8"
        )
        monkeypatch.setattr(launch_context, "app_data_dir", lambda: data_dir)
        assert runtime_python() == sys.executable

    def test_pointer_referencing_missing_interpreter_returns_none(
        self, frozen_environment, monkeypatch, tmp_path
    ):
        data_dir = tmp_path / "appdata"
        (data_dir / "runtimes").mkdir(parents=True)
        (data_dir / "runtimes" / "active.txt").write_text(
            "/definitely/not/a/python\n", encoding="utf-8"
        )
        monkeypatch.setattr(launch_context, "app_data_dir", lambda: data_dir)
        assert runtime_python() is None

    def test_env_override_beats_pointer(self, frozen_environment, monkeypatch, tmp_path):
        data_dir = tmp_path / "appdata"
        (data_dir / "runtimes").mkdir(parents=True)
        (data_dir / "runtimes" / "active.txt").write_text(
            "/definitely/not/a/python\n", encoding="utf-8"
        )
        monkeypatch.setattr(launch_context, "app_data_dir", lambda: data_dir)
        monkeypatch.setenv("AI_PHYSICS_RUNTIME_PYTHON", sys.executable)
        assert runtime_python() == sys.executable

    def test_invalid_env_override_falls_back_to_pointer(
        self, frozen_environment, monkeypatch, tmp_path
    ):
        data_dir = tmp_path / "appdata"
        (data_dir / "runtimes").mkdir(parents=True)
        (data_dir / "runtimes" / "active.txt").write_text(
            f"{sys.executable}\n", encoding="utf-8"
        )
        monkeypatch.setattr(launch_context, "app_data_dir", lambda: data_dir)
        monkeypatch.setenv("AI_PHYSICS_RUNTIME_PYTHON", "/no/such/file")
        assert runtime_python() == sys.executable

    def test_bundled_ffprobe_resolves_platform_binary(self, frozen_environment):
        name = "ffprobe.exe" if sys.platform == "win32" else "ffprobe"
        target = frozen_environment / "ffprobe" / name
        target.parent.mkdir(parents=True)
        target.write_bytes(b"stub")
        assert bundled_ffprobe() == target

    def test_bundled_ffprobe_missing_binary_returns_none(self, frozen_environment):
        assert bundled_ffprobe() is None

    def test_resource_root_points_at_resources(self, frozen_environment):
        assert resource_root() == frozen_environment


class TestAppDataAndLogging:
    def test_app_data_dir_last_component_is_app_name(self):
        from PySide6.QtCore import QCoreApplication

        previous = QCoreApplication.applicationName()
        QCoreApplication.setApplicationName(APP_NAME)
        try:
            assert app_data_dir().name == APP_NAME
        finally:
            QCoreApplication.setApplicationName(previous)

    def test_frozen_file_logging_writes_into_log_dir(
        self, frozen_environment, monkeypatch, tmp_path
    ):
        data_dir = tmp_path / "appdata"
        monkeypatch.setattr(launch_context, "app_data_dir", lambda: data_dir)
        path = configure_file_logging()
        assert path is not None and path.parent == data_dir / "logs"
        import logging

        logging.getLogger("apt.p6.test").info("hello frozen log")
        logging.getLogger().handlers.remove(
            next(h for h in logging.getLogger().handlers if getattr(h, "baseFilename", None) == str(path))
        )
        assert "hello frozen log" in path.read_text(encoding="utf-8")


class TestRuntimeGuards:
    @pytest.fixture
    def message_recorder(self, monkeypatch):
        calls: list[object] = []
        monkeypatch.setattr(
            launch_context, "show_ai_runtime_missing", lambda window: calls.append(window)
        )
        return calls

    def test_model_actions_guard_rejects_missing_runtime(
        self, qtbot, tmp_path, long_video_path, message_recorder
    ):
        from test_model_actions_ui import _experiment_window
        from ai_physics_tracker.gui.model_actions import ModelActions

        window, _session, _experiment = _experiment_window(
            qtbot, tmp_path, long_video_path
        )
        window.modelActions.deleteLater()
        actions = ModelActions(window, runtime_python=None, runner_factory=lambda: pytest.fail(
            "runner must not be constructed without an AI runtime"
        ))
        actions._runtime_python = None   # frozen 无 managed runtime 形态
        assert actions._ensure_runtime() is False
        assert message_recorder and message_recorder[0] is window
        # runJointTraining 在 prepare 之前被守卫拦截:不登记 pending run、不转 busy
        runs_before = [
            r for r in window.analysisSession.project.tracking_runs
            if r.task_type == "train"
        ]
        actions.runJointTraining()
        assert not actions.busy
        runs_after = [
            r for r in window.analysisSession.project.tracking_runs
            if r.task_type == "train"
        ]
        assert runs_after == runs_before

    def test_model_actions_guard_accepts_existing_interpreter(
        self, qtbot, tmp_path, long_video_path, message_recorder
    ):
        from test_model_actions_ui import _experiment_window
        from ai_physics_tracker.gui.model_actions import ModelActions

        window, *_ = _experiment_window(qtbot, tmp_path, long_video_path)
        window.modelActions.deleteLater()
        actions = ModelActions(window, runtime_python=None)
        assert actions._runtime_python == sys.executable   # dev 解析
        assert actions._ensure_runtime() is True
        assert message_recorder == []

    def test_inference_actions_guard_rejects_missing_runtime(
        self, qtbot, message_recorder
    ):
        from ai_physics_tracker.application.video_session import VideoSession
        from ai_physics_tracker.gui.experiment_inference_actions import (
            ExperimentInferenceActions,
        )
        from ai_physics_tracker.gui.main_window import MainWindow
        from ai_physics_tracker.infrastructure.ffprobe_timing import FFprobeTimingProbe
        from ai_physics_tracker.infrastructure.opencv_video_reader import (
            OpenCVVideoReader,
        )
        from ai_physics_tracker.infrastructure.project_repository import (
            ProjectRepository,
        )

        window = MainWindow(
            lambda: VideoSession(OpenCVVideoReader()),
            ProjectRepository(),
            FFprobeTimingProbe(),
        )
        qtbot.addWidget(window)
        window.experimentInferenceActions.deleteLater()
        actions = ExperimentInferenceActions(
            window, runtime_python=None, runner_factory=lambda: pytest.fail(
                "runner must not be constructed without an AI runtime"
            )
        )
        assert actions._runtime_python == sys.executable   # dev 解析仍可用
        actions._runtime_python = None                    # frozen 无 runtime 形态
        assert actions._ensure_runtime() is False
        assert message_recorder and message_recorder[0] is window

    def test_missing_runtime_message_mentions_installation(self, qtbot, monkeypatch):
        from PySide6.QtWidgets import QMessageBox

        recorded: list[tuple[object, str, str]] = []
        monkeypatch.setattr(
            QMessageBox,
            "information",
            staticmethod(lambda parent, title, text, *a, **k: recorded.append((parent, title, text)) or 0),
        )
        launch_context.show_ai_runtime_missing(object())
        assert recorded
        _parent, title, text = recorded[0]
        assert "AI environment is not installed" in title
        assert "AI runtime" in text
