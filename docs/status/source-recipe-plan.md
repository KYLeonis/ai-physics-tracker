# 计算设置统一解释 — 内部整理计划

- 2026-10-18；基线main `362ac85`；分支`codex/source-recipe`，worktree `/Users/leonis/.codex/worktrees/source-recipe/ai-physics-tracker`。
- 用户明确选择“先统一计算设置”，保持现有操作 / 结果；重复间隔联动随后另做。

## Goal / Scope

已知源信号配方的共同事实在一个Qt-free module中定义：SG参数 / 导数阶、参考编解码、步骤读取和时序来源。现有chart_recipe保留图表可读性 / 对比策略与文案；job / 源准备保留各自允许提交 / 自动替换的策略。图例接收明确源kind与参考标签，删除展示文字反解析。同步生成、后台校验、拟合恢复、GUI恢复实际复用共同定义，删除后台线性时序重复覆写。

不改数值算法、JSON格式、未知数据保留、有效性策略、目标版本栅栏、发布事务、Undo、预览隔离或工作区交互。不扩大到重复间隔自动准备、纯计算提取或全局任务统一。现有导入路径按需保留再导出，不建转发类 / 通用schema框架。

## Agent Context Pack

- `current.md`、`phase-6-plan.md`、`phase6-requirements.md`、`CODE_STANDARD.md`、`research/open-source-project-map.md` §3.3。
- ADR-0008 / 0009 / 0019 / 0020 / 0021 / 0023 / 0025：SG与记录、可读旧缓存、源与目标双版本、自动补齐、独立预览等现有契约。
- `fit-linked-source-review.md` F1–F3：控件归属 / 单条配方结构 / 组内一致性必须独立保留。
- `architecture-followup-2026-10-18.md`：重复事实与deletion test，不以行数为完成判据。

## Slices / Acceptance

- [x] S0：记录范围、现有语义和测试基线。
- [x] S1：单一事实定义；同步写入 / job校验 / 源准备 / 控件恢复复用，保留导入兼容。
- [x] S2：ChartSeries携带明确来源事实，图例不解析摘要；来源显示与旧实现一致。
- [ ] S3：既有行为回归、同步 / 后台数值与配方一致、旧 / 损坏 / 未知记录拒绝条件不放宽、未知扩展不丢、独立复审与双平台CI；通过后集成。

验收：SG导数对应表只一份；参考编解码只一份；去除手写SG配方与线性job时序覆盖；GUI不重建参考dict、不通过英文文案猜语义。旧入口的正常结果 / 错误策略、标定 / 时序 / 参考 / 组内冲突、取消 / 迟到 / 历史行为继续成立。UUID / 时间戳外的相同输入数值和配方保持一致。

## Review Gate

High-risk（科学配方解释 / 后台提交校验）。Independent Review只读审核完整diff及行为等价；定向后全量和macOS / Windows CI。此次不设计用户可感知的新行为，纯内部整理不新增HR关卡；若实现暴露需要改变交互 / 数据接受规则，先单列问题并按既有AGENTS §7处理，不悄悄纳入重构。验证通过后`--no-ff`集成main，同步文档 / push，再停止。

## Verification

基线定向99 passed（3.17s）；实现后142 passed（35.92s），新增同步 / 后台与图例回归所在文件30 passed（20.24s）。20个迁移函数 / 类型与基线AST完全一致；源算法与科学策略未改。完整测试 / 独立复审 / 双平台CI进行中。详见[review](../reviews/source-recipe-review.md)。
