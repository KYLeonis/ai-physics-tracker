"""Phase 5.7 — 失败/结束结论的三问属性（§13）：发生了什么/数据还在/下一步。"""

import pytest

from ai_physics_tracker.application import user_messages as um


@pytest.mark.parametrize("message", [
    um.training_failure("boom", unsaved_changes=False),
    um.training_failure("CUDA out of memory", unsaved_changes=True),
    um.evaluation_unavailable(),
    um.inference_failure("codec error"),
    um.mining_failure("cancelled worker"),
    um.task_cancelled("train"),
    um.task_cancelled("infer"),
    um.interrupted_on_reopen(),
    um.no_difficult_frames(),
    um.no_difficult_frames(excluded_count=4),
    um.activation_failure("artifact missing"),
    um.charts_not_updated("inputs changed"),
    um.publication_migration_failed("destination exists"),
    um.publication_created("/tmp/demo"),
])
def test_every_failure_message_answers_three_questions(message) -> None:
    assert message.answers_three_questions()
    assert "unchanged" in " ".join(message.body) or "intact" in " ".join(message.body) \
        or "kept" in " ".join(message.body) or "not adopted" in " ".join(message.body)


def test_no_difficult_frames_keeps_honest_boundary() -> None:
    text = um.no_difficult_frames(excluded_count=3).full_text()
    assert "does not prove every position is accurate" in text
    assert "3 frame(s) were excluded" in text
    assert "spot-check" in text


def test_evaluation_failure_distinct_from_training_failure() -> None:
    assert "Model ready" in um.evaluation_unavailable().title
    assert "Learning failed" in um.training_failure("x", unsaved_changes=False).title
