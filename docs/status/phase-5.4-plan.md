# Subphase Plan — Phase 5.4 Iteration History & Result Activation

- Issue：未创建（GitHub 当前不存在文档曾引用的 #21；流程记录遗漏）
- 分支：`feat/p5.4-result-activation-history`（已合并并清理）
- 日期 / 状态：2026-09-03 · ⚠️ 实现已合并、Review/Human Review 已通过；收尾复核发现 2 项 AC 证据/展示缺口

## Goal

把“推理完成”与“当前轨迹采用该结果”彻底分开：多个 completed infer run 可保留、比较并由
用户显式 Activate/Replace/Clear；同时冻结可复用的 fixed validation series，使后续训练轮次
共享同一验证成员并在现有 Task history 中可追溯。

## Scope

**做**：

- 新 inference 完成时只提交 completed run、原始预测和经过阈值过滤的 observation artifact，
  不自动修改当前 Track 的观测、active result 或 DerivedData。
- 当前 Track 没有 AI 结果时使用 **Activate**；已有结果时使用 **Replace**；使用 **Clear**
  清除当前 Track 的全部 AI observation。三者均由用户显式触发，不自动选择“最佳”结果。
- Activate/Replace 从所选 run 的已校验 observation artifact 重建该 run 的 AI observations；
  保留全部 manual 点，并把与 manual 同帧的所选 AI 点存为 superseded，使删除 manual 后仍能
  恢复当前 active run 的 prediction。
- Replace/Clear 保留所有 TrackingRun、模型、原始 HDF5/CSV、日志和审核记录；只改变当前
  Track 的 AI observation 投影与 active run 指针，并标记相关 DerivedData stale。
- 在当前 Track 的 active manual points 中由用户显式选择 fixed validation frames；保存不可变
  label snapshot。标签成员或坐标变化后原 series 标为不可用于新一轮，用户需创建新 series，
  旧 series 和旧评价不被重写。
- 把 DLC 显式 `trainIndices/testIndices` 接线从原 5.5 Slice 1 提前：一旦启用 fixed validation，
  当前训练就必须真实排除 validation frames，不能只展示“已冻结”却继续发生数据泄漏。
- 复用现有 Task history/list/details 展示 Active/Candidate/Legacy 状态、训练/验证标签数、参数、
  snapshot、train/fixed-validation evaluation、推理 coverage、审核统计和 remaining candidates；
  不增加第二套历史窗口或模型库。
- 兼容 5.4 前的项目：单一可识别 run 的 AI observations 可只读推断为 legacy active；多 run
  混合或无法映射时显示 Legacy mixed，允许 Replace/Clear，但不伪造 active run id。

**不做**（防止范围蔓延）：

- 不新增 Project/Iteration 顶层领域对象，不提升 `project.json` schema version，不迁移旧项目。
- 不实现 5.5 的 Resume/fine-tune、Restart 选择、Training Advisor 或参数建议。
- 不实现 Phase 7 模型库、跨项目 lineage、模型重命名/复制/删除或自动清理 run 产物。
- 不自动激活最新 run、不按 RMSE/confidence 自动选“最佳”、不自动重算图表。
- 不把 coverage/confidence 当 ground-truth 精度；跨轮精度比较只认同一 validation series 的
  fixed-validation evaluation。
- 不允许逐点删除 AI observation；AI 数据只按当前 Track 的 active result 整体切换或清除。
- 不删除旧 run、模型、HDF5/CSV、observation artifact、审核记录或既有 evaluation。
- 不要求本 Subphase 完成真实的 resume/retrain refinement 改善；该闭环仍在 5.5–5.6 验收。

## Persistence and Behavior Contract（已批准并由 ADR-0014 落地）

沿用 schema v1 的 tolerant `extra_fields`，不增加顶层字段：

```text
Track.extra_fields["refinement_state_v1"]
  ├── active_infer_run_id        # UUID | null
  ├── activation_history[]       # activate/replace/clear、from/to、数量、时间
  ├── active_validation_series_id
  └── validation_series{}        # series id → immutable manual label snapshots

train TrackingRun.extra_fields["refinement_iteration_v1"]
  ├── iteration_index / previous_training_run_id / source_infer_run_id
  ├── validation_series_id
  ├── training_labels[]          # point/frame/coordinate snapshots
  └── review_summary             # 训练开始时冻结

infer TrackingRun.extra_fields["prediction_summary_v1"]
  └── row/eligible/missing/low-confidence counts、threshold、coverage
```

