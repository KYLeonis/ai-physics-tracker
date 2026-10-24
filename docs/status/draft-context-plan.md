# R09 草稿上下文集中 — 方案与待办

- 日期 / 状态：2026-10-24 · **用户已授权：mini-plan 形成后直接执行（含建 Issue、完整 Gate）。**
- 用户原话（grilling Q1–Q8 闭合后）："写好mini-plan后你直接执行，记得拉issue，走好我们的流程"。Q1–Q8 决策已冻结，见下方 Goal / Scope / AC / Gate。
- 规划基线：`main @ 94d15ab`（src/tests 自 703ac81 未变，仅文档前进；6.4 mini-plan v1.0 已冻结待开工，本轮先于 6.4 执行）。
- Issue：[#40](https://github.com/KYLeonis/ai-physics-tracker/issues/40)；实现分支：`refactor/draft-context`。
- 风险等级：**Normal-risk**（GUI 内部整理，无数据 / 契约 / 算法变化，`docs/workflow.md` §10.2）；因迁移迟到交付守卫代码位置，用户加码 Review：实现完成后由两个独立只读 Agent 分别排查（Q6）。

## 对使用有什么影响

**无用户可感知变化。** 现有按钮、操作、数值、守卫语义完全不变；任何可感知差异都按 bug 处理，不算优化。本轮收益是后续维护：6.4 参数 SE 与未来分析工具落在同一面板时，「旧数据冒充当前」的失效判定只维护一处，跨模块私有穿越清零。

## Goal

把分析工具页散落的「当前草稿」瞬时事实与「交付还作不作数」判定收进一个 application 层 Qt-free module（`analysis_draft_context`），三份手写清单退化为对它的调用；分析簇的跨模块私有读写清零（GLOSSARY 已增补「草稿上下文（Draft Context）」词条）。

## Agent Context Pack

### Authoritative Docs

- [当前架构总览](../architecture.md#当前架构总览接手先读)：SignalPreview 独立执行器、SignalHistory 历史生命周期、ChartActions 正式执行的既有归属，本轮不改变。
- [ADR-0023](../decisions/0023-preview-task-isolation.md)：预览与正式任务隔离；本轮不合并执行器、不改取消语义。
- [ADR-0027](../decisions/0027-analysis-computation-and-publication.md)：计算与发布分离；本轮不动任何发布路径。
- [6.4 mini-plan v1.0](phase-6.4-plan.md)（已冻结）：参数 SE 的 GUI 改动面（signal_analysis_panel / fit_explanation / 尝试日志 / 历史兼容）与本轮目标簇重合，是本轮的直接受益方。
- `CODE_STANDARD.md`：写码前通读；分层边界由 `tests/test_layer_boundaries.py` 强制。

### Relevant Historical Findings

- [R03 F1](../reviews/recurrence-linked-review.md)、[R08 F1](../reviews/signal-history-review.md)：迟到交付 / 上下文失效是本链历史 bug 家族；本轮迁移的正是这些守卫的代码位置，语义必须逐条等价。
- [6.2 Review F4 / F5 / F7](../reviews/phase-6.2-review.md)：输入变化取消、晚到结果拒绝——判定等价性的对照语义。

### Scientific / Data / Product Invariants

- 预览不发布结果、不写工程 / dirty / Undo；历史查看只读（ADR-0022 / 0023）。
- 三份清单的**键成员与比较语义不变**：导航键、预览输入键、迟到核对各自覆盖的事实集合不得扩大或缩小；仅采集与比较的位置集中。
- `analysisNavigationKey` 在部件缺失 / 状态非法时的降级取值（`None` 等）保持一致，避免 TrackingActions 刷新行为漂移。

### Known Deferred / Accepted Items / Non-goals

- 不动 SignalHistory 流程所有权（R08 成果仅被读取）。
- 不动 `refreshAnalysisSourceBar` 文案逻辑（仅修 `trackingActions._current_workflow_state` 一处私有读，Q8）。
- 不清分析簇之外的私有穿越（`batch_annotation_actions` / `model_actions` / `project_actions` 对 `window._annotation_session` 等）——属候选 D / A 领域，后续另行立项。
- 不建通知框架、不做 R07；不改数据格式 / 依赖 / Undo。

## Scope

**做**：

1. 新增 `application/analysis_draft_context.py`（Qt-free）：冻结 dataclass 承载工具上下文事实（workspace / analysis tab / method / purpose / track / quantity / source 选择 / history 激活 / source reason），及「交付时刻事实是否仍等于启动时刻」的集中判定；纯函数、可直接 pytest。
2. GUI 侧薄 adapter 从控件采集事实（采集失败时按原降级语义产生 fallback 事实）。
3. 三处消费迁移：`MainWindow.analysisNavigationKey`（8 元组）、`SignalPreview.syncContext` 键的共享事实部分、`ChartActions._poll` 迟到核对中的上下文条件（代际号与 job 重组比对留在原处——那是任务身份，不是草稿上下文）。
4. 分析簇跨模块私有穿越清零：panel 视图状态（`_valueRange` / `_previewRange` / `_eventPreview` / `_allowCachedEvents` / `_viewingDiskSaved`）、`ChartActions._closed` / `_signal_job` / `_prepareSignal`、`TrackingActions._current_workflow_state`、`signal_history.py:329` 对 panel 范围的直接写——各归 owner 提供最小公开访问 / 方法；模块内部自读自写保留（Q3）。

**不做**：见 Non-goals。

## Acceptance Criteria

- [ ] AC-1 行为不变：本机全量与双平台 CI 通过；定向覆盖导航刷新、预览失效、迟到拒绝、历史进出路径；无任何用户可感知差异。
- [x] AC-2 三份手写清单退化为集中判定调用：`analysisNavigationKey` 返回值由 facts 构成；`syncContext` 键 = facts + 预览输入身份；`_poll` 上下文条件走集中判定；各自的键成员与原实现逐项等价（实现中以对照表核验）。
- [x] AC-3 分析簇跨模块私有穿越清零：新增源扫描回归（参照 `test_layer_boundaries.py` 精神）禁止 `signal_preview` / `signal_history` / `chart_actions` / `main_window` 对分析簇列名对象的 `_` 属性访问；`trackingActions._current_workflow_state` 改公开属性。
- [x] AC-4 判定逻辑直接单测：facts 相等 / 不等、fallback 事实、交付时刻判定的各分支有 Qt-free pytest 覆盖。

## Slices

- [x] S0 基线与分支：建 Issue / 分支；全量测试确认绿色起点（1329）。
- [x] S1 module + 单测：`analysis_draft_context` 事实与判定 + Qt-free 测试。
- [x] S2 三处消费迁移：导航键 → 预览键共享部分 → `_poll` 迟到条件；逐项对照键成员等价（独立Agent A逐项确认）。
- [x] S3 私有穿越清零 + 源扫描回归；`_current_workflow_state` 公开化；另纳入 `chart_actions` 对 `window._analysisMethodChanged` 的私有调用（`applyAnalysisMethod`）。
- [x] S4 自动 Gate：定向 124 / 本机全量 1337 passed；两个独立只读 Agent 均 Approve with comments，2 项 Minor 已修复闭环（`ad00f9c`），[Review Record](../reviews/draft-context-review.md)。
- [ ] S5 集成收尾：PR 触发双平台 CI → `--no-ff` 合并 → 文档同步（architecture / progress / current / 本计划 Result）→ 关 Issue → push。

## Verification

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_analysis_draft_context.py tests/gui/test_signal_analysis.py tests/gui/test_guided_fit.py tests/gui/test_recurrence_preview.py tests/gui/test_fit_source_updates.py tests/gui/test_signal_history_view.py tests/gui/test_analysis_read_only.py tests/test_layer_boundaries.py
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest   # 全量
```

迟到竞争用可控 Future 验证（沿 R08 手法），不 sleep 碰运气。

## Review Gate

- **Independent Review**：Normal-risk 不强制；按用户 Q6 指示执行**两个独立只读 Agent（轻量模型）分别排查**，重点：三份清单键成员等价、迟到 / 取消守卫语义等价、fallback 语义、公开访问器最小性。findings 由实现方处置、必要者复审；汇总记录 `docs/reviews/draft-context-review.md`。
- **PR**：作为完整 diff 与双平台 CI 容器（`refactor/**` 分支不触发 push CI，须经 PR）。
- **Human Review**：不适用——无用户可感知交互变化；实现中如出现行为差异按 bug 修复，不作为新交互验收。

## Result（收尾时填写）

- 待填。
