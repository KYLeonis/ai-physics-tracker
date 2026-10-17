"""GUI层：完整配方的只读回看，保留草稿并显式复用设置。"""

from contextlib import ExitStack
from typing import TYPE_CHECKING
from uuid import UUID
from PySide6.QtCore import QSignalBlocker, Qt
from PySide6.QtWidgets import QTableWidgetItem

from ai_physics_tracker.domain.analysis import QUANTITIES
from ai_physics_tracker.domain.derived import DerivedData

if TYPE_CHECKING:
    from ai_physics_tracker.gui.signal_analysis_panel import SignalAnalysisPanel


class SignalHistory:
    """历史字段与当前草稿分开；切换查看不触发计算或写入工程。"""

    _combos = ('trackChoice', 'quantityChoice', 'sourceChoice', 'direction')
    _numbers = ('startFrame', 'endFrame', 'budget', 'level', 'hysteresis', 'separation')
    _texts = ('resultName', 'resultFormula')

    def __init__(self, panel: 'SignalAnalysisPanel') -> None:
        self.panel = panel
        self.draft = None
        self.record = None
        self.attempt_id = None
        self.source_text = ''

    @property
    def active(self) -> bool:
        return self.draft is not None

    def capture(self) -> dict:
        p = self.panel
        return {
            'combos': {name: getattr(p, name).currentIndex() for name in self._combos},
            'tracks': [(p.trackChoice.itemText(i), p.trackChoice.itemData(i)) for i in range(p.trackChoice.count())],
            'numbers': {name: (getattr(p, name).minimum(), getattr(p, name).maximum(), getattr(p, name).value()) for name in self._numbers},
            'texts': {name: getattr(p, name).text() for name in self._texts},
            'formula': p.editor.text(), 'method': p.methods.currentIndex(),
            'rows': [[(p.parameterTable.item(row, col).text(), p.parameterTable.item(row, col).checkState()) for col in range(5)]
                     for row in range(p.parameterTable.rowCount())],
            'protected': p.initialProtected, 'estimate': p.estimateLabel.text(),
            'optional': p.optionalGroup.isChecked(), 'bounds': p.parameterOptions.isChecked(),
            'noise': p.noiseOptions.isChecked(),
        }

    def _load(self, state: dict) -> None:
        p = self.panel
        p._loading = True
        try:
            with ExitStack() as stack:
                for name in self._combos + self._numbers + self._texts + ('methods',):
                    stack.enter_context(QSignalBlocker(getattr(p, name)))
                p.trackChoice.clear()
                for text, identity in state['tracks']:
                    p.trackChoice.addItem(text, identity)
                for name, index in state['combos'].items():
                    getattr(p, name).setCurrentIndex(index)
                for name, (low, high, value) in state['numbers'].items():
                    getattr(p, name).setRange(low, high)
                    getattr(p, name).setValue(value)
                for name, value in state['texts'].items():
                    getattr(p, name).setText(value)
                p.methods.setCurrentIndex(state['method'])
                p.editor.setText(state['formula'])
                with QSignalBlocker(p.parameterTable):
                    p.parameterTable.setRowCount(len(state['rows']))
                    for row, cells in enumerate(state['rows']):
                        for col, (text, checked) in enumerate(cells):
                            item = QTableWidgetItem(text)
                            if col in (0, 4):
                                item.setFlags(Qt.ItemFlag.ItemIsEnabled | (Qt.ItemFlag.ItemIsUserCheckable if col == 4 else Qt.ItemFlag.ItemIsSelectable))
                            if col == 4:
                                item.setCheckState(checked)
                            p.parameterTable.setItem(row, col, item)
                p.optionalGroup.setChecked(state['optional'])
                p.parameterOptions.setChecked(state['bounds'])
                p.noiseOptions.setChecked(state['noise'])
                p.editor.setQuantityLabel(p.quantityChoice.currentText() + '(t)')
                p.initialProtected = state['protected']
                p.estimateLabel.setText(state['estimate'])
        finally:
            p._loading = False
        p._methodVisibility()
        p.plotTabs.setTabVisible(1, state['method'] == 0)

    def view(self, metadata: dict, *, record: DerivedData | None = None, attempt_id: str | None = None) -> None:
        p = self.panel
        if not isinstance(metadata, dict):
            raise ValueError('Missing recorded analysis metadata')
        selection, spec, summary = (metadata.get(key) for key in ('selection', 'spec', 'summary'))
        if not all(isinstance(value, dict) for value in (selection, spec, summary)):
            raise ValueError('Missing recorded selection, setup or summary')
        UUID(str(selection.get('track_id')))
        if metadata.get('quantity') not in QUANTITIES:
            raise ValueError('Unsupported recorded quantity')
        interval = selection.get('start_frame'), selection.get('end_frame')
        if any(type(value) is not int for value in interval) or not 0 <= interval[0] <= interval[1]:
            raise ValueError('Unreadable recorded frame interval')
        if not isinstance(spec.get('parameters', []), list) or not all(isinstance(row, dict) for row in spec.get('parameters', [])):
            raise ValueError('Unreadable recorded parameters')
        formulas = summary.get('result_formulas', [])
        if not isinstance(formulas, list) or not all(isinstance(row, dict) for row in formulas):
            raise ValueError('Unreadable recorded result formulas')
        if not self.active:
            self.draft = self.capture()
        self.record, self.attempt_id = record, attempt_id
        if attempt_id is None:
            with QSignalBlocker(p.attemptChoice):
                p.attemptChoice.setCurrentIndex(-1)
            p.attemptDetails.setPlainText('Viewing a saved result above. Select an attempt to inspect a different recorded Fit.')
        state = self.capture()
        identity = selection.get('track_id')
        index = next((i for i, (_, value) in enumerate(state['tracks']) if value == identity), -1)
        if index < 0:
            state['tracks'].append((f'Recorded track {identity}', identity))
            index = len(state['tracks'])-1
        quantity = metadata.get('quantity', 'x')
        state['combos'].update(trackChoice=index, quantityChoice=p.quantityChoice.findText(quantity), sourceChoice=int(bool(selection.get('smoothed'))))
        for name, value in (('startFrame', selection.get('start_frame')), ('endFrame', selection.get('end_frame'))):
            if type(value) is int:
                low, high, _ = state['numbers'][name]
                state['numbers'][name] = (min(low, value), max(high, value), value)
        fitting = 'expression' in spec or attempt_id is not None
        state['method'] = 0 if fitting else 1
        if fitting:
            state['formula'] = spec.get('expression', '')
            state['rows'] = [[(str(parameter.get('name', '')), Qt.CheckState.Unchecked),
                              (str(parameter.get('initial', '')), Qt.CheckState.Unchecked),
                              ('' if parameter.get('lower') is None else str(parameter['lower']), Qt.CheckState.Unchecked),
                              ('' if parameter.get('upper') is None else str(parameter['upper']), Qt.CheckState.Unchecked),
                              ('', Qt.CheckState.Checked if parameter.get('fixed') else Qt.CheckState.Unchecked)]
                             for parameter in spec.get('parameters', [])]
            low, high, _ = state['numbers']['budget']
            budget = spec.get('max_evaluations', 1000)
            state['numbers']['budget'] = (min(low, budget), max(high, budget), budget)
            state['texts'] = {'resultName': formulas[0].get('name', '') if formulas else '',
                              'resultFormula': formulas[0].get('formula', '') if formulas else ''}
        else:
            for name, key in (('level', 'level'), ('hysteresis', 'hysteresis'), ('separation', 'min_separation_s')):
                low, high, _ = state['numbers'][name]
                value = spec.get(key, 0)
                state['numbers'][name] = (min(low, value), max(high, value), value)
            state['combos']['direction'] = 0 if spec.get('direction') == 'rising' else 1
        state['optional'] = True
        state['noise'] = True
        state['bounds'] = any(row[2][0] or row[3][0] or row[4][1] == Qt.CheckState.Checked for row in state['rows'])
        state['protected'] = True
        state['estimate'] = 'Recorded initial values and constraints — read-only; fitted values are shown above the chart.' if fitting else 'Recorded crossing reference and settings — read-only.'
        self._load(state)
        p.previousButton.setEnabled(p.savedRecord(disk=True) is not None)
        p.latestButton.setEnabled(p.savedRecord(disk=False) is not None)
        p.parameterTable.horizontalHeaderItem(1).setText('Recorded initial')
        self.source_text = (f"Viewing history · {p.trackChoice.currentText()} · {quantity} · "
                            f"{'smoothed' if selection.get('smoothed') else 'measured'} · frames {selection.get('start_frame')}–{selection.get('end_frame')}")
        p.contextLabel.setText(self.source_text)
        p.restoreButton.setEnabled(True)
        self.lock()
        p.historyChanged.emit()

    def lock(self) -> None:
        p = self.panel
        for name in self._combos + self._numbers + self._texts + ('editor', 'parameterTable', 'levelSlider', 'centerReferenceButton', 'showSourceButton', 'previewButton', 'fitButton', 'recurrenceButton', 'estimateButton', 'undoButton', 'redoButton', 'preparationHost'):
            getattr(p, name).setEnabled(not self.active)
        p.methods.tabBar().setEnabled(not self.active)
        p.referenceLine.setMovable(not self.active)
        p.returnDraftButton.setVisible(self.active)
        p.refreshSourceChoice()

    def leave(self, *, adopt: bool = False, discard: bool = False) -> None:
        if not self.active:
            return
        p = self.panel
        if adopt:
            session = getattr(p, '_session', None)
            timeline = next((item for item in session.project.timelines if item.video_id == p._video_id), None) if session else None
            identity = p.trackChoice.currentData()
            if (timeline is None or p.quantityChoice.currentIndex() < 0
                    or not any(str(track.track_id) == identity and track.video_id == p._video_id for track in session.tracks)
                    or not timeline.working_zone[0] <= p.startFrame.value() <= p.endFrame.value() <= timeline.working_zone[1]):
                p.showFeedback('Recorded track / interval is outside this video or working zone. Return to draft and prepare the original context first.')
                return
        state = self.draft
        self.draft = self.record = self.attempt_id = None
        if not adopt:
            self._load(state)
        p.parameterTable.horizontalHeaderItem(1).setText('Initial')
        p._viewingDiskSaved = False
        self.lock()
        if not discard:
            p.historyChanged.emit()
        if not discard:
            if adopt:
                p.initialProtected = True
                p.estimateLabel.setText('Recorded setup adopted as an editable draft; not recalculated.')
            p.draftLabel.setText('Current editable draft — recorded setup not recalculated' if adopt else 'Current editable draft restored')
            p.signalPlot.clear()
            p.residualPlot.clear()
            p._eventLines = []
            p._eventSamplesMatch = False
            p._allowCachedEvents = False
            p._previewRange = p._valueRange = None
            p.modelLabel.clear()
            p.meaningLabel.clear()
            p.resultLabel.setText('Current draft — click Fit to calculate.' if p.methods.currentIndex() == 0 else 'Current draft — review the reference, then Measure crossing intervals.')
            p.summary.setPlainText('Current draft — no recorded result is being displayed.')
            p._referenceChanged(p.level.value())
            p.settingsChanged.emit()
            if p.methods.currentIndex() == 1:
                p.sourcePreviewRequested.emit()
            p.showFeedback(('Recorded setup adopted' if adopt else 'Your previous draft restored') +
                           ('. Preview is being prepared; click Fit explicitly.' if p.methods.currentIndex() == 0 else '. Review reference, then click Measure crossing intervals.'))
