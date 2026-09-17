# ADR-0016 — 固定检查帧预选确认与推荐计划显式执行（Phase 5.7 交互政策）

## Status

Accepted（2026-09-17；用户在本轮 Phase 5.7 指令中批准 Astra 设计方向，含 C1/C2）。

## Context

Phase 5.7 交互重构（设计文档 `docs/design/phase-5.7-interaction-redesign.md`）把主交互
改为"三个工作区 + 状态驱动任务卡"。两个既有契约需要细化而非推翻：

- **C1**：ADR-0014 Decision 5 规定 fixed validation series 的成员由用户显式选择帧。
  普通用户不应被迫手工挑选成员，但系统自动冻结会越过"知情显式动作"的约定。
- **C2**：ADR-0015 规定 Advisor 的 Apply 只填表、绝不启动训练；5.5 规则合同的
  输出是建议枚举。任务卡的主动作需要"执行推荐方案"的显式入口，但不能冒称
  原 Apply 行为，也不能绕过任何校验。

## Decision

1. **C1 预选 + 确认（不自动冻结）**：
   - 首次学习前，系统按确定性规则预选检查帧：`n≥4` 时取
     `min(n−3, max(1, floor(0.2n)))` 个，在按帧号排序的 manual 帧上取等间隔内部
     位置（floor 平局取较早帧）。规则在 `application/workflow_projection.py
     ::preselect_fixed_check_frames` 实现（纯函数、可测）。
   - 预选集合必须经用户预览（`gui/fixed_check_dialog.py`）并点击"保留这些检查帧"
     后才调用既有 `create_validation_series` 冻结；用户可"自行挑选"（转既有
     ManageValidationDialog）或"暂不建立"（沿用无 fixed validation 的能力，不制造
     虚假基准）。`n≤3` 时不预选，推荐补标。
   - series 的创建/校验/删除守卫（ADR-0014 + P6R-03）不变；本 ADR 只把"成员怎么
     被提议"产品化，不改数据契约。
2. **C2 推荐计划显式执行（同一执行入口）**：
   - `application/workflow_projection.py::recommended_learning_plan` 把 Advisor 建议
     （或首轮默认 restart/50/8）转换为具体计划（mode/epochs/batch/resume 源）；
     resume 源由 `default_resume_source` 按 P6R-02 资格筛选。
   - 任务卡主动作（Start learning / Continue optimizing / Retry learning）把计划
     **写入既有表单控件**后调用既有 `train()` 路径——与 Advanced 手动启动走完全
     相同的 `prepare_tracking_request` 校验与执行管线，不新建执行通道。
   - **ADR-0015 的 Apply Suggestion 语义不变**（只填表、绝不启动），该入口保留在
     高级区。本 ADR 新增的是独立的显式执行入口，其按钮文案即执行动作本身。
3. **Generate trajectory 绑定策略**：生成轨迹主动作绑定本目标最新 completed
   train run 的模型（§12.1-2），不从历史列表静默换"最佳"；模型列表选择仍是
   Advanced 能力。

## Consequences

- 普通用户不选 run/snapshot/mode/series 即可完成学习与生成；全部技术对象仍可在
  高级区查看与覆盖。
- 预选规则是"保守初版默认"，不是准确性声明；界面与测试不得把"预选完成"表述为
  "训练充分"或"验证集最优"。
- 计划依据（basis）随卡片证据展示；执行参数仍完整写入 run（ADR-0015 契约）。
- 若未来要求"无确认自动冻结"或"跨任务自动流水线"，需另行 ADR，不得静默扩展。
