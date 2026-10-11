# Current Status

> 2026-10-11：用户返回主线继续开发；`main @ b997100` 与 `origin/main` 同步，进入 Phase 6 规划。需求、总计划及 6.1 mini-plan 已起草，待用户确认范围与建议验收门槛；尚未开始产品实现。

> 项目"现在在哪、下一步做什么"的**唯一权威运行时入口**——不知道该做什么时先读这个文件。
> 每个开发会话结束时由 Agent 更新（规则见 `docs/workflow.md` §11.3）；人类可随时手写修改，人类改动优先于 Agent 的判断。
> 本文件是运行时入口，**不是历史日志**：与当前工作无关的条目随手移出（Phase 历史见 roadmap，finding 见 `docs/reviews/`，实现历史见 git log）。

- 最后更新：2026-10-11（主线状态盘点与 Phase 6 规划草案）

## Current

- **Phase**：Phase 6 — Advanced Physics Analysis，规划中（草案待确认）；Phase 5 已完成
- **Subphase / Slice**：6.1 Angular Analysis Foundation mini-plan 草案；无产品实现 Slice
- **Development Mode**：Build Mode（见 `docs/workflow.md` §13）

## Next Recommended Action

**用户确认规划范围与建议验收门槛后，启动 6.1 Slice 1。** 先读
[Phase 6 requirements](../spec/phase6-requirements.md) → [总计划](phase-6-plan.md) →
[6.1 mini-plan](phase-6.1-plan.md) 与 Context Pack；创建 `feat/p6.1-angular-analysis` 分支/Issue，
扫描 scalar kind、双轨迹依赖、首次标定失效与现有消费者，记录契约 ADR，再实现纯数值部分。
计划确认门来源为 `docs/status/README.md`；本轮仅交付可审查草案，不将建议指标当成已接受标准。

## Active Constraints

当前仍然影响下一步的规则（只列规则本身，细节以引用为准；新任务不得破坏）：

**数据与科学契约**

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
- 保存清空应用内 Undo；激活产物指纹为 size-only（已接受的风险）

**工程约束**

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

- **Phase 6 规划草案（2026-10-11）**：已核对主线/远程、既有运动学/图表/DerivedData 契约，新增 requirements、总计划及 6.1 mini-plan；建议误差门槛待确认，未修改产品代码或论文线。主线回归 `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q`：**805 passed，56.91 s**；草案本地链接与 `git diff --check` 通过。基线 `b997100` 最新 CI [36813834691](https://github.com/KYLeonis/ai-physics-tracker/actions/runs/36813834691) 已在线复核 success。
- **Windows 取消维护修复（2026-10-01）**：强杀后原生 join 确认 worker 退出；54 项定向与 Independent Review Approve。main CI [36813075358](https://github.com/KYLeonis/ai-physics-tracker/actions/runs/36813075358) 双平台通过；细节见 [mini-plan](windows-cancel-fix-plan.md)。
- **Agent-first Workflow 2.0 升级（2026-09-18，分支 `docs/agent-workflow-2.0`）**：引入 Agent Context Pack、Cold-start Protocol 2.0、risk-based Review Gate / PR 流程、Source of Truth 分工表、Development Modes、finding 继承规则；重写 subphase-plan 模板，current.md 改为运行时入口结构。顺手修正过期事实：repo 可见性 Private→Public、architecture.md ADR 索引补 0009–0016、AGENTS.md 移除已删除的 CODE_OF_CONDUCT.md 条目。
- **Phase 5 收官（2026-09-18）**：5.7 R1/R2 CLOSED + 最终 Human Review 通过；全量 **804 passed**，双平台 CI 绿（[run 35319559409](https://github.com/KYLeonis/ai-physics-tracker/actions/runs/35319559409)）。Phase 5.0–5.7 全部完成；AC-9 缺口保持归档。各 subphase 交付与 review 见 `docs/status/phase-5.*-plan.md` 与 `docs/reviews/`。
- **Pre-Phase 6 Stabilization（2026-09-16，已合并）**：P6R-01/02/03/04 及 R1 补漏（P6R-02-R1 / 03-R1 / 05）全部关闭，生命周期见 [pre-phase6-project-review.md](../reviews/pre-phase6-project-review.md) §17–19 与 [pre-phase6-stabilization-review.md](../reviews/pre-phase6-stabilization-review.md)；**Phase 6 Entry Gate：READY**。
- **Windows CI heap corruption 根治（2026-09-16）**：根因为 decoder worker 线程 emit 携带 Python 对象的 queued Qt signal；`_DecodeDeliveryBridge` 修复 + 4 项回归（取证与细节见 git log `fix/windows-ci-crash` 与 pre-phase6 review §5）。
