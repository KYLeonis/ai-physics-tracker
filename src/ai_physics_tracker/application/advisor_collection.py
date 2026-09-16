"""Advisor 输入的事实采集器（P6R-04 / P6R-02，Qt-free）。

从活动 ProjectSession 与 run 注册表计算 `AdvisorInput` 的不可变快照：
纯读取（唯一 IO 是 resume snapshot 的存在性检查），不修改会话、不落盘。
`training_advisor.py` 保持"纯函数、不读文件"的模块契约，采集职责在此分离；
GUI 侧（TrackingActions）只补充 pending 任务与表单参数。

事实口径（P6R-04）：
- timeline 按**所选 Track 的 video_id** 解析——`video_id == track_id` 的旧查找
  永不命中，导致 uncovered_zone_segments 恒 False、plateau 分支静默失效；
- last_train_failed 表示**最近一次相关训练**（completed/failed 中 created_at
  最新者）的状态——历史上出现过失败但之后已成功重训时，不得继续报失败。
"""

import logging
from typing import Any
from uuid import UUID

from ai_physics_tracker.application.project_session import ProjectSession
from ai_physics_tracker.application.refinement_history import (
    VALIDATION_COMPARISON_CLEAN,
    VALIDATION_COMPARISON_UNKNOWN,
    extract_refinement_iteration,
    validation_training_exposure,
)
from ai_physics_tracker.domain.tracking_run import TrackingRun
from ai_physics_tracker.application.training_advisor import (
    OOM_MARKERS,
    AdvisorInput,
    RoundMetrics,
)

logger = logging.getLogger(__name__)


def _evaluation_rmse(evaluation: dict) -> tuple[float, float, str, str] | None:
    """从 train run 的 evaluation 提取 (train, validation) RMSE 与名称/单位。

    兼容两种形态：DLC 原生 {train: {metrics: {...}}, test: {...}} 与
    Mock 的 {metrics: {train_rmse, test_rmse}, unit}；无共同指标返回 None。
    """
    if not isinstance(evaluation, dict):
        return None
    unit = "px"
    if isinstance(evaluation.get("metrics"), dict):
        metrics = evaluation["metrics"]
        has_train = isinstance(metrics.get("train_rmse"), (int, float))
        has_test = isinstance(metrics.get("test_rmse"), (int, float))
        if has_train and has_test:
            unit = str(evaluation.get("unit", "px"))
            return float(metrics["train_rmse"]), float(metrics["test_rmse"]), "rmse", unit
        return None
    train_block = evaluation.get("train")
    test_block = evaluation.get("test")
    if not (isinstance(train_block, dict) and isinstance(test_block, dict)):
        return None
    train_metrics = train_block.get("metrics")
    test_metrics = test_block.get("metrics")
    if not (isinstance(train_metrics, dict) and isinstance(test_metrics, dict)):
        return None
    common = set(train_metrics) & set(test_metrics)
    preferred = [name for name in sorted(common) if "rmse" in name.lower()]
    if not preferred:
        return None
    name = preferred[0]
    train_value, test_value = train_metrics[name], test_metrics[name]
    if not (isinstance(train_value, (int, float)) and isinstance(test_value, (int, float))):
        return None
    if isinstance(evaluation.get("units"), dict):
        unit = str((train_block.get("units") or {}).get(name, "px"))
    return float(train_value), float(test_value), name, unit


