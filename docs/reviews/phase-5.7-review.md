# Review Record — Phase 5.7 Interaction Flow Redesign

> 依据 `docs/templates/review.md`；一个 subphase 一个文件，贯穿审查生命周期。

- Subphase / Issue：Phase 5.7 — Interaction Flow Redesign（用户指令驱动，无 Issue）
- Review 范围（commits / 分支 / 文件）：`feat/p5.7-interaction-redesign`，
  `main..HEAD`（slice 1–5 提交）；核心新增 `application/workflow_projection.py`、
  `application/user_messages.py`、`gui/workflow_header.py`、`gui/fixed_check_dialog.py`、
  `tests/test_workflow_projection.py`、`tests/test_user_messages.py`、
  `tests/gui/test_workflow_ui.py`；重构 `gui/main_window.py`（工作区栈）、
  `gui/task_panel.py`（任务卡 + 折叠区）、`gui/chart_panel.py`（dock→widget）、
  `gui/tracking_actions.py`（投影驱动 + 卡片动作）、
  `gui/suggested_frame_review_actions.py`（文案）、`tests/gui/conftest.py`（模态根治）。
- Context（spec / ADR / plan 路径）：
  [phase-5.7 设计](../design/phase-5.7-interaction-redesign.md)（§5/§9–§13/§16）、
  [phase-5.7-plan](../status/phase-5.7-plan.md)、ADR-0013/0014/0015/0016、
  [stabilization review](pre-phase6-stabilization-review.md)（F1 记录）。
- 轮次：R1 2026-09-17（首轮）· R2 待定

## Checklist

**正确性**

- [ ] 状态/卡片/比较/预选/分析可用性语义与设计 §9–§12 一致；不持久化第二套状态
- [ ] C1：预选确定性 + 用户确认才 freeze；C2：与 Advanced 同一执行与校验入口；Apply 语义不变
- [ ] 候选/采用/分析三态分离；history 只 preview；采用与更新图表两步
- [ ] 失败文案三问；no-difficult-frames/未改善有边界结论

**质量**

- [ ] 无 Phase 6 功能/schema 变更/第二 runner/自动训练推理采用
- [ ] 既有控件与信号兼容；测试更新均为 IA 变更的合理结果
- [ ] GUI teardown 模态隐患（stabilization R1 F1）已根治且复现配方通过

**流程**

- [ ] Conventional Commits；ADR-0016 已记录 C1/C2
- [ ] 全量 pytest + compileall + 双平台 CI

## Findings

（R1 findings 由 Reviewer 产出后填入。）

## Review Log

- R1（2026-09-17）：dispatch fresh independent reviewer（只读），focus =
  设计关闭条件 + 是否引入 state/persistence/GUI 回归 + F1 根治有效性。
