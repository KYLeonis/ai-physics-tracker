# R04分析主干职责重构 — Review Record

2026-10-18；基线main 2edf0b9，分支codex/analysis-workflow；产品583ce05 / 10f6887，最终修复bd848f1。[计划](../status/analysis-workflow-plan.md) / [ADR-0027](../decisions/0027-analysis-computation-and-publication.md)。High-risk：科学输入、结果构造、受控发布与后台交付。

## Scope

motion_computation构造线性 / 角运动候选；job只持有必要冻结输入；同步入口与后台共用prepare/run/validated/apply，Session保留唯一事务所有权。analysis_readiness为提示、按钮与源执行准备提供共同事实；工作流同轮复用执行事实，实际状态变化后仍重新采集。不改算法 / schema / 依赖 / Undo协议，不重写AI、解码和保存。

## Verification

- 数值 / 发布 / 源与分层：93 passed（3.01s）。
- R01–R03相关GUI：70 passed（51.63s）。
- 新无会话计算 / 同步后台等价 / 不完整批次原子拒绝 / 嵌套输入隔离 / 资格事实与界面一致性：12 passed（3.79s）。新增GUI测试初版把ActionSpec.action_id误写为action，之后提前在Qt调度刷新前断言按钮；纠正字段并等待实际刷新后通过，未为测试改变用户调度。
- 工作流 / 保存 / AI / 批量标注 / Undo：75 passed（16.83s）。
- 10f6887本机全量1310 passed（147.78s，Python3.12，无skip）。在R04 worktree运行：`PYTHONPATH=src QT_QPA_PLATFORM=offscreen /Users/leonis/Documents/ai-physics-tracker/.venv/bin/python -m pytest -q`。
- 首版10f6887的[双平台CI39119078812](https://github.com/KYLeonis/ai-physics-tracker/actions/runs/39119078812)全部success：macOS / Windows Python3.11各1308 passed / 2 skipped；skip是test_difficult_frames / test_dlc_predictions未安装pandas的既有可选测试。[PR #37](https://github.com/KYLeonis/ai-physics-tracker/pull/37)为diff容器。
- 最终bd848f1本机1316 passed（142.73s，1733 warnings，无skip）；同一命令全量。[最终双平台CI39119607020](https://github.com/KYLeonis/ai-physics-tracker/actions/runs/39119607020)全部success，macOS1314 passed / 2 skipped（184.50s），Windows1314 passed / 2 skipped（247.83s），既有可选skip不变。后续仅同步文档，源码 / 测试树保持bd848f1。

## Review Log

### R1 — A/B只读预审

独立Reviewer fit_source_final_review：Approve，无阻塞finding；定向88 passed（1.84s），diff检查 / compile / 兼容AnalysisInputs别名及无snapshot检查通过。数值、缺测 / 标定 / 单位 / 时序 / 配方保持；捕获必要嵌套输入而非整个Project；未知扩展在validated发布时合并；原子写入、输入 / 目标 / 配方核对与F1–F3保护保持。

### R2 — 完整diff复审

独立Reviewer只读审核2edf0b9..10f6887：A/B通过，C共享事实、缓存与发布保护正确；定向12 + 130 passed，diff检查 / compileall通过。发现下面F1，虽来自基线旧代码，仍属于本轮C验收范围，实施方决定Fix Before Close，不豁免。独立完整结论待修复复审收口。

## Findings / Verdict

### F1 — 自动补齐源仍触发显式反馈定位（Closed，修复 / 独立复审通过）

- Severity：Blocker（Reviewer P1体验问题）。chart_actions.ensureSignalSource启动时showFeedback发出feedbackRequested，MainWindow把工具页scrollbar置0。
- Decision：Fix Before Close；旧R01路径遗留，但R04 C明确要求自动刷新不抢页面位置，不能按历史问题豁免。
- 复现：清除当前轨迹的源，滚动到页面中部，再普通刷新自动补源。新增双工具×成功 / 取消 / 失败6个回归，在旧实现全部失败，实际0 != 250。
- Fix：源任务启动、取消、失败4处只更新jobLabel；显式Preview仍由request(immediate=True)单独发送定位信号，正式Fit / Measure反馈保持。检查候选源发布、原始观测不改和无正式分析结果。
- Fix commit：bd848f1。修复后facts / fit_source_updates / recurrence_preview / signal_analysis定向58 passed（45.27s）；独立增量确认Closed，最终本机1316及双平台CI39119607020通过。

### R3 — F1增量只读复审

Reviewer复核10f6887..bd848f1：**Approve，F1 Closed，完整R04通过独立复审**。独立58 passed（45.14s）及diff检查通过；自动源启动 / 取消 / 迟到取消 / 失败4条反馈只更新标签，显式Preview定位、正式Fit / Measure路径保留。结合R1 / R2全部结论，无未处置finding；Reviewer未改文件。

**独立复审Approve / 自动Gate完成，F1 Closed，无未处置finding。** 最终bd848f1全量与双平台通过；2026-10-18用户明确确认本轮5项HR“通过”，085219e以--no-ff集成main，R04已收口 / 已合并。

## Human Review

按[计划中的独立副本与5步操作](../status/analysis-workflow-plan.md#human-review自动gate全部通过后执行)交付用户；2026-10-18用户回复“通过”，本轮HR完成。副本可加载600观测 / 12记录且外部视频存在，原R03副本所有文件hash核对未变。

## Integration

085219e合并树与53c2886一致，源码 / 测试与bd848f1一致，保留此前完整验证，不重复无变化的本机全量。主分支集成CI39127491849另记回执；产品之后仅文档收尾。
