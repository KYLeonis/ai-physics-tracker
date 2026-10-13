# Phase 6 Plan — Advanced Physics Analysis

> 2026-10-11：本文件为旧规划草案，**不得直接启动实施**。用户已确认由用户给出方程、平台通用计算；见[ADR-0017](../decisions/0017-user-defined-equation-analysis-platform.md)。固定拟合模型仅可作为示例，下一轮规划须重新对齐输入 / 求解 / 拟合范围。

- 日期 / 状态：2026-10-11 · **规划草案，待用户确认；未开始产品实现**
- 需求入口：[phase6-requirements.md](../spec/phase6-requirements.md)
- 基线：`main @ b997100`，Phase 5 完成、Entry Gate READY，Windows 取消维护修复已集成。

## 1. 顺序与交付

| Subphase | 目标 / 验收 | 依赖与 Review Gate |
| --- | --- | --- |
| 6.1 — Angular Analysis Foundation | 固定支点/两点方向定义、θ/ω/α 纯计算与 Session 快照事务；解析测试、依赖失效、保存重开。对应 AC-1/2 及 AC-7 的角运动部分 | 首先执行；High-risk，Independent Review；无 GUI 增量，不触发 Human Review |
| 6.2 — Angular Charts & Phase Space | 角度配置、三种时间曲线、θ–ω 与 x–vx 相图，源帧导航；AC-3 的角运动部分 | 6.1；科学适配/参考配置需 Independent Review，交互需 Human Review |
| 6.3 — Period & Fitting | 段内周期、线性/二次/阻尼正弦拟合、参数/残差/失败说明及 GUI 入口；AC-4、AC-6 的拟合部分、AC-7 的拟合部分 | 6.2；High-risk，Independent Review + Human Review；先冻结真实周期参考，不等拟合结果出来再选 |
| 6.4 — Comparison & Error Interpretation | 同视频多轨迹比较/同帧差值、周期离散/拟合标准误差及局限展示；AC-3 的比较部分、AC-6 | 6.3；High-risk，Independent Review + Human Review；不做完整系统误差传播 |
| 6.5 — Integrated Pendulum Acceptance | 冻结真实单摆全流程，AC-1–7 与 roadmap 两项逐条核对，文档/双平台 CI/最终 Human Review；AC-5 | 6.1–6.4；Independent Review + Human Review；完成后停止，不进入 Phase 7 |

每个子阶段按 mini-plan 建分支/Issue、分 Slice 实现、验证、review、`--no-ff` 集成并 push。
High-risk 建议 PR 作为完整 diff 容器；PR 不承担额外审批。首个计划见
[phase-6.1-plan.md](phase-6.1-plan.md)，其余不预生成空计划。

## 2. 复用与改动面

- domain：复用密集网格、标定变换、NaN 分段、SG；角度使用独立内聚模块。
- application：沿用 `analysis_inputs`/独立 Session 快照/主线程输入复核；
  新增双轨迹依赖时显式扩展目标结果校验，不重写既有运动学任务。
- persistence：优先复用 DerivedData 与可扩展字段；首个 ADR 核对注册/依赖契约。
- GUI：沿用 ChartActions、ChartData、ChartPanel 与既有“分析与图表”工作区。
- tests：解析合成数据、Session 原子性/失效、round-trip、offscreen 与既有回归。
- docs：每个子阶段同步 current；涉及接受的科学方法/数据契约时记录 ADR。

## 3. 冻结证据与停止条件

确认前不把建议误差指标写成已接受验收标准，不创建实现分支/Issue。
6.3 开始时冻结真实视频与人工周期参考；6.5 同时报告成功项与未达成项。
依赖、技术栈、schema 不兼容或指标变更必须按 AGENTS.md 的决策门处理。
已有 Windows/CUDA 延期与 Phase 5 AC-9 明示归档保持原口径。
论文线仅作为可追溯参考；不复制产品源码，不默认 merge/cherry-pick 论文线。

## 4. 本轮结果

已完成主线状态盘点与需求/总计划/6.1 mini-plan 草案；产品代码无改动。
本机全量回归 805 passed（56.91 s）；基线 `b997100` 最新 GitHub CI 36813834691 success。
草案本地链接与 diff 空白检查通过。复用 SG 对 AC-2 指定解析信号的可行性探针得到
ω/α 归一化 RMSE 0.226%/0.164%；只验证已有 primitive，不代表新角运动实现已验收。
下一步：用户确认范围与建议验收门槛后，执行 6.1 Slice 1 的契约 ADR 与纯数值实现。
