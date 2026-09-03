# ADR-0014 — Result Activation and Fixed Validation History

## Status

Accepted（2026-09-03；随 Phase 5.4 规划批准落地）。

## Context

Phase 4 完成了 AI 训练、模型评价与推理全流程，但推理完成后会立即将结果写入当前 Track 的观测中（engine first-wins），缺乏结果版本管理。随着 Phase 5 引入代表帧、困难帧挖掘与人工纠偏迭代，用户在同一 Track 上可能产生多次推理（infer runs），必须能够对多个候选结果进行比对、选择性激活、替换或清空（Phase 4 Review F2 / Phase 5 R4）。

此外，模型的跨轮次迭代优化需要可靠的精度评价基准。目前训练默认按比例随机切分训练集与测试集，无法保证多轮训练在相同的测试集上进行横向比较，且易发生数据泄漏。因此需要支持用户冻结固定验证集（fixed validation series），并将其真实传导到 DeepLabCut 数据集切分中（`trainIndices/testIndices`）。

约束：
1. 不修改 `project.json` 顶层 schema version，不引入数据库或外部持久化框架。
2. 现有 TrackStore 与 ProjectSession 的观测模型需保持不变：`project.observations` 仅承载当前处于 Active 状态的结果投影。
3. 任何切换或清除 AI 观测的操作绝不能丢失人工标注点（manual points），也不能删除或破坏旧 TrackingRun 产物。

## Decision

1. **推迟观测写入（Candidate 模式）**：
   新推理任务完成时，仅持久化 completed TrackingRun、原始预测文件及经阈值过滤的观测中间件（`data/engines/<run_id>/observations.json`）与统计快照（`prediction_summary_v1`）。当前 Track 的观测、active run 指针、DerivedData 保持不变，UI 显示 `Completed · Not active`。

2. **版本化状态扩展契约**：
   在 `Track.extra_fields["refinement_state_v1"]` 中保存：
   - `active_infer_run_id`: `UUID | None`，记录当前轨迹激活的推理运行 ID。
   - `activation_history`: 激活历史列表，记录每次操作（activate / replace / clear）、from/to run、点数统计及时间戳。
   - `active_validation_series_id`: `UUID | None`，当前激活的固定验证集 ID。
   - `validation_series`: 映射字典 `series_id -> ValidationSeries`，保存不可变标签快照（`point_id`, `frame_index`, `pixel_x`, `pixel_y`, `modified_at`）。

3. **训练迭代解释层契约**：
   在 `train TrackingRun.extra_fields["refinement_iteration_v1"]` 中保存：
   - `iteration_index`: 迭代轮次序号。
   - `previous_training_run_id` / `source_infer_run_id`: 上游运行关联。
   - `validation_series_id`: 所采用的验证集 ID。
   - `training_labels`: 训练集标签快照列表。
   - `review_summary`: 启动训练时的审核进度快照。

4. **原子激活事务（Activate / Replace / Clear）**：
   - **Activate**：用于无活动 AI 结果的 Track，校验产物文件后载入 AI 观测。
   - **Replace**：用于已有 AI 结果的 Track，清除旧 AI 观测后载入新 run 的 AI 观测。
   - **Clear**：清除当前 Track 全部非 manual 观测，重置 `active_infer_run_id` 为 None。
   - **规则**：全部操作严格保留所有 manual 点；若 AI 点与 manual 点同帧，AI 点以 `superseded` 状态保留，确保后续删除 manual 点时可恢复；事务同步更新 DerivedData stale 状态与激活历史；支持完整 Undo/Redo。

5. **固定验证集（Fixed Validation Series）与训练防泄漏**：
   - 用户从当前 active manual points 显式选择若干帧冻结为验证集，生成不可变的标签快照。
   - 若用户后续修改或删除了对应 manual 点，当前验证集失效（不可用于新一轮训练），用户需创建新 series；旧 series 历史评价保持不变。
   - 训练请求准备时，若存在 active validation series，将 manual points 划分为 training labels 与 validation labels，向底层引擎（如 DLC）显式传递互斥的 `trainIndices` 和 `testIndices`，杜绝验证数据进入训练集。

6. **旧项目向下兼容**：
   - 旧项目若无 `refinement_state_v1`，单一来源的 AI 观测只读推断为 legacy active；多来源或不确定来源标记为 Legacy mixed。
   - 允许用户对 legacy 状态执行 Replace 或 Clear，平滑过渡到新体系。

## Consequences

- 实现了推理结果与活动轨迹投影的清晰解耦，支持用户灵活试验与对比不同模型结果（F2 闭环）。
- 固定验证集提供了跨迭代轮次横向对比的坚实科学基准，且通过底层 `trainIndices/testIndices` 杜绝了数据泄漏。
- 架构上完全遵循 schema v1 的 tolerant `extra_fields` 契约，零顶层数据迁移负担。
- Undo/Redo 与 ProjectSession 事务天然继承，保持了数据操作的可逆性与安全性。
