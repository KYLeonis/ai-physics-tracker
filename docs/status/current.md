# Current Status

> 2026-10-13：当前工作分支 `fix/initial-annotation-guidance`，首次 GUI 学习需 20 个不同人工帧，
> 默认 20 / K-means，推荐框直达自定义算法；[本轮 Human Review](../notes/initial-annotation-guidance-human-review.md)待反馈。
> 最新全量 **933 passed**，`85be73e` [双平台 CI success](https://github.com/KYLeonis/ai-physics-tracker/actions/runs/38349426753)。
> Phase 6.1 完整代码复审 / 修复完成，新增 R8–R13 和原 R2 全部 Closed；
> 6.1 复审时全量 **929 passed**、独立复审 Approve、代码 `4842560` 双平台 CI success。
> [6.2 子计划](phase-6.2-plan.md)已形成，可进入实现准备；本轮未实现 6.2。
> 分支顺序仍为前置三项增量 → 6.1 → 本轮标注引导；不得越过对应 HR。

> 项目"现在在哪、下一步做什么"的**唯一权威运行时入口**——不知道该做什么时先读这个文件。
> 每个开发会话结束时由 Agent 更新（规则见 `docs/workflow.md` §11.3）；人类可随时手写修改，人类改动优先于 Agent 的判断。
> 本文件是运行时入口，**不是历史日志**：与当前工作无关的条目随手移出（Phase 历史见 roadmap，finding 见 `docs/reviews/`，实现历史见 git log）。

- 最后更新：2026-10-13（首次 20 帧 / 自定义选帧引导实现，Human Review 待反馈）

## Current

- **Phase**：Phase 6.1 完整复审完成待集成；Phase 6.2 计划就绪，后续方程部分按 ADR-0017 重规划
- **Subphase / Slice**：首次标注引导 S1–S3 完成，代码 `b9267e3`，Issue #26；本轮与前置增量 Human Review 待反馈；6.2 仅计划就绪
- **Development Mode**：Build Mode（见 `docs/workflow.md` §13）

## Next Recommended Action

0. **用户执行本轮 [Human Review](../notes/initial-annotation-guidance-human-review.md)（A/B/C）**：20 帧门槛、默认 K-means、自定义确认 / 取消及新项目默认值；计划见 [initial-annotation-guidance-plan.md](initial-annotation-guidance-plan.md)。工作分支基于 `d7b9161`，通过后也须按下面的前置顺序集成，不直接将整栈视为 HR 已通过。
1. **用户执行前置增量的 [Human Review](../notes/main-guided-refinement-model-import-human-review.md)（A/B/C 反馈）**——通过后按 `--no-ff` 集成 `feat/main-guided-refinement-model-import`、验证同树 / main CI、文档收尾 / push、关闭 Issue #24。
2. 随后按序 `--no-ff` 集成 `feat/p6.1-angular-analysis`，代码 `4842560` [CI 38274300024](https://github.com/KYLeonis/ai-physics-tracker/actions/runs/38274300024) 双平台 success；Issue #25 随集成关闭。保存 / 结果身份 / 配方条件见 [review](../reviews/phase-6.1-review.md) 和 ADR-0020。
   再集成本轮 `fix/initial-annotation-guidance`（需要本轮 HR 已通过），验证 main CI / 文档收尾 / push / 关闭 Issue #26。
3. 6.2 技术入口 READY，读取 [phase-6.2-plan.md](phase-6.2-plan.md)；下一次用户明确启动后创建 Issue / `feat/p6.2-angular-charts` 并从 S1 科学适配开始。集成仍不能越过前置 HR。
4. R2 区间失效已经修复；R7 测试竞态已闭环。旧 autosave 期间 Open/Save 菜单静默忽略只留后续 UX 档案，未混入本轮无 GUI 的 6.1 修复。

后续 Phase 6 其余子阶段必须按[ADR-0017](../decisions/0017-user-defined-equation-analysis-platform.md)的**用户提供方程、通用平台分析**口径重规划，不执行旧固定拟合草案。触及相关阶段时必须核对[后续回移档案](main-backport-backlog.md)。

## Active Constraints

当前仍然影响下一步的规则（只列规则本身，细节以引用为准；新任务不得破坏）：

**数据与科学契约**

- main 用户提供方程 / 公式，由通用平台计算与分析；论文硬编码 ODE 仅作复现参考（ADR-0017）
- 同步 / 后台计算均需本次时序授权；修改区间置相关派生 stale，不改 raw 时间；提交还核对目标结果版本 / 配方 / 标定（ADR-0020）。
- 角运动四种标量 kind（angular_position / smoothed_angular_position / angular_velocity / angular_acceleration，rad 系，单列 values）；每轨迹每种 kind 至多一条，重算整组替换（ADR-0019）；6.2 前图表不消费角运动数据

- raw 层只存像素；世界坐标是 `CalibrationTransform` 的派生结果，`pixel_` / `world_` 前缀严格分层
- `frame_index` 是 int、时间是 float 秒；换算只经 Timeline 纯函数（nominal 模型 `frame/fps_nominal`，非 VFR 引擎）
- 缺测展开为 NaN 并按连续段滤波：不跨 NaN 段求导、不静默插值、短段按既定缩窗规则（ADR-0008）
- 平滑微分 = SG 先平滑后微分，默认 window=7 / polyorder=2（ADR-0008）
- Phase 6 规划约束：现有 `KINEMATICS_KINDS` 四项批次与图表两列 values 不是通用高级分析接口；新标量量和双轨迹依赖须显式适配并验证失效（pre-phase6 review §10）
- 预测永不自动成为 ground truth：completed infer 只是候选，显式 Activate/Replace/Clear 原子事务才改观测
- Accept 不产生 ground truth；Correct 才写 manual 并保留 prediction provenance
- `FrameSelectionResult` 只含帧号，不创建 TrackPoint
- 验证比较资格三态 clean / contaminated / unknown，fail-closed；series ID 相同 ≠ 可独立比较（Resume 祖先暴露）
- 被 train run 引用的 validation series 拒绝物理删除（Undo 路径同守卫）
- 显式 Save / Save as 清空应用内 Undo；静默 autosave 保留 Undo/Redo（accept_autosaved_snapshot）；激活产物指纹为 size-only（已接受的风险）

**工程约束**

- 首次 GUI 学习需当前轨迹 20 个不同 active manual 帧；已有 completed train 的该轨迹保留原再训练门槛。默认选帧 20 / K-means，推荐框和高级表单共享选帧信号 / 算法选择；新建 / 切换项目重置默认。不改变引擎至少 3 个训练帧的技术契约；固定检查帧可从 20 个标注中留出。候选 / Skip 不算标签；教师模型自检 / 推理不受此训练门槛限制。
- decoder 交付对象走 `queue.SimpleQueue` + 无参 Qt signal 唤醒：禁止 worker 线程直接 emit 携带 Python 对象的 queued signal（Windows heap corruption 教训）
- 训练强制 fresh per-run DLC 目录（复用旧目录会导致 shuffle 编号错位）
- Windows 真机 / CUDA 验收已批准延期至 Phase 9 打包前
- Phase 5.6 AC-9 改善目标缺口已归档（最佳 −3.3%，未达 ≥5%）：不重开、不改口径，留待独立保留帧或第二视频再评估

## Relevant Risks / Historical Context

- High-risk 改动（schema/持久化、坐标/时间语义、数值算法、拟合/不确定度、Undo/Redo、AI 激活、后台并发、打包/迁移）默认触发 Independent Review，在 mini-plan Review Gate 提前声明（`docs/workflow.md` §10.2）
- **P6R-02 教训**（[pre-phase6-project-review.md](../reviews/pre-phase6-project-review.md)）：不得从 ID 本身推断科学有效性——同 series 也可能因祖先训练暴露而不可比；历史 RMSE 未改写，资格为 compute-on-read
- **P6R-01 教训**：Undo/Redo 必须维护 Track / run / 引用的一致事务，越依赖原子拒绝（回归：`tests/test_undo_run_integrity.py`）
- `Closed` finding 只代表当时证据下关闭；再触同一 invariant 时经 mini-plan Context Pack 引用（`docs/workflow.md` §6.3）

## Recently Completed

- **首次学习 / 选帧引导（2026-10-13）**：分支 `fix/initial-annotation-guidance`，代码 `b9267e3`，Issue [#26](https://github.com/KYLeonis/ai-physics-tracker/issues/26)。首次 GUI 学习需 20 个不同人工帧，推荐框 / 高级训练 / 连续标注完成提示一致；20 / K-means 默认选帧，推荐框自定义弹窗解释并选择 K-means / Uniform，取消不启动，同一项目沿用算法，新建 / 切换项目恢复默认。已有 completed train 的同轨迹再训练保留门槛，教师模型路径与引擎至少 3 个训练帧契约不变。新增 4 回归；定向 118、末轮 58、最终全量 **933 passed（56.79 s）**，diff 检查通过；`85be73e` [CI 38349426753](https://github.com/KYLeonis/ai-physics-tracker/actions/runs/38349426753) macOS / Windows Python3.11 success，Human Review 待反馈。未合 main / 未启动 6.2，实现与集成次序见[计划](initial-annotation-guidance-plan.md)。

- **6.1 完整复审 / 6.2 计划（2026-10-12–13）**：复审整个 6.1 调用链，修复原 R2 与新增 R8–R13：旧构造兼容、公共计算时序、近似 / 区间来源、旧批次覆盖新结果、规格 / SG / 引用一致、标定 pipeline 一致；代码 `80661c1` / `aacb379` / `5f50a16` / `4842560`。新增 21 回归，定向87、全量 **929 passed（66.38 s）**，全新最终独立复审 Approve，[CI 38274300024](https://github.com/KYLeonis/ai-physics-tracker/actions/runs/38274300024) macOS / Windows Python3.11 success。ADR-0020 与 6.2 mini-plan 已写，未改论文 worktree / 未实现 6.2 / 未合 main；前置 HR 仍待反馈。

- **Phase 6.1 角运动分析基础（2026-10-11）**：分支 `feat/p6.1-angular-analysis`（Issue #25），实现+review 修复共 3 提交。交付 ADR-0019、`domain/angular.py`、`DerivedInput.reference_track_id`（双轨迹失效/级联/同视频校验）、`compute_angular`、`angular_job` 后台原子批次与序列化往返；新增 43 测试，本机全量 **908 passed** 零回归，分支 [CI 38157600556](https://github.com/KYLeonis/ai-physics-tracker/actions/runs/38157600556) 双平台 success。Independent Review 首轮 Approve with findings（7 项：5 修复+复审确认、2 延期——R2 zone 失效移交 6.2、R7 父分支 flake 与本 diff 无关）；[review record](../reviews/phase-6.1-review.md)。分支已 push，CI 结果与集成动作见 Next；集成 main 待前置增量 HR 通过。

- **本轮三项增量实现 / 复审（2026-10-11）**：工作分支 `feat/main-guided-refinement-model-import`，代码 `1743f61` / `229b7d4` / `c998fd0` / `0c71910`；定向45 + 末轮28通过，全量 **865 passed（77.50 s）**，最新代码 [CI 38144024802](https://github.com/KYLeonis/ai-physics-tracker/actions/runs/38144024802) macOS/Windows Python3.11 success。R1/R2/R3 六项 findings Closed / Approve；[review record](../reviews/main-guided-refinement-model-import-review.md)。实际 DLC spawn 四点自检及三帧 tip 推理 `auto → mps` 成功；Human Review 待反馈、Issue #24 open、未合 main。方程口径与后续档案同步 ADR-0017/0018 / AGENTS / roadmap / specs / README。

- **主线 UI 维护 HR / 集成（2026-10-11）**：用户整体确认“上一轮的HR通过”，五项回移与顶部推荐完成 `--no-ff` 集成 / push（`017cc04`）；无新产品 / 测试修改，合并树与分支 `24ec071` 的双平台 success CI 一致。main [CI 38138010183](https://github.com/KYLeonis/ai-physics-tracker/actions/runs/38138010183) 双平台 success，Issue #23 已关闭。用户未提供逐项设备 / 平台明细，不扩大为 Windows/CUDA 全阶段验收。后续优先级见[区别文档 §10](../notes/publication-main-feature-ui-differences.md#10-hr-通过后的回移建议2026-10-11)。

- **论文 / main 全量区别扫描（2026-10-11）**：固定 main `50a7924` / 论文集成 `b459e4a` / 最新工作线 `154f262` / 当前维护 `3c43544`；完整 inventory **637 文件、229 提交、80 源码模块（53 新增 / 27 修改）**，明确已同步、待主线 HR、论文独有及 main 独有文档。补充 Analysis 模式仍可保留标注的内存探针与回移候选；保留 E3 30/48 / E2 47/48 与发行真人缺项。公开 v0.1.0 的 11 资产 / 固定源码重新在线核对；链接、计数、diff 检查通过。仅文档，未跑真实训练 / 论文全量、未改用户工程 / 论文 worktree / 合并产品；[报告及附件](../notes/publication-main-feature-ui-differences.md)。

- **macOS Start learning 设备核查（2026-10-11）**：主线 auto 保留到 worker，按 CUDA→MPS→CPU 解析；本机 `.venv` Torch 2.13.0 实测解析 mps / 张量 mps:0。GUI 捕获三种设备选择均保留，定向 4+9 passed；论文 `5ada419` 是联合路径固定 CPU 修复，单轨无需回移。仅记录检查，未改产品/用户工程、未启动 DLC 完整训练；[核查记录](../notes/publication-backport-assessment.md#start-learning--macos-auto-设备核查2026-10-11)。

- **顶部推荐扩展（2026-10-11）**：按用户补充授权，常驻主线 TaskCard 的摘要/主动作/最多两个旁路；复用原动作入口，空会话推荐 Add video，审核/标注返回获取轨迹。定向 **72 passed（9.19 s）**，全量 **820 passed（48.44 s）**，self-review/diff/窄窗口布局探针通过。代码 `8c16908` / CI checkpoint `fe051f5` 双平台通过，Human Review 本轮用户已确认通过；[mini-plan](main-ui-backports-plan.md)。

- **UI 回移自动验证（2026-10-11）**：代码 `53a6fb9`，三个 GUI 文件/十项滚轮回归，五项通用修复与源提交溯源；定向 107 passed（12.60 s）、全量 815 passed（49.36 s）、实际 widget 展示断言及 diff 检查通过。checkpoint `167a518` 的 [CI 38110444232](https://github.com/KYLeonis/ai-physics-tracker/actions/runs/38110444232) 双平台 success；无论文 schema/领域/依赖改动。分支已 push，用户已确认 HR 通过，本轮已集成 main（`017cc04`）。
- **论文线回移评估（2026-10-11）**：审查 publication 集成分支及最新发行分支 `154f262`；确认两项值得优先回移的通用 UI 问题、三项小改进，取消源码/测试已等价同步。主线定向 50 passed（7.07 s），只读探针与目标 patch 适用性检查通过；产品代码未修改。详见 [评估记录](../notes/publication-backport-assessment.md)。
- **Phase 6 规划草案（2026-10-11）**：已核对主线/远程、既有运动学/图表/DerivedData 契约，新增 requirements、总计划及 6.1 mini-plan；建议误差门槛待确认，未修改产品代码或论文线。主线回归 `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q`：**805 passed，56.91 s**；草案本地链接与 `git diff --check` 通过。基线 `b997100` 最新 CI [36813834691](https://github.com/KYLeonis/ai-physics-tracker/actions/runs/36813834691) 已在线复核 success。
- **Windows 取消维护修复（2026-10-01）**：强杀后原生 join 确认 worker 退出；54 项定向与 Independent Review Approve。main CI [36813075358](https://github.com/KYLeonis/ai-physics-tracker/actions/runs/36813075358) 双平台通过；细节见 [mini-plan](windows-cancel-fix-plan.md)。
- **Agent-first Workflow 2.0 升级（2026-09-18，分支 `docs/agent-workflow-2.0`）**：引入 Agent Context Pack、Cold-start Protocol 2.0、risk-based Review Gate / PR 流程、Source of Truth 分工表、Development Modes、finding 继承规则；重写 subphase-plan 模板，current.md 改为运行时入口结构。顺手修正过期事实：repo 可见性 Private→Public、architecture.md ADR 索引补 0009–0016、AGENTS.md 移除已删除的 CODE_OF_CONDUCT.md 条目。
- **Phase 5 收官（2026-09-18）**：5.7 R1/R2 CLOSED + 最终 Human Review 通过；全量 **804 passed**，双平台 CI 绿（[run 35319559409](https://github.com/KYLeonis/ai-physics-tracker/actions/runs/35319559409)）。Phase 5.0–5.7 全部完成；AC-9 缺口保持归档。各 subphase 交付与 review 见 `docs/status/phase-5.*-plan.md` 与 `docs/reviews/`。
- **Pre-Phase 6 Stabilization（2026-09-16，已合并）**：P6R-01/02/03/04 及 R1 补漏（P6R-02-R1 / 03-R1 / 05）全部关闭，生命周期见 [pre-phase6-project-review.md](../reviews/pre-phase6-project-review.md) §17–19 与 [pre-phase6-stabilization-review.md](../reviews/pre-phase6-stabilization-review.md)；**Phase 6 Entry Gate：READY**。
- **Windows CI heap corruption 根治（2026-09-16）**：根因为 decoder worker 线程 emit 携带 Python 对象的 queued Qt signal；`_DecodeDeliveryBridge` 修复 + 4 项回归（取证与细节见 git log `fix/windows-ci-crash` 与 pre-phase6 review §5）。
