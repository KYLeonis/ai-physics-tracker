# Current Status

> 项目"现在在哪、下一步做什么"的**唯一权威入口**——不知道该做什么时先读这个文件。
> 每个开发会话结束时由 Agent 更新（规则见 `docs/workflow.md` §11）；人类可随时手写修改，人类改动优先于 Agent 的判断。

- 最后更新：2026-08-30（Phase 3.1 完结）

---

## Current Phase

**Phase 3 — Calibration & Physics Engine** 🔄 进行中

## Current Subphase

**3.1 — Calibration UI**（[Issue #7](https://github.com/KYLeonis/ai-physics-tracker/issues/7)）：实现交互式标定工具（比例尺、原点、旋转）。✅ **已完成**

下一 Subphase 为 **3.2 — Kinematics Engine**：实现轨迹平滑与物理量计算。

## Current Slice

N/A（等待进入 3.2）。

## Current Goal

实现基础的视频坐标系标定，将像素与物理世界尺寸建立映射，为之后的运动学物理量计算提供前提。现已完成并在 Human Review 中验收通过。

## Recently Completed

- **Phase 3.1 — Calibration UI**（✅ 2026-08-30）：
  - 扩展 `ProjectSession` 支持 `add_calibration`, `set_active_calibration`, 等操作及 undo/redo。
  - 在 `VideoView` 中实现了标定模式，支持绘制比例尺线段及点击设置原点，并提供了 Overlay 渲染。
  - 在 `MainWindow` 的侧边栏添加了完善的 Calibration 控制面板与属性弹窗（默认单位 `mm`）。
  - GitHub Issue #7 收尾合并，全量测试覆盖。
- **Phase 3.0 — Spec & Requirements**（✅ 2026-08-30）：完成 Phase 3 需求规范（10 条 AC）及 ADR-0008。
- **Phase 2 — Video Analysis MVP**（✅ 2026-08-30）：完整的 GUI 视频分析 MVP；macOS Human Review 通过。
- **Phase 1 — Project & Data Foundation**（✅ 2026-08-29）：统一数据体系。

## Current Decisions / Blockers

**已定决策**

- Python 3.11（ADR-0002）
- 持久化格式：JSON 清单优先混合方案（ADR-0003）
- 外部视频 locator（ADR-0004）
- Phase 2 GUI/视频栈：PySide6-Essentials + OpenCV headless + NumPy（ADR-0005）
- 项目工作流：候选提交与 FFprobe 时序关卡（ADR-0006）
- 响应式首帧预览与显式近似时序确认（ADR-0007）
- **数值微分与平滑：Savitzky-Golay 先平滑后微分（ADR-0008）**

**延后项**：Windows 真机验收由用户决定延后执行。

## Next Recommended Action

执行 Subphase 3.1 收尾，将 `feat/p3.1-calibration-ui` 合并至 `main`。随后进入 **Subphase 3.2 — Kinematics Engine**：按照 ADR-0008 的设计实现坐标系转换、平滑、数值微分（Savitzky-Golay filter，依赖 `scipy.signal.savgol_filter`），在 `DerivedData` 中计算位移、速度与加速度，并编写基于单摆小角度合成数据的单元测试。
