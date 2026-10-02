# Publication P5.2 Independent Review

- 日期：2026-10-02；reviewer：gpt-6-luna/max；主实现方：root。
- 首轮范围：`9f5cff7..4238f8a`科学导出/可携带副本/native PNG/PDF/ProjectActions取消事务。
- 最终Independent Verdict：R2 **Approve**，F1 Closed。最终用户/学生HR未完成；用户后续导出图像finding的局部修复与Self-review记录见下。

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

## 用户HR follow-up — fit figure columns（Normal-risk / Self-review）

- `2fca191`修复完整M0/M1模型ID与m0/m1列映射错误；原fit/CSV/JSON有值，PNG/PDF却读到None。`98bfd25`补纵轴标题/tick间距。范围仅曲线数据选择/版式，不改科学结果、schema或发布事务；root实施与Self-review，未冒称本补充有独立审查。
- 新回归旧代码两种模式失败；修复后最终6项导出定向通过（5.13s），覆盖两模型/单模型预测与残差、缺口及既有导出边界。实际P012各3243个残差，同一冻结结果重新输出，CSV/JSON字节一致、原文件及manifest未改。
- 最终两个PDF经Poppler渲染核查曲线恢复、文字不重叠；新导出位于ignored `P012_teacher_test/scientific-results-corrected`。用户图像HR待复测；[最终源码CI](https://github.com/KYLeonis/ai-physics-tracker/actions/runs/36991011627)执行中，Windows真机及学生pilot不算通过。
