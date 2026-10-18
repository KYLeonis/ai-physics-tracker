# 重复间隔源联动与候选交叉点 — Review Record

2026-10-18；main基线0afe9f9，开发分支`codex/recurrence-linked`，实现0888297。High-risk，Scope / Context / Gate见[计划](../status/recurrence-linked-plan.md)、[ADR-0026](../decisions/0026-live-recurrence-preview.md)。

## Scope

复用SignalPreview独立执行器与源准备，纯预览在application，候选事件不发布记录。正式Measure / 科学算法 / 格式 / 事务不变。保留R01 F1–F3设置归属、未知 / 损坏组及内部冲突拒绝。

## Verification

- 首批GUI兼容与新增预览70项：69 passed；唯一失败为新测试错误地禁止换工具后启动新工具的预览，断言已纠正，旧工具迟到源仍要求不发布。
- 最终定向源 / 新预览 / signal job / recurrence：59 passed（31.81s，277 warnings）。覆盖自动补齐且不碰其他轨迹、空正式槽 / 无尝试日志、参考线 / 方向 / 抑噪与显式Measure一致、保curve / view、不改Undo、raw / 区间 / 量更新、历史 / 换页 / 换方法 / 换轨迹迟到拒绝、Measure不等待预览、已知缺测段 / 非零绝对时间、取消和未知源。
- 0888297产品全量1289 passed（220.19s，1661 warnings）；f5c727a仅补充测试，无源码改动，两文件31 passed（36.65s，301 warnings），追加角量 / 支点 / 单位联动、历史 / 保存 / 失败、工程代际、保存busy延后显示。
- Independent Reviewer `fit_source_final_review`只读审核f7fe7a2..0888297源码及f5c727a测试，**Approve，无新增finding**。独立定向50 passed，先前兼容51 passed；diff检查、compileall、模块导入通过。确认候选事件不发布、生命周期 / 保存busy / 曲线保持、F1–F3与Fit兼容。
- 最终[CI39103525201](https://github.com/KYLeonis/ai-physics-tracker/actions/runs/39103525201)，f5c727a的macOS / Windows Python3.11均success（各1293 passed / 2 skipped）；产品初版0888297的[CI39103232233](https://github.com/KYLeonis/ai-physics-tracker/actions/runs/39103232233)也均success。CI两个skip为未安装pandas的既有可选测试（test_difficult_frames / test_dlc_predictions），本机全量没有skip。

## Findings / Result

独立完整复审已Approve，无待处置finding；最终双平台CI通过，自动Gate完成。首次Human Review除拖线跳顶外，其余项目已由用户确认通过；4bd723a修复跳顶，定向81 / 独立17通过，最新双平台CI通过，用户随后回复“通过”，本项HR完成且F1 Closed；全部Gate通过，2600f2a已集成main。PR [#35](https://github.com/KYLeonis/ai-physics-tracker/pull/35)为diff与CI容器。

## Human Review

[计划中的启动命令与5条操作 → 预期](../status/recurrence-linked-plan.md#human-review自动gate通过后执行)；提供独立工程副本，不替代原工程。用户2026-10-18反馈“其他通过”，仅拖线松手后页面跳到顶部未通过。

### F1 — 自动交叉预览把页面滚回顶部（Closed：修复 / 自动Gate / 真人复测通过）

- 用户两张截图显示外层工具页滚动位置重置，曲线本身范围未改；旧回归只检查plot view，未检查页面scrollbar。
- 根因：SignalPreview.renderRecurrence调用showFeedback，feedbackRequested由MainWindow接到外层scrollbar.setValue(0)。
- 4bd723a仅把被动预览提示改为jobLabel.setText，与Fit预览一致；显式查看预览 / Measure仍保留原定位。没有新增保存 / 算法 / 任务生命周期改动。
- 新增reference（含松手信号）/ direction / separation三种页面滚动回归；旧代码全部复现失败（0 != 250），修复后相关GUI回归81 passed（80.61s，593 warnings）。独立Reviewer增量Approve，定向17 passed，确认显式Preview / Measure定位仍保留；diff检查 / compileall通过。4bd723a的最新[CI39105765356](https://github.com/KYLeonis/ai-physics-tracker/actions/runs/39105765356) macOS / Windows Python3.11均success；既有可选pandas测试的2个skip不变。
- 本轮仅要求拖线稳定性复测；其余已通过项不重开。原试用工程副本保留用户操作 / 保存状态，不重新复制覆盖。

2026-10-18用户明确回复“通过”，拖线稳定性复测完成；此前“其他通过”覆盖其余HR项目。F1 Closed，无未关闭finding；2600f2a集成main，合并树与b2823b9一致，源码 / 测试与4bd723a一致。收尾只同步文档，不再修改产品。

集成收尾ddb5bd3的[主分支CI39107041901](https://github.com/KYLeonis/ai-physics-tracker/actions/runs/39107041901) macOS / Windows Python3.11均success；之后仅补文档回执，不再改动源码 / 测试。
