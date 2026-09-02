# Review Record — Phase 5.1 Representative Frame Selection

> **用法**：一个 subphase 一个文件，贯穿整个审查生命周期。
> **审查依据**：diff 与 Context 文档判断。流程规则见 `docs/workflow.md` §6。

- Subphase / Issue：5.1 — Representative Frame Selection
- Review 范围（commits / 分支 / 文件）：
  - `src/ai_physics_tracker/application/tracking_types.py`
  - `src/ai_physics_tracker/infrastructure/engine_adapter.py`
  - `src/ai_physics_tracker/infrastructure/dlc_adapter.py`
  - `src/ai_physics_tracker/infrastructure/mock_engine_adapter.py`
  - `src/ai_physics_tracker/application/tracking_job.py`
  - `src/ai_physics_tracker/gui/task_panel.py`
  - `src/ai_physics_tracker/gui/tracking_actions.py`
  - `src/ai_physics_tracker/gui/main_window.py`
  - `tests/test_frame_selection.py`
  - `tests/gui/test_frame_selection_actions.py`
- Context（spec / ADR / plan 路径）：`docs/spec/phase5-requirements.md` (R1 / AC-1), `docs/status/phase-5.1-plan.md`
- 轮次：R1 2026-09-02（多智能体并发审查：Domain & Engine, GUI & Concurrency, Test & Spec）

## Checklist

**正确性**

- [x] 实现与 subphase plan 的 AC / 相关 spec 一致（R1 / AC-1 建议帧不落盘、不造点）
- [x] 边界情况处理正确（空候选、全排除、 working zone 边界、取消事件）
- [x] 数值逻辑有合成数据验证（合成 OpenCV 视频、Uniform / K-means 采样收敛）

**质量**

- [x] diff 无范围外改动
- [x] 遵守 `docs/development.md` §1.1 可移植性规则（pathlib / UTF-8 / 无 symlink / Windows 保留名）
- [x] 公开接口与数据结构有说明，命名与既有代码一致
- [x] 测试真实覆盖新逻辑，包含合成视频真实抽帧与完整异步调度生命周期

**流程**

- [x] 提交信息符合 Conventional Commits
- [x] 属于 ADR 级别的决策是否已记录（复用既有 Phase 4 / Phase 5 决策，无破坏性变更）

## Findings

### F1 — `prepare_frame_selection_request` 错误访问 `video.timeline` 与 `video.working_zone` 导致运行时异常

- **Severity**：Blocker
- **Evidence**：`src/ai_physics_tracker/application/tracking_job.py:363` 原代码直接读取 `video.timeline`，而 `Video` 领域模型不持有 `timeline` 与 `working_zone`。
- **Impact**：在真实会话中发起代表帧选取会抛出 `AttributeError` 崩溃。
- **Recommendation**：从 `session.project.timelines` 中根据 `track.video_id` 查找 `Timeline` 并获取 `working_zone`。
- **Decision**：Fix Now —— 核心领域模型边界必须正确。
- **Fix commit**：working directory fix
- **Verification**：`tests/test_frame_selection.py::TestPrepareFrameSelectionRequest`（3 个测试全部通过）
- **Status**：Closed

### F2 — `_kmeans_suggest` 捕获通用 `Exception` 吞并 `CancelledError`

- **Severity**：Blocker
- **Evidence**：`src/ai_physics_tracker/infrastructure/dlc_adapter.py:815`
- **Impact**：用户取消时被误判定为普通异常并进入 fallback 重复计算。
- **Recommendation**：在捕获通用异常前显式 `except CancelledError: raise`。
- **Decision**：Fix Now
- **Fix commit**：working directory fix
- **Verification**：`tests/test_frame_selection.py::TestDLCAdapterSuggestFramesSynthetic::test_dlc_adapter_kmeans_cancelled`
- **Status**：Closed

### F3 — 上下文切换与窗口关闭时未取消后台执行的子进程

