# Current Status

> 项目"现在在哪、下一步做什么"的**唯一权威入口**——不知道该做什么时先读这个文件。
> 每个开发会话结束时由 Agent 更新（规则见 `docs/workflow.md` §11）；人类可随时手写修改，人类改动优先于 Agent 的判断。

- 最后更新：2026-08-30（Phase 3.3 计划草案完成，等待确认）

---

## Current Phase

**Phase 3 — Calibration & Physics Engine** 🔄 进行中

## Current Subphase

**3.3 — Interactive Charts / Charting UI**：**Plan / Draft，待用户确认**。
计划见 [phase-3.3-plan.md](phase-3.3-plan.md)；尚未开始实现或安装 PyQtGraph，
Issue 与工作分支在确认计划后创建或复用。

上一 Subphase **3.2 — Kinematics Engine**（[Issue #8](https://github.com/KYLeonis/ai-physics-tracker/issues/8)）
已完成，并由 `3d3ad90` 合并至 `main`；本轮基线为 `e49132a`。原“先合并 3.2”建议已过期。

## Current Slice

Plan：五种图表、双向帧同步、多 Track 叠加、SG 重算与 stale 状态；仅规划文档变更。

## Current Goal

将 3.2 的派生结果接入可交互图表，明确单位、缺测、呈现帧同步、时序授权与重算的
事务边界。先确认 3.3 计划，不自动安装依赖或展开实现；导出仍属 Phase 8。

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

**3.3 拟定方案与待确认**

- PyQtGraph 0.13.7（spec 范围 >=0.13,<0.14）；确认后修改项目依赖并做 Qt/NumPy smoke test。
- 首次设置标定后，既有 px 派生数据未置 stale，纳入 3.3 集成修复。兼容已有
  `world_position(px)` 命名，界面按实际单位/标定引用显示，不迁移原始数据。
- 时序权限、后台批次提交和 GUI 已呈现帧通知需补齐；不在绘图层重做数值引擎。
- 本地 `.venv` SciPy **1.18.1** 与 `requirements.txt` 的 **1.17.1** 不一致；已有测试
  通过不代表锁定环境/Windows Python 3.11 通过。实施前对齐；本轮未修改环境或 CI。
- Phase 2 Windows 真机验收按用户决定延后，继续保留后续事项，不影响本次规划。

## Next Recommended Action

请用户确认 [Phase 3.3 计划](phase-3.3-plan.md) 的范围及引入 PyQtGraph/对齐项目虚拟环境。
确认后创建或复用 Issue，建立 `feat/p3.3-interactive-charts`，先执行 Slice 1 的依赖验证与
ADR/spec 澄清，再逐步实现。不得重复合并 3.2，不在确认前开始代码/依赖变更；
push、CI 配置修改仍需单独授权。
