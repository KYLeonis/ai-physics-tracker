# GLM原报告剩余项复核（R04之后，讨论记录）

- 2026-10-18，基线main `0ef606e`；产品代码只读核对，未实施新重构。
- 用户在grill-me讨论中表示：使用上没有必要继续R07，要求回到GLM原报告找更值得优化的点。R07搁置，不能继续按其T01–T08开工。
- 重新读取原始`architecture-review-20261016-160921.html`及后续`architecture-review-20261018-132406.html`，对照当前源码、R01–R04和既有测试。
- 两条独立只读事实核查：`remaining_glm_tasks`负责① / ④，`remaining_glm_history`负责② / ⑤；均未修改文件或运行测试。本记录为讨论证据，不是新Review Gate通过或实施授权。

## 结论

原报告中收益最明确的配方统一、无会话写入计算、结构化来源、执行事实同轮复用和预览隔离，已经完成。剩余项没有发现值得立即启动的大重构或已证实的新用户故障；不因GLM当时的Strong排序自动开工。

若用户仍希望从GLM剩余项做一次内部整理，理由最具体的是**撤销 / 保存历史快照的显式命名**，范围应限定在现有记录结构和所有读取方，保持规则与事务所有权；不直接抽出UndoTransaction。这主要改善维护可靠性，操作体验 / 数值不变，收益也不足以声称一定高于新功能。

## 五项重新对账

| GLM原建议 | 当前事实 | 本次判断 |
| --- | --- | --- |
| ①统一后台生命周期 | task_runner已集中spawn / IPC / 取消 / 强制回收；预览与正式计算已隔离；保存、模型导入、自检、时序仍有不同交付条件 | 不建全局JobSupervisor，不合并专属guard。选帧 / 困难帧挖掘的两份进度外壳仅有局部共用候选，无已证实体验收益 |
| ②拆Session中的计算与Undo | 计算已由R04提取；Undo仍在Session，七字段历史快照有类型注解，但数字位置被多个用途读取 | 命名快照是窄的维护候选；当前无证据支撑整套事务抽取 |
| ③pipeline唯一解释点 | R02的source_recipe及R04构造 / 发布复用已落地 | 已完成，不重做，不再另建全项目schema体系 |
| ④执行状态 / 全局快照 | R04在refresh同轮采集一次ExecutionInput，供缓存键与投影共用；恢复真实审核状态后重采集有必要 | 具体重复已处理；没有发现剩余互锁冲突证据，不建立WorldSnapshot |
| ⑤统一绘图及移出GUI数学 | 来源文字反解析已删除；正式拟合残差已在计算层。剩余重复主要是背景 / 轴 / 网格样式，初始预览还有一次残差减法 | 两种图表交互有意不同，通用Renderer收益不足；单独移动减法不值得作为下一轮整体优化 |

## 撤销 / 保存候选的具体依据与限制

`application/project_session.py`中的 `_SessionDataSnapshot`（约125行）有七个字段及 `_SNAPSHOT_DATA_FIELDS=6`；`accept_saved_snapshot`（约497行）比较前六项，`_is_analysis_only_history`（约889行）读取`[0]..[6]`，undo / redo（约926 / 940行）读取`[5]`，`_history_transition`（约980行）再按顺序解包。

这些用法当前已有类型和回归保护。维护成本来自增加或调整字段时必须同步多个数字位置；不能据此宣称当前存在撤销错误或数据丢失。

若选择此方向，最小完整范围为：

1. 用有名称的私有快照类型明确轨迹、点、标定、源结果、审核范围和运行记录。
2. 同步迁移捕获、恢复、Analysis专用判断及保存期间数据比较，删除旧下标 / 切片约定；避免只替换定义、不迁移消费者。
3. 保持Session拥有历史栈与事务，保持50步上限、拒绝时不动栈、后台run进展不回滚、scoped review、Save清历史 / autosave保留历史、Analysis栈顶限制。
4. 复用既有Undo / 保存 / 审核 / 分析测试，按Undo高风险安排独立复审；有实际体验变化才按项目规则重新HR。未冻结mini-plan前不实施。

现有回归包括`tests/test_project_session.py`、`tests/test_undo_run_integrity.py`、`tests/test_signal_analysis_job.py`中的结果Undo。报告中“Undo无测试”不沿用。

## 其他剩余项的证据

- `infrastructure/task_runner.py:49–153`已有进程协议和强制回收；`gui/tracking_actions.py:1451–1539`与`gui/suggested_frame_review_actions.py:332–389`保留各自进度与结果读取。没有证明两者可连同上下文规则一起合并。
- `gui/tracking_actions.py:146 / 224`复用同一执行事实，338–339的重采集发生在审核状态确实改变之后。model / frame selection / review等入口互锁差异有语义理由。
- `gui/chart_panel.py:81–160`负责真实帧游标 / 样本导航 / 相空间；`gui/analysis_plot.py:37`之后负责页面滚动 / 缩放 / 参考线。
- `gui/signal_preview.py:196–197`的初始预览仍做测量值减预测值；正式残差由domain计算、application保存，不能说整个拟合计算仍在GUI。

## 当前讨论边界

R07讨论路径已搁置；下一步与用户确认是否接受上述小范围内部可靠性整理，或结束纯架构重构转向可见的新功能。没有冻结R06实现范围，没有自动启动6.4 / 6.5。本文没有新的全量、性能或真人验收证据；沿用已验收产品不变的事实。
