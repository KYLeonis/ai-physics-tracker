"""native科学图来自同一payload，worker绘图/格式与选择历史的默认行为。"""

from concurrent.futures import ThreadPoolExecutor
from threading import Event
from types import SimpleNamespace

from PySide6.QtGui import QImage
import pytest

from ai_physics_tracker.application.pendulum_analysis import prepare_analysis_job, run_analysis_job
from ai_physics_tracker.application.pendulum_fit import FIT_KIND
from ai_physics_tracker.application.scientific_export import ScientificExport, prepare_scientific_export, publish_scientific_export
from ai_physics_tracker.domain.pendulum_ode import M0, M1
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


@pytest.mark.parametrize("models", [(M0,), (M0, M1)])
def test_fit_figures_include_saved_predictions_and_residuals_with_gaps(models):
    rows = [
        {"time_release_relative_s": 0., "theta_rad": .3, "m0_theta_rad": .28,
         "m0_residual_rad": -.02, "m1_theta_rad": .31, "m1_residual_rad": .01},
        {"time_release_relative_s": .1, "theta_rad": None, "m0_theta_rad": None,
         "m0_residual_rad": None, "m1_theta_rad": None, "m1_residual_rad": None},
        {"time_release_relative_s": .2, "theta_rad": .1, "m0_theta_rad": .13,
         "m0_residual_rad": .03, "m1_theta_rad": .105, "m1_residual_rad": .005},
    ]
    snapshot = ScientificExport(SimpleNamespace(kind=FIT_KIND),
        {"rows": rows, "fits": dict.fromkeys(models)}, True, None, "Synthetic fit")

    plots = {name: curves for name, _, _, _, curves in scientific_plot_data(snapshot)}

    time = [0., .1, .2]
    assert plots["angle"][0] == ("Observed θ", time, [.3, None, .1])
    expected = [(M0, [.28, None, .13], [-.02, None, .03]),
                (M1, [.31, None, .105], [.01, None, .005])][:len(models)]
    assert plots["angle"][1:] == [(model, time, prediction) for model, prediction, _ in expected]
    assert plots["residual"] == [(model, time, residual) for model, _, residual in expected]
