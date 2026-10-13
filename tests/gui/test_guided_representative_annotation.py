"""推荐标注必须消费算法返回的代表帧队列，不能退回逐帧扫描。"""

import pytest

from ai_physics_tracker.application.tracking_types import FrameSelectionResult
from ai_physics_tracker.application.annotation_batch import AnnotationBatch
from ai_physics_tracker.infrastructure.mock_engine_adapter import MockEngineAdapter
from tests.gui.test_tracking_actions import _FakeHandle, _FakeRunner, _opened_window

pytestmark = pytest.mark.parametrize("synthetic_video_path", [148], indirect=True)

_REPRESENTATIVE_FRAMES = (1, 6, 26, 28, 39, 42, 44, 46, 47, 49,
                          59, 60, 62, 63, 64, 105, 110, 114, 129, 143)


def _publish_selection(window, track_id, frames, algorithm="kmeans"):
    actions = window.frameSelectionActions
    actions._running_track_id = track_id
    actions._finish_success(FrameSelectionResult(
        request_algorithm=algorithm, suggested_frames=frames,
        actual_n=len(frames), excluded_count=0, params_snapshot={"algorithm": algorithm}))


@pytest.mark.parametrize("from_header", [False, True])
def test_representative_results_start_a_batch_instead_of_first_twenty_frames(
    qtbot, synthetic_video_path, tmp_path, from_header,
):
    window, session, track = _opened_window(
        qtbot, synthetic_video_path, tmp_path, _FakeRunner(), manual_count=0)
    _publish_selection(window, track, _REPRESENTATIVE_FRAMES)
    panel = window.trackingActions.panel
    assert not session.project.observations
    assert panel._primary_action_id == "label_frame"
    button = window.workflowHeader.nextStepButtons[0] if from_header else panel.cardPrimaryButton
    button.click()
    batch = window.batchAnnotationActions
    assert batch.batch.frames == _REPRESENTATIVE_FRAMES

    for frame_index in _REPRESENTATIVE_FRAMES:
        qtbot.waitUntil(lambda: window.presented_frame_index == frame_index
                        and not window._has_pending_request)
        assert batch.handleClick(20, 30)

    assert batch.batch.finished
    assert tuple(p.frame_index for p in session.manual_points(track)) == _REPRESENTATIVE_FRAMES
    assert panel._primary_action_id == "start_learning"
    assert not window.trackingActions.pending
    qtbot.waitUntil(lambda: not window.projectActions.busy)


def test_guided_batch_keeps_manual_labels_and_never_falls_back_to_sequential_frames(
    qtbot, synthetic_video_path, tmp_path,
):
    window, session, track = _opened_window(
        qtbot, synthetic_video_path, tmp_path, _FakeRunner())
    original = session.manual_points(track)
    _publish_selection(window, track, (1, 6, 26, 143))
    window.trackingActions._onCardAction("label_frame")
    batch = window.batchAnnotationActions
    assert batch.batch.frames == (6, 26, 143)
    for frame_index in (6, 26, 143):
        qtbot.waitUntil(lambda: window.presented_frame_index == frame_index
                        and not window._has_pending_request)
        batch.handleClick(20, 30)
    assert all(p in session.manual_points(track) for p in original)
    assert {p.frame_index for p in session.manual_points(track)} == {0, 1, 2, 6, 26, 143}
    before = session.project.observations
    window.trackingActions._onCardAction("label_frame")
    assert session.project.observations == before
    assert batch.batch.finished
    assert window.presented_frame_index == 143
    qtbot.waitUntil(lambda: not window.projectActions.busy)


@pytest.mark.parametrize("finished", [False, True])
def test_new_selection_replaces_old_representative_batch_even_after_twenty_labels(
    qtbot, synthetic_video_path, tmp_path, finished,
):
    window, session, track = _opened_window(
        qtbot, synthetic_video_path, tmp_path, _FakeRunner(), manual_count=20)
    batch = window.batchAnnotationActions
    batch.batch = (AnnotationBatch(track, (19,), index=1, corrected=1) if finished else
                   AnnotationBatch(track, (19,), paused=True))
    batch.refresh()
    assert window.trackingActions.panel._primary_action_id == ("start_learning" if finished else "batch_resume")
    selection = window.frameSelectionActions
    handle = _FakeHandle()
    selection.adapter = MockEngineAdapter()
    selection.runner = _FakeRunner(handle)
    window.trackingActions._onCardAction("pick_frames")
    assert batch.batch is None
    qtbot.waitUntil(lambda: selection._handle is handle)
    handle._alive = False
    _publish_selection(window, track, (26, 105, 143))
    qtbot.waitUntil(lambda: window.trackingActions.panel._primary_action_id == "label_frame")
    window.trackingActions._onCardAction("label_frame")
    assert batch.batch.frames == (26, 105, 143)
    assert len(session.manual_points(track)) == 20
    batch.pause()
