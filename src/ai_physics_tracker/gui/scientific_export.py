"""科学输出选择与native Qt独立图绘制；复用ProjectActions后台/取消生命周期。"""

from concurrent.futures import CancelledError
from math import isfinite
from pathlib import Path
from threading import Event

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPageLayout, QPageSize, QPdfWriter, QPen
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QDialogButtonBox, QFileDialog, QLabel, QListWidget,
    QListWidgetItem, QMessageBox, QVBoxLayout,
)

from ai_physics_tracker.application.pendulum_analysis import ANALYSIS_KIND
from ai_physics_tracker.application.pendulum_fit import FIT_KIND
from ai_physics_tracker.application.scientific_export import (
    ScientificExport, prepare_scientific_export, publish_scientific_export, save_portable_copy,
)


class ScientificExportDialog(QDialog):
    """按时间/执行/新鲜度选择确切结果，默认不允许历史导出。"""

    def __init__(self, records, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Export scientific results")
        self.setMinimumWidth(540)
        layout = QVBoxLayout(self)
        hint = QLabel("Select one saved result. CSV/JSON retain full precision and the frozen adopted measurement. Candidate previews are excluded.")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self.resultList = QListWidget()
        for record in sorted(records, key=lambda r: r.created_at, reverse=True):
            kind = "Kinematics" if record.kind == ANALYSIS_KIND else "ODE fit"
            item = QListWidgetItem(f"{record.created_at.astimezone():%Y-%m-%d %H:%M:%S} · {kind} · {record.execution_status} · {record.freshness}")
            item.setData(Qt.ItemDataRole.UserRole, record.result_id)
            self.resultList.addItem(item)
        layout.addWidget(self.resultList)
        self.historical = QCheckBox("Allow historical result — export its frozen inputs, with a stale warning")
        layout.addWidget(self.historical)
        self.figures = QCheckBox("Include standalone PNG and vector PDF figures")
        self.figures.setChecked(True)
        layout.addWidget(self.figures)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        self.resultList.currentRowChanged.connect(lambda _row: self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(self.resultList.currentItem() is not None))
        if self.resultList.count():
            self.resultList.setCurrentRow(0)
        else:
            self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(False)
            hint.setText("No saved scientific result yet. In Analysis, compute kinematics or run an ODE fit, then return here to export.")


def scientific_plot_data(snapshot: ScientificExport) -> list[tuple]:
    """曲线只取选定payload，保留None断点；测试与绘图共用数据入口。"""
    rows = snapshot.payload["rows"]
    time = [r["time_release_relative_s"] for r in rows]
    theta = [r.get("theta_rad") for r in rows]
    plots = [("angle", "Angle", "Time from release (s)", "Angle (rad)", [("Observed θ", time, theta)])]
    if snapshot.record.kind == ANALYSIS_KIND:
        omega = [r.get("omega_rad_s") for r in rows]
        plots += [
            ("angular-velocity", "Angular velocity", "Time from release (s)", "Angular velocity (rad/s)", [("ω", time, omega)]),
            ("phase-portrait", "Phase portrait", "Angle (rad)", "Angular velocity (rad/s)", [("θ, ω", theta, omega)]),
            ("reference-energy", "Reference energy (proxy, not joules)", "Time from release (s)", "Reference energy (s^-2)",
             [("E reference", time, [r.get("energy_s_inv2") for r in rows])]),
        ]
    else:
        for model in snapshot.payload["fits"]:
            plots[0][4].append((model, time, [r.get(f"{model.lower()}_theta_rad") for r in rows]))
        plots.append(("residual", "Raw residual: prediction − observation", "Time from release (s)", "Residual (rad)",
                      [(model, time, [r.get(f"{model.lower()}_residual_rad") for r in rows]) for model in snapshot.payload["fits"]]))
    return plots


def _finite(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and isfinite(value)


def _draw_plot(painter: QPainter, snapshot: ScientificExport, plot: tuple, cancel: Event) -> None:
    """同一绘图函数输出PNG/PDF；完整画布1400×900，与屏幕状态无关。"""
    _, title, xlabel, ylabel, curves = plot
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.fillRect(QRectF(0, 0, 1400, 900), Qt.GlobalColor.white)
    painter.setFont(QFont("Sans Serif", 16))
    painter.setPen(Qt.GlobalColor.black)
    painter.drawText(QRectF(130, 15, 1200, 45), title)
    painter.setFont(QFont("Sans Serif", 11))
    status = "CURRENT" if snapshot.current else "HISTORICAL / STALE"
    painter.drawText(QRectF(130, 65, 1200, 35), f"{status} · {snapshot.record.execution_status} · {snapshot.record.created_at.isoformat()}")
    painter.drawText(QRectF(130, 100, 1200, 35), f"Source result {snapshot.record.result_id} · {snapshot.record.core_version}")
    bounds = QRectF(145, 180, 1170, 570)
    painter.drawRect(bounds)
    values = [(x, y) for _, xs, ys in curves for x, y in zip(xs, ys) if _finite(x) and _finite(y)]
    if not values:
        painter.drawText(bounds, Qt.AlignmentFlag.AlignCenter, "Unavailable: no finite values in this saved result")
        return
    xmin, xmax = min(x for x, _ in values), max(x for x, _ in values)
    ymin, ymax = min(y for _, y in values), max(y for _, y in values)
    dx, dy = xmax-xmin, ymax-ymin
    dx = dx if dx > 0 else max(1., abs(xmin)*.1)
    dy = dy if dy > 0 else max(.1, abs(ymin)*.1)
    xmin -= dx*.03; xmax += dx*.03
    ymin -= dy*.06; ymax += dy*.06
    for i in range(6):
        x = bounds.left() + bounds.width()*i/5
        y = bounds.bottom() - bounds.height()*i/5
        painter.setPen(QPen(QColor("#dddddd"), 1))
        painter.drawLine(QPointF(x, bounds.top()), QPointF(x, bounds.bottom()))
        painter.drawLine(QPointF(bounds.left(), y), QPointF(bounds.right(), y))
        painter.setPen(Qt.GlobalColor.black)
        painter.drawText(QRectF(x-50, bounds.bottom()+10, 100, 30), Qt.AlignmentFlag.AlignCenter, f"{xmin+(xmax-xmin)*i/5:.5g}")
        painter.drawText(QRectF(8, y-15, 125, 30), Qt.AlignmentFlag.AlignRight, f"{ymin+(ymax-ymin)*i/5:.5g}")
    painter.drawText(QRectF(145, 820, 1170, 35), Qt.AlignmentFlag.AlignCenter, xlabel)
    painter.save(); painter.translate(34, 740); painter.rotate(-90)
    painter.drawText(QRectF(0, 0, 570, 35), Qt.AlignmentFlag.AlignCenter, ylabel); painter.restore()
    colors = ("#2456a6", "#d55e00", "#00845b")
    for index, (label, xs, ys) in enumerate(curves):
        if cancel.is_set():
            raise CancelledError()
        painter.setPen(QPen(QColor(colors[index % len(colors)]), 2.5))
        painter.drawText(QRectF(160+index*330, 140, 320, 30), label)
        previous = None
        for x, y in zip(xs, ys):
            if not (_finite(x) and _finite(y)):
                previous = None
                continue
            xx = bounds.left() + (x-xmin)/(xmax-xmin)*bounds.width()
            yy = bounds.bottom() - (y-ymin)/(ymax-ymin)*bounds.height()
            if previous is not None:
                painter.drawLine(QPointF(*previous), QPointF(xx, yy))
            else:
                painter.drawEllipse(QRectF(xx-2, yy-2, 4, 4))
            previous = (xx, yy)


def render_scientific_figures(snapshot: ScientificExport, folder: Path, cancel: Event) -> None:
    """QImage/QPdfWriter为worker可用的非widget绘图设备，不捕获UI。"""
    for plot in scientific_plot_data(snapshot):
        if cancel.is_set():
            raise CancelledError()
        image = QImage(1400, 900, QImage.Format.Format_ARGB32)
        painter = QPainter(image)
        try:
            _draw_plot(painter, snapshot, plot, cancel)
        finally:
            painter.end()
        if not image.save(str(folder / f"{plot[0]}.png")):
            raise OSError("Could not write scientific PNG")
        pdf = QPdfWriter(str(folder / f"{plot[0]}.pdf"))
        pdf.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
        pdf.setPageOrientation(QPageLayout.Orientation.Landscape)
        pdf.setResolution(144)
        painter = QPainter(pdf)
        try:
            scale = min(pdf.width()/1400, pdf.height()/900)
            painter.scale(scale, scale)
            _draw_plot(painter, snapshot, plot, cancel)
        finally:
            painter.end()
        if not (folder / f"{plot[0]}.pdf").is_file():
            raise OSError("Could not write scientific PDF")


def _idle(window) -> bool:
    controllers = (getattr(window, "modelActions", None), getattr(window, "experimentInferenceActions", None),
                   getattr(window, "frameSelectionActions", None), getattr(window, "reviewActions", None))
    if (window.projectActions.busy or window.trackingActions.pending
            or any(c is not None and c.busy for c in controllers)
            or window.pendulumFitActions.pending or window.pendulumAnalysisActions._future is not None):
        QMessageBox.information(window, "Finish the current task", "Finish or cancel the running task before exporting or making a portable copy.")
        return False
    return True


def export_scientific_results(window) -> None:
    """File动作，选择身份后用已有后台事务执行，阻止同时修改输入。"""
    session = window.analysisSession
    experiment = window.currentPendulumExperiment()
    if session is None or experiment is None or not _idle(window):
        return
    records = [r for r in session.project.scientific_results if r.experiment_id == experiment.experiment_id
               and r.kind in (ANALYSIS_KIND, FIT_KIND)]
    dialog = ScientificExportDialog(records, window)
    if dialog.exec() != QDialog.DialogCode.Accepted:
        return
    result_id = dialog.resultList.currentItem().data(Qt.ItemDataRole.UserRole)
    historical, figures = dialog.historical.isChecked(), dialog.figures.isChecked()
    selected, _ = QFileDialog.getSaveFileName(window, "Choose a NEW scientific export directory", "scientific-results")
    if not selected:
        return
    candidate = session.detached()
    def work(cancel):
        snapshot = prepare_scientific_export(candidate, result_id, allow_historical=historical)
        return publish_scientific_export(snapshot, Path(selected), cancel, render_scientific_figures if figures else None)
    window.projectActions._run(work, lambda path: window.statusBar().showMessage(f"Scientific results exported: {path}"),
                              cancellable=True, progress_label="Validating saved results / exporting scientific data…",
                              completion_after_cancel=True)


def export_portable_project(window) -> None:
    session = window.analysisSession
    if session is None or not _idle(window):
        return
    selected, _ = QFileDialog.getSaveFileName(window, "Choose a NEW portable project directory", "portable-experiment")
    if not selected:
        return
    candidate = session.detached()
    window.projectActions._run(lambda cancel: save_portable_copy(candidate, Path(selected), cancel),
        lambda path: window.statusBar().showMessage(f"Portable copy saved (original remains open): {path}"),
        cancellable=True, progress_label="Copying project assets and video — cancel takes effect at copy boundaries…",
        completion_after_cancel=True)
