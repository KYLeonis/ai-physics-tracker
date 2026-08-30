# Current Status

> 项目"现在在哪、下一步做什么"的**唯一权威入口**——不知道该做什么时先读这个文件。
> 每个开发会话结束时由 Agent 更新（规则见 `docs/workflow.md` §11）；人类可随时手写修改，人类改动优先于 Agent 的判断。

- 最后更新：2026-08-30（Phase 3.3 已确认，依赖验证完成，正在实现）

---

## Current Phase

**Phase 3 — Calibration & Physics Engine** 🔄 进行中

## Current Subphase

**3.3 — Interactive Charts / Charting UI**：**In Progress，用户已确认**。
计划见 [phase-3.3-plan.md](phase-3.3-plan.md)，[Issue #9](https://github.com/KYLeonis/ai-physics-tracker/issues/9)，
工作分支 `feat/p3.3-interactive-charts`。PyQtGraph 0.13.7 与锁定 SciPy 1.17.1 已安装，smoke 通过。

上一 Subphase **3.2 — Kinematics Engine**（[Issue #8](https://github.com/KYLeonis/ai-physics-tracker/issues/8)）
已完成，并由 `3d3ad90` 合并至 `main`；本轮基线为 `e49132a`。原“先合并 3.2”建议已过期。

## Current Slice

Slice 2–5：图表数据适配、批次重算与 GUI 集成；完成自动化和独立复审后发起 Human Review。

## Current Goal

将 3.2 的派生结果接入可交互图表，明确单位、缺测、呈现帧同步、时序授权与重算的
事务边界。按已确认计划实现并验证，交付后停在 Human Review；导出仍属 Phase 8。

## Recently Completed

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
- **重算触发**：本阶段为底层开放了 `compute_kinematics` 等 API，明确将在 3.3 阶段由 GUI 层统一提供刷新触发 UI。

**3.3 已确认方案与当前事项**

- PyQtGraph 0.13.7（spec 范围 >=0.13,<0.14）；项目依赖已安装并完成 Qt/NumPy smoke test。
- 首次设置标定后，既有 px 派生数据未置 stale，纳入 3.3 集成修复。兼容已有
  `world_position(px)` 命名，界面按实际单位/标定引用显示，不迁移原始数据。
- 时序权限、后台批次提交和 GUI 已呈现帧通知需补齐；不在绘图层重做数值引擎。
- 本地 `.venv` 已按授权从 SciPy 1.18.1 对齐至锁定的 **1.17.1**；260 项原有回归再次通过。
  尚未验证远端 Windows Python 3.11。本轮不修改 CI。
- Phase 2 Windows 真机验收按用户决定延后，继续保留后续事项，不影响本次规划。

## Next Recommended Action

完成图表/批次重算的集成、回归和独立复审，再向用户发起 Human Review 并停止。
通过后才处理 3.3 的 CI/合并及 3.4；push、CI 配置修改仍需单独授权。
