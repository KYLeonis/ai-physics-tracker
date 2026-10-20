# R08 历史查看流程归属 — 方案与待办

- 日期：2026-10-20；基线：main `3eb6efb`。
- 状态：**目标、两个入口及三条验收已由用户确认；整份实施方案待最终确认，尚未实施。**
- 用户原话：“是，两个入口一起整理，按以上三条验收”。这是讨论中的范围确认，不记作实现完成或开工授权。
- 风险：High-risk（迁移后台查看任务的取消、迟到交付及关闭职责；不更改拟合算法）。
- 实施分支 / worktree：尚未创建；启动后按项目规则使用 `codex/` 工作分支，先核对实际基线。

## 对使用有什么影响

现有按钮和操作保持一致。把“暂存当前编辑 → 只读查看记录 → 返回或采用记录设置”作为一段完整流程管理，以后修改历史功能时，草稿恢复、取消和画面更新能一起维护。

没有证据表明目前出现了新的用户故障；本轮收益是减少后续修改遗漏，不承诺提高计算精度或速度。

## Goal / Scope

两个入口共同纳入：

1. `Latest applied result` / `Last saved result`：现有拟合与重复间隔结果。
2. 拟合尝试选择：成功、失败、取消等既有尝试记录；有资格时按原规则只读重建曲线。

共同出口包含返回草稿、显式采用记录设置、连续选择其他记录、离开分析工具、切换视频 / 工程以及关闭窗口。各出口保持现有产品含义；切换工程仍遵循原工程切换规则，不把旧工程草稿带入新工程。

本轮不增加跨重启草稿恢复、历史结果库、后台任务框架或新依赖；不更改工程 / 日志格式、Undo、科学算法、训练流程或已搁置的R07。

## 三条用户验收（已确认，完成后才勾选）

- [ ] **AC1 草稿原样恢复**：进入历史查看后返回，之前的公式、参数及相关编辑状态恢复，包括未写完的公式、非数字参数文本；连续看多条记录不能覆盖最初保留的草稿。
- [ ] **AC2 迟到结果不覆盖当前画面**：选择另一记录或返回当前编辑后，较晚完成的旧历史计算不能替换当前曲线 / 说明；切换视频、工程、工作区及关闭时同样失效。
- [ ] **AC3 查看与计算明确分开**：历史查看不调用正式拟合、不发布结果、不改工程dirty / Undo或尝试记录；显式采用记录设置后仅成为可编辑设置，仍需点击Fit / Measure才产生正式结果。

## 当前证据与目标归属

当前相关实现位于 `src/ai_physics_tracker/`：

| 位置 | 当前职责 / 证据 | 本轮处理方向 |
| --- | --- | --- |
| `gui/signal_history.py` | `capture` / `_load` / `view` / `leave` / `lock`保护草稿、投影历史设置、返回或采用设置 | 加深既有SignalHistory module，让它完整拥有历史查看流程；原始文本保留方式不被数值解析替代 |
| `gui/chart_actions.py` | `_viewAttempt` / `_pollHistory` / `_cancelHistory`及`_history*`状态管理异步历史重建；直接使用`preview._executor` | 历史选择 / 取消 / 核对 / 交付随流程迁出；ChartActions保留正式分析、源准备和日志写入协调 |
| `gui/signal_analysis_panel.py` | `displaySaved` / `restoreSaved`及历史按钮接线，与历史查看共同控制显示 | 保留面板显示能力；两个入口经同一历史查看归属进入 / 退出，不复制第二套草稿保护 |
| `gui/main_window.py` | 工作区 / 用途切换参与历史退出与预览失效 | 使用明确的历史退出入口，覆盖切离、换上下文和关闭；窗口不自行拼接历史内部清理 |
| `gui/signal_preview.py` | 依ADR-0023拥有独立只读执行器，现被历史查看借用 | 保留资源所有权及正式计算隔离，消除历史代码对其私有字段的访问 |
| `application/fit_attempt_view.py` | 严格匹配源，重建只读历史曲线 | 沿用其科学核对和只读语义；不与正式求解 / 发布合并 |

### 执行资源与退出顺序

沿用现有“正式计算一个执行器、只读计算一个执行器”的资源数量。历史查看与草稿预览继续共用现有只读资源；在既有GUI组合处明确提供提交能力，历史查看不持有SignalPreview或读取它的私有字段。只读执行器仍由SignalPreview创建和关闭，符合ADR-0023；不为本轮额外增加线程池或通用调度module。

SignalHistory拥有自己请求的Future、轮询、当前记录身份、上下文核对和取消 / 失效状态。返回或切换先使旧请求失效，再恢复 / 进入下一份显示；关闭先清理历史请求和轮询，再关闭共享只读资源。不能假定`Future.cancel()`能强制终止已运行的数值调用，旧计算即使完成也不得触碰Qt或当前画面。

上面确定职责与资源约束，不预先固定新的类型层级或大量方法。若实现发现必须改变ADR-0023的资源所有权或并发契约，先记录具体理由并补充决策，不能直接改Accepted ADR正文或悄悄扩展本轮范围。

### 改完应退出的旧路径

- 历史查看直接调用`preview._executor`。
- ChartActions持有历史任务的Future / 定时器 / 上下文并自行交付曲线。
- 两个查看入口各自拼接进入、恢复和取消步骤。
- 测试为了控制历史迟到结果而替换`actions.preview._executor`；改为控制历史查看明确获得的执行能力，保留行为断言。

这是提高locality与leverage：复杂流程集中在既有module内，两个入口共用；不是增加一个shallow转发module。