- validation label snapshot 至少保存 `point_id/frame_index/pixel_x/pixel_y/modified_at`；series
  一旦创建不原地修改。新训练请求必须验证当前 manual points 与 active series snapshot 一致。
- training labels 同样在请求开始时冻结；iteration 是现有 completed train run 的解释层，不新增
  独立集合。训练参数、model snapshot、evaluation 和 infer 的 `training_run_id` 继续读取已有字段。
- active result 是 Track 状态，因此与 observations 一起进入现有 Session Track 快照；无需把所有
  TrackingRun 纳入 Undo/Redo。activation history 也随事务撤销/重做，不记录失败操作。
- `project.observations` 中的非 manual `TrackPoint` 明确作为“当前 active result 的物化投影”；
  Replace/Clear 可移除旧投影，但对应 TrackingRun 与原始/交换产物永久保留，可再次 Activate。
- 新 infer run 持久化 `observations_path` 与轻量 `observations_file_info`。Activate 前复核路径、
  文件状态、run/track/video/source/time；任何失败都发生在候选 Store 提交前。
- 旧项目没有 `refinement_state_v1` 时不自动写盘。单一 source detail 可推断 legacy active；多
  source detail 或孤立来源为 Legacy mixed，直到用户显式 Replace/Clear。
- 新 inference 无论当前是否已有 AI 点都保留完整 completed result；不再出现 first-wins 导致
  “0 inserted = 没有可用新结果”的产品语义。

这是新增的稳定持久化约定，已随 mini-plan 获批，并由
[ADR-0014](../decisions/0014-result-activation-and-fixed-validation-history.md) 接受；实现未修改顶层
schema。

## Acceptance Criteria

- [x] 新 inference 完成后 run/artifacts/summary 持久化，但当前 observations、active run、
  DerivedData 和 marker 均不改变；UI 明示 `Completed · Not active`。
- [x] Activate/Replace 只接受当前 Track 的 completed infer run 且 observation artifact 完整；
  selected run 的 AI points 被完整重建，manual 全保留，同帧 AI 以 superseded 形式保留。
- [x] Clear 只移除当前 Track 的非 manual observations；其他 Track、全部 manual、TrackingRun、
  模型、原始预测、日志、审核记录和评价不变（F2 / R4）。
- [x] Activate/Replace/Clear 在一个事务中更新 observations、active pointer、activation summary
  和 DerivedData stale；失败零写入，Undo/Redo 与保存重开一致。
- [x] 替换前确认对话框显示 from/to run 与将移除/载入/保留的点数；artifact 缺失、跨 Track、
  非 completed run、上下文变化或迟到结果时明确禁用/拒绝。
- [x] fixed validation 只可从当前 active manual points 显式选择；series 保存 immutable label
  snapshots。标签缺失/坐标变化时禁止沿用并提示创建新 series，旧 series/evaluation 不改写。
- [x] 启用 active validation series 的训练真实向 DLC 传入互斥且覆盖全部 manual labels 的
  `trainIndices/testIndices`；training run 冻结相同 membership 与训练标签快照。
- [ ] 两个 train run 可引用同一 validation series，历史把 train/fixed-validation RMSE 与 infer
  coverage/confidence 分栏显示；不同 series 不宣称可直接比较。
- [ ] Task history 同屏可辨认 train iteration、completed infer Candidate、当前 Active 与 Legacy
  mixed；显示 labels/corrections/params/snapshot/evaluation/coverage/remaining candidates。
- [x] 5.4 前单 run、mixed run、无 observations artifact 的项目都有明确兼容行为；不静默猜测、
  不自动迁移、不破坏 5.3 review state。
- [x] 定向测试、全量 offscreen pytest、compileall、真实 DLC fixed-split smoke 与独立 review
  通过；随后发起 macOS Human Review并停止，用户通过前不合并、不关闭 Issue、不 push。

## Relevant Context

