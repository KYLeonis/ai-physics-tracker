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

- [x] 状态/卡片/比较/预选/分析可用性语义与设计 §9–§12 一致；不持久化第二套状态（R1 A 项核对通过）
- [x] C1：预选确定性 + 用户确认才 freeze；C2：与 Advanced 同一执行与校验入口；Apply 语义不变（R1 B 项；F2 失效分支已修）
- [x] 候选/采用/分析三态分离；history 只 preview；采用与更新图表两步（R1 C 项；F1 检查绑定已修）
- [x] 失败文案三问；no-difficult-frames/未改善有边界结论（R1 D 项；F6 接线补齐）

**质量**

- [x] 无 Phase 6 功能/schema 变更/第二 runner/自动训练推理采用
- [x] 既有控件与信号兼容；测试更新均为 IA 变更的合理结果
- [x] GUI teardown 模态隐患（stabilization R1 F1）已根治且复现配方通过（27/55/117 passed）

**流程**

- [x] Conventional Commits；ADR-0016 已记录 C1/C2
- [ ] 全量 pytest + compileall + 双平台 CI（本地 788 passed + compileall OK；CI 待合并后）

## Findings

### F1 — “Check this trajectory” 绑定最旧 completed infer run（Blocker）

- **Evidence**：`tracking_actions.py` inspect 分支无 reversed/候选筛选，probe 复现
  active v1 + 候选 v2 时 requestMining 收到 v1。
- **Decision**：Fix Now ——改为投影 `trajectory_facts().candidate.run_id`，
  无候选时回退最新 completed infer。
- **Verification**：`test_inspect_binds_candidate_not_oldest_run`；全量 788。
- **Status**：Closed

### F2 — 固定检查集失效时无重建路径，Start learning 死循环（Blocker）

- **Evidence**：`needs_check_set` 含失效但对话框条件只覆盖"无 series"；失效校验
  只在 worker 侧，重试每轮真实消耗一次训练启动。
- **Decision**：Fix Now ——投影新增 `fixed_check_invalid` 状态与
  `confirm_check_frames` 主动作卡（设计 §10 失效行）；确认逻辑提取为
  `_confirm_fixed_check_set`（无集/失效都走；KEEP 先停用旧集再 freeze，P6R-03
  保留旧集溯源）；`_learning_evidence` 对 <4 标签不再承诺确认框。
- **Verification**：`test_invalid_fixed_check_set_drives_rebuild_card`、
  `test_invalid_series_rebuild_flow_via_card`（含旧集停用不删除断言）；全量 788。
- **Status**：Closed

### F3 — candidate_comparison 不防非有限指标（Suggestion）

- **Decision**：Fix Now ——`isfinite` 双值守卫，非有限/基准≤0 → incomparable
  并展示原值。
- **Verification**：`test_candidate_comparison_non_finite_metrics_are_incomparable`。
- **Status**：Closed

### F4 — 采用路径双重模态确认（Suggestion）

- **Decision**：Fix Now ——卡片采用单次影响确认后直接调用 session
  activate/replace 原子事务（失败走 activation_failure 文案）；history 入口
  的旧确认保留。
- **Verification**：`test_adopt_card_replaces_after_confirmation_and_history_only_previews`
  适配后通过；全量 788。
- **Status**：Closed

### F5 — 分析限制计算后无界面显示（Suggestion）

- **Decision**：Fix Now ——WorkflowHeader 新增 limitations 行，由
  `_refresh_header` 接 `state.analysis.limitations`（§11.1 并列限制数量/范围）。
- **Verification**：`test_analysis_source_bar_and_chip_reflect_projection` 扩展路径；
  全量 788。
- **Status**：Closed

### F6 — 三条 §13 文案未接线（Suggestion）

- **Decision**：Fix Now ——evaluation unavailable 时完成路径显示
  `evaluation_unavailable()`；重开中断 run 的恢复卡换 `interrupted_on_reopen()`
  文案；激活/替换/清除失败对话框改 `activation_failure().full_text()`。
- **Verification**：全量 788（文案结构由 test_user_messages 覆盖）。
- **Status**：Closed

### F7 — 小项（Suggestion）

- a 死代码 `_advisor_recommendation` 重复定义：删除旧定义。
- b 取消期间卡片不切 stopping：`cancel()` 失效 `_context_key`。
- c `_execution_input` 直接访问 frameSelectionActions：getattr 防护。
- d 多候选只投影最新：文档注记为最小实现边界（高级区可达全部 run）。
- e `_finish_cancelled` 死参数：移除。
- **Decision**：Fix Now（全部）；**Status**：Closed


## Review Log

- R1（2026-09-17）：dispatch fresh independent reviewer（只读），focus =
  设计关闭条件 + 是否引入 state/persistence/GUI 回归 + F1 根治有效性。
