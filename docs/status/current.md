# Current Status

> 项目"现在在哪、下一步做什么"的**唯一权威入口**——不知道该做什么时先读这个文件。
> 每个开发会话结束时由 Agent 更新（规则见 `docs/workflow.md` §11）；人类可随时手写修改，人类改动优先于 Agent 的判断。

- 最后更新：2026-08-31（Phase 3.4 计划草案完成，等待确认）

---

## Current Phase

**Phase 3 — Calibration & Physics Engine** 🔄 进行中

## Current Subphase

**3.4 — Integration & Phase Close**：**Plan / Draft，未开始执行**。
计划见 [phase-3.4-plan.md](phase-3.4-plan.md)，确认后创建或复用 Issue 与工作分支。

上一 Subphase **3.3 — Interactive Charts** ✅ 已完成；Human Review 5 轮通过，
[Issue #9](https://github.com/KYLeonis/ai-physics-tracker/issues/9) 已关闭，merge `51c1cce`。
已只读核实该提交的 [CI run 33353856199](https://github.com/KYLeonis/ai-physics-tracker/actions/runs/33353856199)
macOS/Windows Python 3.11 jobs 均成功。当前规划基线 `main` / `162017e`。

更早的 Subphase **3.2 — Kinematics Engine**（[Issue #8](https://github.com/KYLeonis/ai-physics-tracker/issues/8)）
已完成，并由 `3d3ad90` 合并至 `main`，不重复执行其收尾。

## Current Slice

Plan：确认 3.4 的集成场景、验收证据与 Windows 收尾条件；不改实现。

## Current Goal

核验标定→标注→重算→图表/PNG→保存重开的同项目闭环，补全 Phase 3 验收证据。
现有 PNG 快照属于 3.3 HR 已批准增量；CSV/Excel/科学图表导出仍属 Phase 8。
Phase 3 最终收尾后停止，不自动进入 Phase 4。

## Recently Completed

- **Phase 3.4 规划盘点**（2026-08-31）：已有版本本地复跑 **303 passed**、依赖检查通过；
  Luna-max 只读映射 AC 与测试缺口，形成三个优先集成场景。未进行 3.4 功能修改/真人验收。

- **Phase 3.3 完成**（2026-08-31）：五标签页 QDockWidget、多 Track 叠加、物理/像素
  单位、缺测断线、呈现帧/目标帧双游标和 x-y 点选；SG 参数与后台批次重算、一次 Undo、
  保存/切换/取消隔离；首次标定 stale 与旧缓存标定引用守卫；请求编号贯穿解码成功/失败，
  修复旧结果覆盖新请求；HR 新增多选轨迹视频同屏、? 帮助气泡与当前图表 PNG。
  初次交付 297 tests → 收尾 **303 tests**，5 轮 HR 及双平台 CI 通过，merge `51c1cce`。

- **Phase 3.3 规划盘点**（2026-08-30）：读取 Phase 3 spec/ADR-0008 与图表参考；
  Luna-max 只读核对应用/GUI 接口；形成 mini-plan。规划时工作区干净，已有回归
  **260 passed**（本机 Python 3.12.13），`pip check` 通过；不是 3.3 功能验收。

- **Phase 3.2 — Kinematics Engine**（✅ 2026-08-30）：
  - 纯领域层 `kinematics.py`：实现密集网格展开、按 NaN 切分、Savitzky-Golay 平滑与数值微分，完全隔离 UI。
  - 应用层 `ProjectSession.compute_kinematics`：完整生成 4 条 `DerivedData` 记录并入库，记录 pipeline 参数。
  - 测试：使用解析单摆、匀速、匀加速数据完成了所有 260 项测试。
- **Phase 3.1 — Calibration UI**（✅ 2026-08-30）：交互式比例尺与标定 UI 工具。
- **Phase 3.0 — Spec & Requirements**（✅ 2026-08-30）：编写 Phase 3 需求规范及 ADR-0008。
- **Phase 2 — Video Analysis MVP**（✅ 2026-08-30）：完整的视频分析与人工追踪功能。

## Current Decisions / Blockers

**已定决策**

- 运动学平滑与微分：Savitzky-Golay（ADR-0008），在 3.2 阶段已完整落实。
- **重算触发**：3.3 已提供 Recompute checked tracks，按 ADR-0009 在后台计算并原子提交；
  默认 SG window=7 / polyorder=2，不在播放帧回调中重算。

**已继承的方案与 3.4 待办**

- PyQtGraph 0.13.7（spec 范围 >=0.13,<0.14）；项目依赖已安装并完成 Qt/NumPy smoke test。
- 首次设置标定后既有 px 派生数据未置 stale 的缺口已修复。兼容已有
  `world_position(px)` 命名，界面按实际单位/标定引用显示，不迁移原始数据。
- 时序权限、后台批次提交和 GUI 已呈现帧通知已补齐；绘图层不重做数值引擎。
- 本地 `.venv` 使用锁定 SciPy **1.17.1** / PyQtGraph **0.13.7**；当前 **303 tests** 通过。
  3.3 远端双平台 CI 已核实；未来 3.4 交付仍需绑定其自身验证版本，不能借用旧 run。
- 3.3 PNG 与 ADR-0009 的原始“不导出”条款需要补记已批准例外；3.4 Slice 1 拟新增
  ADR-0010，不改写 Accepted ADR 正文、不扩展科学导出。
- PNG 取消测试的恒真断言、双轨迹均有点的 overlay、带数据的当前 tab PNG 等覆盖缺口，
  纳入 3.4 的最小补测；本次只记录，不修改测试实现。
- Phase 2 Windows 真机延期仍保留；`development.md` 的 Phase 收尾要求也仍有效。
  3.4 可先做本地/自动化验收，但若要继续延期并关闭 Phase 3，需要用户明确确认例外。

## Next Recommended Action

请用户确认 [3.4 计划](phase-3.4-plan.md)，再建立 Issue/工作分支，从证据表与文档例外整理开始，
补必要集成回归并交付整体 Human Review。保留 Windows 收尾条件；需要延期、改变验收标准、
修改 CI 或 push 时单独请求授权。本轮仅规划与本地文档提交，不开始实现，不直接进入 Phase 4。
