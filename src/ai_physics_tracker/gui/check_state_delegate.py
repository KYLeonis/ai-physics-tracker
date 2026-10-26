"""GUI层：复用列表整行 / 表格整格的复选交互。"""

from PySide6.QtCore import QAbstractItemModel, QEvent, QModelIndex, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QStyledItemDelegate, QStyleOptionViewItem


class CheckStateDelegate(QStyledItemDelegate):
    """整格左键切换；键盘与只读状态沿用Qt。"""

    def editorEvent(self, event: QEvent, model: QAbstractItemModel,
                    option: QStyleOptionViewItem, index: QModelIndex) -> bool:
        if (isinstance(event, QMouseEvent)
                and event.type() == QEvent.Type.MouseButtonRelease
                and event.button() == Qt.MouseButton.LeftButton
                and option.rect.contains(event.position().toPoint())
                and index.flags() & Qt.ItemFlag.ItemIsEnabled
                and index.flags() & Qt.ItemFlag.ItemIsUserCheckable):
            checked = index.data(Qt.ItemDataRole.CheckStateRole) == Qt.CheckState.Checked.value
            state = Qt.CheckState.Unchecked if checked else Qt.CheckState.Checked
            return model.setData(index, state.value, Qt.ItemDataRole.CheckStateRole)
        return super().editorEvent(event, model, option, index)
