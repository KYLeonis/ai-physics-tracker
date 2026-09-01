# Subphase Plan — Phase 5.0 Tracking Pipeline Consolidation

- Issue：[Phase 5.0 — Tracking Pipeline Consolidation #17](https://github.com/KYLeonis/ai-physics-tracker/issues/17)
- 分支：`feat/p5.0-tracking-pipeline`
- 日期 / 状态：2026-09-01 至 2026-09-02 · 已完成

## Goal

让 `TrackingJobRunner + TrackingActions + BackgroundTaskRunner` 成为训练与推理唯一的长任务生命周期路径，关闭 Phase 4 Review F3。

## Scope

**做**：

- 保留训练准备、推理准备与结果读取边界，移除旧 coordinator 的 start/poll/cancel 生命周期。
- 把真实 DLC 训练→推理冒烟脚本迁移到统一 request/runner/candidate 路径。
- 将旧生命周期测试中仍有价值的行为迁移到 `tracking_job`，删除仅证明双轨存在的重复测试。
- 运行定向测试、全回归与独立 architecture review，并同步 F3 状态。

**不做**：

- 不实现 F2 的 AI 轨迹 clear/activate/replace；F2 保留给 5.4。
- 不添加代表帧、困难帧、Suggested Frames、Advisor 或其他 Phase 5 产品能力。
- 不改 GUI 交互、project schema、依赖、CI 或 DLC 算法。

## Acceptance Criteria

- [x] 生产代码与脚本不再调用旧 `TrainingCoordinator` / `InferenceCoordinator` 生命周期 API。
- [x] 训练与推理只通过 `TrackingJobRunner + TrackingActions + BackgroundTaskRunner` 管理启动、轮询与取消。
- [x] prepare/read helper 仍覆盖训练准备、推理输入身份、原始结果校验与 first-wins 导入边界。
- [x] 真实 DLC 冒烟脚本使用统一 runner，现有 GUI 产品行为不变。
- [x] 定向测试、Qt offscreen 全回归和独立 architecture review 通过，F3 标记 Closed。

## Relevant Context

- `docs/spec/phase5-requirements.md` R0、AC-11
- `docs/status/phase-5-plan.md` §3 Phase 5.0
- `docs/reviews/phase4-architecture-reliability-review.md` F3
- `docs/decisions/0012-gui-tracking-task-boundaries.md`
- `src/ai_physics_tracker/application/tracking_job.py`
- `src/ai_physics_tracker/application/training_job.py`
- `src/ai_physics_tracker/application/inference_job.py`

## Slices

- [x] Slice 1：盘点旧 lifecycle 调用者，确认 GUI 已使用统一 runner，旧调用仅存于测试与一个冒烟脚本。
- [x] Slice 2：收缩 prepare/read 边界，移除旧 lifecycle，并迁移测试与冒烟脚本。
- [x] Slice 3：定向/全量验证、独立 review 与文档收尾；合并/CI 证据在推送后补记。

## Verification

- `rg` 确认 production/script 不存在旧 lifecycle API 调用。
- `python -m pytest tests/test_training_job.py tests/test_inference_job.py tests/test_tracking_job.py tests/test_training_session.py tests/gui/test_tracking_actions.py`
- `QT_QPA_PLATFORM=offscreen python -m pytest`
- `python -m compileall src scripts/smoke_test_dlc_infer.py`
- 独立 reviewer 核对只有一个长任务生命周期所有者，且 F2/5.1 未混入。

## Result（收尾时填写）

- 完成日期 / 合并 commit：2026-09-02 / 待 `--no-ff` 合并后补记
- AC 勾选结果：5/5 通过；本地全回归 433 passed，真实 DLC CPU smoke 通过。
- 偏离计划之处及原因：R1 指出旧测试删除后统一路径边界覆盖不足；追加 `ba3d870` 后 R2 通过。无产品范围偏离。
- 遗留问题：F2 继续由 5.4 处理；5.1 等待用户单独批准后开始。
- 独立 review 结论：[phase-5.0-review.md](../reviews/phase-5.0-review.md) R2 通过，F3 Closed。
