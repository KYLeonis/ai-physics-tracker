# Current Status

> 项目"现在在哪、下一步做什么"的**唯一权威入口**——不知道该做什么时先读这个文件。
> 每个开发会话结束时由 Agent 更新（规则见 `docs/workflow.md` §11）；人类可随时手写修改，人类改动优先于 Agent 的判断。

- 最后更新：2026-08-31（Phase 3.3 Human Review 5 轮通过，收尾中）

---

## Current Phase

**Phase 3 — Calibration & Physics Engine** 🔄 进行中

## Current Subphase

**3.3 — Interactive Charts / Charting UI** ✅ 已完成（Human Review 5 轮通过：
基础图表联动 → 多选轨迹同屏 → ？帮助气泡 → PNG 导出）。
[Issue #9](https://github.com/KYLeonis/ai-physics-tracker/issues/9) 已关闭；merge 见 git log。

上一 Subphase **3.2 — Kinematics Engine**（[Issue #8](https://github.com/KYLeonis/ai-physics-tracker/issues/8)）
已完成，并由 `3d3ad90` 合并至 `main`；本轮基线为 `e49132a`。原“先合并 3.2”建议已过期。

## Current Slice

无（3.3 已收尾，303 tests；等待 3.4 启动指令）

## Current Goal

将 3.2 的派生结果接入可交互图表，明确单位、缺测、呈现帧同步、时序授权与重算的
事务边界。按已确认计划实现并验证，交付后停在 Human Review；导出仍属 Phase 8。

## Recently Completed

- **Phase 3.3 本地增量（待 HR/CI）**：五标签页 QDockWidget、多 Track 叠加、物理/像素
  单位、缺测断线、呈现帧/目标帧双游标和 x-y 点选；SG 参数与后台批次重算、一次 Undo、
  保存/切换/取消隔离；首次标定 stale 与旧缓存标定引用守卫；请求编号贯穿解码成功/失败，
  修复旧结果覆盖新请求。功能提交 `79c4795` / `69c0864`，**297 passed**，复审通过。

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

**3.3 已确认方案与当前事项**

- PyQtGraph 0.13.7（spec 范围 >=0.13,<0.14）；项目依赖已安装并完成 Qt/NumPy smoke test。
- 首次设置标定后既有 px 派生数据未置 stale 的缺口已修复。兼容已有
  `world_position(px)` 命名，界面按实际单位/标定引用显示，不迁移原始数据。
- 时序权限、后台批次提交和 GUI 已呈现帧通知已补齐；绘图层不重做数值引擎。
- 本地 `.venv` 已按授权从 SciPy 1.18.1 对齐至锁定的 **1.17.1**；260 项原有回归再次通过。
  尚未验证远端 Windows Python 3.11。本轮不修改 CI。
- Phase 2 Windows 真机验收按用户决定延后，继续保留后续事项；3.3 远端 CI 也尚待执行。

## Next Recommended Action

等待用户按 [3.3 计划中的 Human Review](phase-3.3-plan.md) 亲测并逐项反馈，暂不继续开发。
未通过则按反馈修复并重验；通过后申请 push 授权、运行双平台 CI，再合并/关闭 Issue #9，
进入 3.4。push、CI 配置修改仍需单独授权，本轮未推送或修改 CI。
