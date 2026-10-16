"""首次学习 20 帧门槛及推荐框的选帧默认值、算法定制与取消。"""

from dataclasses import replace
from uuid import uuid4

import pytest
from PySide6.QtWidgets import QInputDialog

from ai_physics_tracker.application.annotation_batch import AnnotationBatch
from ai_physics_tracker.domain.tracking_run import create_tracking_run, mark_run_completed
from tests.gui.test_tracking_actions import _FakeRunner, _opened_window

pytestmark = pytest.mark.parametrize("synthetic_video_path", [20], indirect=True)


def test_first_learning_requires_twenty_distinct_labels_in_all_gui_entries(
    qtbot, synthetic_video_path, tmp_path, monkeypatch,
):
    window, session, track = _opened_window(
        qtbot, synthetic_video_path, tmp_path, _FakeRunner(), manual_count=19)
    actions = window.trackingActions
    panel = actions.panel
    batch = window.batchAnnotationActions
    batch.batch = AnnotationBatch(track, (18,), index=1, corrected=1)
    batch.refresh()

    assert "19/20" in window.workflowHeader.nextStepLabel.text()
    assert panel._primary_action_id == "pick_frames"
    assert not panel.trainButton.isEnabled() and not batch.learnButton.isEnabled()
    assert "20 distinct frames" in batch.learnButton.toolTip()
    monkeypatch.setattr(actions, "_confirm_fixed_check_set",
                        lambda *_args: pytest.fail("too few labels must not open the check dialog"))
    actions._onCardAction("start_learning")
    actions.train()
    assert not actions.pending and not session.tracking_runs()
    assert "19/20" in panel.stageLabel.text()

    session.mark_point(track, 18, 30, 30)
    batch.refresh()
    assert len(session.manual_points(track)) == 19
    assert not panel.trainButton.isEnabled()
    session.mark_point(track, 19, 30, 30)
    batch.refresh()
    assert panel.trainButton.isEnabled() and batch.learnButton.isEnabled()
    assert panel._primary_action_id == "start_learning"


def test_existing_training_allows_refinement_only_for_its_own_track(
    qtbot, synthetic_video_path, tmp_path,
):
    window, session, track = _opened_window(
        qtbot, synthetic_video_path, tmp_path, _FakeRunner())
    video = session.tracks[0].video_id
    other = session.add_track(video)
    run = create_tracking_run(video, other.track_id, "train", engine_version="mock")
    session.record_tracking_run(mark_run_completed(run))
    actions = window.trackingActions
    assert actions._trainingLabelReason(session, track) is not None
    session.record_tracking_run(mark_run_completed(replace(run, run_id=uuid4(), track_id=track)))
    assert actions._trainingLabelReason(session, track) is None
    actions._context_key = None
    actions.refresh()
    assert actions.panel.trainButton.isEnabled()


@pytest.mark.parametrize("accepted", [False, True])
def test_header_custom_algorithm_uses_same_selection_path_and_cancel_is_inert(
    qtbot, synthetic_video_path, tmp_path, monkeypatch, accepted,
):
    window, session, _ = _opened_window(
        qtbot, synthetic_video_path, tmp_path, _FakeRunner(), manual_count=0)
    panel = window.trackingActions.panel
    calls = []
    panel.suggestFramesRequested.disconnect()
    panel.suggestFramesRequested.connect(lambda n, algorithm: calls.append((n, algorithm)))
    assert panel.nFramesSpinBox.value() == 20
    assert panel.algorithmComboBox.currentData() == "kmeans"
    window.workflowHeader.nextStepButtons[0].click()
    assert calls == [(20, "kmeans")]
    calls.clear()

    def choose(parent, title, description, choices, current, editable):
        assert "visually diverse" in description and "evenly" in description
        assert choices == ["K-means", "Uniform"] and current == 0 and not editable
        return "Uniform", accepted

    monkeypatch.setattr(QInputDialog, "getItem", choose)
    # 选帧属于Acquire；Analysis的推荐已改为用途入口。
    window.setWorkspace("acquire")
    custom = next(button for button in window.workflowHeader.nextStepButtons
                  if button.property("actionId") == "customize_frames")
    assert custom.isVisible() and custom.isEnabled()
    custom.click()
    assert window.currentWorkspace == "acquire"
    assert calls == ([(20, "uniform")] if accepted else [])
    assert panel.algorithmComboBox.currentData() == ("uniform" if accepted else "kmeans")
    assert not session.project.observations and not window.trackingActions.pending
    calls.clear()
    window.workflowHeader.nextStepButtons[0].click()
    assert calls == [(20, "uniform" if accepted else "kmeans")]
    calls.clear()
    panel.nFramesSpinBox.setValue(7)
    panel.algorithmComboBox.setCurrentIndex(1)
    window.adoptEmptyProject()
    assert panel.nFramesSpinBox.value() == 20
    assert panel.algorithmComboBox.currentData() == "kmeans"
    assert not calls
