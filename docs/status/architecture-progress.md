# 架构重构进度 — 接手入口

> 当前架构以[architecture.md](../architecture.md)顶部总览及代码为准；本表记录落地状态。GLM HTML与notes下的扫描 / 建议是历史输入，不是当前实现或自动授权。

## 状态与更新规则

- **已完成 / 已合并**：代码、必要验证 / 独立复审 / HR均完成，已进入main并push；填写集成commit及计划 / Review。
- **进行中**：已授权，尚有实现或Gate待做；注明worktree / 分支与缺少的Gate。代码实现不等于完成。
- **待规划 / 后置**：未实施；授权并形成对应计划后推进。
- 每次重构同步本表、对应mini-plan / Review及architecture.md受影响关系；current.md写唯一下一步，AGENTS保留入口。不要在代码中堆“已完成”注释。

## 落地清单

| ID / 目标 | 状态 | 当前事实 / 删除的旧做法 | 证据 |
| --- | --- | --- | --- |
| R01 公式拟合源自动补齐与预览联动 | **已完成 / 已合并** | 当前拟合页复用prepare_signal_source及既有job；不再要求缺源时切Charts；Fit仍显式 | [计划](fit-linked-source-plan.md) / [Review](../reviews/fit-linked-source-review.md)；aa86d79；全量1271 / 独立 / 双平台 / HR通过 |
| R02 计算配方统一解释 | **已完成 / 已合并** | source_recipe拥有共同事实与构造，chart_recipe保留图表策略。删除重复导数阶表、角参考恢复、图例摘要反解析、线性job时序覆写 | [计划](source-recipe-plan.md) / [Review](../reviews/source-recipe-review.md)；26af812；全量1276 / 独立134 / 双平台通过，无新增交互 |
| R03 重复间隔源联动与交叉预览 | **已完成 / 已合并** | 两个工具共用prepare_signal_source / SignalPreview；改线 / 方向 / 区间自动更新候选点，Measure仍显式。自动预览不滚回顶部，保留曲线及页面位置 | [计划](recurrence-linked-plan.md) / [Review](../reviews/recurrence-linked-review.md) / [PR #35](https://github.com/KYLeonis/ai-physics-tracker/pull/35) / [ADR-0026](../decisions/0026-live-recurrence-preview.md)；2600f2a；独立 / 双平台CI / 全部HR通过，F1 Closed |
| R04 分析主干职责重构（含计算 / 写入分离） | **已完成 / 已合并** | 583ce05计算退出Session，job删除snapshot，同步 / 后台同一核对发布；10f6887提示 / 按钮 / 执行共享源事实；bd848f1修复自动补源跳顶F1（Closed）。本机1316 / 独立Approve / 最终双平台CI / 本轮HR通过；2026-10-18用户确认“通过”，085219e集成main | [实施计划](analysis-workflow-plan.md) / [Review](../reviews/analysis-workflow-review.md) / [整体方案](architecture-next-round-plan.md) / [PR #37](https://github.com/KYLeonis/ai-physics-tracker/pull/37) |
| R05 全局JobSupervisor / WorldSnapshot | **后置，未实施** | 现有runner及各任务专属校验继续有效；没有通用hash替代科学条件 | [首次复核](../notes/architecture-review-assessment-2026-10-17.md) / [后续复核](../notes/architecture-followup-2026-10-18.md) |
| R06 Undo拆分 / 通用图表渲染器 | **后置，未实施** | Session拥有事务；ChartPlot / AnalysisPlot保留不同交互；不按文件大小重写 | 同上；不与R03 / R04捆绑 |
| R07 工程变更与界面更新链路 | **用户已搁置，未实施** | 用户认为使用上没有必要继续；不启动T01–T08，转为重新核对GLM剩余建议 | [保留原方案](change-notification-proposal.md) / [剩余项复核](../notes/glm-remaining-review-2026-10-18.md) |
| R08 历史查看流程归属 | **已完成 / 已合并** | SignalHistory拥有两个入口及Future / 轮询 / 取消 / 上下文；删除preview私有执行器借用，仍共两个执行器。703ac81修复切Charts / Explore未退出F1（Closed） | [计划](signal-history-plan.md) / [Review](../reviews/signal-history-review.md) / [PR #39](https://github.com/KYLeonis/ai-physics-tracker/pull/39)；f34d3b8；定向121 / 全量1329 / 独立R2 Approve / 双平台 / 本轮HR通过 |
| R09 草稿上下文集中 | **已完成 / 已合并** | analysis_draft_context（Qt-free）拥有草稿导航事实与源准备迟到判定；导航键 / 预览键共享成员 / _poll迟到核对退化为集中调用，求值顺序与旧or链逐位一致；_source_selection+_source_method合并为_source_stamp；分析簇枚举的跨模块私有穿越清零（panel 7个视图状态公开方法、closed / signalJobActive / prepareSignal / currentWorkflowState / applyAnalysisMethod） | [计划](draft-context-plan.md) / [Review](../reviews/draft-context-review.md) / [PR #41](https://github.com/KYLeonis/ai-physics-tracker/pull/41)；c14c78a；定向124 / 全量1337 / 两独立Agent Approve / 双平台通过，无新交互不设HR |

## 不要恢复的旧做法

1. 不再新增SG阶数表、参考恢复或来源解释；复用source_recipe。chart_recipe旧路径为兼容再导出，不是第二实现。
2. 不从pipeline_summary英文文案判断来源；ChartSeries已有reference_label / source_smoothed。
3. 可读旧缓存、允许新计算、允许自动覆盖是不同策略；不得合成一个valid布尔值或删除源 / 目标版本核对。
4. 预览与正式执行器按ADR-0023隔离；不得改回同一单线程队列。预览不发布正式结果。
5. 不恢复Review timing / Yes；合格Near-CFR按ADR-0024自动采用，保留来源与异常处理。
6. 自动预览只更新提示，不调用会触发滚动定位的showFeedback；显式操作才定位。页面scrollbar与图表view要分别验证。
7. 不把“生命周期Normal-risk”“Undo / recipe无测试”“6.3.1未实施”等旧报告陈述当现状。
8. R04已集成：计算已退出Session；不恢复job.snapshot或在worker临时会话写Undo。兼容compute_*协调prepare/run/apply，事务仍归Session。

9. R08已集成：历史生命周期归SignalHistory，不恢复ChartActions的`_historyFuture` / `_historyTimer`或历史直接借用`preview._executor`。
10. R09已集成：草稿导航事实与源准备迟到判定归analysis_draft_context；不恢复MainWindow / SignalPreview / ChartActions各自手写的键清单或`_source_selection` / `_source_method`散字段；迟到核对求值位次（selection在workspace之前）有钉子测试，调整前先核对旧or链。signal_history对panel的六个遗留私有访问（_loading等）待后续清理，不新增同类访问（tests/gui/test_analysis_private_access.py守卫枚举集）。

最后核对：2026-10-24，R01–R04 / R08 / R09已完成 / 已合并；R07继续搁置；R09（草稿上下文集中）c14c78a集成main；下一步以[current.md](current.md)为准。
