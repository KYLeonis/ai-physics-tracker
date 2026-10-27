"""P6.5 preparation must isolate manual work and preserve frozen observations."""

import math
from pathlib import Path
import runpy

import pytest

from ai_physics_tracker.application.project_session import ProjectSession
from ai_physics_tracker.application.video import VideoStreamInfo
from ai_physics_tracker.application.video_timing import TimingReport
from ai_physics_tracker.infrastructure.project_repository import ProjectRepository


@pytest.fixture(scope="module")
def preparation():
    return runpy.run_path(str(Path(__file__).resolve().parents[1] / "scripts/prepare_p65_acceptance.py"))


@pytest.fixture
def reference(tmp_path):
    session = ProjectSession.start(ProjectRepository(), "Synthetic preparation test")
    video, _ = session.register_external_video(tmp_path / "synthetic.avi", VideoStreamInfo(300, 300, 30, 600, "avi", "cfr"))
    track = session.add_track(video.video_id)
    session.add_calibration(video.video_id, (100, 20), (100, 80), 1, origin_px=(100, 20))
    for frame in range(600):
        theta = .2 * math.cos(6 * frame / 30)
        session.mark_point(track.track_id, frame, pixel_x=100 + 60 * math.sin(theta), pixel_y=20 + 60 * math.cos(theta))
    return session.project


def test_new_manual_project_has_new_ids_but_no_inherited_labels_runs_or_results(preparation, reference, tmp_path):
    original = reference
    project = preparation["prepare_manual_project"](reference, TimingReport("cfr", "synthetic", 600, 30, 30), tmp_path / "manual")
    assert project.project_id != reference.project_id
    assert project.videos[0].video_id != reference.videos[0].video_id
    assert project.tracks[0].track_id != reference.tracks[0].track_id
    assert not project.observations and not project.derived and not project.tracking_runs
    assert project.ui_state["workflow"]["video_id"] == str(project.videos[0].video_id)
    assert project.ui_state["workflow"]["selected_track_id"] == str(project.tracks[0].track_id)
    assert project.calibrations[0].known_length == reference.calibrations[0].known_length
    assert ProjectRepository().load(tmp_path / "manual") == project
    assert reference == original and len(reference.observations) == 600


def test_reference_analysis_roundtrip_reports_separate_periods_without_touching_source(preparation, reference, tmp_path):
    protocol = {"calibration": {"pivot_px": [100, 20]}, "interval_frames_inclusive": [0, 214],
                "period_request": {"reference_level_rad": 0, "direction": "rising", "hysteresis": .002, "min_separation_s": .2}}
    summary = preparation["run_reference_analysis"](reference, TimingReport("cfr", "synthetic", 600, 30, 30),
                                                   tmp_path / "analysis", protocol, 2 * math.pi / 6)
    assert summary["fit_passed"] and summary["recurrence_passed"]
    assert summary["fit_period_s"] == pytest.approx(2 * math.pi / 6, abs=1e-5)
    assert summary["save_reload_equal"] and summary["fit_sample_count"] == 215
    assert len(summary["recurrence_summary"]["intervals_s"]) >= 5
    assert set(summary["charts"]) == {"theta_t", "omega_t", "alpha_t", "theta_omega"}
    assert summary["fit_summary"]["parameter_uncertainty"]["version"] == 2
    assert len(reference.observations) == 600 and not reference.derived


def test_prepare_refuses_existing_output_and_modified_reference(preparation, tmp_path):
    sentinel = tmp_path / "keep.json"
    sentinel.write_text("original", encoding="utf-8")
    with pytest.raises(FileExistsError):
        preparation["prepare"](tmp_path / "missing-reference", tmp_path)
    assert sentinel.read_text(encoding="utf-8") == "original"
    reference_root = tmp_path / "reference"
    reference_root.mkdir()
    protocol = reference_root / "benchmark-protocol.json"
    protocol.write_text("{}", encoding="utf-8")
    output = tmp_path / "new-output"
    with pytest.raises(ValueError, match="fingerprint mismatch"):
        preparation["prepare"](reference_root, output)
    assert not output.exists() and protocol.read_text(encoding="utf-8") == "{}"
