# R08 Signal History — Review Record

2026-10-20；基线 `5fff1fc`；首轮审核实现提交 `adce32c`，High-risk，范围与验收见[计划](../status/signal-history-plan.md)。上下文： [ADR-0021](../decisions/0021-function-fit-and-recurrence-result-contract.md)、[ADR-0022](../decisions/0022-guided-fit-preparation-and-attempt-journal.md)、[ADR-0023](../decisions/0023-preview-task-isolation.md)、[ADR-0027](../decisions/0027-analysis-computation-and-publication.md)、[R03 F1](recurrence-linked-review.md)、[R04 F1](analysis-workflow-review.md)。

## Scope

审核 `5fff1fc..adce32c` 的完整实现差异：SignalHistory集中保存结果 / 拟合尝试的只读查看、草稿恢复与后台重建；SignalPreview公开只读提交能力并继续拥有执行器；ChartActions、SignalAnalysisPanel和MainWindow接线；历史流程回归及近CFR测试mock调整。数值算法、项目格式与持久化契约未改变。

## Checklist

**正确性**

- [ ] 实现符合全部AC（F1仍未闭环）
- [x] 已检查边界输入、取消、关闭、上下文与保存busy路径
- [x] 未改动数值算法；既有只读重建测试仍在定向集合中

**质量**

- [x] 差异落在计划范围内
- [x] 跨平台路径规则无新增风险
- [x] 新公开的提交入口有说明，历史请求 / 执行器所有权清楚
- [x] 新增测试使用受控Future，并断言视图和工程状态

**流程**

- [x] 改动提交使用Conventional Commit
- [x] 未改变Accepted ADR或数据契约

## Findings

### F1 — 离开工具页切到Charts后，旧历史请求仍可交付

- **Severity**：Blocker
- **Evidence**：R1实现中的`MainWindow._analysisTabsChanged(index=0)`只切换purpose、更新用途UI并发出`analysisChanged`；它没有退出`SignalHistory`。`SignalHistory.poll()`核对工程、代际、视频和时序，但不核对当前分析标签页。受控复现：Fit完成后提交未完成的历史尝试读取，执行`window.analysisTabs.setCurrentIndex(0)`仍得到`history.active=True`、`history.pending=True`；完成Future并调用`history.poll()`后，隐藏工具页的图表出现两条历史曲线。手动切Charts和`openAnalysisPurpose('explore')`均走此出口。
- **Impact**：用户离开分析工具后，历史表单仍锁定；旧尝试的迟到曲线仍会写入隐藏工具页，返回工具页时呈现历史模式，违背计划中离开工具的共同退出和AC2。
- **Recommendation**：标签页切到Charts时调用既有`history.leave()`，复用同一取消 / 草稿恢复流程；为手动切换和Explore用途导航各补一条受控Future回归。
- **Decision**：Fix Before Close — 已修复并由R2复审确认。
- **Fix commit**：`703ac81`；`_analysisTabsChanged(index=0)`调用统一的`history.leave()`。
- **Verification**：R2定向命令`PYTHONPATH=src QT_QPA_PLATFORM=offscreen /Users/leonis/Documents/ai-physics-tracker/.venv/bin/python -m pytest -q tests/gui/test_signal_history_view.py tests/test_fit_attempt_view.py tests/gui/test_signal_analysis.py tests/gui/test_guided_fit.py tests/gui/test_recurrence_preview.py tests/gui/test_fit_source_updates.py tests/gui/test_analysis_read_only.py tests/test_layer_boundaries.py`：**117 passed**（72.03s）。新受控Future回归覆盖手动切Charts与Explore用途导航；差异`git diff --check 5fff1fc..703ac81`通过。
- **Re-review**：R2确认手动切Charts及`openAnalysisPurpose('explore')`均经`leave()`取消历史交付并恢复草稿；迟到Future不能改写返回后的显示、工程状态或尝试日志。完整复审同时确认历史取消 / 采用、reset / close、上下文与保存busy守卫、不可读记录处理、只读重建、原双执行器数量，以及SignalHistory不再访问`preview._executor`。未发现其他阻塞问题。
- **Status**：Closed

### F2 — 非整数JSON版本值可能被当作版本1采用

- **Severity**：Suggestion
- **Evidence**：R1中的`signal_history.py`版本守卫使用`metadata.get('version') != 1`（showSaved / adoptSaved）。Python中`True == 1`、`1.0 == 1`，因此损坏或未来格式若以这些值标版本，会通过守卫；“Use recorded setup”可将其采用后重新计算。ADR-0021 §3要求未知版本不可用于新计算。该相等比较来自基线既有读取逻辑，本轮迁移没有扩大接受范围；同类检查也存在于其他读取 / 解析层。
- **Impact**：格式版本类型错误或未知的记录可能被当前实现解释并采用。
- **Recommendation**：未来若收紧版本验证，应统一所有GUI / application / session读取处的类型与版本守卫，并用`true`、`1.0`覆盖；不要只在SignalHistory局部更改。
- **Decision**：Defer — 本轮迁移只移动既有守卫，不改变兼容边界；后续由统一版本验证增量处理。
- **Fix commit**：N/A
- **Verification**：静态检查Python相等语义；未新增运行测试。
- **Re-review**：N/A，本轮接受延后。
- **Status**：Closed (deferred)

## Review Log

### R1 — 2026-10-20 · 首轮

- 范围 / 基线：`5fff1fc..adce32c`；High-risk R08完整实现差异。
- 结论：Request changes；F1未关闭前不能Approve。两个入口的任务所有权、取消时序、关闭顺序、保存busy延迟、只读边界和受控Future测试均通过检查；发现切离工具标签页缺少共同退出。
- Findings变化：新增F1（Open）、F2（Deferred / Closed）。

### R2 — 2026-10-20 · F1修复后最终复审

- 范围 / 基线：复审完整差异`5fff1fc..703ac81`，包含实现`adce32c`及F1修复`703ac81`。
- 结论：Approve。F1修复使切到Charts与Explore导航共用历史退出流程；相关受控Future回归及完整定向测试通过。未发现其他需处置的finding。
- 验证：8个相关测试模块**117 passed**（72.03s）；`git diff --check 5fff1fc..703ac81`通过。本轮未运行全量pytest或替代真人Human Review。
- Findings变化：F1 Closed；F2保持Deferred / Closed。

## Final Verdict

- [ ] 通过（无未处置Blocker）
- [x] 修改后通过（findings按Decision处置完毕，复审确认）
- [ ] 需要修改

- 最终结论：Approve。F1修复已复审并关闭；F2按原决定Deferred。本结论不代表全量pytest、CI或Human Review已通过。
- 日期 / 依据轮次：2026-10-20 / R2


## 自动Gate回执（实施方补充，不替代Reviewer结论或HR）

最终产品703ac81；本机定向121 passed（75.65s）、全量1329 passed（166.45s）；[最终双平台CI](https://github.com/KYLeonis/ai-physics-tracker/actions/runs/39400901956) macOS / Windows Python3.11各1327 passed / 2个既有pandas可选skip，全部步骤success。R2完整独立Approve、F1 Closed，F2按Decision延期。Human Review待用户，分支尚未合并。
