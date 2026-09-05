# ADR-0015 — Training Advisor 与 Resume/Restart 重训练持久化契约

## Status

Accepted（2026-09-04；随 Phase 5.5 mini-plan 批准落地）。

## Context

Phase 5.4 交付了 fixed validation series 与迭代历史（ADR-0014），跨轮精度比较具备了科学基准。
Phase 5.5 要在此之上提供确定、有限、可解释的规则型 Training Advisor，并支持用户显式选择
Resume/fine-tune（从已完成 snapshot 继续训练）或 Restart（从头训练）。

约束（沿用 ADR-0014）：
1. 不提升 `project.json` schema version，不迁移旧项目。
2. Advisor 建议是可重新计算的界面状态，不是历史事实；不能把过时建议持久化成记录。
3. 只有用户显式启动的训练才产生新的 train run；实际执行的参数与 lineage 必须随 run 可追溯。

## Decision

1. **迭代解释层扩展（tolerant extra_fields 内）**：`train TrackingRun.extra_fields
   ["refinement_iteration_v1"]` 新增两个键：
   - `training_mode`: `"restart" | "resume"`；记录本次训练实际使用的模式。
   - `resume_from_training_run_id`: `UUID | null`；仅 resume 非空，指向不可变的 completed
     parent train run。source snapshot 由 parent run 的 `model_snapshot` 唯一确定，produced
     snapshot 仍记录在当前 run 的 `model_snapshot`，不重复存路径。
   - 反序列化：旧 run 无这两个键时按 `training_mode="restart"`、`resume_from_training_run_id
     =None` 读取（5.5 前不存在产品级 resume 入口）。
2. **执行参数照旧存 `TrackingRun.config`**：本次 epochs、batch size、device 等实际值进入
   config 快照；`epochs` 在 resume 语境下是"本次追加 epochs"。
3. **Advisor 建议不持久化**：`application/training_advisor.py` 为纯函数规则引擎（固定优先级、
   有限参数档位），输入输出均为不可变值对象；建议只存在于界面，Apply Suggestion 仅填表。
4. **Resume 的 snapshot 传递**：通过 `EngineAdapter.train(..., snapshot_path=...)` 可选参数
   传入 DLC `train_network(snapshot_path=...)`；worker 启动前完成 parent run/snapshot 的
   身份与文件校验。Restart 不传 snapshot。

## Consequences

- 跨轮 lineage（restart/resume、parent run、produced snapshot）随 train run 完整可追溯，
  满足 R5/R6；旧项目零迁移。
- Advisor 规则调整不涉及任何持久化迁移；建议与历史事实的边界清晰。
- DLC snapshot 是否携带 optimizer/scheduler 状态由 DLC 决定，产品语义统一称 Resume/fine-tune，
  不承诺完整训练状态恢复。