- `docs/spec/phase5-requirements.md` R4、R5、R8、AC-6/AC-7/AC-11
- `docs/status/phase-5-plan.md` §3 Phase 5.4、§5
- `docs/reviews/phase4-architecture-reliability-review.md` F2
- `docs/status/phase-5.3-plan.md` Result
- `docs/decisions/0011-deeplabcut-integration-architecture.md`
- `docs/decisions/0012-gui-tracking-task-boundaries.md`
- `docs/decisions/0013-run-scoped-suggested-frame-review-state.md`
- `docs/spec/data-model.md` §3.5、§4（manual last-wins / engine first-wins / run clear）
- `docs/spec/project-format.md` Phase 4/5 引擎产物与 tolerant extensions
- `docs/research/open-source-project-map.md` §3.4
- `docs/research/raw/deeplabcut-notes.md` “Refinement、fixed split 与 retraining”
- `CODE_STANDARD.md` §4、§8–§9、§14–§15
- `src/ai_physics_tracker/application/tracking_job.py`
- `src/ai_physics_tracker/application/training_job.py`
- `src/ai_physics_tracker/application/inference_job.py`
- `src/ai_physics_tracker/application/project_session.py`
- `src/ai_physics_tracker/domain/track_store.py`
- `src/ai_physics_tracker/gui/task_panel.py`
- `src/ai_physics_tracker/gui/tracking_actions.py`

## Slices

- [x] **Slice 1 — Contract + validation series**：新增 ADR-0014、Qt-free refinement state/
  label snapshot 校验与 ProjectSession series 事务；验证 tolerant round-trip、series immutable、
  标签变化检测、Undo/Redo 及 5.3 review state 共存。
- [x] **Slice 2 — Fixed split + iteration snapshot**：扩展 adapter/dataset builder 接受显式
  train/test indices；训练请求冻结同一 validation series、training labels、上轮/active infer 与
  review summary；用 mock、真实 DLC smoke 和双轮同 membership 测试证明无 validation leakage。
- [x] **Slice 3 — Completed candidate + activation transaction**：推理完成改为只登记 Candidate；
  实现 artifact reader 与 Activate/Replace/Clear candidate Store，保证 manual 下 AI 保留、统计、
  stale、失败回滚、Undo/Redo、保存重开及 legacy mixed 行为。
- [x] **Slice 4 — History/activation GUI + review gate**：复用 Task history/details 增加状态、指标、
  fixed-validation 管理、确认框和操作按钮；覆盖任务并发/切换/迟到/缺产物矩阵，完成独立 review、
  全回归后发起 Human Review，等待用户反馈再收尾。

## Verification

```bash
# 定向：持久化、fixed split、iteration、activation 与 GUI
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest \
  tests/test_refinement_history.py \
  tests/test_training_job.py \
  tests/test_dlc_adapter.py \
  tests/test_inference_session.py \
  tests/test_tracking_job.py \
  tests/test_project_repository.py \
  tests/gui/test_tracking_activation_actions.py \
  tests/gui/test_task_panel.py -v

# 全回归、编译与真实 DLC fixed-split smoke
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest
.venv/bin/python -m compileall src scripts tests
.venv/bin/python scripts/smoke_test_dlc_train.py
```

Human Review 在自动化、真实 DLC smoke 与独立 review 全绿后进行，最多 5 项：完成新 inference
但不替换轨迹、Activate/Replace、Clear + Undo、fixed validation 创建/失效、保存重开与历史比较。

## Result（收尾时填写）

- 完成日期 / 合并 commit：2026-09-03 / `13f48c2`；Entry Gate 收口：2026-09-04（随 5.5 分支）
- AC 勾选结果：**11/11 有充分证据**（Entry Gate 已于 2026-09-04 补齐：双 train run 同 series/
  跨 series 不可比证据测试、`_runDetails`/详情面板完整迭代展示与 GUI 断言）。
- 偏离计划之处及原因：无实质偏离。在独立 Review 建议下增强了 DLC 配置的 `TrainingFraction` 自动同步。
- 遗留问题：`validation_series` writer 已改为 ADR-0014 的 series-id 映射形态（reader 兼容旧 list，
  不迁移旧项目）；`ActivationRecord` 新增容错 `superseded_count` 字段（R2 复审 M-1 语义统一）。
  复审其余延期项（崩溃恢复死锁、shuffle 编号、指纹策略）记录于
  [phase-5.4-review.md](../reviews/phase-5.4-review.md) R2 轮，随 5.5+ 处置。
- 独立 review 结论：
  - 派出 2 个子智能体（Domain & Transaction Reviewer + GUI & Test Reviewer），报告包含 F-01~F-09 以及领域边界 P1~P3 findings。
  - 全部 finding 均已 100% 针对性解决并编写补充测试覆盖。
  - 全回归 **652 passed**，真实 DLC smoke test 通过。
