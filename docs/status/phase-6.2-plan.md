# Subphase Plan — Phase 6.2 Angular Charts and Phase Space

- 日期：2026-10-13；状态：**计划已形成，尚未开始实现**。
- Issue：实现启动时创建；计划分支：`feat/p6.2-angular-charts`。
- 基线：`feat/p6.1-angular-analysis` 完整复审与修复；具体最终提交 / CI 见 [current.md](current.md)。
- 风险：High-risk（标量 / 相空间科学适配、双输入参考、异步提交与缓存状态）；GUI 必须 Human Review。

## Goal

在现有 Analysis 工作区配置角运动参考，计算和查看 θ(t)、ω(t)、α(t)、θ–ω 与 x–vx 相空间；
同视频多轨迹可比较同量，曲线点保持源帧身份，能定位只读视频；旧线性图表继续可用。

这是通用方程平台的测量输入与可视化能力（ADR-0017），不在本阶段增加动力学方程、
论文 M0/M1、周期提取、拟合或表达式执行器。

## Entry / Integration

1. 6.1 已完成（代码 `4842560` / 全量929 / 独立 Approve / 双平台CI）；实现入口 READY：角量定义 / SG / 标量持久化、多输入失效、时序授权、结果版本与配方核对，
   独立复审及双平台 CI；[最终证据](../reviews/phase-6.1-review.md)。原 R2 的 zone-only 失效已在本轮修复，不留给 6.2 再选择口径。
2. 可以进入 6.2 实现准备；实际实现需下一条启动指令。本轮只建立计划。
3. 集成次序仍为 Issue #24 三项增量 HR 通过 → 增量合 main → 6.1 合 main → 6.2 开发周期集成。
   若前置 HR 尚未结束，可在明确记录基线的工作分支上叠加开发；不得先越过前置 HR 合 main。

## Agent Context Pack

### Authoritative Docs

- [phase6-requirements](../spec/phase6-requirements.md) R1/R2/R4/R5、AC-3/7；[Phase master](phase-6-plan.md)。
- [6.1 mini-plan](phase-6.1-plan.md) / [review](../reviews/phase-6.1-review.md)：本轮新增审查与修复。
- ADR-0017：用户方程；ADR-0019：四种 rad 系单列 kind、参考定义、每轨迹整组替换；
  ADR-0020：分析批次的目标结果身份、配方与时序边界。
- ADR-0008：分段 SG / 短段 / 物理 dt；ADR-0009：图表快照与主线程提交；ADR-0010：当前图表 PNG。
- `CODE_STANDARD.md`；`docs/research/open-source-project-map.md` §3.3/3.11/3.12，借鉴行为不复制论文实现。
- [后续回移档案](main-backport-backlog.md)：本阶段吸收角量 / 相图 / 可见参数；周期、拟合及完整历史结果契约仍留后续。

### Relevant Findings / Existing Adaptation Points

- 6.1 R2：working_zone 改变会改变 SG 边界与 unwrap 起点；现已统一使相关派生 stale，不改变 raw time。
- 6.1 新审查：旧批次不能覆盖后来计算的参数 / 参考结果；配方、双轨迹引用、实际输入集合须一致。
- `chart_data._prepare_derived_rows` 只接受两列，`_source_kind` / ChartKind 只有线性五图。
- `ChartPlot` 当前以 `kind == "xy"` 区分相空间和时间导航；新的相空间绝不能把位置 / 角度误当秒。
- `analysis_facts` 当前任意 valid derived 即 latest；angular-only 不能让线性图表显示已就绪。
- 旧 R7 的真实重开测试：先等待 autosave 结束，再等 session 身份变化；不使用固定 sleep 判定完成。

### Invariants

- Analysis 视频保持只读；参考配置不新增标注、不改标定、不改变 AI 激活。
- 单摆固定支点是像素参数；两点 A→B 的参考轨迹是完整依赖，必须同视频且不能自引用。
- 内部 / 持久化始终 rad、rad/s、rad/s²；degree 只在显示层转换，相空间两轴分别使用正确单位。
- 时间轴使用绝对源帧时间；相空间使用两序列同帧有效交集，断线按源帧间隙，拒绝跨缺测补值。
- 相空间组合的输入 / 参考定义、标定和 SG 配方必须一致；不按数组行号 zip 两个稀疏结果。
- stale 缓存可以明示只读展示，但不得伪装最新；混合 valid/stale 的相图整体标为 stale。
- 重算只替换目标分析族，保留另一族 / 未选轨迹 / 未知扩展字段；取消、参数变更、换工程或晚到结果不提交。

### Deferred / Non-goals

无新依赖、schema 迁移、四角色约束、跨视频比较、跨缺测插值、任意两列图表编辑器。
不新增 working_zone 编辑 UI、跨段整周恢复、周期 / 拟合 / 不确定度推断、完整版本历史和批量导出。
Windows/CUDA 真机仍按原批准延期；已有 PNG 入口继续适用，不扩大 Phase 8 范围。

## Scope / Minimal UX

