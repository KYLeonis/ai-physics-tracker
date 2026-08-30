"""GUI 测试的对话框与资源清理约定；专门的 dirty 测试自行覆盖回答。"""

import pytest
from PySide6.QtWidgets import QMessageBox


@pytest.fixture(autouse=True)
def discard_test_projects(monkeypatch, qapp):
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Discard)
    yield
    # 测试退出只清理测试窗口；脏数据对话框的业务分支另有独立断言。
    for window in qapp.topLevelWidgets():
        if hasattr(window, "projectActions"):
            window.projectActions.close_allowed = True
            window.close()
