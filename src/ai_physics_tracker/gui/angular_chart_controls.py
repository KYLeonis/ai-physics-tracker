"""角运动参考配置控件：显式确认的支点 / 参考轨迹与零方向说明。

只做显示与交互（CODE_STANDARD §13）：编辑值是"草稿"，必须经 Apply
reference 显式确认后才成为 ``appliedReference()``；重算只接受已确认的
参考，绝不默认使用 (0,0) 或标定原点。单摆支点为像素参数，允许有限画外
坐标；两点参考的 B 轨迹下拉只列当前视频轨迹，"目标集含 B" 的拒绝在
ChartActions.recompute 处执行（控件不知道勾选集）。
"""

from uuid import UUID

from PySide6.QtCore import QSignalBlocker, Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ai_physics_tracker.domain.angular import AngularReference, PendulumReference, TwoPointReference
from ai_physics_tracker.domain.track import Track

# 支点坐标的录入范围：允许画外有限值（单摆可以摆出画面），只排除无穷。
_PIVOT_LIMIT = 1e9

_ZERO_DIRECTION_HELP = {
    "pendulum": (
        "Pendulum zero direction: the bob hanging straight down (world −y). "
        "Positive θ swings to the right. Align the calibration axes with the "
        "actual vertical of the experiment first."
    ),
    "two_point": (
        "Two-point zero direction: the +x axis of world coordinates. "
        "Positive θ is counterclockwise from A to B."
    ),
}


