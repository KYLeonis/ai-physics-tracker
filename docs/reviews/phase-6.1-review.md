# Review Record — Phase 6.1 Angular Analysis Foundation

- Subphase：[phase-6.1-plan.md](../status/phase-6.1-plan.md) · Issue [#25](https://github.com/KYLeonis/ai-physics-tracker/issues/25)
- 分支：`feat/p6.1-angular-analysis`（叠加于待 HR 的 `feat/main-guided-refinement-model-import`）
- Reviewer：Independent code-reviewer（只读，全新实例，Flash 模型）
- 首轮日期：2026-10-11 · 状态：Final Verdict 已出

## Scope

实现提交 `feat: add angular analysis foundation with multi-input derived data`
（domain/angular.py 新增；DerivedInput.reference_track_id additive 扩展；
compute_angular / angular_job / serializer / validate_project / delete_track 级联；
41 项新测试）。审查维度按 mini-plan Review Gate：A 科学定义与数值、B 多输入依赖失效、
C 存储兼容、D 事务、E 代码规范。权威上下文：ADR-0019、phase6-requirements R1/R5、
ADR-0008、pre-phase6 review §10（P6R-01）。

## Findings（首轮 R1）

| # | 维度 | Severity | Observed/Inferred | 摘要 |
| --- | --- | --- | --- | --- |
| R1 | A | Low | Observed（数值复现） | `-dy + 0.0` 规整无可观测行为差异且注释论据错误（`atan2(y>0, ±0)` 恒 π/2；dx=dy=0 已被重合守卫覆盖） |
| R2 | B | Low | Observed | `update_timeline` 仅 working_zone 变化时不置 stale，角运动/运动学共用此既有缺口（非本 diff 引入） |
| R3 | D | Low | Inferred | `prepare_angular_job` 不预检 active calibration，无标定批次在 worker 内才失败 |
| R4 | B | Low | Observed | `validate_project` 对 reference_track_id 只校验存在性，不校验同视频 |
| R5 | E | Nit | Observed | `compute_angular` docstring "同一角度定义下" 与无条件整组替换的实现不符 |
| R6 | 文档 | Low | Observed | 提交时 plan/current.md 未同步（Slice 4 中间态，收尾必须完成） |
| R7 | 范围外 | Low | Observed | `tests/gui/test_suggested_frame_review_reliability.py::test_save_reopen_and_resume_review_matrix` 负载下时序 flake（父分支 1ee9323 既有） |

维度结论：A/B/C/D/E 五个维度均无 High/Medium finding；B 维度逐点核对了全部
`mark_tracks_stale` 调用点与删除/Undo 路径，未发现失效传播漏洞。

## Triage 与 Fixes

- **R1 → Fixed**：删除无效规整与错误注释（reviewer 复核 atan2 语义后确认守卫已覆盖）。
- **R3 → Fixed**：`prepare_angular_job` 对目标/参考轨迹所属视频 fail-fast 校验 active
  calibration，新增回归测试。
- **R4 → Fixed**：`validate_project` 增加 reference_track_id 同视频聚合校验，新增跨视频
  拒绝测试。
- **R5 → Fixed**：docstring 改为"重算即整组替换（含更换参考模式）"。
- **R2 → Deferred（接受）**：zone-only 变更不失效是 Phase 3 以来的既有语义，kinematics
  同样继承；当前 GUI 无 zone 编辑入口。移交 Phase 6.2（角运动图表暴露 zone 相关 UI 前）
  处理，届时统一决定 zone 变更的失效策略。
- **R6 → Fixed**：Slice 4 收尾同步（本文件 + plan AC/Slice 勾选 + current.md）。
- **R7 → Fixed（根因定位，两层）**：父分支 flake，与 6.1 diff 无关（在 a36007e 上复现证实）。
  第一层：reliability 测试在 Correct 触发的静默 autosave（`projectActions.busy`）尚未结束时
  就调用 `_load`，而 `_run` 在 busy 时**静默丢弃**加载请求——慢环境（CI）下重开从未发生，
  测试全程操作旧 session 反而"稳定通过"（CI 历史绿的原因）；快环境（本地）下重开启动但
  adopt 中途落地，`projectChanged` 重置审核 UI，面板回退到重开前摘要（~1/5–1/3 失败率）。
  第二层：两个 GUI 测试用 `waitUntil(analysisSession is not None)` 等待重开完成——`_load`
  期间旧 session 对象一直非 None，该条件被立即满足。真实用户有模态进度框与禁用 UI 挡住
  交互，无此竞态——纯测试缺陷。修复（对照 test_suggested_frame_review_actions.py 既有模式）：
  重开前先等 `not projectActions.busy`，重开后等 **session 身份变化**
  （`analysisSession is not session`）；另保留 8 处超时 3000→15000 ms 余量。修复后两文件
  10/10 全绿。产品侧遗留观察（backlog）：autosave 期间不禁用菜单动作，用户此刻点
  Open/Save 会被静默忽略，与 `_run` 的 busy 早退组合成真实 UX 缺陷，非本子阶段范围。

## Verification

- 首轮：Reviewer 独立运行新增 41 项 + 相邻回归 114 项 + 全量 4 次（3×906 passed）。
- 修复后（实现方）：定向 angular 43 项 passed；全量 906/907 passed（唯一失败为 R7
  flake，与本 diff 无关）。

## Re-review

修复提交 `fix: dispose independent review findings R1/R3/R4/R5` 由全新独立 code-reviewer
复审（2026-10-11）：R1 数值情形逐一验证语义不变；R3 覆盖目标+参考、同视频多 spec 无
误拒、与 worker 校验逐字一致；R4 索引安全且不破坏既有构造（定向 57 + 全量 908
passed）；R5 与实现一致；两项新回归测试在修复前必失败、真实覆盖。附 2 条风格 nit
（`_job_track_ids` 重复计算、"R1" 引用口径），实现方当场处置。**结论：确认修复完毕
（approve）。**

## Final Verdict

**修改后通过（Approve with findings disposed）**：R1/R3/R4/R5/R6/R7 已修复（R7 为父分支
测试竞态根因修复，见 Triage；均非 6.1 实现缺陷）；复审附带的 2 条 nit 已处置；R2 记档
延期移交 6.2；科学定义、多输入依赖失效、存储兼容与事务四大高风险面通过审查。
集成前剩余条件：双平台 CI 绿。

## 完整复审 — 2026-10-12–13（用户要求）

基线 `e1de4da`，检查整个 `a36007e..e1de4da` 的 6.1 增量及相邻生产调用链，修复至 `4842560`。
主 Agent 审查纯数值 / Session / 消费者，独立 `p61_data_review` 审查数据、失效、序列化和批次；
`p61_fix_review` 复审新修复，最终标定配方补漏交全新 `p61_final_review` 确认。
使用场景为单用户桌面、可取消后台计算；未扩大成论文线审查或性能 / 打包阶段。

### 覆盖范围

- `domain/angular.py`：两种角度方向、重合 / NaN、段内 unwrap、短段与 SG 物理 dt。
- `compute_angular`：标定旋转 / 平移 / 比例尺、非零源帧区间、参考同视频与有效交集、四种 rad 系记录。
- DerivedInput / Project：旧构造兼容，主 / 参考编辑、AI 激活、审核、删除、标定、Timeline、Undo/Redo 失效与级联。
- serializer / repository：scalar 行、reference UUID、pipeline、未知键、保存重开；旧线性四量继续使用。
- angular / kinematics job：detached、取消、失败 / 部分批次、输入变化、同目标结果竞争、配方 / 引用一致与原子提交。
- 消费者：当前 chart_data 只处理两列；analysis_facts 任意 valid derived 即 latest；ChartPlot 仅 xy 走非时间导航。
  这些已明确纳入 [6.2 计划](../status/phase-6.2-plan.md)，本轮不实现新 GUI。
- GUI 测试增量：重开等待真实 session 替换、autosave 完成；未把固定 sleep 当完成证据。

### Findings / 处置

| ID | 问题 / 具体复现与影响 | 最小修复 | Commit | 状态 |
| --- | --- | --- | --- | --- |
| R2（重开） | 只改 working_zone 后 θ/ω/α 仍 valid；SG 边界及 unwrap 起点可能与当前区间不同 | domain.update_timeline 统一置该视频相关派生 stale，保留 raw / 冻结时间；相同区间不误失效 | 80661c1 | Closed，最终复审确认 |
| R8 | 旧 `DerivedInput(id, None, False, extras)` 把 extras 当参考轨迹，扩展字段丢到错误位置 | 新字段尾追加，保留旧四位置参数；新增兼容回归 | 80661c1 | Closed，复审确认 |
| R9 | 重开未授权时，直接 compute_angular / compute_kinematics 仍生成 valid 速度 / 加速度 | 两个公共计算入口检查 can_measure；可读缓存保持原样，新媒体确认后才重算 | 80661c1 / 5f50a16 | Closed，复审确认 |
| R10 | direct compute_angular 在 near-CFR 授权下输出无 timing_context；重开丢失近似计算依据 | 同步入口统一保存 fps / working_zone / approximation，后台使用相同结果并删去重复拼装 | aacb379 | Closed，复审确认 |
| R11 | 先提交新 pivot / window 结果，再应用旧后台结果，会被旧结果覆盖 | prepare 捕获目标族 derived_id 基线；提交核对目标结果身份，其他族 / 参考轨迹自身结果不误阻止 | 5f50a16 | Closed，复审确认 |
| R12 | 把 AngularResult.inputs 换成无关 C 或把记录引用改成 C 仍可提交；linear 同样可携带参考轨迹 | 核对 specs / 实际输入集合 / record 引用 / reference pipeline / SG 参数；完整批次原子拒绝 | 5f50a16 | Closed，复审确认 |
| R13 | 改 pipeline.calibration_id 为全零，保留正确 calibration_ref，依然能提交错误溯源 | 有标定恰好一个匹配 step；无标定无 step；错误 / 重复 / 缺失全部原子拒绝 | 4842560 | Closed，最终复审确认 |

R2 旧 Deferred 决定被本轮直接修复取代。上述修复不改 schema、不新增依赖、不复制论文 ODE。
结果版本和配方策略记 [ADR-0020](../decisions/0020-analysis-batch-result-and-recipe-consistency.md)。

### 数值与测试证据

- 初始新增 angular 集：43 passed；复现原四位置参数 / 未授权计算 / zone-only stale，再增加对应回归。
- 独立数据审查：76 passed；修复后最后定向集：87 passed（1.46 s）。
- 全链解析回归：两种角定义在旋转 37°、非零原点、比例尺改变、工作区间源帧 12–42 时，恒定 ω=0.8 rad/s，α=0；不重编号源帧。
- θ=0.2 sin(πt)，60 fps，20 s，SG7/2，去两端各3样本：ω 内部归一化 RMSE **0.22544791%**，
  α **0.15481570%**；端点 RMSE 分别 **0.00344700119946 rad/s**、**0.221540545018 rad/s²**。
  端点不计入内部误差门槛，6.2 必须显示方法 / 窗口，不把这些测试等同真实实验准确性。
- 最新全量：**929 passed（66.38 s）**；代码 `4842560` [CI 38274300024](https://github.com/KYLeonis/ai-physics-tracker/actions/runs/38274300024) macOS/Windows Python 3.11 均 success。最终独立复审 Approve。

### 新独立复审记录

- `p61_data_review`：复核 e1de4da / 80661c1，依赖失效 / 保存 / 取消通过；发现 R11/R12 和 R9 的 linear 旁路。
- `p61_fix_review`：复核 80661c1 / aacb379 / 5f50a16，R8–R12 与 R2 修复总体正确；R13 阻断，已由实现方修复。
- `p61_final_review`：**Approve**，确认 4842560 关闭标定配方 blocker；新增定向 7 passed、相关 job/session 63 passed，真实标定线性批次成功提交四条匹配标定步骤结果，diff 检查通过；未修改产品 / 测试。

### 6.2 Entry 最终结论

**READY（实现准备）**：本轮新 finding 和原 R2 全部 Closed，独立复审 Approve，最新代码双平台 CI 通过。可进入 6.2 实现准备；[6.2 子计划](../status/phase-6.2-plan.md)已形成。
main 集成仍须先等 Issue #24 的 HR，再按序集成前置增量和 6.1。本轮没有启动 6.2 实现。

本轮最终判定：修改后通过；6.2 技术入口无未处置 blocker。main 集成前仍保持前置 HR 条件，
未把本轮后端验证扩展为真人 GUI 或 Windows/CUDA 真机验收。
