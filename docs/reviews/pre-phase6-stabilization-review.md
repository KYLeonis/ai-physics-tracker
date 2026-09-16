# Review Record — Pre-Phase 6 Stabilization（P6R-01/02/04/03）

> 依据 `docs/templates/review.md`。本 record 记录 stabilization 的独立审查生命周期；
> 原始 Findings 见 [pre-phase6-project-review.md](pre-phase6-project-review.md)（不改写）。

- Subphase / Issue：Pre-Phase 6 Stabilization（无 Issue，用户指令驱动）
- Review 范围（commits / 分支 / 文件）：`fix/pre-phase6-stabilization`，`main..HEAD`
  （7c160b0 / c384cd8 / 1c3769d）；核心改动
  `application/project_session.py`、`application/tracking_job.py`、
  `application/refinement_history.py`、`application/training_advisor.py`、
  `application/advisor_collection.py`、`gui/tracking_actions.py`、`gui/main_window.py`、
  `domain/project.py` 及新增/更新测试。
- Context（spec / ADR / plan 路径）：
  [pre-phase6-project-review.md](pre-phase6-project-review.md)（关闭条件）、
  [pre-phase6-stabilization-plan.md](../status/pre-phase6-stabilization-plan.md)（设计决策）、
  ADR-0013/0014/0015、`docs/workflow.md` §6。
- 轮次：R1 2026-09-16（首轮，fresh reviewer，Verdict PASS + F1–F3）·
  R2 2026-09-16（复审，fresh reviewer，Verdict **CLOSED**）

## Checklist

**正确性**

- [x] P6R-01 关闭条件逐项满足（原子拒绝五不变量、恢复引用一致、无关 run 不回滚、save/reopen、GUI 路径）
- [x] P6R-02 关闭条件逐项满足（clean/直接 parent/祖先/换 series/legacy unknown/restart/比较资格/旧数字不篡改）
- [x] P6R-04 事实口径修复且组合测试真实走 production collector
- [x] P6R-03 守卫语义正确（被引用拒绝删除、停用保留、未引用可删）

**质量**

- [x] diff 无范围外改动；无 schema migration / 新持久化状态
- [x] 遵守可移植性规则；命名与既有代码一致
- [x] 新增测试覆盖失败路径而非只覆盖 happy path

**流程**

- [x] 提交信息符合 Conventional Commits
- [x] 无需新 ADR（既有 ADR-0013/0014/0015 语义内收窄，未改变数据契约形态）

## Findings

### F1 — 特定 pytest 文件排序下 GUI teardown 模态挂起（既有测试基建隐患）

- **Severity**：Suggestion（非本 stabilization 引入）
- **Evidence**：Reviewer 指定验证命令（应用层文件排在 GUI 文件前）2/2 挂起，卡点
  `tests/gui/test_training_advisor_actions.py` 第 5 测试 teardown，栈停在
  `project_actions.py:329` 的 `QMessageBox.question("Unsaved changes…")`。
  主会话复现并二分：最小组合 `tests/gui/test_undo_rejection_ui.py +
  tests/test_validation_lineage.py + tests/gui/test_training_advisor_actions.py`
  挂起；**用 main 上既有文件同模式** `tests/gui/test_annotation_ui.py +
  tests/test_project_session.py + tests/gui/test_training_advisor_actions.py`
  **在 main worktree 上同样挂起**——与 stabilization 提交无关。仓库自然收集序
  与 CI 的全量 `python -m pytest` 从不触发（本分支全量 733 passed；reviewer
  亦验证 main 等价排序通过）。
- **Impact**：仅影响人为指定文件顺序的局部运行；CI/全量不受影响；无产品状态损坏。
- **Recommendation**：GUI 测试 teardown 的 dirty 模态处理需要系统性修复
  （如 conftest 对窗口关闭路径统一 `close_allowed` 或模态自动应答加固）。
- **Decision**：Defer ——既有隐患且不在本轮授权范围（"有限 stabilization"）；
  目标：Phase 5.7 交互重构的测试刷新时一并处理，届时 GUI conftest 会被触碰。
