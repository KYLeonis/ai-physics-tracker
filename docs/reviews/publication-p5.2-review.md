# Publication P5.2 Independent Review

- 日期：2026-10-02；reviewer：gpt-6-luna/max；主实现方：root。
- 首轮范围：`9f5cff7..4238f8a`科学导出/可携带副本/native PNG/PDF/ProjectActions取消事务。
- 最终Verdict：R2 **Approve**，F1 Closed。最终用户/学生HR未发生。

## R1 — Request Changes

F1/P2：拟合CSV只导出主tip QC及四点数值，未导出冻结测量的逐角色missing reason；辅助QC位于重建诊断，不在fit rows中，造成空坐标缺原因。

Reviewer独立18项定向通过（13.58s），只读审查。完整JSON已保留missing reasons，所以是CSV完整性finding，不是原始payload损坏。

## 修复

- CSV补四角色`*_missing_reason`，直接取原冻结测量，不从当前会话补值。
- 拟合CSV补`auxiliary_qc_reasons`，复用相同冻结测量的typed reconstruction；不改不可变`result.json`、不改算法/拟合门槛。
- 实际fit结果回归检查缺body_bottom/pivot时CSV原因存在，来源/精度及payload roundtrip继续验证。

## R2

- 复审范围：`ac53a8b`的冻结逐角色missing reason与辅助QC修复。
- Reviewer确认四个`*_missing_reason`直接来自冻结测量；fit的`auxiliary_qc_reasons`由同一冻结测量重建，未改原始`result.json`。
- 独立实际fit回归 **1 passed**，覆盖frame20缺body_bottom/pivot及JSON未变；F1 Closed，无开放blocking finding。
