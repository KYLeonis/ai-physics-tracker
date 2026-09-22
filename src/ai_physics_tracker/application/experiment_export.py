"""experiment 四 bodypart 导出计划（P1.2-S5，Qt-free 纯函数）。

从 join 事实构建 DLC 导出行：complete 帧 ∩ 排除 fixed-check 帧 = 训练行，
fixed-check 帧 = 检查行（共同 split，契约 §3）。任何 3/4、AI 补点、
non-finite 帧都不会进入计划（join 已过滤；duplicate 在 join 即拒绝）。
"""

from dataclasses import dataclass

from ai_physics_tracker.application.annotation_join import (
    fixed_check_status,
    join_complete_frames,
)
from ai_physics_tracker.domain.pendulum import PendulumExperiment
from ai_physics_tracker.domain.project import Project


@dataclass(frozen=True)
class ExperimentExportRow:
    """一行 DLC 标注：帧号 + 规范 role 顺序的四组坐标。"""

    frame_index: int
    coordinates: tuple[tuple[float, float], ...]  # 长度恒 4（tip/body_top/body_bottom/pivot）


@dataclass(frozen=True)
class ExperimentExportPlan:
    """导出计划：训练行与固定检查行（行序 = 帧号升序 = DLC 索引序）。"""

    train_rows: tuple[ExperimentExportRow, ...]
    test_rows: tuple[ExperimentExportRow, ...]

    @property
    def total_rows(self) -> int:
        return len(self.train_rows) + len(self.test_rows)

    def split_indices(self) -> tuple[tuple[int, ...], tuple[int, ...]]:
        """DLC train/test 行索引（行序 = 全部行按帧号升序，与导出一致）。"""

        ordered = sorted(
            (*self.train_rows, *self.test_rows),
            key=lambda row: row.frame_index,
        )
        test_frames = {row.frame_index for row in self.test_rows}
        train_indices: list[int] = []
        test_indices: list[int] = []
        for index, row in enumerate(ordered):
            (test_indices if row.frame_index in test_frames else train_indices).append(
                index
            )
        return tuple(train_indices), tuple(test_indices)


def build_experiment_export_plan(
    project: Project, experiment: PendulumExperiment
) -> ExperimentExportPlan:
    """构建导出计划；fixed-check 未冻结或已失效时整体拒绝（fail closed）。"""

    valid, reason = fixed_check_status(project, experiment)
    if not valid:
        raise ValueError(
            f"cannot build the export plan: fixed check is not valid ({reason}); "
            "freeze a valid fixed-check set first"
        )
    fixed_check = experiment.fixed_check
    assert fixed_check is not None  # status 为 valid 时必然存在
    result = join_complete_frames(project, experiment)
    labels_by_frame = {label.frame_index: label for label in result.complete}
    check_set = set(fixed_check.frames)

    train_rows: list[ExperimentExportRow] = []
    test_rows: list[ExperimentExportRow] = []
    for frame in sorted(labels_by_frame):
        label = labels_by_frame[frame]
        row = ExperimentExportRow(
            frame_index=frame, coordinates=label.coordinates
        )
        if frame in check_set:
            test_rows.append(row)
        else:
            train_rows.append(row)
    return ExperimentExportPlan(
        train_rows=tuple(train_rows), test_rows=tuple(test_rows)
    )
