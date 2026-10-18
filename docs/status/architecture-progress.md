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
| R03 重复间隔源联动与交叉预览 | **进行中** | 已授权自动准备源、拖线 / 改方向预览候选点，Measure仍显式。`codex/recurrence-linked`；worktree `/Users/leonis/.codex/worktrees/recurrence-linked/ai-physics-tracker`；实现 / 独立 / CI / 本轮HR待完成 | [计划](recurrence-linked-plan.md) / [ADR-0026](../decisions/0026-live-recurrence-preview.md) |
| R04 计算 / 记录装配与Session写入分离 | **待规划** | worker仍对detached Session调用compute入口；尚未提取，不混入Undo | [依据](../notes/architecture-followup-2026-10-18.md)；R03验收后再确认 |
| R05 全局JobSupervisor / WorldSnapshot | **后置，未实施** | 现有runner及各任务专属校验继续有效；没有通用hash替代科学条件 | [首次复核](../notes/architecture-review-assessment-2026-10-17.md) / [后续复核](../notes/architecture-followup-2026-10-18.md) |
| R06 Undo拆分 / 通用图表渲染器 | **后置，未实施** | Session拥有事务；ChartPlot / AnalysisPlot保留不同交互；不按文件大小重写 | 同上；不与R03 / R04捆绑 |

## 不要恢复的旧做法

1. 不再新增SG阶数表、参考恢复或来源解释；复用source_recipe。chart_recipe旧路径为兼容再导出，不是第二实现。
2. 不从pipeline_summary英文文案判断来源；ChartSeries已有reference_label / source_smoothed。
3. 可读旧缓存、允许新计算、允许自动覆盖是不同策略；不得合成一个valid布尔值或删除源 / 目标版本核对。
4. 预览与正式执行器按ADR-0023隔离；不得改回同一单线程队列。预览不发布正式结果。
5. 不恢复Review timing / Yes；合格Near-CFR按ADR-0024自动采用，保留来源与异常处理。
6. 不把“生命周期Normal-risk”“Undo / recipe无测试”“6.3.1未实施”等旧报告陈述当现状。

最后核对：2026-10-18，main产品基线0afe9f9。R03仍未完成，下一步以[current.md](current.md)为准。
