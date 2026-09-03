# Review Record: Phase 5.4 — Result Activation, Refinement History & Fixed Validation

**Subphase**: Phase 5.4 — Iteration History & Result Activation  
**日期**: 2026-09-03  
**分支**: `feat/p5.4-result-activation-history`  
**Reviewers**:
- Subagent 1: `Domain & Transaction Reviewer` (Model: Gemini 3.8 Flash, Read-Only)
- Subagent 2: `GUI & Test Reviewer` (Model: Gemini 3.8 Flash, Read-Only)

---

## 1. 审查范围

- **数据与领域契约**: `src/ai_physics_tracker/application/refinement_history.py`、`src/ai_physics_tracker/domain/track_store.py`、`src/ai_physics_tracker/domain/tracking_run.py`、`docs/decisions/0014-result-activation-and-fixed-validation-history.md`
- **训练与引擎集成**: `src/ai_physics_tracker/application/training_job.py`、`src/ai_physics_tracker/infrastructure/dlc_adapter.py`
- **推理候选与激活事务**: `src/ai_physics_tracker/application/tracking_job.py`、`src/ai_physics_tracker/application/inference_job.py`、`src/ai_physics_tracker/application/project_session.py`
- **GUI 交互与状态机**: `src/ai_physics_tracker/gui/task_panel.py`、`src/ai_physics_tracker/gui/tracking_actions.py`、`src/ai_physics_tracker/gui/validation_dialog.py`
- **测试覆盖**: `tests/test_refinement_history.py`、`tests/test_result_activation.py`、`tests/test_track_store.py`、`tests/gui/test_task_panel.py`、`tests/gui/test_tracking_activation_actions.py`

---

## 2. Findings 汇总与处置

### Subagent 1: Domain & Transaction Reviewer Findings

| ID | 等级 | 模块 | 发现描述 | 处置方案与验证 |
|---|---|---|---|---|
| **D-01** | **[P1]** | `refinement_history.py` | `validation_series` 反序列化仅支持 list，若项目文件或外部格式按 ADR-0014 存为字典映射将静默丢失历史。 | **已修复**：`deserialize_refinement_state` 宽容兼容 list 与 dict；新增字典形式反序列化单元测试。 |
| **D-02** | **[P2]** | `dlc_adapter.py` | `train_indices` 与 `test_indices` 单边传入时静默回退到随机划分，存在验证集数据泄露隐患。 | **已修复**：增加互斥检查 `if (train_indices is None) ^ (test_indices is None): raise ValueError(...)`。 |
| **D-03** | **[P2]** | `track_store.py` | `replace_track_engine_points` 校验了 `point_id` 唯一性，但未校验传入观测的 `frame_index` 唯一性。 | **已修复**：增加帧号唯一性断言 `if len(set(frames)) != len(frames): raise ValueError(...)` 并编写测试。 |
| **D-04** | **[P2]** | `project_session.py` | `activate_infer_run` 与 `clear_active_ai_observations` 缺少应用层活动任务互斥保护（可能在后台推理时被调用）。 | **已修复**：增加 `if any(r.track_id == track_id and r.status in {"pending", "running"}): raise ProjectSessionError(...)`。 |
| **D-05** | **[P3]** | `refinement_history.py` | `RefinementIterationInfo` 虽为 frozen dataclass，但 `review_summary` 是可变字典。 | **已修复**：在 `__post_init__` 中执行浅拷贝保护；确保不可变性。 |
| **D-06** | **[P3]** | `dlc_adapter.py` | `[list(train_indices)] * num_shuffles` 产生了对同一子列表引用的共享。 | **已修复**：改为列表推导式 `[list(train_indices) for _ in range(num_shuffles)]`。 |
| **D-07** | **[P3]** | `project_session.py` | 当 Track 的 AI 激活状态已为 `"none"` 时，`clear_active_ai_observations` 仍产生空记录。 | **已修复**：状态为 `"none"` 时抛出显式错误 `Track has no active AI observations to clear`。 |
| **D-08** | **[P3]** | `refinement_history.py` | 验证集标签一致性诊断信息将重新打点归为坐标修改。 | **已修复**：区分 `point_id` 改变（replaced）与坐标偏差（modified）。 |

