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

---

## 4. 收尾后复核（2026-09-03）

实现合并与 Human Review 后的独立仓库复核确认原 review findings 均已处置，但发现原审查范围
遗漏以下收口项：

1. `serialize_refinement_state()` 写出 `validation_series` list，而 ADR-0014 规定规范形态为
   `series_id → ValidationSeries` mapping；reader 已兼容两者，writer 尚待对齐。
2. 缺少“两次 train run 使用同一 validation series”及“不同 series 不直接比较”的明确测试证据。
3. Task history/details 尚未完整显示计划要求的 label/review/prediction coverage/remaining candidates
   信息及不可比较原因。

因此本 Review Record 的原 findings 处置结论仍成立，但 Phase 5.4 整体最终状态改为
**Follow-up required**；上述项目列入 Phase 5.5 mini-plan 的 Entry Gate，关闭前不开始 Advisor 实现。

---

## 4. 合并后复审（R2 轮，2026-09-03 · 用户指令的风险排查专项）

**执行方式**：三个 GLM-5.3-Flash 只读 subagent 并行（激活事务与领域契约 / 数据泄漏防线 / GUI 生命周期），
基线 652 passed，合并 commit CI 绿（run 33771353773）。已排除首轮 D-*/G-* findings。

### 结论

三方均 **approve-with-comments**，无 Blocker。最关键的防泄漏契约经独立验证**真实成立**：
DLC `trainIndices/testIndices` 为全局帧位置语义（`trainingsetmanipulation.py:1113-1136`、
`dlcloader.py:296-306` 只用 `df_train`）；PNG 字典序与应用侧 enumerate 对齐成立；
per-run 全新 DLC 项目使 shuffle 恒为 1；取消/失败路径干净。

### 已直修（轻量，本轮 commit）

| # | 来源 | Severity | 问题 | 修复 |
| --- | --- | --- | --- | --- |
| 1 | 领域 M-1 | Medium | `manual_preserved_count` 在 activate/replace 存 superseded 数、在 clear 存 manual 数，语义不一致 | 统一为"操作时 active manual 点数"；`ActivationRecord` 新增容错字段 `superseded_count`，序列化/反序列化同步；测试断言更新 |
| 2 | 领域 L-1 | Low | 激活路径对损坏产物抛裸 `JSONDecodeError`/`KeyError` | 包裹为 `ProjectSessionError`（含 run id 与路径上下文） |
| 3 | 领域 L-2 | Low | status="none" 时 `replace_active_infer_run` 仍成功，污染激活历史 | 显式拒绝（legacy 两态保留放行） |
| 4 | 领域 L-4 | Low | 容错反序列化可产出零快照空 series 并可设为活动集 | 有效快照为空时整条丢弃（返回 None） |
| 5 | 领域 L-6 | Low | 激活/替换缺 `can_measure` 门禁，与 `import_engine_points` 口径不一 | 补齐授权检查 |
| 6 | 泄漏 F-2 | Medium | PNG 固定 5 位宽度：帧号 ≥100000 时字典序 ≠ 数值序，train/test 索引静默错位 | 宽度跟随视频总帧数（`max(5, len(str(frame_count-1)))`）；per-run 目录无旧名引用负担 |
| 7 | 泄漏 F-4/领域 L-5 | Low | `training_job.py` 用 `Any` 未导入 | 补 import |
| 8 | 泄漏 F-6 | Nit | 空 list 的 train/test 索引通过互斥检查后静默不建集 | 显式拒绝空 list |
| 9 | 泄漏 F-3 | Medium | history 详情未展示 train run 所用 validation series，违反"不同 series 不宣称可直接比较" | `_runDetails` 增加 `validation_series=` 行 |
| 10 | GUI F-2(缓解) | High | 崩溃后遗留 pending/running run 使 track 永久锁死，激活按钮却可用（点击必失败） | GUI 缓解：当前 track 存在 pending/running run 时禁用四个按钮并给 tooltip；**根治需用户批准**（见延期项） |
| 11 | GUI F-3 | Low | autosave 窗口期按钮可用但静默无效 | `setContext` 新增 `project_busy`，矩阵随项目操作禁用 |
| 12 | GUI F-4 | Low | 项目级 history 把其他 track 的 active run 标为 "Not active" | 新增 "Active (other track)" 标注（`setRuns` 接收 per-track active 映射） |
| 13 | GUI F-5 | Low | 激活/验证集操作守卫缺 frameSelection/review busy | `_interaction_blocked()` 统一互斥口径 |
| 14 | GUI F-1 | Medium | Replace/Clear 确认框缺 from-run 与点数统计（plan AC 已勾选但实现不符） | 对话框补 from-run id、manual 点数、目标 run 预测点数（`prediction_summary_v1.eligible_count`） |
| 15 | GUI F-7 | Nit | legacy_inferred 选中被推断 run 时 Replace 禁用无解释 | tooltip 说明 Clear→Activate 路径 |

全量回归 **658 passed**（652 + 新增 6），compileall 通过。

### 需要决策/大修（不阻塞，已记录待处置）

| # | Severity | 问题 | 建议处置 |
| --- | --- | --- | --- |
| A | High | **崩溃恢复死锁（GUI F-2 根因）**：任务运行中项目被保存（autosave/手存），之后强退 → 重开后 pending/running run 无进程对应，train/infer/激活全部永久禁用 | **已批复（2026-09-04）：方案 1 批准**——打开项目时把无对应进程的 pending/running run 标记为 failed（含 "interrupted by shutdown" 信息）。实施排入 **5.6 Slice 0** |
| B | Medium | **shuffle 数量/编号语义错位（泄漏 F-1）**：复用同一 DLC 项目目录二次建集会创建 shuffle 2，而训练仍跑 shuffle 1（旧划分）——series 变化即真实泄漏；当前 GUI 因 per-run 新目录不可达 | **已批复（2026-09-04）：方案 2**——删除 prepare_training 的 DLC 目录复用路径，强制每次训练使用全新 per-run 目录，从根上消除该场景。实施排入 **5.6 Slice 0** |
| C | Medium | **产物指纹 mtime 纳秒强等值（领域 M-2）**：合法文件拷贝/备份还原改变 mtime 后候选永久无法激活 | **已批复（2026-09-04）：方案 2**——激活时的产物指纹放宽为仅比对文件大小（接受防篡改强度下降）。实施排入 **5.6 Slice 0** |
| D | Low | GUI F-6：非活动 validation series 无法删除、无限累积 | 5.5+/Phase 7（模型库清理）一并处理 |
| E | Low | 领域 L-3：`refinement_state_v1` 内部未知键在下次写盘被丢弃 | 已选择"文档化契约"方案：序列化处注明内部结构由 v1 独占，扩展需升级版本号 |