def collect_advisor_input(
    session: ProjectSession,
    track_id: UUID,
    runs: tuple[TrackingRun, ...],
    *,
    has_active_task: bool,
    requested_batch_size: int,
    requested_epochs: int,
) -> AdvisorInput:
    """从活动会话采集 Advisor 的全部输入事实（纯读取，不修改会话）。"""
    track = next((t for t in session.tracks if t.track_id == track_id), None)
    timeline = (
        next((t for t in session.project.timelines if t.video_id == track.video_id), None)
        if track is not None else None
    )
    completed_train = [r for r in runs
                       if r.track_id == track_id and r.task_type == "train"
                       and r.status == "completed"]
    # P6R-04：失败事实 = 最近一次相关训练（completed/failed 取 created_at 最新）
    # 的状态；成功重训之后不再保留历史失败的 OOM 证据。created_at 相同（时钟
    # 分辨率限制，Windows CI 实测可触发）时取注册表更靠后者——注册顺序即尝试顺序。
    relevant_train = [r for r in runs
                      if r.track_id == track_id and r.task_type == "train"
                      and r.status in {"completed", "failed"}]
    latest_train_attempt = None
    for train_attempt in relevant_train:
        if (latest_train_attempt is None
                or train_attempt.created_at >= latest_train_attempt.created_at):
            latest_train_attempt = train_attempt
    last_train_failed = latest_train_attempt is not None and latest_train_attempt.status == "failed"
    last_failure_oom = False
    if last_train_failed:
        error_text = str(latest_train_attempt.error_message or "").lower()
        last_failure_oom = any(marker in error_text for marker in OOM_MARKERS)

    latest_train = completed_train[-1] if completed_train else None
    manual_points = [p for p in session.manual_points(track_id)]
    new_labels = 0
    if latest_train is not None and latest_train.completed_at is not None:
        new_labels = sum(
            1 for p in manual_points if p.modified_at > latest_train.completed_at)

    # P6R-02：各轮按自身完整 Resume ancestry 计算比较资格；series 已删除或
    # 无 series 的轮次按 unknown（不可独立比较）处理。
    ref_state = session.get_refinement_state(track_id)
    series_by_id = {s.series_id: s for s in ref_state.validation_series}
    recent_rounds: list[RoundMetrics] = []
    for train_run in completed_train:
        evaluation = train_run.extra_fields.get("evaluation")
        iteration = extract_refinement_iteration(train_run)
        if not isinstance(evaluation, dict) or iteration is None:
            continue
        metrics_pair = _evaluation_rmse(evaluation)
        if metrics_pair is None:
            continue
        train_rmse, val_rmse, metric_name, unit = metrics_pair
        series = (
            series_by_id.get(iteration.validation_series_id)
            if iteration.validation_series_id is not None else None
        )
        if series is not None:
            qualification = validation_training_exposure(
                runs, train_run.run_id, series.frame_indices).qualification
        else:
            qualification = VALIDATION_COMPARISON_UNKNOWN
        recent_rounds.append(RoundMetrics(
            training_run_id=str(train_run.run_id),
            validation_series_id=(
                str(iteration.validation_series_id)
                if iteration.validation_series_id is not None else None
            ),
            train_rmse=train_rmse,
            validation_rmse=val_rmse,
            comparison_qualification=qualification,
            metric_name=metric_name,
            metric_unit=unit,
        ))

    # 审核统计：当前 track 最新 completed infer run 的 review summary
    infer_runs = [r for r in runs
                  if r.track_id == track_id and r.task_type == "infer"
                  and r.status == "completed"]
    pending_candidates = 0
    correction_yield = None
    if infer_runs:
        latest_infer = infer_runs[-1]
        try:
            rev_sum = session.get_review_summary(latest_infer.run_id)
        except Exception as error:
            # 审核摘要仅是 Advisor 输入的证据之一；不可读时降级为无统计而非失败，
            # 但不留静默吞错（CODE_STANDARD §8）
            logger.debug("review summary unavailable for run %s: %s",
                         latest_infer.run_id, error)
            rev_sum = None
        if rev_sum is not None:
            pending_candidates = rev_sum.pending_count
            if rev_sum.total_reviewed > 0:
                correction_yield = rev_sum.corrected_count / rev_sum.total_reviewed

    active_series = ref_state.active_series

    def _resumable(train_run) -> bool:
        # P6R-02：与 prepare_tracking_request 的 Resume 门同一资格口径——
        # 不把会被入口拒绝的源推荐给用户
        if not train_run.model_snapshot or session.project_root is None:
            return False
        if not (session.project_root / train_run.model_snapshot).is_file():
            return False
        if active_series is None:
            return True
        return validation_training_exposure(
            runs, train_run.run_id, active_series.frame_indices
        ).qualification == VALIDATION_COMPARISON_CLEAN

    has_compatible_source = any(_resumable(r) for r in completed_train)

    uncovered = False
    if timeline is not None and track is not None and manual_points:
        # P6R-04：timeline 必须取自 track.video_id；此前误用 track_id 查找导致
        # uncovered 恒 False、plateau 分支静默失效
        zone_start, zone_end = timeline.working_zone
        span = max(zone_end - zone_start, 1)
        quarter_size = span / 4
        covered = set()
        for p in manual_points:
            covered.add(max(0, min(int((p.frame_index - zone_start) / quarter_size), 3)))
        uncovered = len(covered) < 4

    # 覆盖率证据对（5.6 Slice 1，仅证据行）：最近两个 completed infer run 的
    # prediction coverage
    infer_runs_all = sorted(
        (r for r in runs if r.track_id == track_id and r.task_type == "infer"
         and r.status == "completed"),
        key=lambda r: r.created_at)

    def _coverage(infer_run) -> float | None:
        summary: Any = infer_run.extra_fields.get("prediction_summary_v1")
        if isinstance(summary, dict) and isinstance(summary.get("coverage"), (int, float)) \
                and not isinstance(summary.get("coverage"), bool):
            return float(summary["coverage"])
        return None

    coverage_previous = _coverage(infer_runs_all[-2]) if len(infer_runs_all) >= 2 else None
    coverage_latest = _coverage(infer_runs_all[-1]) if infer_runs_all else None
    # 激活引导：最新 completed infer run 若尚未成为活动结果（指针不指向它），
    # 就是可激活的候选；判据必须是 active 指针而非 model_snapshot
    # （候选 run 同样带 snapshot，此前判据恒为假 → 引导永不出现）
    active_infer_id = session.get_track_activation_status(track_id)[1]
    latest_infer_id = None
    if infer_runs_all and str(infer_runs_all[-1].run_id) != str(active_infer_id):
        latest_infer_id = str(infer_runs_all[-1].run_id)

    if active_series is not None:
        validation_valid, validation_invalid_reason = session.validate_active_validation_series(
            track_id)
    else:
        validation_valid, validation_invalid_reason = True, None

    return AdvisorInput(
        has_active_task=has_active_task,
        artifacts_missing=False,
        validation_valid=validation_valid,
        validation_invalid_reason=validation_invalid_reason,
        last_train_failed=last_train_failed,
        last_failure_is_oom=last_failure_oom,
        pending_candidates=pending_candidates,
        completed_train_runs=len(completed_train),
        new_labels_since_last_train=new_labels,
        has_compatible_source=has_compatible_source,
        recent_rounds=tuple(recent_rounds),
        correction_yield=correction_yield,
        uncovered_zone_segments=uncovered,
        requested_batch_size=requested_batch_size,
        requested_epochs=requested_epochs,
        coverage_previous=coverage_previous,
        coverage_latest=coverage_latest,
        latest_infer_run_id=latest_infer_id,
    )
