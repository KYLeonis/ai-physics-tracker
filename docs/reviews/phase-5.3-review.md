# Review Record — Phase 5.3 Suggested Frame Review & Correction

> **用法**：一个 subphase 一个文件，贯穿整个审查生命周期。
> **审查依据**：diff 与 Context 文档判断。流程规则见 `docs/workflow.md` §6。

- Subphase / Issue：5.3 — Suggested Frame Review & Correction · [#20](https://github.com/KYLeonis/ai-physics-tracker/issues/20)
- Review 范围（commits）：
  - Slice 1：`bae2af2`（审核契约、值对象、会话事务与 scoped Undo/Redo）
  - Slice 2：`b53e843`（挖掘发起入口、审核队列控制器、快捷键路由）
  - Slice 3：`b2c40a0`（审核区、导航、一次性 Correct 模式、完成统计、当前帧 manual 删除）
- Context：`docs/spec/phase5-requirements.md` R3/R8、`docs/status/phase-5.3-plan.md`、ADR-0013（run-scoped 审核状态持久化）
- 轮次：R1 2026-09-03（2 智能体并发只读审查：Domain & Session Reviewer + GUI & Concurrency Reviewer）

---

## Findings & Dispositions (R1)

### 1. Domain & Session Reviewer Findings

| # | Priority | 问题 | 处置 | 状态 |
|---|---|---|---|---|
| **D-01** | **[P1]** | `accept_suggested_frame` / `skip_suggested_frame` 允许对已修正（corrected）候选直接执行，导致原 manual point 孤立且与 review 状态脱节 | 在 `accept_suggested_frame` 和 `skip_suggested_frame` 中检查当前帧若为 `DISPOSITION_CORRECTED` 则抛出 `ProjectSessionError`，强制要求用户先删除 manual point 或 Undo 才能修改 disposition | **Closed** |
| **D-02** | **[P2]** | `delete_active_manual_point` 中直接调用 `extract_review_state(r)`，遇到畸变 extra_fields 时抛出未捕获的 `ValueError` | 改为调用安全的 `self.get_suggested_frame_review(r.run_id)`（内置 try-except 容错） | **Closed** |
| **D-03** | **[P2]** | `prepare_difficult_frame_request` 中未对历史排除帧/先验帧作视频最大帧号范围过滤，视频缩短时可能触发校验异常 | 过滤 `excluded_review_frames` 与 `resolved_prior_correct` 到 `0 <= f < video.frame_count` 范围 | **Closed** |
| **D-04** | **[P3]** | `ReviewQueueController.correct_current` 中使用裸 `assert st is not None` | 替换为显式 `if st is None or c.frame_index not in st.reviewed_frames: raise ValueError(...)` 检查 | **Closed** |
| **D-05** | **[P3]** | `ReviewCandidate` 为 frozen dataclass，但内部 `components` 和 `raw_components` 字典未作防御性拷贝 | 在 `__post_init__` 中使用 `object.__setattr__` 进行深拷贝转换字典 | **Closed** |

### 2. GUI & Concurrency Reviewer Findings

| # | Priority | 问题 | 处置 | 状态 |
|---|---|---|---|---|
| **G-01** | **[P1]** | 跨 Track 上下文错乱：在 Task history 中选择其他 Track 的 run 时，审核面板仍被激活且可能错标 | 在 `onRunSelected` 中严格要求 `run.track_id == self.window.selectedTrackId`，不一致或无选中 Track 时置空控制器并禁用审核面板；切 Track 时取消 Correct 模式 | **Closed** |
| **G-02** | **[P1]** | 异步解码在途时删除点竞态：`_deleteCurrentManualPoint` 缺少 `_has_pending_request` 保护，可能误删旧帧人工点 | 在 `_deleteCurrentManualPoint` 头部增加 `if self._has_pending_request: return` 守卫与状态栏提示 | **Closed** |
| **G-03** | **[P1]** | Correct 模式下步进/拖动时间轴/播放未退出 Correct 模式，画面点击会导致坐标错位到目标候选帧 | `handleCorrectClick` 增加 `presented_frame_index == c.frame_index` 校验；在 `_step`、`_goToFrame`、`_scrubStarted`、`startPlayback` 中自动取消 Correct 模式 | **Closed** |
| **G-04** | **[P1]** | 队列为空或无选中候选时按快捷键 `A` / `S` 触发未捕获 `ValueError` 导致 GUI 崩溃 | 在 `acceptCurrent`、`skipCurrent` 和 `MainWindow` 快捷键处理函数中增加候选有效性前置检查 | **Closed** |
| **G-05** | **[P2]** | `Accept` 和 `Skip` 未刷新 MainWindow 撤销/重做按钮、脏状态及自动保存触发器 | 在 `acceptCurrent` 和 `skipCurrent` 中同步调用 `_refreshHistoryButtons()`、`_refreshDeletePointButton()` 和 `_register_mark_for_autosave()` | **Closed** |
| **G-06** | **[P2]** | 取消 Correct 模式（Esc 或切 Track）未重置 `videoView.set_annotation_mode(False)` | 在 `cancelCorrectMode()` 中显式调用 `self.window.videoView.set_annotation_mode(False)` | **Closed** |
| **G-07** | **[P2]** | `DifficultFrameReviewActions.shutdown()` 使用 `cancel_futures=True`，可能取消正在排队的取消任务 | 改为 `cancel_futures=False`，确保正在排队的取消操作能可靠投递给工作进程 | **Closed** |
| **G-08** | **[P2]** | 快捷键与输入框焦点防冲突缺少自动化测试覆盖 | 在 `test_suggested_frame_review_actions.py` 中增加 5 个测试，覆盖 `QTest.keyClick`、输入焦点防冲突、空队列稳定性与跨 Track 隔离 | **Closed** |
| **G-09** | **[P3]** | 切换 Track 或关闭项目时未清除 `mineStatusLabel` 残留文本 | 在 `onSelectedTrackChanged` 和 `onProjectChanged` 中重置 `setMineStatus("")` | **Closed** |
| **G-10** | **[P3]** | `handleCorrectClick` 缺少 `ProjectSessionError` 异常壁垒 | 使用 try-except 包裹 `ctrl.correct_current`，捕获领域与参数异常并输出到状态栏 | **Closed** |

---

## Verification

所有修复均通过定向与全量自动化测试验证：

```bash
# 定向审核与 GUI 测试（16/16 passed）
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/gui/test_suggested_frame_review_actions.py

# 核心领域与层边界测试（109/109 passed）
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_suggested_frame_review.py tests/test_project_session.py tests/test_difficult_frames.py tests/test_layer_boundaries.py

# 全量测试套件（621/621 passed）
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest
```

- **全量结果**：`621 passed in 47.67s`
- **层边界检查**：`tests/test_layer_boundaries.py` 5/5 全部通过，零架构层越界导入。
- **R1 结论**：**Approve**。12 项 finding 全部妥善处置闭环，Slice 1–3 代码健壮性达标，可推进至 Slice 4。

---

## Findings & Dispositions (R2: Slice 4 & Full Reliability Review)

- 轮次：R2 2026-09-03（2 智能体并发只读审查：Test & Spec Reviewer + Domain & Concurrency Reviewer）
- Review 范围：`tests/gui/test_suggested_frame_review_reliability.py`、Slice 4 可靠性矩阵及全生命周期边界。

| # | Reviewer | Priority | 问题 | 处置 | 状态 |
|---|---|---|---|---|---|
| **T-01** | Test & Spec | **[P1]** | 对已 corrected 候选在 GUI 上仍使能 Accept/Skip 按钮，且 `acceptCurrent` / `skipCurrent` 缺少异常屏障，导致领域异常泄漏到 Qt 事件循环 | 在 `TaskPanel.setReviewBatch` 中若 `disp == "corrected"` 则禁用 Accept/Skip 按钮并设提示；在 `acceptCurrent` 和 `skipCurrent` 中增加 try-except 异常屏障与状态栏提示；测试中增加 GUI 级点击与提示断言 | **Closed** |
| **T-02** | Test & Spec | **[P1]** | `MainWindow._onAnnotationClicked` 中 Correct 处理失败或帧不匹配时穿透到底部执行普通 `mark_point` | 将 `return` 移出 `if handled:` 块，确保在 `is_correcting` 模式下无论处理结果如何均立即返回，绝不穿透；新增帧不匹配穿透防护测试 | **Closed** |
| **C-01** | Domain & Concurrency | **[P1]** | 困难帧挖掘与 AI 训练/推理、建议帧选取三者缺少双向互斥，可能引发多任务并发冲突 | 在 `DifficultFrameReviewActions._refresh_mining_enabled` / `requestMining`、`TrackingActions.refresh` / `_start` 及 `FrameSelectionActions` 中补齐三方双向互斥与状态提示 | **Closed** |
| **C-02** | Domain & Concurrency | **[P2]** | `MainWindow.seekFrame()` 编程式跳帧（图表点击、建议帧双击）未退出 active Correct 模式，导致界面高亮残留与后续点击帧不匹配 | 在 `seekFrame()` 头部增加 `cancelCorrectMode()` 调用；增加测试验证图表跳帧时自动退出 Correct 模式 | **Closed** |
| **C-03** | Domain & Concurrency | **[P2]** | `DifficultFrameReviewActions` 缺少 `_closed` 生命周期保护标志与 `shutdown()` 状态重置 | 增加 `self._closed = False`；在 `_poll()` 中快速返回；在 `shutdown()` 中重置 `_reset()` 并停止计时器 | **Closed** |
| **T-03** | Test & Spec | **[P2]** | AC-9 参数微调框 (Top N, Min Gap) 传参连通性与 AC-5 重开后修正点坐标精度未在 GUI 测试中断言 | 新增 `test_mining_params_spinbox_wiring_ac9`；在 `test_save_reopen_and_resume_review_matrix` 中增加重开后修正点坐标与 manual 属性断言 | **Closed** |

---

## Final Verification Summary

所有 R1 与 R2 的 18 项审查意见全部清零闭环，并通过全量自动化测试验证：

```bash
# 全量测试套件（631/631 passed）
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest
```

- **测试通过率**：`631 passed in 49.62s`（0 failed, 0 skipped）
- **层边界检查**：`tests/test_layer_boundaries.py` 5/5 通过，架构依赖与 ADR-0013 保持 100% 一致。
- **最终评审裁定**：**Pass / Ready for Human Review**。代码健壮性、状态机安全性与可靠性矩阵完备，正式发起真人验收（Human Review）。
