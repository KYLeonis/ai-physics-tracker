# Subphase Plan — Phase 5.0 Tracking Pipeline Consolidation

- Issue：[Phase 5.0 — Tracking Pipeline Consolidation #17](https://github.com/KYLeonis/ai-physics-tracker/issues/17)
- 分支：`feat/p5.0-tracking-pipeline`
- 日期 / 状态：2026-09-01 · 进行中

## Goal

让 `TrackingJobRunner` 成为训练与推理唯一的长任务生命周期入口，关闭 Phase 4 Review F3。

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

- [ ] 生产代码与脚本不再调用旧 `TrainingCoordinator` / `InferenceCoordinator` 生命周期 API。
- [ ] 训练与推理只通过 `TrackingJobRunner` / `BackgroundTaskRunner` 管理启动、轮询与取消。
- [ ] prepare/read helper 仍覆盖训练准备、推理输入身份、原始结果校验与 first-wins 导入边界。
- [ ] 真实 DLC 冒烟脚本使用统一 runner，现有 GUI 产品行为不变。
- [ ] 定向测试、Qt offscreen 全回归和独立 architecture review 通过，F3 标记 Closed。

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
- [ ] Slice 2：收缩 prepare/read 边界，移除旧 lifecycle，并迁移测试与冒烟脚本。
- [ ] Slice 3：定向/全量验证、独立 review、文档收尾、合并与 CI。

## Verification

- `rg` 确认 production/script 不存在旧 lifecycle API 调用。
- `python -m pytest tests/test_training_job.py tests/test_inference_job.py tests/test_tracking_job.py tests/test_training_session.py tests/gui/test_tracking_actions.py`
- `QT_QPA_PLATFORM=offscreen python -m pytest`
- `python -m compileall src scripts/smoke_test_dlc_infer.py`
- 独立 reviewer 核对只有一个长任务生命周期所有者，且 F2/5.1 未混入。

## Result（收尾时填写）

- 完成日期 / 合并 commit：
- AC 勾选结果：
- 偏离计划之处及原因：
- 遗留问题：F2 继续由 5.4 处理；5.1 等待用户单独批准后开始。
- 独立 review 结论：