1. 复用 `ChartPanel` 的独立 Track 勾选，不改变 Acquire 的标注目标选择。
2. 角运动参考配置提供两种已有定义：固定支点 `pixel_x/y`，或同视频参考轨迹 B。
   支点须由用户明确确认；允许有限的画外坐标，不静默使用标定原点。
   多目标批次共用当前参考；目标包含参考 B 时明确拒绝，不静默删掉一个目标。
   不新增 Analysis 视频取点模式；像素坐标数值录入足以交付本阶段。
3. 显示 / 恢复已计算结果的参考与 SG 参数，未应用设置和已计算配方明确区分。
   参数修改时取消本 GUI 拥有的任务；结果版本栅栏仍由应用层兜底。
4. 增加三张角量时间图、θ–ω、x–vx。θ 原始 wrapped / 平滑 unwrapped 可区分；
   θ–ω 默认使用同配方平滑 unwrapped θ 和 ω，图例明确量及参考。
   原始 wrapped θ 跨 ±π 不画虚假的跨界斜线；不对数据做额外 unwrap 或写回。
5. 时间图沿用请求 / 呈现双游标；相空间隐藏时间直线，按屏幕距离选真实样本的源帧，
   重合点采用确定顺序并披露定位轨迹。呈现帧改变时只高亮该帧真实存在的点，不吸附造点。
6. 同量多轨迹比较限同视频、同角度定义与同世界坐标 / 单位；每条图例显示实际支点或 A→B。
   不把单摆零方向与两点 +x 零方向混在一张“同量”图中；不在本阶段计算差值或误差区间。
7. 对线性 / 角运动分别判断缺失、stale、latest；按钮按当前分析族和时序授权提供重算。
   显示当前 / 缓存的 fps、区间、SG 参数、参考及近似时序来源；短段无导数要给明确原因。
   缓存与当前时序不一致时明确拒绝科学配对 / 比较，不猜测旧文件未记录的来源。

## Implementation Surface

| 层 | 复用 / 修改 |
| --- | --- |
| application | `chart_data.py`：显式单列 / 两列 kind 映射和共同校验，新增相空间按帧交集；按分析族修复 `analysis_facts`，保持默认线性调用兼容 |
| GUI | `chart_actions.py` / `chart_panel.py`：扩展现有 action、参数和 plot 分类；任务复用现有 executor / cancel / context 机制 |
| calculation | 复用 `angular_job` / `kinematics_job`、ADR-0020；不再增加第二套计算 / 提交管线 |
| persistence | 参考和计算配方仍在 DerivedData；显示选项用已有 view state，旧项目缺省可打开 |
| tests | scalar / phase-space 纯数据、帧导航 offscreen、任务 / 设置变化、旧图表与 round-trip 回归 |

## Acceptance Criteria

- [ ] AC-1：两种参考明确配置；无标定 / 未授权时序 / 自引用 / 跨视频拒绝，失败不改变 raw、AI 激活或既有结果。
- [ ] AC-2：四种角运动单列数据可消费；rad / degree 转换数值正确，模型仍存 rad；旧 x/y/v/a/xy 图不退化。
- [ ] AC-3：θ–ω / x–vx 按源帧交集建立，稀疏错位、不同配方 / 参考、缺测、wrapped 跨界均有可复现数据测试。
- [ ] AC-4：时间图与相空间点击定位准确源帧；请求 / 呈现不混淆，多轨迹重合点确定；Analysis 视频始终只读。
- [ ] AC-5：同量比较、图例参考 / 单位、短段 / 无数据 / stale / 近似时序提示可用；angular-only 不误标线性 latest。
- [ ] AC-6：改参数 / 参考 / track / project / 区间后不接受旧任务；只替换目标族、原子 Undo/Redo、保存重开和旧项目兼容。
- [ ] AC-7：定向 / 全量 / macOS+Windows CI、Independent Review 及新 Human Review 通过后集成。

## Slices / Verify

1. S1：冻结时间图 / 相空间 source kind、单列宽度、单位、配方一致性与缓存族分类；纯数据适配测试。
2. S2：参考 / 显示配置与复用 angular 后台任务；先测错误、取消、版本 / 参数栅栏和旧线性流程。
3. S3：新图表、多轨迹及源帧导航；offscreen 验证期望样本、游标 / 只读和明显空数据提示。
4. S4：旧线性五图、保存重开 / Undo、项目切换、定向与全量；独立审查 / 修复 / 新会话复审；双平台 CI。
5. S5：给出 `.venv/bin/python -m ai_physics_tracker`、逐条操作→预期、封闭问题，停止等 Human Review；通过后 `--no-ff` / 文档 / push / 收尾。

数值数据优先用已知源帧与解析角信号：源帧从非零开始、缺口、两轨迹不一致的稀疏采样、
不同参考与单位。不得只测试一条完整零起点数组。验证命令：
`QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest`；不新增 UI 自动截图代替真人验收。

## Review Gate

- Independent：必须，全新只读审查科学配对 / 参考 / 单位、输入与结果版本、存储和生命周期；记录 `docs/reviews/phase-6.2-review.md`。
- PR：可选完整 diff 容器。
- Human：必须，新配置、多图与帧导航为新交互，前一轮 HR 不覆盖；具体体验问题在可运行增量完成后提交。

## Result

本轮只交付计划；6.2 产品代码尚未实现。实施前读取本计划、6.1 最终审查记录及 current 的确切基线。
