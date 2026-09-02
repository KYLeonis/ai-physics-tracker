#!/usr/bin/env python
"""Phase 5.2 困难帧基准入口：生成盲评审计表 / 对已标注审计表计分。

用法（详见 docs/benchmarks/README.md）：

    # 1) 从本地项目的 completed infer run 生成开发集审计表（打乱、隐藏来源）
    python scripts/benchmark_difficult_frames.py emit-audit \
        --project <项目目录> [--run <run_id>] [--top-n 10] [--seed 0] \
        [--confidence-threshold 0.6] [--min-gap-s 0.25] \
        [--output docs/benchmarks/phase-5.2-development.csv]

    # 2) 人工标注 CSV 中每帧 needs_review / needs_correction / note 后计分
    python scripts/benchmark_difficult_frames.py score \
        --project <项目目录> --audit <审计表.csv> \
        [--output docs/benchmarks/phase-5.2-report.md]

score 阶段会用相同输入/参数/seed 确定性重算两种策略并核对 emit 时记录的
候选帧；视频文件缺失或产物被改动会直接报错而不是静默给出不同结果。
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from ai_physics_tracker.application.benchmark import (
    AuditTable, build_audit_table, lowest_confidence_baseline, read_audit_labels,
    score_strategy, write_audit_csv,
)
from ai_physics_tracker.application.difficult_frame_job import (
    DifficultFrameResult, prepare_difficult_frame_request, read_difficult_frame_result,
    run_difficult_frame_worker,
)
from ai_physics_tracker.application.difficult_frames import MiningParams
from ai_physics_tracker.application.project_session import ProjectSession
from ai_physics_tracker.infrastructure.dlc_adapter import DLCAdapter
from ai_physics_tracker.infrastructure.project_repository import ProjectRepository


class _ListQueue:
    """内联执行 worker 时的消息收集队列。"""

    def __init__(self) -> None:
        self.items: list = []

    def put(self, item) -> None:
        self.items.append(item)


class _UnsetEvent:
    def is_set(self) -> bool:
        return False


def _load_session(project_dir: Path, run_id: str | None) -> tuple[ProjectSession, UUID]:
    """加载项目并定位 completed infer run；旧 run 缺 prediction_path 时在内存中回填。"""
    root = project_dir.resolve()
    repository = ProjectRepository()
    project = repository.load(root)
    runs = [r for r in project.tracking_runs
            if r.task_type == "infer" and r.status == "completed"]
    if run_id is not None:
        wanted = UUID(run_id)
        runs = [r for r in runs if r.run_id == wanted]
    if not runs:
        raise SystemExit("no completed inference run found (use --run to pick one)")
    run = max(runs, key=lambda r: r.created_at)

    if not run.extra_fields.get("prediction_path"):
        # 旧版本 run 未持久化产物引用：从其专属 run 目录定位唯一 h5（回填仅存内存）
        run_dir = root / "data" / "engines" / str(run.run_id)
        candidates = sorted(p for p in run_dir.iterdir()
                            if p.suffix.lower() in {".h5", ".hdf5", ".csv"})
        h5_files = [p for p in candidates if p.suffix.lower() != ".csv"]
        if len(h5_files) == 1:
            artifact = h5_files[0]
        elif len(candidates) == 1:
            artifact = candidates[0]
        else:
            raise SystemExit(
                f"cannot locate the raw prediction artifact in {run_dir}: {candidates}; "
                "re-run inference with the current version"
            )
        run = replace(run, extra_fields={
            **run.extra_fields,
            "prediction_path": artifact.relative_to(root).as_posix(),
        })
        project = replace(project, tracking_runs=tuple(
            run if r.run_id == run.run_id else r for r in project.tracking_runs))
        print(f"[legacy] backfilled prediction_path in memory: "
              f"{run.extra_fields['prediction_path']}")
    return ProjectSession(repository, project, root), run.run_id


def _mine(session: ProjectSession, run_id: UUID, params: MiningParams) -> tuple[UUID, DifficultFrameResult]:
    request_id = UUID("00000000-0000-4000-8000-{:012d}".format(params.seed))
    job = prepare_difficult_frame_request(session, run_id, params)
    payload = run_difficult_frame_worker(request_id, _ListQueue(), _UnsetEvent(),
                                         job, DLCAdapter())
    if payload.get("status") != "completed":
        raise SystemExit(f"mining did not complete: {payload}")
    return request_id, read_difficult_frame_result(session.project_root, request_id)


def _baseline_frames(session: ProjectSession, run_id: UUID, params: MiningParams) -> tuple[int, ...]:
    run = next(r for r in session.tracking_runs() if r.run_id == run_id)
    root = session.project_root
    prediction_path = root / run.extra_fields["prediction_path"]
    video = next(v for v in session.project.videos if v.video_id == run.video_id)
    timeline = next(t for t in session.project.timelines if t.video_id == run.video_id)
    predictions = DLCAdapter().read_raw_predictions(prediction_path, frame_count=video.frame_count)
    zone_start, zone_end = timeline.working_zone
    manual = frozenset(p.frame_index for p in session.manual_points(run.track_id)
                       if zone_start <= p.frame_index <= zone_end)
    return lowest_confidence_baseline(predictions, params.top_n,
                                      zone_start=zone_start, zone_end=zone_end,
                                      manual_frames=manual)


def _artifact_identity(session: ProjectSession, run_id: UUID) -> dict[str, object]:
    run = next(r for r in session.tracking_runs() if r.run_id == run_id)
    video = next(v for v in session.project.videos if v.video_id == run.video_id)
    stat = (session.project_root / run.extra_fields["prediction_path"]).stat()
    return {
        "video": video.display_name,
        "frame_count": video.frame_count,
        "run_id": str(run_id),
        "prediction_file": run.extra_fields["prediction_path"],
        "prediction_file_size": stat.st_size,
        "prediction_file_mtime_ns": stat.st_mtime_ns,
    }


def cmd_emit(args: argparse.Namespace) -> int:
    project_dir = Path(args.project)
    session, run_id = _load_session(project_dir, args.run)
    params = MiningParams(top_n=args.top_n, seed=args.seed,
                          confidence_threshold=args.confidence_threshold,
                          min_gap_s=args.min_gap_s)
    request_id, result = _mine(session, run_id, params)
    baseline = _baseline_frames(session, run_id, params)
    policy = tuple(candidate.frame_index for candidate in result.candidates)

    table: AuditTable = build_audit_table(policy, baseline, shuffle_seed=args.seed)
    output = Path(args.output)
    write_audit_csv(table, output)
    meta = {
        "emitted_at": datetime.now(UTC).isoformat(),
        **_artifact_identity(session, run_id),
        "request_id": str(request_id),
        "top_n": params.top_n,
        "seed": params.seed,
        "confidence_threshold": params.confidence_threshold,
        "min_gap_s": params.min_gap_s,
        "policy_frames": list(policy),
        "baseline_frames": list(baseline),
        "diversity_status": result.diversity_status,
        "params_snapshot": result.params_snapshot,
    }
    meta_path = output.with_suffix(".meta.json")
    meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"policy   top {len(policy)}: {list(policy)}")
    print(f"baseline top {len(baseline)}: {list(baseline)}")
    print(f"audit table: {output} ({len(table.rows)} rows, shuffled, sources hidden)")
    print(f"meta (local only, gitignored): {meta_path}")
    print("\n下一步：逐帧打开视频核对预测，填写 needs_review / needs_correction / note，")
    print("然后运行 score 子命令。填写约定见 docs/benchmarks/README.md。")
    return 0


def cmd_score(args: argparse.Namespace) -> int:
    audit_path = Path(args.audit)
    meta = json.loads(audit_path.with_suffix(".meta.json").read_text(encoding="utf-8"))
    session, run_id = _load_session(Path(args.project), meta["run_id"])
    params = MiningParams(top_n=meta["top_n"], seed=meta["seed"],
                          confidence_threshold=meta["confidence_threshold"],
                          min_gap_s=meta["min_gap_s"])
    _, result = _mine(session, run_id, params)
    baseline = _baseline_frames(session, run_id, params)
    policy = tuple(candidate.frame_index for candidate in result.candidates)

    recorded_policy = tuple(meta["policy_frames"])
    recorded_baseline = tuple(meta["baseline_frames"])
    if policy != recorded_policy or baseline != recorded_baseline:
        raise SystemExit(
            "recomputed candidates differ from emit time; inputs changed "
            "(video/prediction file modified?) — re-emit the audit table"
        )
    labels = read_audit_labels(audit_path)
    policy_score = score_strategy(policy, labels)
    baseline_score = score_strategy(baseline, labels)

    report = [
        "# Phase 5.2 Difficult Frame Benchmark Report",
        "",
        f"- 日期：{datetime.now(UTC).date().isoformat()}",
        f"- 视频：{meta['video']}（{meta['frame_count']} 帧）",
        f"- infer run：`{meta['run_id']}`",
        f"- 预测产物：`{meta['prediction_file']}` "
        f"(size={meta['prediction_file_size']}, mtime_ns={meta['prediction_file_mtime_ns']})",
        f"- 审计表：`{audit_path.as_posix()}`（{len(labels)} 帧已标注）",
        f"- 参数：top_n={params.top_n}, seed={params.seed}, "
        f"confidence_threshold={params.confidence_threshold}, min_gap_s={params.min_gap_s}, "
        f"diversity={result.diversity_status}",
        "",
        "| 策略 | actual_n | needs_review | Precision@N | needs_correction | review yield |",
        "| --- | --- | --- | --- | --- | --- |",
        f"| difficult-frame policy | {policy_score.actual_n} | "
        f"{policy_score.needs_review_count} | {policy_score.precision_at_n:.3f} | "
        f"{policy_score.needs_correction_count} | {policy_score.review_yield:.3f} |",
        f"| lowest-confidence baseline | {baseline_score.actual_n} | "
        f"{baseline_score.needs_review_count} | {baseline_score.precision_at_n:.3f} | "
        f"{baseline_score.needs_correction_count} | {baseline_score.review_yield:.3f} |",
        "",
    ]
    policy_wins = (policy_score.precision_at_n > baseline_score.precision_at_n
                   and policy_score.review_yield > baseline_score.review_yield)
    report.append(
        "**结论：policy 在 Precision@N 与 review yield 上均优于基线（AC-10 达成）**"
        if policy_wins else
        "**结论：policy 未同时优于基线（AC-10 未达成）——保留证据，回到开发集调整，"
        "不得在冻结集上反向调参**"
    )
    report_path = Path(args.output)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(report) + "\n", encoding="utf-8")
    print(f"report written: {report_path}")
    print(f"policy   Precision@N={policy_score.precision_at_n:.3f} "
          f"review_yield={policy_score.review_yield:.3f}")
    print(f"baseline Precision@N={baseline_score.precision_at_n:.3f} "
          f"review_yield={baseline_score.review_yield:.3f}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    subparsers = parser.add_subparsers(dest="command", required=True)

    emit = subparsers.add_parser("emit-audit", help="生成盲评审计表（开发集或冻结集）")
    emit.add_argument("--project", required=True, help="项目目录（含 project.json）")
    emit.add_argument("--run", help="completed infer run id（默认取最新）")
    emit.add_argument("--top-n", type=int, default=10)
    emit.add_argument("--seed", type=int, default=0)
    emit.add_argument("--confidence-threshold", type=float, default=0.6)
    emit.add_argument("--min-gap-s", type=float, default=0.25)
    emit.add_argument("--output", default="docs/benchmarks/phase-5.2-development.csv")
    emit.set_defaults(func=cmd_emit)

    score = subparsers.add_parser("score", help="对已标注审计表计分并写报告")
    score.add_argument("--project", required=True)
    score.add_argument("--audit", required=True, help="emit-audit 输出的 CSV")
    score.add_argument("--output", default="docs/benchmarks/phase-5.2-report.md")
    score.set_defaults(func=cmd_score)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
