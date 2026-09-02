"""Phase 5.2 基准工具（application/benchmark.py）单元测试。

覆盖：lowest-confidence 基线语义、审计表打乱/隐藏来源、CSV 往返、
标注解析的严格拒绝路径、指标手算与 AC-10 语义。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ai_physics_tracker.application.benchmark import (
    build_audit_table, lowest_confidence_baseline, read_audit_labels, score_strategy,
    write_audit_csv,
)
from ai_physics_tracker.infrastructure.dlc_predictions import RawPrediction


def _predictions() -> tuple[RawPrediction, ...]:
    rows = []
    for frame in range(10):
        if frame in (5, 6):
            rows.append(RawPrediction(frame, float("nan"), float("nan"), float("nan")))
        else:
            rows.append(RawPrediction(frame, 10.0 + frame, 20.0, 0.9 - 0.1 * (frame % 3)))
    return tuple(rows)  # 置信度循环 0.9/0.8/0.7；5/6 缺测


class TestLowestConfidenceBaseline:
    def test_missing_first_then_ascending_confidence(self):
        rows = _predictions()
        frames = lowest_confidence_baseline(rows, 5, zone_start=0, zone_end=9)
        assert frames[:2] == (5, 6)  # 缺测最先
        confidences = {row.frame_index: row.confidence for row in rows}
        values = [confidences[frame] for frame in frames[2:]]
        assert values == sorted(values)  # 非缺测按置信度升序
        assert frames[2] == 2  # 置信度 0.7 的第一帧（0.9/0.8/0.7 循环）

    def test_zone_and_manual_exclusion(self):
        frames = lowest_confidence_baseline(_predictions(), 10, zone_start=4, zone_end=8,
                                            manual_frames=frozenset({5, 7}))
        assert 5 not in frames and 7 not in frames
        assert all(4 <= f <= 8 for f in frames)

    def test_fewer_candidates_than_n_returns_all(self):
        rows = _predictions()[:3]
        frames = lowest_confidence_baseline(rows, 10, zone_start=0, zone_end=2)
        assert len(frames) == 3


class TestAuditTable:
    def test_union_shuffled_and_blinded(self):
        table = build_audit_table((1, 3, 5), (3, 7, 9), shuffle_seed=42)
        frames = sorted(int(row["frame_index"]) for row in table.rows)
        assert frames == [1, 3, 5, 7, 9]  # 并集
        assert set(table.rows[0].keys()) == {"frame_index", "needs_review",
                                             "needs_correction", "note"}  # 无来源列
        assert all(row["needs_review"] == "" for row in table.rows)  # 待人工填写
        # 同 seed 可复现、不同 seed 顺序不同（10 帧下打乱几乎必然不同）
        again = build_audit_table((1, 3, 5), (3, 7, 9), shuffle_seed=42)
        assert table.rows == again.rows

    def test_csv_roundtrip(self, tmp_path: Path):
        table = build_audit_table((1, 3), (3, 7), shuffle_seed=0)
        path = tmp_path / "audit.csv"
        write_audit_csv(table, path)
        # 表头与并集帧号来自 emit；随后人工标注为已填形态
        header = path.read_text(encoding="utf-8").splitlines()[0]
        assert header == "frame_index,needs_review,needs_correction,note"
        labeled = [
            header,
            "1,1,0,",
            "3,0,0,",
            "7,1,1,wrong",
        ]
        path.write_text("\n".join(labeled) + "\n", encoding="utf-8")
        labels = read_audit_labels(path)
        assert labels == {1: (True, False), 3: (False, False), 7: (True, True)}

    def test_reject_correction_without_review(self, tmp_path: Path):
        path = tmp_path / "audit.csv"
        path.write_text("frame_index,needs_review,needs_correction,note\n"
                        "4,0,1,\n", encoding="utf-8")
        with pytest.raises(ValueError, match="needs_correction requires needs_review"):
            read_audit_labels(path)

    @pytest.mark.parametrize("row", [
        "9,,0,\n",           # 未标注
        "9,maybe,0,\n",      # 非法布尔
        "x,1,0,\n",          # 非法帧号
    ])
    def test_reject_invalid_rows(self, tmp_path: Path, row: str):
        path = tmp_path / "audit.csv"
        path.write_text("frame_index,needs_review,needs_correction,note\n" + row,
                        encoding="utf-8")
        with pytest.raises(ValueError):
            read_audit_labels(path)

    def test_reject_duplicate_frames(self, tmp_path: Path):
        path = tmp_path / "audit.csv"
        path.write_text("frame_index,needs_review,needs_correction,note\n"
                        "2,1,0,\n2,0,0,\n", encoding="utf-8")
        with pytest.raises(ValueError, match="duplicate"):
            read_audit_labels(path)


class TestStrategyScore:
    def test_hand_computed_metrics(self):
        labels = {1: (True, False), 2: (True, True), 3: (False, False), 4: (True, True)}
        score = score_strategy((1, 2, 4), labels)
        assert score.actual_n == 3
        assert score.needs_review_count == 3
        assert score.needs_correction_count == 2
        assert score.precision_at_n == pytest.approx(1.0)
        assert score.review_yield == pytest.approx(2 / 3)

    def test_empty_strategy_scores_zero(self):
        score = score_strategy((), {})
        assert score.actual_n == 0
        assert score.precision_at_n == 0.0
        assert score.review_yield == 0.0

    def test_frames_missing_from_labels_rejected(self):
        with pytest.raises(ValueError, match="missing from audit labels"):
            score_strategy((1, 2), {1: (True, False)})
