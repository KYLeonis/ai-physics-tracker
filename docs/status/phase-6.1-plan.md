# Subphase Plan — Phase 6.1 Angular Analysis Foundation

> 2026-10-11：用户确认启动本子阶段（角运动基础与 ADR-0017"角运动/求导是通用平台输入能力"口径兼容；6.1 的 non-goals 本就排除周期/拟合，R3 固定拟合部分仍留待按 ADR-0017 重规划）。科学/数据契约见[ADR-0019](../decisions/0019-angular-kinematics-and-multi-input-derived-data.md)。

- Issue / 分支：[#25](https://github.com/KYLeonis/ai-physics-tracker/issues/25) / `feat/p6.1-angular-analysis`（此前叠加于 `feat/main-guided-refinement-model-import`，现均已集成 main）
- 日期 / 状态：2026-10-13 · **实现 / 完整复审 / 按序集成完成**（merge `890f5b1`）
- 风险等级：High-risk（角度定义、unwrap/微分、多输入依赖与派生结果事务）

## Goal

无需 GUI 即可从有效观测计算单摆/两点方向 θ、ω、α，并验证依赖失效与可复现存储。

## Agent Context Pack

### Authoritative Docs

- [phase6-requirements.md](../spec/phase6-requirements.md) R1/R5、AC-1/2/7；[总计划](phase-6-plan.md)。
- [data-model.md](../spec/data-model.md) §3.8/§4/§6：派生数据、有效观测及坐标契约。
- ADR-0008：SG 的物理 dt、NaN 分段与短段；ADR-0009：后台快照与原子结果提交。
- [ADR-0020](../decisions/0020-analysis-batch-result-and-recipe-consistency.md)：本轮结果版本、配方一致性与公共时序边界修复。
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

- [x] AC-1：单摆/两点方向的基准方向、符号、±π 跨界、恒角速/恒角加速、缺测/重合/短段测试通过（`tests/test_angular.py` 19 项）。
- [x] AC-2：requirements AC-1/2 的解析精度和物理单位门槛通过；端点误差单独报告（随断言消息披露，不设门槛）。
- [x] AC-3：两点任一输入编辑/删除、标定/时序变化使结果失效；Undo/Redo 不留下悬空引用（`tests/test_angular_session.py` + 域校验测试）。
- [x] AC-4：保存重开保留完整参考/算法参数/单位/未知字段；旧项目和既有四项运动学结果不退化（round-trip 测试 + 全量 908 passed 零回归）。
- [x] AC-5：后台取消、输入变化、迟到与部分批次不提交；成功批次原子提交（`tests/test_angular_job.py` 9 项）。
- [x] AC-6：Independent Review findings 已处置，定向/全量验证及双平台 CI 通过（[review record](../reviews/phase-6.1-review.md) 闭环；[CI 38157600556](https://github.com/KYLeonis/ai-physics-tracker/actions/runs/38157600556) macOS/Windows Python 3.11 success）。

## Slices

- [x] Slice 1：扫描调用链，记录 angular/data-dependency ADR（[ADR-0019](../decisions/0019-angular-kinematics-and-multi-input-derived-data.md)），实现纯角度、段内 unwrap 与 SG 导数及解析测试。
- [x] Slice 2：scalar 结果溯源与多输入依赖失效；Session/保存重开/Undo 回归。
- [x] Slice 3：快照后台计算、输入复核和原子提交，补取消/迟到/部分批次测试。
- [x] Slice 4：独立 review → 处置/复审 → 文档同步 → 集成/push/CI（前置 HR 已通过，main merge `890f5b1`；最新 CI / push 见 current）。

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

2026-10-11 完成 Slice 1–4 实现（用户本日确认启动，与 ADR-0017 口径兼容：角运动/求导是
通用平台的输入能力；6.3 固定拟合仍留待按 ADR-0017 重规划）。交付：`domain/angular.py`
（θ 定义/段内 unwrap/标量记录）、`DerivedInput.reference_track_id` additive 扩展与
失效/级联/聚合校验、`compute_angular` 四种标量 kind（rad 系）、`angular_job` 后台批次
（复用 detached/复核/原子提交骨架）、序列化往返；新增 43 项测试（解析 AC-1/2、失效与
Undo AC-3/4、批次 AC-5），本机全量 **908 passed** 零回归。Independent Review 首轮
7 findings：R1/R3/R4/R5/R6 修复并经复审确认（[review record](../reviews/phase-6.1-review.md)），
首轮曾延期 R2 / R7：R7 后续根因修复；R2 已由 2026-10-12–13 完整审查直接修复，
不再留给 6.2。新增后台版本 / 配方、公共时序边界与计算溯源修复见审查记录。
当时分支 `feat/p6.1-angular-analysis` 已 push，[双平台 CI 38157600556](https://github.com/KYLeonis/ai-physics-tracker/actions/runs/38157600556) success；前置 HR 后按序集成的条件现已满足，收尾见末节。

## 完整复审补充（2026-10-13）

用户要求完整复审后直接修复潜在问题；新 finding / 复现 / 修复与独立确认统一记在
[review record](../reviews/phase-6.1-review.md) 的“完整复审”章节。新增 ADR-0020 分析结果版本 / 配方策略，
补旧构造兼容、时序授权、区间失效、近似来源，以及两种模式在旋转 / 非零区间下的解析回归。
最新测试 / CI 以 current 为准；[6.2 子计划](phase-6.2-plan.md)已形成，当前不含 GUI 实现。

最终完整复审：R2 / R8–R13 全部 Closed，最新全量929 passed（66.38 s），
代码4842560 / 双平台CI38274300024 success；6.2技术入口READY。

## main 集成收尾（2026-10-13）

用户确认前置增量 A/B/C 全部通过后，先集成增量 `126e71d`，再以 `--no-ff` 集成本分支
（`890f5b1`），合并树与 `d7b9161` 完全一致。随后集成已通过 HR 的 20 帧 / 代表帧引导
（`4c8398e`）；最终产品 / 测试与 `653e315` 双平台 success CI 相同。
本轮无新科学 / 数据 / GUI 变更，原独立复审结论保留；6.2 仅计划就绪，尚未启动。
main `24403f0` [CI 38364390179](https://github.com/KYLeonis/ai-physics-tracker/actions/runs/38364390179) macOS / Windows Python3.11 success；已 push，Issue #25 已更新最终 Result 并 Closed。
