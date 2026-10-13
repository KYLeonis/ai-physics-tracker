# Subphase Plan — Phase 6.1 Angular Analysis Foundation

> 2026-10-11：本文件为旧规划草案，**不得直接启动实施**。用户已确认由用户给出方程、平台通用计算；见[ADR-0017](../decisions/0017-user-defined-equation-analysis-platform.md)。固定拟合模型仅可作为示例，下一轮规划须重新对齐输入 / 求解 / 拟合范围。

- Issue / 分支：尚未创建（规划确认后 `feat/p6.1-angular-analysis`）
- 日期 / 状态：2026-10-11 · **草案，待用户确认**
- 风险等级：High-risk（角度定义、unwrap/微分、多输入依赖与派生结果事务）

## Goal

无需 GUI 即可从有效观测计算单摆/两点方向 θ、ω、α，并验证依赖失效与可复现存储。

## Agent Context Pack

### Authoritative Docs

- [phase6-requirements.md](../spec/phase6-requirements.md) R1/R5、AC-1/2/7；[总计划](phase-6-plan.md)。
- [data-model.md](../spec/data-model.md) §3.8/§4/§6：派生数据、有效观测及坐标契约。
- ADR-0008：SG 的物理 dt、NaN 分段与短段；ADR-0009：后台快照与原子结果提交。
- `CODE_STANDARD.md`；`docs/research/open-source-project-map.md` §3.3/3.11/3.12/§7。

### Relevant Historical Findings

- [pre-phase6-project-review.md](../reviews/pre-phase6-project-review.md) §10：四种运动学结果及两列图表是具体契约；新 scalar kind 和首次标定失效需显式适配。
- P6R-01（同 Review Record）：Undo/Redo 必须维护全部依赖引用，不留下部分提交。
- [pre-phase6-stabilization-review.md](../reviews/pre-phase6-stabilization-review.md)：Entry Gate 已关闭历史 blocker，不重开无关 AI finding。

### Scientific / Data / Product Invariants

- 角度方向、参考点、单位与段内 unwrap 按 R1；缺测不连接、不补值。
- raw 不存世界坐标，稀疏持久化不写 NaN，源帧/时间不重新编号。
- 双轨迹按同帧有效交集；参考轨迹也是完整计算依赖，编辑/删除需失效。
- SG 默认 7/2、物理 dt；原始 θ 与平滑 θ 分开保留，导数方法留痕。
- 批次全成功且输入未变才提交；未知字段与旧四项派生结果保留。

### Known Deferred / Accepted Items

- Windows/CUDA 真机验收延期到 Phase 9 前；双平台 CI 仍需通过。
- Phase 5 AC-9 ≥5% 改善缺口已归档，与角运动基础无关。

### Explicit Non-goals

GUI、周期/拟合、误差传播、AI 管线修改、无标定角度模式、通用 pipeline 框架。

## Scope

做：纯角度计算、scalar DerivedData 注册/溯源、双输入依赖失效、Session 计算和快照事务、保存重开。
不做：上述 non-goals；不为了新量把现有 x/y/v/a 接口整体泛化。

首个 Slice 必须先扫描 `KINEMATICS_KINDS`、两列 values 假设、registry、失效调用点和消费者；
ADR 需决定 scalar kinds/多输入参数的 additive 落点，并核对旧项目读取行为。
若实现必须变更不兼容格式或引入依赖，停在具体方案处按 AGENTS.md 决策门处理。

## Acceptance Criteria

- [ ] AC-1：单摆/两点方向的基准方向、符号、±π 跨界、恒角速/恒角加速、缺测/重合/短段测试通过。
- [ ] AC-2：requirements AC-1/2 的解析精度和物理单位门槛通过；端点误差单独报告。
- [ ] AC-3：两点任一输入编辑/删除、标定/时序变化使结果失效；Undo/Redo 不留下悬空引用。
- [ ] AC-4：保存重开保留完整参考/算法参数/单位/未知字段；旧项目和既有四项运动学结果不退化。
- [ ] AC-5：后台取消、输入变化、迟到与部分批次不提交；成功批次原子提交。
- [ ] AC-6：Independent Review findings 已处置，定向/全量验证及双平台 CI 通过。

## Slices

- [ ] Slice 1：扫描调用链，记录 angular/data-dependency ADR，实现纯角度、段内 unwrap 与 SG 导数及解析测试。
- [ ] Slice 2：scalar 结果溯源与多输入依赖失效；Session/保存重开/Undo 回归。
- [ ] Slice 3：快照后台计算、输入复核和原子提交，补取消/迟到/部分批次测试。
- [ ] Slice 4：独立 review → 处置/复审 → 文档同步 → 集成/push/CI。

## Verification

定向运行新增 angular、Session/job、serialization、kinematics 测试；收尾运行
`QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest`，push 后确认 macOS/Windows CI。
数值证据必须记录采样率、时间区间、SG 参数和误差定义，不凭肉眼判断曲线。

## Review Gate

- **Independent Review**：触发；全新只读 Reviewer 审查科学定义、多输入依赖、存储兼容与事务。
  记录在 `docs/reviews/phase-6.1-review.md`，Context 为本计划及其上述引用。
- **PR**：建议作为完整 diff 容器；无强制审批。
- **Human Review**：不适用，本子阶段不增加 GUI 交互；6.2 单独触发。

## Result

本轮只完成 mini-plan 草案；没有实现、没有勾选 AC，也未执行实现的 Independent Review。
