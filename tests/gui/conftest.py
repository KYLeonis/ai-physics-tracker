"""GUI 测试的对话框与资源清理约定；专门的 dirty 测试自行覆盖回答。

Phase 5.7（stabilization R1 F1 修复）：本 fixture 显式依赖 ``qtbot``，
使其 setup 晚于、teardown 早于 qtbot 的窗口关闭——即在 pytestqt 关闭
窗口之前就把 ``close_allowed`` 置位，避免 dirty 会话在 teardown 中弹出
真实保存模态（offscreen 下无人应答 → 挂起；该隐患在“GUI 文件、应用层
文件、GUI 文件”的进程内排序下可稳定复现，见
docs/reviews/pre-phase6-stabilization-review.md F1）。
同时把 critical/warning/information 桩化为立即返回，防止断言失败路径
上的错误对话框把 offscreen 测试挂死；需要断言这些对话框的测试自行
monkeypatch 覆盖。
"""

import pytest
from PySide6.QtWidgets import QMessageBox


@pytest.fixture(scope="session", autouse=True)
def no_native_modals(qapp):
    """会话级封死原生模态（5.7 / stabilization R1 F1 根治）。

    qtbot 的窗口关闭发生在 hook wrapper 的 pre-yield（先于/交错于函数级
    fixture 终结），函数级 monkeypatch 的生效窗口无法覆盖全部关闭时序；
    在会话级直接替换 QMessageBox 的模态入口，使原生对话框在本测试进程中
    不可能出现。个别测试用 monkeypatch 覆盖返回值（如 Yes），undo 后恢复
    到本会话级桩，不会漏回原生实现。
    """
    QMessageBox.question = staticmethod(
        lambda *args, **kwargs: QMessageBox.StandardButton.Discard)
    QMessageBox.critical = staticmethod(
        lambda *args, **kwargs: QMessageBox.StandardButton.Ok)
    QMessageBox.warning = staticmethod(
        lambda *args, **kwargs: QMessageBox.StandardButton.Ok)
    QMessageBox.information = staticmethod(
        lambda *args, **kwargs: QMessageBox.StandardButton.Ok)
    yield


@pytest.fixture(autouse=True)
def discard_test_projects(monkeypatch, qtbot, qapp):
    monkeypatch.setattr(QMessageBox, "question",
                        lambda *args: QMessageBox.StandardButton.Discard)
    yield
    # 先解除窗口的保存确认（teardown 早于 qtbot 关闭窗口），再清理测试窗口；
    # 脏数据对话框的业务分支另有独立断言。
    for window in qapp.topLevelWidgets():
        if hasattr(window, "projectActions"):
            window.projectActions.close_allowed = True
    for window in qapp.topLevelWidgets():
        if hasattr(window, "projectActions"):
            window.close()
