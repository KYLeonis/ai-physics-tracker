"""Phase 5.7 — 面向用户的失败/结束结论文案（设计 §13，Qt-free）。

每条结论必须回答三问：发生了什么？已有数据是否还在？下一步怎么做？
本模块只做纯文案构造，不执行任何动作；GUI 把结论放进状态/卡片，
原始错误与技术详情仍进入日志与“结果与历史”。
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class UXMessage:
    """一条用户可见结论：标题 + 正文行 + 下一步。"""

    title: str
    body: tuple[str, ...] = ()
    next_hint: str = ""

    def full_text(self) -> str:
        parts = [self.title, *self.body]
        if self.next_hint:
            parts.append(f"Next: {self.next_hint}")
        return "\n".join(line for line in parts if line)

    def answers_three_questions(self) -> bool:
        """三问自检：发生了什么（title）、数据是否还在（body）、下一步（hint）。"""
        return bool(self.title and self.body and self.next_hint)


def training_failure(error: str, *, unsaved_changes: bool) -> UXMessage:
    """训练失败：模型未产出。"""
    body = ["Learning did not finish. Manual points and any adopted trajectory "
            "are unchanged."]
    if unsaved_changes:
        body.append("Your edits are in memory but not yet saved to disk.")
    return UXMessage(
        title=f"Learning failed: {error}",
        body=tuple(body),
        next_hint="Retry learning (after an out-of-memory error the plan halves "
                  "the batch size), or open Results & history for the log.",
    )


def evaluation_unavailable() -> UXMessage:
    """训练完成、评价失败：模型可用，比较依据未生成（与训练失败分开）。"""
    return UXMessage(
        title="Model ready; comparison evidence unavailable",
        body=("Learning finished and the model can track the video. The "
              "fixed-check evaluation for this run could not be produced, so "
              "improvement cannot be judged.",
              "Your labels and adopted trajectory are unchanged.",),
        next_hint="Generate the trajectory; comparison stays unavailable until "
                  "a later run evaluates successfully.",
    )


def inference_failure(error: str) -> UXMessage:
    return UXMessage(
        title=f"Trajectory generation failed: {error}",
        body=("The whole-video trajectory was not produced. Learning results "
              "and manual positions are unchanged; the current trajectory stays "
              "as it was.",),
        next_hint="Retry generating the trajectory; retraining is not required "
                  "for an inference problem.",
    )


def mining_failure(error: str) -> UXMessage:
    return UXMessage(
        title=f"Checking did not finish: {error}",
        body=("This check run was not completed — it is not a verdict that "
              "everything is fine. Earlier corrections and review records are "
              "kept.",),
        next_hint="Retry the check or return to the current trajectory.",
    )


def task_cancelled(task_type: str) -> UXMessage:
    """取消：用户动作；已完成任务与旧结果保留。"""
    what = {
        "train": "learning", "infer": "trajectory generation",
        "mining": "checking", "frame_selection": "frame selection",
    }.get(task_type, task_type)
    return UXMessage(
        title=f"{what.capitalize()} cancelled",
        body=("The task was stopped before finishing. No new result was "
              "adopted; manual points and completed results are intact.",),
        next_hint="Restart the step when you want to continue.",
    )


def interrupted_on_reopen() -> UXMessage:
    return UXMessage(
        title="Previous task was interrupted",
        body=("The project was closed while a learning or tracking task was "
              "still running; its unfinished run is marked failed. Saved data "
              "is intact.",),
        next_hint="Start the step again from the task card.",
    )


def no_difficult_frames(*, excluded_count: int = 0) -> UXMessage:
    """筛查成功但无触发池（不证明整段准确；可自由抽查）。"""
    body = [
        "The screen found no frames that clearly need checking for this model "
        "in the working zone.",
    ]
    if excluded_count:
        body.append(f"{excluded_count} frame(s) were excluded (already "
                    "reviewed or manually marked).")
    body.append("This does not prove every position is accurate — you can "
                "still spot-check any frame. Existing corrections and labels "
                "are unchanged.")
    return UXMessage(
        title="No new frames to check",
        body=tuple(body),
        next_hint="Review the trajectory summary and decide whether to adopt "
                  "it or keep the current one.",
    )


def activation_failure(error: str) -> UXMessage:
    return UXMessage(
        title=f"Trajectory not adopted: {error}",
        body=("No new trajectory was adopted; the current trajectory and all "
              "manual positions are unchanged.",),
        next_hint="Retry after checking the result files, or choose another "
                  "available result in Results & history.",
    )


def charts_not_updated(reason: str) -> UXMessage:
    return UXMessage(
        title=f"Charts were not updated: {reason}",
        body=("The charts keep the last valid results for their inputs; no "
              "half-updated mixture is shown. Chart data and the trajectory "
              "are unchanged.",),
        next_hint="Update the charts again, or fix the stated prerequisite "
                  "first.",
    )
