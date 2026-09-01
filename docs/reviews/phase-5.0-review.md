# Review Record — Phase 5.0 Tracking Pipeline Consolidation

- Subphase / Issue：5.0 · [#17](https://github.com/KYLeonis/ai-physics-tracker/issues/17)
- Review 范围：`feat/p5.0-tracking-pipeline` 的 `db6c735` / `3afa280` / `ba3d870`
- Context：`docs/spec/phase5-requirements.md` R0/AC-11、`docs/status/phase-5.0-plan.md`、Phase 4 Review F3、ADR-0012
- 轮次：R1 2026-09-01（首轮）· R2 2026-09-02（修复后复审）

## Checklist

**正确性**

- [x] 旧 Training/Inference coordinator 生命周期已移除，prepare/read 边界保留
- [x] 统一路径覆盖启动、取消/回收、迟到、上下文变化、失败、first-wins 与产物校验
- [x] 真实 DLC CPU 训练→评价→推理→导入→保存闭环通过

**质量**

- [x] diff 只处理 F3、测试迁移与直接相关文档；未混入 F2/5.1/schema/依赖
- [x] 路径与文件读写遵守跨平台规则
- [x] 旧 API 从 `src/`、`scripts/`、`tests/` 消失
- [x] 模块级 prepare/read API 有职责说明

**流程**

- [x] 提交信息符合 Conventional Commits
- [x] 无 ADR 级变更；本次执行既有 ADR-0012 的单一任务事务边界

## Findings

### F1 — 生命周期边界测试未完全迁移到统一路径

- **Severity**：Blocker（R1 Medium；关闭 5.0 前需补齐）
- **Evidence**：R1 发现旧推理 lifecycle 测试移除后，统一路径缺少真实取消/回收、启动/训练失败、上下文变化、产物篡改与 unchanged-stat 策略的等价回归；全量测试由 441 降至 425。
- **Impact**：架构已单轨，但不足以证明取消、迟到、归属和失败语义在唯一产品路径继续成立。
- **Recommendation**：只补统一路径的最小回归，不恢复旧 coordinator 测试。
- **Decision**：Fix Before Close——Issue #17 的验收直接要求保留这些边界。
- **Fix commit**：`ba3d870`
- **Verification**：新增 runner facade、真实 spawn 推理取消、训练失败、GUI 启动失败、timing/project root/generation 变化取消、media/config/model/observation 篡改拒绝与 unchanged-stat 测试；定向 30 passed，全量 433 passed；[CI run 33531403393](https://github.com/KYLeonis/ai-physics-tracker/actions/runs/33531403393) 双平台通过。
- **Re-review**：R2 独立 reviewer 确认 Medium 已关闭。
- **Status**：Closed

### F2 — 生命周期所有权措辞应包含三层协作

- **Severity**：Suggestion
- **Evidence**：`TrackingJobRunner` 负责统一启动，`BackgroundTaskRunner` 持有进程/句柄，`TrackingActions` 负责轮询、取消触发与活动 session 状态提交。
- **Impact**：只写“runner 独自拥有生命周期”会误导后续实现者。
- **Recommendation**：文档统一写为 `TrackingJobRunner + TrackingActions + BackgroundTaskRunner` 是唯一生命周期路径。
- **Decision**：Fix Before Close——纯文档且能消除歧义。
- **Fix commit**：收尾文档提交
- **Verification**：`docs/architecture.md`、5.0 plan 与 roadmap 同步措辞。
- **Re-review**：R2 确认该项非阻断；实现方按建议收口。
- **Status**：Closed

## Review Log

### R1 — 2026-09-01 · 首轮

- 范围 / 基线：`57b4194..3afa280`
- 结论：F3 架构收敛成立，但生命周期边界测试迁移不足，新增 F1；另有措辞建议 F2。
- Findings 变化：新增 F1、F2；关闭 —

### R2 — 2026-09-02 · 复审

- 范围：追加 `ba3d870`
- 结论：新增统一路径回归覆盖 R1 缺口；Critical/High/Medium/Low 均无，F3 可关闭。
- Findings 变化：F1 Closed；F2 由收尾文档关闭。

## Final Verdict

- [x] 修改后通过（findings 按 Decision 处置完毕，复审确认）
- [ ] 通过（首轮无 finding）
- [ ] 需要重做

- 最终结论：旧双轨状态机已删除，唯一生命周期路径及关键边界有本地自动化、真实 DLC smoke 与双平台 CI 证据；F3 Closed。
- 日期 / 依据轮次：2026-09-02 · R1 + R2
