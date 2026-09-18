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
def discard_test_projects(monkeypatch, qtbot):
    monkeypatch.setattr(QMessageBox, "question",
                        lambda *args: QMessageBox.StandardButton.Discard)
    original_add_widget = qtbot.addWidget

    def add_widget(widget, *, before_close_func=None):
        def prepare_close(registered_widget):
            if hasattr(registered_widget, "projectActions"):
                registered_widget.projectActions.close_allowed = True
            if before_close_func is not None:
                before_close_func(registered_widget)

        original_add_widget(widget, before_close_func=prepare_close)

    # 把保存确认解除动作挂到 pytest-qt 自己的唯一 close 调用上。这样既不会
    # 因 fixture teardown 顺序过晚而弹出原生模态，也不会由两套 teardown
    # 重复关闭带 decoder/executor 的 MainWindow（曾在 macOS/Windows CI
    # 分别触发 SIGSEGV / 0xc0000374）。
    monkeypatch.setattr(qtbot, "addWidget", add_widget)
    monkeypatch.setattr(qtbot, "add_widget", add_widget)
    yield