### Subagent 2: GUI & Test Reviewer Findings

| ID | 等级 | 模块 | 发现描述 | 处置方案与验证 |
|---|---|---|---|---|
| **G-01** | **[P1]** | `tracking_actions.py` | `activateRun`、`replaceRun`、`clearActivation` 成功后未调用 `_refreshMarkers()`、`_refreshHistoryButtons()`，导致画面点位和工具栏撤销按钮未联动更新。 | **已修复**：操作成功后均调用 `_refreshMarkers()` 与 `_refreshHistoryButtons()`（联动派发 `analysisChanged`）。 |
| **G-02** | **[P1]** | `task_panel.py` | 跨 Track 选中 completed infer run 时依然使能 Activate / Replace 按钮，点击后弹窗报错。 | **已修复**：`_updateActivationButtonStates` 严格断言 `run.track_id == self._current_track_id`。 |
| **G-03** | **[P2]** | `task_panel.py` & `tracking_actions.py` | 后台训练/推理任务忙碌时未禁用激活/替换/清除与验证集按钮，未阻止并发调用。 | **已修复**：`setContext` 传入 `_busy` 禁用全部激活按钮；操作前置检查 `if self.pending or self.window.projectActions.busy: return`。 |
| **G-04** | **[P2]** | `tracking_actions.py` | `manageValidation()` 冻结/删除验证集后未刷新主窗口撤销/重做按钮。 | **已修复**：对话框关闭后调用 `_refreshHistoryButtons()`。 |
| **G-05** | **[P2]** | `test_task_panel.py` | 缺少对 `historyList` 条目文本（`Active`、`Completed · Not active`、`iter N`）的断言。 | **已修复**：在 `test_task_panel.py` 增加完整条目状态与文本断言。 |
| **G-06** | **[P2]** | `test_tracking_activation_actions.py` | 缺少针对 Replace 与 Clear 对话框点击“No”取消的测试及撤销按钮状态验证。 | **已修复**：补齐 Replace/Clear 弹窗取消断言与 `undoButton.click()` 测试。 |
| **G-07** | **[P3]** | `validation_dialog.py` | 手工点不足 4 个时 Freeze 按钮禁用无 tooltip 提示原因。 | **已修复**：补充明确 tooltip（需要至少 4 个手工点，1 个用于验证，3 个用于训练）。 |
| **G-08** | **[P3]** | `validation_dialog.py` | 手工点选择框列表未按 `frame_index` 升序排序。 | **已修复**：按 `p.frame_index` 排序展示。 |
| **G-09** | **[P3]** | `test_result_activation.py` | 缺少对激活非 infer run（如 train run）或未完成 run 的领域异常拒绝断言。 | **已修复**：新增 `test_activation_rejects_invalid_task_type_incomplete_or_cross_track` 覆盖。 |

---

## 3. 验证与回归结果

1. **定向与全量自动化测试**:
   - `tests/gui/test_task_panel.py`: 5 passed
   - `tests/gui/test_tracking_activation_actions.py`: 2 passed
   - `tests/test_result_activation.py`: 5 passed
   - `tests/test_refinement_history.py`: 9 passed
   - `tests/test_track_store.py`: 9 passed
   - **全量回归**: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest` → **652 passed** (耗时 ~51s)。
2. **字节码编译检查**:
   - `.venv/bin/python -m compileall src scripts tests` → 0 errors。
3. **真实 DeepLabCut 3.x 固定验证集训练冒烟**:
   - `.venv/bin/python scripts/smoke_test_dlc_train.py` → **PASSED**（自动同步 `TrainingFraction`，3/2 互斥划分，1 epoch 训练并产出 `snapshot-001.pt`）。
