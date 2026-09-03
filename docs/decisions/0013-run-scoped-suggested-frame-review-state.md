# ADR-0013 — Run-scoped Suggested Frame Review State

## Status

Accepted（2026-09-03；用户确认 Phase 5.3 mini-plan、持久化约定与删除语义）。

## Context

Phase 5.2 已能从一个 completed infer run 生成困难帧候选，但结果文件只是后台任务交换产物，
不能单独承担 Phase 5.3 的项目事实：用户需要保存并重开审核队列，Accept/Skip 只应抑制同一
infer run，Correct 还必须保留低于导入阈值或缺测 prediction 的来源信息。

现有 `project.json` schema v1 已允许 `TrackingRun.extra_fields` tolerant read / faithful
write-back。候选方案包括新增 Project 顶层集合、另建审核 sidecar，或把审核状态绑定到对应
infer run。前两种方案分别带来 schema/迁移成本或多文件一致性问题；run-scoped 状态与 R2.8
“同 run 抑制、新 run 可重新评估”的语义直接一致。

另一个约束是现有 ProjectSession Undo/Redo 只覆盖观测、标定和派生数据，不覆盖
`TrackingRun`。若 Correct 分两次写入 manual point 与 disposition，或只撤销其中之一，会产生
“点已撤销但仍显示 corrected”的不一致；若所有普通历史快照都包含全部 TrackingRun，又可能
错误回滚无关的后台训练/推理状态。

## Decision

1. 在对应 completed infer run 的 `TrackingRun.extra_fields` 中保存版本化对象
   `suggested_frame_review_v1`；不新增 Project 顶层字段，不提升 `schema_version`，不迁移旧项目。
2. 对象包含：
   - `active_batch`：当前 mining request id、参数快照和候选列表；候选保留 frame index、
     finite scores/components、reasons，以及 prediction 或 `null`。
   - `reviewed_frames`：以十进制 frame index 字符串为 key，记录 `accepted | corrected |
     skipped`、审核时间、来源 request、当时 prediction，以及 Correct 对应的 manual point id。
3. 未出现在 `reviewed_frames` 的候选即 pending；进入 Correct 模式但尚未在画面点击不写项目。
   新 mining 可替换 `active_batch`，但保留同 run 的 `reviewed_frames`。Accept/Skip 作为同 run
   excluded frames；Correct 生成的 active manual point继续由既有 manual 排除规则处理。
4. Correct 复用 manual last-wins：原 AI observation 若已导入则保留为 superseded；若 prediction
   低于导入阈值或缺测，则由审核记录中的 prediction 快照保留 provenance，缺测写 `null`，不写 NaN。
5. ProjectSession 为审核操作使用 scoped history snapshot：Accept/Skip/Correct 及删除 Correct
   点时，同时快照相关 review state 与既有数据状态。普通标注、标定和后台 TrackingRun 更新不
   因此纳入全部 run 历史。
6. “删除当前帧人工点”只作用于当前 Track/帧的 active manual point，沿用
   `TrackStore.delete_manual_point`：硬删除该 manual 点并恢复被它直接遮蔽的 AI observation。
   若它由 Correct 创建，对应候选恢复为 pending。删除可在下一次保存前 Undo；保存会清空应用内
   Undo/Redo，之后只能在仍存在且尚未被下一次保存轮换时由用户手工利用项目 backup 恢复。
7. 不允许逐点删除 AI observation。AI result 的 clear/activate/replace 仍属于 Phase 5.4。

## Consequences

- 审核进度与 prediction provenance 跟随 infer run 保存，旧项目缺少该 key 时自然表现为空队列；
  schema v1 和现有序列化器继续使用，无迁移与新依赖。
- 同一 run 的 Accept/Skip 不会反复出现，新 infer run 仍可重新评估；Correct 的 manual 数据不依赖
  当前 batch 是否后来被替换。
- 审核事务的 Undo/Redo 能保持 point、disposition、派生 stale 状态与 marker 一致，同时避免
  普通撤销回滚后台任务历史；代价是 ProjectSession 历史快照需要区分普通与审核事务。
- `extra_fields` 中该 namespaced key 从此是稳定格式契约；实现必须严格校验类型、枚举、有限数值、
  run/track/frame 身份，并在写回时保留未知 sibling keys。
- manual 删除在保存后不能通过应用内 Undo 恢复，GUI 必须在操作处明确提示该边界。