- **Severity**：Blocker
- **Evidence**：`src/ai_physics_tracker/gui/tracking_actions.py`
- **Impact**：切换 track/project 或关闭窗口后，后台计算密集型进程继续运行变成孤儿进程。
- **Recommendation**：在 `_onContextChanged` 与 `shutdown` 中调用 `_cancel_active_task`。
- **Decision**：Fix Now
- **Fix commit**：working directory fix
- **Verification**：`tests/gui/test_frame_selection_actions.py::TestFrameSelectionActions::test_context_change_cancels_running_task`
- **Status**：Closed

### F4 — `FrameSelectionActions._poll` 未消费 IPC 消息导致错误原因被掩盖

- **Severity**：Blocker
- **Evidence**：`src/ai_physics_tracker/gui/tracking_actions.py`
- **Impact**：后台 worker 失败时，UI 显示 "Frame selection result not found" 而非真实错误原因。
- **Recommendation**：在 `_poll()` 中读取 `poll_messages()` 并检查 `TaskResult` 的 success 与 error 字段。
- **Decision**：Fix Now
- **Fix commit**：working directory fix
- **Verification**：`tests/gui/test_frame_selection_actions.py::TestFrameSelectionActions::test_async_workflow_failure_shows_error`
- **Status**：Closed

### F5 — `jumpToFrame` 跳帧后丢失标注模式

- **Severity**：Suggestion
- **Evidence**：`src/ai_physics_tracker/gui/main_window.py:382`
- **Impact**：用户双击建议帧后视频处于 Browse 模式，需要重新在 Track 列表中点击选中才能打标。
- **Recommendation**：在 `jumpToFrame` 中若当前有选中 Track 且允许测量，激活 `set_annotation_mode(True)`。
- **Decision**：Fix Now
- **Fix commit**：working directory fix
- **Verification**：`tests/gui/test_frame_selection_actions.py::TestFrameSelectionActions::test_jump_to_frame_restores_annotation_mode`
- **Status**：Closed

### F6 — 修复 GUI 测试中永真断言并在真实会话中断言不变式

- **Severity**：Blocker
- **Evidence**：`tests/gui/test_frame_selection_actions.py` 原代码 `assert all(p.source != "manual" or True for p in points)`
- **Impact**：测试无效，无法守护"建议帧不自动生成 TrackPoint"的核心契约。
- **Recommendation**：在带项目的会话中，断言建议帧前后 manual 点数严格不变且内容一致。
- **Decision**：Fix Now
- **Fix commit**：working directory fix
- **Verification**：`tests/gui/test_frame_selection_actions.py::TestTaskPanelSuggestControls::test_suggest_frames_not_creating_track_points_invariant`
- **Status**：Closed

### F7 — 补齐 DLCAdapter 合成视频测试与 FrameSelectionRunner 单元测试

- **Severity**：Suggestion
- **Evidence**：`tests/test_frame_selection.py`
- **Impact**：缺少对真实 OpenCV 抽帧与 K-means 聚类逻辑的离线自动化测试。
- **Recommendation**：补充基于合成 OpenCV 视频的 uniform / kmeans / cancelled 测试。
- **Decision**：Fix Now
- **Fix commit**：working directory fix
- **Verification**：`TestDLCAdapterSuggestFramesSynthetic` (3 tests), `TestFrameSelectionRunner` (1 test)
- **Status**：Closed

## Review Log

### R1 — 2026-09-02 · 首轮（3 智能体并发审查）

- 范围 / 基线：Subphase 5.1 完整实现（S1–S4 与测试）
- 结论（一句话）：识别 1 项 P0 缺陷、5 项 P1 缺陷与多项建议，全部 7 项 Finding 已完成就地修复并通过 494 项全回归测试。
- Findings 变化：新增 F1–F7；全部修复并验证为 Closed。

## Final Verdict

- [x] 修改后通过（findings 按 Decision 处置完毕，复审确认）

- 最终结论：Subphase 5.1 领域模型、算法适配器、后台任务及 GUI 交互实现健壮，7 项 Finding 全部修复，全库 494 测试全绿，准备进入 Human Review。
- 日期 / 依据轮次：2026-09-02 · R1
