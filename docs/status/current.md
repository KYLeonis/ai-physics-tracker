# Current Status

> 项目"现在在哪、下一步做什么"的**唯一权威入口**——不知道该做什么时先读这个文件。
> 每个开发会话结束时由 Agent 更新（规则见 `docs/workflow.md` §11）；人类可随时手写修改，人类改动优先于 Agent 的判断。

- 最后更新：2026-09-02（Subphase 5.1 代码+测试完成，**等待 Human Review**）

---

## Phase / Subphase / Slice

| Level | Name | Status |
| --- | --- | --- |
| Phase | Phase 5 — AI-assisted Annotation & Refinement | 🚧 进行中 |
| Subphase | 5.0 — Tracking Pipeline Consolidation | ✅ 已完成 (2026-09-02) |
| Subphase | 5.1 — Representative Frame Selection | 🚧 S1–S4 完成，**等待 Human Review** |

## Recently Completed

- **Phase 5.1 — Representative Frame Selection**（2026-09-02，开发与 3 智能体并发 Review 完成，**等待 Human Review**）：
  - S1：`FrameSelectionRequest` + `FrameSelectionResult` Qt-free 数据类（`application/tracking_types.py`）
  - S2：`EngineAdapter` Protocol 新增 `suggest_frames`；`DLCAdapter`（uniform / K-means + scipy fallback，显式支持 color_mode 与 cancel）；`MockEngineAdapter` 确定性实现
  - S3：`FrameSelectionRunner` + `prepare_frame_selection_request`（严格从 `session.project.timelines` 取 working_zone）+ `run_frame_selection_worker` + `read_frame_selection_result`（`application/tracking_job.py`）
  - S4：`TaskPanel` 新增建议帧控件组；`FrameSelectionActions`（含 IPC 错误消费、会话切换/窗口关闭取消、互斥守卫）；`MainWindow.jumpToFrame`（跳帧后保持标注模式）
  - 独立审查：3 个并发子智能体审查识别 7 项 Finding，全部修复闭环（见 [phase-5.1-review.md](../reviews/phase-5.1-review.md)）
  - 全回归：**494 passed in 64.60s**（新增 45 单元测试 + 16 GUI offscreen 测试，原 433 不退化）
- **Phase 5.0 — Tracking Pipeline Consolidation**（✅ 2026-09-02，merge `5569e93`）：TrackingJobRunner 统一，433 tests 通过，CI 双平台绿。
- **Phase 5 规划**（2026-09-01，只改文档）：新增 `phase5-requirements.md` + `phase-5-plan.md`。
- **Phase 4 — Deep Learning Tracking**（✅ 2026-09-01）：4.0–4.5 全部完成，CI macOS/Windows 双平台绿，Issue #15 已关闭。

## Current Goal

**Human Review（AGENTS.md §7）**

GUI 交互包含用户可感知行为（建议帧列表、跳帧），需要用户亲自在 macOS 验收。

## Current Decisions / Deferred Checks

**已定决策**

- DeepLabCut 集成架构（ADR-0011）：适配器隔离 + 后台子进程 (spawn 模式) + 单 bodypart 先行
- K-means 选帧：优先调用 DLC `KmeansbasedFrameselection` + sklearn；不可用时退回 scipy fallback
- `FrameSelectionResult` 只含帧号，不创建 TrackPoint（Phase 5.1 R1 核心约束）

**已批准延期**：Windows 真机/CUDA 延期到 Phase 9 打包前；DLC K-means 真实视频视觉效果留 Human Review 确认。

## Next Recommended Action

**请执行 Human Review**，按以下步骤操作，然后回复结果：

```bash
# macOS 启动（已有 .venv）
cd /Users/leonis/Documents/ai-physics-tracker
source .venv/bin/activate
python -m ai_physics_tracker.gui.app
```

验收步骤：
1. 打开一个现有项目（或新建 + 打开视频 + 新建 Track）
2. 打开底部 **AI tasks** 面板
3. 找到左侧 **"Suggest Representative Frames"** 控件组
4. 选择算法（K-means 或 Uniform）、设置帧数（如 10）
5. 点击 **"Suggest Frames"** 按钮
6. 等待结果出现在列表中（应显示帧号与 excluded 统计）
7. **双击**一个建议帧 → 确认视频跳转到该帧
8. 确认跳帧后**无新 manual 标记点**（建议帧不自动打标）

请回答：
- Q1：建议帧列表是否正常显示？（是/否）
- Q2：双击跳帧是否工作？（是/否）
- Q3：跳帧后确认无自动 TrackPoint 创建？（是/否）
- Q4：有无 UI 体验问题？

**Human Review 通过后**：Agent 执行 git commit + push，停止等待 Phase 5.2 指令。
