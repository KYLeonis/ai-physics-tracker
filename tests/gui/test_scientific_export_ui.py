"""native科学图来自同一payload，worker绘图/格式与选择历史的默认行为。"""

from concurrent.futures import ThreadPoolExecutor
from threading import Event

from PySide6.QtGui import QImage

from ai_physics_tracker.application.pendulum_analysis import prepare_analysis_job, run_analysis_job
from ai_physics_tracker.application.scientific_export import prepare_scientific_export, publish_scientific_export
from ai_physics_tracker.gui.scientific_export import ScientificExportDialog, render_scientific_figures, scientific_plot_data
from test_pendulum_analysis import analysis_session


def test_native_worker_figures_and_result_selection(qtbot, tmp_path, synthetic_video_path):
    session, experiment = analysis_session(tmp_path, synthetic_video_path)
    result = run_analysis_job(prepare_analysis_job(session, experiment.experiment_id, 11), Event())
    session.apply_pendulum_analysis_result(result)
    snapshot = prepare_scientific_export(session, result.record.result_id)
    data = scientific_plot_data(snapshot)
    assert data[0][4][0][1] == [r["time_release_relative_s"] for r in snapshot.payload["rows"]]
    assert data[1][4][0][2] == [r["omega_rad_s"] for r in snapshot.payload["rows"]]
    dialog = ScientificExportDialog((result.record,))
    qtbot.addWidget(dialog)
    assert not dialog.historical.isChecked() and dialog.figures.isChecked()
    assert dialog.resultList.currentItem().data(0x0100) == result.record.result_id
    with ThreadPoolExecutor(max_workers=1) as executor:
        folder = executor.submit(publish_scientific_export, snapshot, tmp_path / "figures", Event(), render_scientific_figures).result(timeout=20)
    for plot in data:
        image = QImage(str(folder / f"{plot[0]}.png"))
        assert image.width() == 1400 and image.height() == 900
        assert (folder / f"{plot[0]}.pdf").read_bytes().startswith(b"%PDF")
