# Current Status

> 项目"现在在哪、下一步做什么"的**唯一权威入口**——不知道该做什么时先读这个文件。
> 每个开发会话结束时由 Agent 更新（规则见 `docs/workflow.md` §11）；人类可随时手写修改，人类改动优先于 Agent 的判断。

- 最后更新：2026-08-30（Phase 3.2 完结）

---

## Current Phase

**Phase 3 — Calibration & Physics Engine** 🔄 进行中

## Current Subphase

**3.2 — Kinematics Engine**（[Issue #8](https://github.com/KYLeonis/ai-physics-tracker/issues/8)）：实现从标定后的像素轨迹到物理运动学量（位移、速度、加速度）的完整计算管线。✅ **已完成**

下一 Subphase 为 **3.3 — Charting UI**：实现基础运动学图表（x-t, y-t, v-t, a-t, x-y）的 PyQtGraph 渲染与交互，并提供界面触发重算（recompute kinematics）的按钮/逻辑。

## Current Slice

N/A（等待进入 3.3）。

## Current Goal

计算出具有物理意义的坐标、速度、加速度序列，以供分析图表绘制和导出使用。现已完成核心计算，所有单元测试涵盖 AC-3/4/5/6 验证通过。

## Recently Completed

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

## Next Recommended Action

执行 Subphase 3.2 收尾，将 `feat/p3.2-kinematics-engine` 合并至 `main`。随后进入 **Subphase 3.3 — Charting UI**：引入 PyQtGraph（在 `pyproject.toml` 中添加），构建五种基础物理图表面板，能够调用 3.2 中写好的 `ProjectSession.derived_data` 接口并绘制，同时做到视频帧与图表时间轴同步。