class AngularReferenceControls(QWidget):
    """单摆支点 / 两点参考 B 的录入、确认与状态披露。"""

    referenceEdited = Signal()   # 草稿变化：已确认参考失效，需重新 Apply
    referenceApplied = Signal()  # 显式确认完成

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.modeCombo = QComboBox()
        self.modeCombo.addItems(["Fixed pivot (pendulum)", "Reference track B (two-point)"])
        self.pivotX = QDoubleSpinBox()
        self.pivotX.setRange(-_PIVOT_LIMIT, _PIVOT_LIMIT)
        self.pivotX.setDecimals(12)
        self.pivotX.setValue(0.0)
        self.pivotY = QDoubleSpinBox()
        self.pivotY.setRange(-_PIVOT_LIMIT, _PIVOT_LIMIT)
        self.pivotY.setDecimals(12)
        self.pivotY.setValue(0.0)
        self.referenceTrack = QComboBox()
        self.applyButton = QPushButton("Apply reference")
        self.applyButton.setToolTip(
            "Confirm the current pivot / reference track. Recompute is refused "
            "until the reference is applied; values are never used silently."
        )
        self.stateLabel = QLabel("Reference not applied — set it and click Apply reference")
        self.stateLabel.setWordWrap(True)
        self._help = QLabel("?")
        self._help.setProperty("helpText", _ZERO_DIRECTION_HELP["pendulum"])
        self._help.setStyleSheet(
            "color: #888; border: 1px solid #bbb; border-radius: 7px;"
            "min-width: 14px; max-width: 14px; min-height: 14px; max-height: 14px;"
            "qproperty-alignment: AlignCenter;"
        )
        self._help.setMouseTracking(True)

        row = QHBoxLayout()
        row.addWidget(QLabel("Angle reference"))
        row.addWidget(self.modeCombo)
        row.addWidget(QLabel("pivot x"))
        row.addWidget(self.pivotX)
        row.addWidget(QLabel("y"))
        row.addWidget(self.pivotY)
        row.addWidget(QLabel("Track B"))
        row.addWidget(self.referenceTrack, 1)
        row.addWidget(self.applyButton)
        row.addWidget(self._help)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(row)
        layout.addWidget(self.stateLabel)

        self._applied: AngularReference | None = None
        self._tracks_by_id: dict[UUID, Track] = {}

        self.modeCombo.currentIndexChanged.connect(self._modeChanged)
        self.pivotX.valueChanged.connect(lambda _value: self._draftChanged())
        self.pivotY.valueChanged.connect(lambda _value: self._draftChanged())
        self.referenceTrack.currentIndexChanged.connect(lambda _index: self._draftChanged())
        self.applyButton.clicked.connect(self.applyReference)
        self._syncModeWidgets()

    # ------------------------------------------------------------------
    # 状态查询
    # ------------------------------------------------------------------

    @property
    def currentMode(self) -> str:
        return "pendulum" if self.modeCombo.currentIndex() == 0 else "two_point"

    def appliedReference(self) -> AngularReference | None:
        """已显式确认的参考；None = 未确认，重算必须被拒绝。"""

        return self._applied

    def appliedSummary(self) -> str:
        """已确认参考的图例 / 状态披露文案。"""

        reference = self._applied
        if isinstance(reference, PendulumReference):
            return f"pendulum pivot px ({reference.pivot_px[0]:g}, {reference.pivot_px[1]:g})"
        if isinstance(reference, TwoPointReference):
            track = self._tracks_by_id.get(reference.reference_track_id)
            label = track.name if track is not None else str(reference.reference_track_id)
            return f"two-point A→B (reference: {label})"
        return "not applied"

    # ------------------------------------------------------------------
    # 编辑与确认
    # ------------------------------------------------------------------

    def applyReference(self) -> None:
        """把当前草稿确认为重算参考；两点模式未选 B 时拒绝确认。"""

        # 缓存参考保留完整精度；未编辑字段时再次确认不能用显示舍入值改写配方。
        if self._applied is not None:
            self.referenceApplied.emit()
            return
        if self.currentMode == "pendulum":
            self._applied = PendulumReference(
                pivot_px=(self.pivotX.value(), self.pivotY.value())
            )
        else:
            track_id = self.referenceTrack.currentData()
            if track_id is None:
                self.stateLabel.setText(
                    "Select a reference track B before applying the two-point reference")
                return
            self._applied = TwoPointReference(reference_track_id=track_id)
        self._updateStateLabel()
        self.referenceApplied.emit()

    def _draftChanged(self) -> None:
        """草稿编辑使已确认参考失效；确认与结果从此互不混淆。"""

        self._applied = None
        self._updateStateLabel()
        self.referenceEdited.emit()

    def _modeChanged(self, _index: int) -> None:
        self._syncModeWidgets()
        self._draftChanged()

    def _syncModeWidgets(self) -> None:
        pendulum = self.currentMode == "pendulum"
        self.pivotX.setEnabled(pendulum)
        self.pivotY.setEnabled(pendulum)
        self.referenceTrack.setEnabled(not pendulum)
        self._help.setProperty("helpText", _ZERO_DIRECTION_HELP[self.currentMode])
        self._help.setToolTip(_ZERO_DIRECTION_HELP[self.currentMode])

    def _updateStateLabel(self) -> None:
        if self._applied is None:
            self.stateLabel.setText(
                "Reference not applied — set it and click Apply reference. "
                + _ZERO_DIRECTION_HELP[self.currentMode].split(". ")[0] + ".")
        else:
            self.stateLabel.setText(f"Reference ready for recompute: {self.appliedSummary()}")

    # ------------------------------------------------------------------
    # 轨迹下拉与恢复
    # ------------------------------------------------------------------

    def setTracks(self, tracks: tuple[Track, ...]) -> None:
        """重建当前视频的参考轨迹 B 下拉；已确认 B 消失时确认失效。"""

        self._tracks_by_id = {track.track_id: track for track in tracks}
        previous = self.referenceTrack.currentData()
        with QSignalBlocker(self.referenceTrack):
            self.referenceTrack.clear()
            self.referenceTrack.addItem("— select reference track B —", None)
            for track in tracks:
                self.referenceTrack.addItem(track.name, track.track_id)
            index = self.referenceTrack.findData(previous)
            if index >= 0:
                self.referenceTrack.setCurrentIndex(index)
        applied = self._applied
        if isinstance(applied, TwoPointReference) and applied.reference_track_id not in self._tracks_by_id:
            self._applied = None
            self._updateStateLabel()

    def seedApplied(self, reference: AngularReference) -> None:
        """把已计算结果携带的参考恢复为已确认状态（保存重开 / 缓存检查）。

        不发 referenceEdited / referenceApplied：恢复的是缓存事实，不是
        新的编辑，也不该取消任何任务。
        """

        self._applied = None
        if isinstance(reference, PendulumReference):
            with QSignalBlocker(self.modeCombo), QSignalBlocker(self.pivotX), \
                    QSignalBlocker(self.pivotY):
                self.modeCombo.setCurrentIndex(0)
                self.pivotX.setValue(reference.pivot_px[0])
                self.pivotY.setValue(reference.pivot_px[1])
            self._applied = reference
        elif isinstance(reference, TwoPointReference):
            with QSignalBlocker(self.modeCombo), QSignalBlocker(self.referenceTrack):
                self.modeCombo.setCurrentIndex(1)
                index = self.referenceTrack.findData(reference.reference_track_id)
                if index < 0:
                    return  # 参考轨迹不在当前视频：保持未确认，不猜测。
                self.referenceTrack.setCurrentIndex(index)
            self._applied = reference
        else:
            return
        self._syncModeWidgets()
        self._updateStateLabel()

    def clearApplied(self) -> None:
        """视频 / 工程切换后丢弃确认状态；坐标语义只属于原视频。"""

        self._applied = None
        self._updateStateLabel()
