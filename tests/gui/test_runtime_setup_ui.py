"""安装 UI 的后台终态/取消/解释器切换验证；不真实安装。"""

from concurrent.futures import Future, CancelledError
import sys

import pytest

from test_model_actions_ui import _experiment_window, long_video_path  # noqa: F401
from ai_physics_tracker.gui import launch_context
from ai_physics_tracker.application.runtime_setup import RuntimeProgress


@pytest.fixture
def setup(qtbot, tmp_path, long_video_path, monkeypatch):
    monkeypatch.setattr(launch_context, "app_data_dir", lambda: tmp_path / "appdata")
    window, _, _ = _experiment_window(qtbot, tmp_path, long_video_path)
    actions = window.runtimeSetup
    actions.open()
    yield actions
    actions._future = None
    actions.shutdown()


@pytest.mark.parametrize("error", [CancelledError(), RuntimeError("download failed")])
def test_failed_or_cancelled_setup_preserves_interpreter(setup, error):
    previous = setup.window.modelActions._runtime_python
    setup._begin(installing=True)
    setup._future = Future()
    setup._future.set_exception(error)
    setup._poll()
    assert setup.window.modelActions._runtime_python == previous
    assert not setup.busy
    assert "cancelled" in setup.dialog.phaseLabel.text() or "failed" in setup.dialog.phaseLabel.text()


def test_success_switches_both_ai_controllers(setup, monkeypatch):
    monkeypatch.setenv("AI_PHYSICS_RUNTIME_PYTHON", "old override")
    setup._begin(installing=True)
    setup._future = Future()
    setup._future.set_result(sys.executable)
    setup._poll()
    assert setup.window.modelActions._runtime_python == sys.executable
    assert setup.window.experimentInferenceActions._runtime_python == sys.executable
    assert setup.window.experimentInferenceActions._runtime_changed
    assert setup.dialog.progressBar.value() == 100


def test_byte_progress_elapsed_and_close_cancel(setup):
    setup._begin(installing=True)
    setup._future = Future()
    setup._progress.put(RuntimeProgress("Downloading", "Python", 50, 100))
    setup._poll()
    assert setup.dialog.progressBar.value() == 500
    setup._started_s -= 10
    setup._poll()
    assert "10 s" in setup.dialog.phaseLabel.text()
    setup.dialog.close()
    assert setup._cancel.is_set() and setup.busy


def test_missing_interpreter_opens_setup(setup):
    setup.dialog.hide()
    setup.window.modelActions._runtime_python = None
    assert not setup.window.modelActions._ensure_runtime()
    assert setup.dialog.isVisible()
