#!/usr/bin/env python
"""Phase 5.6 闭环归档工具（开发侧证据生成，不进产品 GUI）。

从 project.json 读取 completed train/infer runs 与 refinement 状态，
按 validation series 归类相邻两轮评价，输出三类 delta（精度/覆盖/工作量）
的 markdown 归档，作为 AC-9 验收证据（用户无需阅读）。

用法：
    python scripts/generate_loop_report.py --project <项目目录> \
        [--output docs/benchmarks/phase-5-loop-report.md]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

RMSE_TREND_THRESHOLD = 0.05


def _rmse(evaluation: dict | None, split: str) -> float | None:
    if not isinstance(evaluation, dict):
        return None
    block = evaluation.get(split)
    if not isinstance(block, dict):
        return None
    metrics = block.get("metrics")
    if isinstance(metrics, dict) and isinstance(metrics.get("rmse"), (int, float)):
        return float(metrics["rmse"])
    return None


def _coverage(run: dict) -> float | None:
    summary = run.get("prediction_summary_v1")
    if isinstance(summary, dict) and isinstance(summary.get("coverage"), (int, float)):
        return float(summary["coverage"])
    return None


def _review(run: dict) -> dict:
    value = run.get("review_summary")
    return value if isinstance(value, dict) else {}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True)
    parser.add_argument("--output", default="docs/benchmarks/phase-5-loop-report.md")
    args = parser.parse_args(argv)

    root = Path(args.project)
    data = json.loads((root / "project.json").read_text(encoding="utf-8"))
    train_runs = sorted(
        (r for r in data["tracking_runs"]
         if r["task_type"] == "train" and r["status"] == "completed"),
        key=lambda r: r["created_at"],
    )
    infer_runs = sorted(
        (r for r in data["tracking_runs"]
         if r["task_type"] == "infer" and r["status"] == "completed"),
        key=lambda r: r["created_at"],
    )
    tracks = {t["track_id"]: t for t in data["tracks"]}

    lines = [
        "# Phase 5.6 Refinement Loop Evidence（Agent 归档，验收证据）",
        "",
        f"- 项目：`{root}`",
        f"- 生成时间：见文件 mtime；数据源：project.json（schema v1 tolerant extra_fields）",
        "",
        "## 训练轮次（按 validation series 归类）",
        "",
    ]
    comparable = []
    for run in train_runs:
        it = run.get("refinement_iteration_v1") or {}
        series = it.get("validation_series_id")
        val_rmse = _rmse(run.get("evaluation"), "test")
        train_rmse = _rmse(run.get("evaluation"), "train")
        lines.append(
            f"- `{run['run_id'][:8]}` iter={it.get('iteration_index')} "
            f"mode={it.get('training_mode', 'restart')} "
            f"series={str(series)[:8] if series else '—'} "
            f"train_labels={len(it.get('training_labels') or [])} "
            f"val_rmse={val_rmse} train_rmse={train_rmse} epochs={run.get('config', {}).get('epochs')}"
        )
        if series and val_rmse is not None:
            comparable.append((run, it, val_rmse, train_rmse))
        if it.get("resume_from_training_run_id"):
            lines.append(f"  - resume_from: `{it['resume_from_training_run_id'][:8]}`")

    lines += ["", "## 三类 delta（同 series 相邻两轮）", ""]
    deltas_written = 0
    for index in range(1, len(comparable)):
        prev_run, prev_it, prev_val, _prev_train = comparable[index - 1]
        last_run, last_it, last_val, last_train = comparable[index]
        if prev_it.get("validation_series_id") != last_it.get("validation_series_id"):
            continue
        prev_series_train = _rmse(prev_run.get("evaluation"), "train")
        if not prev_val or prev_val <= 0:
            continue
        val_delta = (last_val - prev_val) / prev_val
        lines.append(f"### {prev_run['run_id'][:8]} → {last_run['run_id'][:8]}")
        lines.append("")
        verdict = ("improved" if val_delta <= -RMSE_TREND_THRESHOLD
                   else "worsened" if val_delta >= RMSE_TREND_THRESHOLD else "plateau")
        lines.append(f"- **精度**：validation RMSE {prev_val:.4g} → {last_val:.4g} "
                     f"（{val_delta:+.1%}，{verdict}）")
        train_delta = (last_train - prev_series_train) / prev_series_train \
            if prev_series_train else None
        if train_delta is not None:
            lines.append(f"- 训练集 RMSE {prev_series_train:.4g} → {last_train:.4g} "
                         f"（{train_delta:+.1%}）")
        prev_cov = _coverage(next((r for r in infer_runs
                                   if r.get("config", {}).get("training_run_id")
                                   == prev_run["run_id"]), {}))
        last_cov = _coverage(next((r for r in infer_runs
                                   if r.get("config", {}).get("training_run_id")
                                   == last_run["run_id"]), {}))
        if prev_cov is not None and last_cov is not None:
            lines.append(f"- **覆盖**：prediction coverage {prev_cov:.1%} → {last_cov:.1%} "
                         "（informational only, not accuracy）")
        prev_review = _review(prev_run)
        last_review = _review(last_run)
        lines.append(
            f"- **工作量**：审核 remaining {prev_review.get('pending_count', '—')} → "
            f"{last_review.get('pending_count', '—')}；correction yield "
            f"{last_review.get('corrected_count', 0)}/"
            f"{last_review.get('total_reviewed', last_review.get('reviewed_count', 0))}"
        )
        lines.append("")
        deltas_written += 1
    if deltas_written == 0:
        lines.append("- 暂无可比的同 series 两轮评价。")

    lines += ["", "## 推理结果与激活", ""]
    for run in infer_runs:
        lines.append(
            f"- `{run['run_id'][:8]}` model_train=`{str(run.get('config', {}).get('training_run_id', '—'))[:8]}` "
            f"coverage={_coverage(run)} activated={'是' if _is_activated(data, run) else '否'}"
        )

    lines += ["", "## 激活历史", ""]
    for track in data["tracks"]:
        state = (track.get("extra_fields") or {}).get("refinement_state_v1") or {}
        for record in state.get("activation_history", []):
            lines.append(
                f"- {record['timestamp'][:19]} {track['name']}: {record['action']} "
                f"{str(record.get('from_run_id'))[:8]} → {str(record.get('to_run_id'))[:8]} "
                f"({record['point_count']} pts)"
            )

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"loop evidence written: {output} ({deltas_written} comparable delta pair(s))")
    return 0


def _is_activated(data: dict, infer_run: dict) -> bool:
    for track in data["tracks"]:
        state = (track.get("extra_fields") or {}).get("refinement_state_v1") or {}
        if state.get("active_infer_run_id") == infer_run["run_id"]:
            return True
    return False


if __name__ == "__main__":
    sys.exit(main())
