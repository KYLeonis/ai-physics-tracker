"""GUI 测试的对话框与资源清理约定；专门的 dirty 测试自行覆盖回答。

诊断分支专用：teardown 打印窗口关闭与线程时间线（写 fd 2 绕过 pytest 捕获）。
"""

import faulthandler
import os
import sys

import pytest
from PySide6.QtWidgets import QMessageBox


def _diag(message: str) -> None:
    os.write(2, f"\nDIAG {message}\n".encode())


@pytest.fixture(autouse=True)
def discard_test_projects(monkeypatch, qapp):
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Discard)
    yield
    # 测试退出只清理测试窗口；脏数据对话框的业务分支另有独立断言。
    _diag(f"teardown begin windows={len(qapp.topLevelWidgets())}")
    for window in qapp.topLevelWidgets():
        if hasattr(window, "projectActions"):
            window.projectActions.close_allowed = True
            accepted = window.close()
            _diag(f"closed {type(window).__name__} accepted={accepted} visible={window.isVisible()}")
    _diag("teardown end; threads:")
    faulthandler.dump_traceback(file=sys.__stderr__, all_threads=True)
