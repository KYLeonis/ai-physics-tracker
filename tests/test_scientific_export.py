"""完整精度/冻结身份、stale策略、损坏与取消原子输出、搬移重开。"""

from concurrent.futures import CancelledError
import csv
import json
from threading import Event

import pytest

from ai_physics_tracker.application.pendulum_analysis import prepare_analysis_job, run_analysis_job
from ai_physics_tracker.application.pendulum_fit import prepare_fit_job, run_fit_job, load_fit_result
from ai_physics_tracker.application.project_session import ProjectSession, ProjectSessionError
from ai_physics_tracker.application.scientific_export import prepare_scientific_export, publish_scientific_export, save_portable_copy
from ai_physics_tracker.infrastructure.project_repository import ProjectRepository
from test_pendulum_fit_job import fit_session
from test_pendulum_analysis import analysis_session


def test_fit_export_full_precision_four_roles_and_historical_frozen_inputs(tmp_path, synthetic_video_path):
    session, experiment, options = fit_session(tmp_path, synthetic_video_path)
    result = run_fit_job(prepare_fit_job(session, experiment.experiment_id, options), Event())
    session.apply_pendulum_fit_result(result)
    before = session.project
    snapshot = prepare_scientific_export(session.detached(), result.record.result_id)
    folder = publish_scientific_export(snapshot, tmp_path / "科学输出", Event())
    with (folder / "observations.csv").open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    payload = json.loads((folder / "result.json").read_text(encoding="utf-8"))
    provenance = json.loads((folder / "provenance.json").read_text(encoding="utf-8"))
    assert payload == json.loads(json.dumps(result.payload))
    assert float(rows[-1]["theta_rad"]) == result.payload["rows"][-1]["theta_rad"]
    assert float(rows[-1]["m0_residual_rad"]) == result.payload["rows"][-1]["m0_residual_rad"]
    assert rows[0]["m0_theta_rad"] == ""
    assert set(f"{role}_pixel_x" for role in ("tip", "body_top", "body_bottom", "pivot")) <= rows[0].keys()
    assert provenance["units"]["theta_rad"] == "rad"
    assert provenance["units"]["m0_residual_rad"] == "rad"
    assert provenance["measurement"]["active_run_id"] == str(experiment.active_infer_run_id)
    assert provenance["current_at_export"] and session.project == before
    session.mark_point(experiment.roles.tip, 10, 9., 95.)
    with pytest.raises(ProjectSessionError, match="stale"):
        prepare_scientific_export(session, result.record.result_id)
    history = prepare_scientific_export(session, result.record.result_id, allow_historical=True)
    assert not history.current and history.reason
    assert history.payload["measurement"] == snapshot.payload["measurement"]
    with pytest.raises(FileExistsError):
        publish_scientific_export(history, folder, Event())
    assert (folder / "result.json").read_text(encoding="utf-8") == json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def test_kinematics_export_cancellation_corruption_and_failed_render_leave_no_target(tmp_path, synthetic_video_path):
    session, experiment = analysis_session(tmp_path, synthetic_video_path)
    result = run_analysis_job(prepare_analysis_job(session, experiment.experiment_id, 11), Event())
    session.apply_pendulum_analysis_result(result)
    snapshot = prepare_scientific_export(session, result.record.result_id)
    cancelled = Event(); cancelled.set()
    with pytest.raises(CancelledError):
        publish_scientific_export(snapshot, tmp_path / "cancelled", cancelled)
    def broken_renderer(*_args):
        raise OSError("disk full simulation")
    with pytest.raises(OSError, match="disk full"):
        publish_scientific_export(snapshot, tmp_path / "failed", Event(), broken_renderer)
    assert not (tmp_path / "cancelled").exists() and not (tmp_path / "failed").exists()
    assert not list(tmp_path.glob(".scientific-export-*"))
    path = session.project_root / result.record.payload.path
    path.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="hash"):
        prepare_scientific_export(session, result.record.result_id, allow_historical=True)


def test_portable_copy_reopens_after_source_and_external_video_move(tmp_path, synthetic_video_path):
    session, experiment, options = fit_session(tmp_path, synthetic_video_path)
    result = run_fit_job(prepare_fit_job(session, experiment.experiment_id, options), Event())
    session.apply_pendulum_fit_result(result)
    before = session.project
    output = save_portable_copy(session.detached(), tmp_path / "portable", Event())
    assert session.project == before
    moved = tmp_path / "搬移工程"
    output.rename(moved)
    source = session.project_root
    source.rename(tmp_path / "old-source")
    synthetic_video_path.rename(synthetic_video_path.with_suffix(".hidden"))
    reopened = ProjectSession.load(ProjectRepository(), moved)
    video = reopened.project.videos[0]
    assert reopened.video_path(video).is_relative_to(moved)
    payload, valid, reason = load_fit_result(reopened, reopened.project.scientific_results[-1])
    assert valid, reason
    assert payload["input_digest"] == result.payload["input_digest"]
    assert payload["rows"] == json.loads(json.dumps(result.payload["rows"]))
    assert not list(tmp_path.glob(".portable-project-*"))
