"""Phase 5.2 困难帧基准：审计表生成与指标计算（Qt-free 纯函数）。

开发集与冻结审计集共用同一套流程（docs/benchmarks/README.md）：
候选并集 → 固定种子打乱并隐藏来源 → 人工标注 → 重算策略并计分。
策略帧不写入审计表；score 阶段从相同输入/参数/seed 确定性重算并核对，
保证盲评不泄漏、结果可复现（spec R2 / Phase 5 AC-10）。
"""

import csv
import random
from dataclasses import dataclass
from math import isnan
from pathlib import Path

from ai_physics_tracker.infrastructure.dlc_predictions import RawPrediction

_TRUTHY = frozenset({"1", "true", "yes"})
_FALSY = frozenset({"0", "false", "no"})


def lowest_confidence_baseline(
    predictions: tuple[RawPrediction, ...],
    top_n: int,
    *,
    zone_start: int,
    zone_end: int,
    manual_frames: frozenset[int] = frozenset(),
) -> tuple[int, ...]:
    """基线策略：working zone 内置信度最低的 top_n 帧（缺测最先，非 manual）。

    与困难帧策略同输入、无时间去重——基线的意义正在于没有去重与多样性。
    """
    rows = [
        row for row in predictions
        if zone_start <= row.frame_index <= zone_end and row.frame_index not in manual_frames
    ]
    ordered = sorted(
        rows,
        key=lambda row: (
            0.0 if isnan(row.confidence) else row.confidence,  # 缺测视为最低
            0 if isnan(row.confidence) else 1,
            row.frame_index,
        ),
    )
    return tuple(row.frame_index for row in ordered[:top_n])


@dataclass(frozen=True)
class AuditTable:
    """盲评审计表：打乱后的并集帧号与待人工填写字段。"""

    rows: tuple[dict[str, str], ...]
    policy_frames: tuple[int, ...]
    baseline_frames: tuple[int, ...]


def build_audit_table(
    policy_frames: tuple[int, ...],
    baseline_frames: tuple[int, ...],
    *,
    shuffle_seed: int,
) -> AuditTable:
    """生成打乱、隐藏来源的审计表；两侧策略帧原样保留在结构体中供核对。"""
    union = sorted(set(policy_frames) | set(baseline_frames))
    rows = [
        {
            "frame_index": str(frame),
            "needs_review": "",
            "needs_correction": "",
            "note": "",
        }
        for frame in union
    ]
    random.Random(shuffle_seed).shuffle(rows)
    return AuditTable(tuple(rows), tuple(policy_frames), tuple(baseline_frames))


def write_audit_csv(table: AuditTable, path: Path) -> None:
    """写审计表 CSV（UTF-8；人工填写 needs_review/needs_correction/note）。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(table.rows[0].keys()))
        writer.writeheader()
        writer.writerows(table.rows)


def read_audit_labels(path: Path) -> dict[int, tuple[bool, bool]]:
    """读取已标注审计表 → {frame_index: (needs_review, needs_correction)}。

    严格拒绝：未知帧号、未标注字段、非法布尔值、needs_correction 为真但
    needs_review 为假（违反 needs_correction => needs_review 约定）。
    """
    with path.open("r", newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    if not rows:
        raise ValueError(f"audit table has no rows: {path}")
    labels: dict[int, tuple[bool, bool]] = {}
    for position, row in enumerate(rows, start=2):
        try:
            frame = int(row["frame_index"])
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError(f"audit row {position}: invalid frame_index") from error
        needs_review = _parse_flag(row.get("needs_review"), "needs_review", position)
        needs_correction = _parse_flag(row.get("needs_correction"), "needs_correction", position)
        if needs_correction and not needs_review:
            raise ValueError(
                f"audit row {position} (frame {frame}): needs_correction requires needs_review"
            )
        if frame in labels:
            raise ValueError(f"audit row {position}: duplicate frame_index {frame}")
        labels[frame] = (needs_review, needs_correction)
    return labels


@dataclass(frozen=True)
class StrategyScore:
    """单策略在审计集上的指标（Phase 5 AC-10）。"""

    actual_n: int
    needs_review_count: int
    needs_correction_count: int

    @property
    def precision_at_n(self) -> float:
        """Precision@N = needs_review / actual_n；actual_n 为 0 时记 0。"""
        return self.needs_review_count / self.actual_n if self.actual_n else 0.0

    @property
    def review_yield(self) -> float:
        """review yield = needs_correction / actual_n。"""
        return self.needs_correction_count / self.actual_n if self.actual_n else 0.0


def score_strategy(frames: tuple[int, ...], labels: dict[int, tuple[bool, bool]]) -> StrategyScore:
    """对一组策略帧计分；帧不在审计表中说明审计表与策略不一致，拒绝。"""
    missing = [frame for frame in frames if frame not in labels]
    if missing:
        raise ValueError(f"strategy frames missing from audit labels: {missing[:5]}")
    reviewed = sum(1 for frame in frames if labels[frame][0])
    corrected = sum(1 for frame in frames if labels[frame][1])
    return StrategyScore(len(frames), reviewed, corrected)


def _parse_flag(raw: str | None, label: str, position: int) -> bool:
    value = (raw or "").strip().lower()
    if value in _TRUTHY:
        return True
    if value in _FALSY:
        return False
    raise ValueError(
        f"audit row {position}: {label} must be one of 1/0/true/false/yes/no, got {raw!r}"
    )