## Agent Context Pack

- 接手入口：`AGENTS.md` → [当前架构](../architecture.md#当前架构总览接手先读) → [架构进度](architecture-progress.md) → [当前状态](current.md)；写代码前读`CODE_STANDARD.md`。
- Phase约束：[phase6-requirements](../spec/phase6-requirements.md)、[phase-6-plan](phase-6-plan.md)；6.4 / 6.5不属于本轮。
- [ADR-0021](../decisions/0021-function-fit-and-recurrence-result-contract.md)：来源 / 目标版本及只读旧记录；不得弱化科学核对。
- [ADR-0022](../decisions/0022-guided-fit-preparation-and-attempt-journal.md)：尝试日志独立，不能因查看改写日志 / 工程。
- [ADR-0023](../decisions/0023-preview-task-isolation.md)：预览与正式任务隔离、取消语义、GUI线程交付。
- [ADR-0027](../decisions/0027-analysis-computation-and-publication.md)：科学计算 / 核对 / Session原子发布各自归属，历史查看不新增发布路径。
- 历史finding：[R03 F1](../reviews/recurrence-linked-review.md)、[R04 F1](../reviews/analysis-workflow-review.md)。自动交付不抢页面位置，显式点击与自动提示分开；页面滚动和图表范围分别核对。
- 现有证据：`tests/gui/test_signal_history_view.py`、`tests/test_fit_attempt_view.py`、`tests/gui/test_guided_fit.py`、`tests/gui/test_recurrence_preview.py`。已有草稿、迟到、时序撤销和只读测试，不把本轮描述成填补整块无测试代码。
- 已接受事项：原生数值调用不能强行中止；源变化时允许历史曲线不可重建，须保留原因和返回草稿能力；未记录过的旧尝试不补造。

### 必须检查的迁移风险

当前`SignalHistory.view`发出`historyChanged`，而`ChartActions._historyChanged`会取消历史Future。迁移后须先使旧读取失效、再发布状态、最后启动当前读取，避免通用状态回调误取消刚启动的请求。历史与预览继续共享只读单线程队列，可能等待已经运行的旧只读计算；这保持现有排队特性，不承诺强行中断或降低等待时长。

## 待办 / Slices

- [x] P0 讨论与事实核对：用户确认目标、两个入口和三条验收；形成方案。此勾选只表示规划工作已做，不表示方案已获最终启动确认。
- [ ] S0 最终确认后启动：记录授权、核对工作区 / 基线，建立工作分支；列齐当前全部历史进入 / 退出 / 关闭调用及测试控制点。
- [ ] S1 完整迁移：在SignalHistory收拢两个入口的流程、后台请求和交付；同步面板 / ChartActions / MainWindow接线与共享资源关闭顺序，移除上述旧路径。
- [ ] S2 行为验证：迁移现有回归，按实际缺口补充迟到 / 切换 / 关闭与只读测试；验证采用重复间隔设置后仍仅预览、正式Measure需显式触发。
- [ ] S3 自动Gate与独立复审：相关测试 → 本机全量 → macOS / Windows CI；独立只读review完整diff，finding由实施方修复闭环。
- [ ] S4 真人验收与收尾：用户验证两类入口的三条验收；通过后更新架构 / 进度 / Review等，标明实现完成、HR通过和已合并，按`--no-ff`集成 / push后停止。

## Verification / Review Gate

**High-risk，Independent Review适用**：重点审查异步历史任务所有权、共享资源shutdown、上下文 / 记录身份核对、只读不发布、取消与草稿完整恢复。PR建议作为完整diff与CI容器，不另设形式审批。

优先运行已有相关测试：

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/gui/test_signal_history_view.py tests/test_fit_attempt_view.py tests/gui/test_signal_analysis.py tests/gui/test_guided_fit.py tests/gui/test_recurrence_preview.py tests/gui/test_fit_source_updates.py tests/gui/test_analysis_read_only.py tests/test_layer_boundaries.py
```

采用可控Future验证迟到，不用sleep碰运气。至少覆盖：切换历史记录、返回草稿、采用设置、离开分析、工程 / 视频改变、时序撤销、关闭；历史失败 / 源不可匹配仍可返回草稿；Project / dirty / Undo / 尝试记录在查看前后不变。复用现有场景，不为迁移的每一行新增同构测试。

定向通过后本机全量`.venv/bin/python -m pytest`及双平台CI；已有检查通过后仅因新改动、失败或尚未解决疑点追加验证。

**Human Review适用**：本轮迁移GUI事件接线与反馈交付，需确认用户原有操作没有退步。自动Gate通过后提供最短启动命令和独立试用工程，正式发起以下≤4步验收并停止等待；不能用截图或computer-use代替。

1. 输入另一份公式 / 参数，包含一项未完成内容；分别查看已应用 / 已保存结果与拟合尝试，再返回：之前编辑原样恢复。
2. 连续切换几条历史记录，再返回或离开分析页后回来：当前显示稳定，不被旧记录换掉；实际迟到竞争由自动化可控Future验证。
3. 查看旧拟合，点击Use recorded setup：设置变为可编辑，尚未新增正式结果；点击Fit后才重新计算。
4. 对重复间隔执行查看 / 返回 / 采用设置：参考值恢复对应状态，候选预览与正式测量区分，点击Measure才发布；自动更新保持页面位置。

## Result / Handoff

仅规划：三条用户验收已确认，整份方案等待最终确认与启动。源码 / 测试未改，未运行产品测试；本轮仅检查文档差异和本地链接。没有新ADR或已落地架构变更，R01–R04完成状态保持。