- **Fix commit**：N/A
- **Verification**：复现配方已记录（上述三文件组合，60s 超时可稳定复现）。
- **Re-review**：R2 确认 Defer 记录充分。
- **Status**：Closed（Defer）

### F2 — `accept_saved_snapshot` 将 run registry 计入 changed，产生空撤销步

- **Severity**：Suggestion（P6R-01 快照扩为 7 元组时引入的行为回退）
- **Evidence**：保存窗口期间仅后台 `update_tracking_run`（pending→running）→
  `accept_saved_snapshot` 后 `can_undo=True`（main 为 False）；该步 undo 因
  "存续 track 保留当前 registry"规则无可回滚内容，表现为无效撤销步。
- **Impact**：UX 噪音；无状态损坏。
- **Recommendation**：changed 判定排除 registry。
- **Decision**：Fix Now ——本 stabilization 引入的回退，应随本轮关闭。
- **Fix commit**：见 stabilization 分支第 4 个提交（`_SNAPSHOT_DATA_FIELDS` 切片比较）。
- **Verification**：`tests/test_undo_run_integrity.py::
  test_run_only_progression_during_save_keeps_no_ghost_undo_step`（run-only →
  无撤销步；真实编辑 → 保留一步且 undo 有效）；全量 733 passed。
- **Re-review**：R2 确认。
- **Status**：Closed

### F3 — `advisor_collection.py` 风格偏差与 `_history_transition` 不可达分支措辞

- **Severity**：Suggestion
- **Evidence**：裸 `tuple` 参数类型；`logger` 定义未使用；`_evaluation_rmse`
  继承的超长行；拒绝消息中 redo 分支不可达（raise 仅 undo 方向）。
- **Impact**：纯风格/死代码。
- **Recommendation**：顺手修。
- **Decision**：Fix Now。
- **Fix commit**：同第 4 个提交（类型标注 `tuple[TrackingRun, ...]`；review
  summary 降级处补 debug 日志消除静默吞错；长行拆分；消息改为单向措辞并注释
  说明 redo 不可达的原因）。
- **Verification**：targeted 11 passed；全量 733 passed；compileall 通过。
- **Re-review**：R2 确认。
- **Status**：Closed

## R1 Verdict（Reviewer 原文结论）

**PASS** ——P6R-01/02/04/03 关闭条件经代码审查、既有与新测试、/tmp probe 三重
验证成立（A–E 逐项核对均为"满足"，详见 R1 报告；主会话已将全文要点并入本
record 的关闭条件核对，原文要点：无"先改状态后校验"路径；redo 方向拒绝不可达
论断成立；contaminated/unknown 不可能产生 delta；采集器只读、无历史 RMSE 写入；
无 Windows 路径/编码风险）。附带 F1–F3 如上处置。

----

## Review Log

- R1（2026-09-16）：dispatched fresh-context independent reviewer（只读），focus =
  四项 closing conditions + 是否引入新的 state/persistence regression。
  Verdict **PASS**；findings F1（Defer，既有测试基建隐患）/ F2 / F3（Fix Now）。
- Findings 处置（主会话，提交 `405b91b`）：F2 修复（`_SNAPSHOT_DATA_FIELDS`
  切片比较 + 双向回归测试）；F3 修复（类型标注/debug 日志/长行/消息措辞）；
  F1 经 main worktree 复现确认为既有隐患后 Defer 并记录配方。
- R2（2026-09-16）：fresh re-reviewer 只验证 findings 处置与第 4 个提交的
  diff。逐项结论：F2 修复语义精确（切片恰好排除 registry、双向测试真实、
  既有 workflow/session/activation 55 passed 无回归）；F3 无行为变化；F1
  Defer 有据（`git diff main..HEAD` 对挂起点三文件为空、复现配方独立抽查成立）；
  第 4 个提交无新问题。实测 batch 53/55 passed、全量 **733 passed**、
  compileall OK。
- **Final Verdict：CLOSED**（2026-09-16，R2）。

## 附：处置提交索引

| Finding | 提交 |
| --- | --- |
| P6R-01 | `7c160b0` |
| P6R-02 | `c384cd8` |
| P6R-04 + P6R-03 | `1c3769d` |
| R1 F2/F3 修复、F1 Defer 记录 | `405b91b` |
