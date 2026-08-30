# Current Status

> 项目"现在在哪、下一步做什么"的**唯一权威入口**——不知道该做什么时先读这个文件。
> 每个开发会话结束时由 Agent 更新（规则见 `docs/workflow.md` §11）；人类可随时手写修改，人类改动优先于 Agent 的判断。

- 最后更新：2026-08-30（Phase 3.0 Spec & Requirements 进行中）

---

## Current Phase

**Phase 3 — Calibration & Physics Engine** 🔄 进行中

## Current Subphase

**3.0 — Spec & Requirements**（[Issue #6](https://github.com/KYLeonis/ai-physics-tracker/issues/6)）：编写 Phase 3 需求规范与 ADR-0008。

上一 Phase 2 已完成（macOS Human Review 通过；Windows 真机验收经用户决定延后）。

## Current Slice

Slice 2/3：`phase3-requirements.md` 与 ADR-0008 编写完成，文档同步中。

## Current Goal

完成 Phase 3 的需求规范文档和数值微分/平滑的架构决策，为 Subphase 3.1–3.4 的实现提供设计依据。

## Recently Completed

- **Phase 3.0 — Spec & Requirements**（2026-08-30 进行中）：
  - `docs/spec/phase3-requirements.md`：标定 GUI / 运动学引擎 / 基础图表，10 条验收标准（AC-1…AC-10），Subphase 3.0–3.4 划分建议
  - `docs/decisions/0008-numerical-differentiation-and-smoothing.md`（ADR-0008）：Savitzky-Golay 先平滑后微分、默认 window=7 / polyorder=2、NaN 连续段分割策略
  - GitHub Issue #6 创建，工作分支 `feat/p3.0-spec-requirements`
- **Phase 2 — Video Analysis MVP**（✅ 2026-08-30）：完整的 GUI 视频分析 MVP——视频播放/缩放/平移、时间轴、手工标注（创建/删除 Track、逐帧标记）、项目生命周期（保存/加载/重连/保护）；macOS Human Review 通过；223 tests
- **Phase 1 — Project & Data Foundation**（✅ 2026-08-29）：统一数据体系、持久化、标定域模型；56 tests

## Current Decisions / Blockers

**已定决策**

- Python 3.11（ADR-0002）
- 持久化格式：JSON 清单优先混合方案（ADR-0003）
- 外部视频 locator（ADR-0004）
- Phase 2 GUI/视频栈：PySide6-Essentials + OpenCV headless + NumPy（ADR-0005）
- 项目工作流：候选提交与 FFprobe 时序关卡（ADR-0006）
- 响应式首帧预览与显式近似时序确认（ADR-0007）
- **数值微分与平滑：Savitzky-Golay 先平滑后微分（ADR-0008）**——window=7, polyorder=2, delta=1/fps_nominal；NaN 连续段分割；pipeline 注册表预留 butterworth/kalman 等

**本轮新增**：ADR-0008 确定数值微分方法；Phase 3 需求规范（10 条 AC）编写完成。

**延后项**：Windows 真机验收（原 P24-10）由用户决定延后执行。

## Next Recommended Action

完成 Subphase 3.0 收尾（文档同步提交 + 合并回 main + push），然后进入 **Subphase 3.1 — Calibration UI**：在 VideoView 上实现交互式标定工具（比例尺线段拖拽、坐标原点设置、旋转角输入、overlay 显示）。参照 `phase3-requirements.md` R1–R3 和 AC-1/AC-2。
