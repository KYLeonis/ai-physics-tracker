# Subphase Plan — Phase 5.5 Training Advisor & Retraining

- Issue：待创建（mini-plan 批准后同步到 GitHub）
- 分支：`feat/p5.5-training-advisor-retraining`（尚未创建）
- Issue：[#21](https://github.com/KYLeonis/ai-physics-tracker/issues/21)
- 日期 / 状态：2026-09-04 · 🚧 Slices 0–4 实现完成；独立 review 与 Human Review 进行中

## Goal

在 5.4 的固定验证集与迭代历史上增加一个确定、有限、可解释的 Training Advisor；用户可以把
建议填入训练表单，并明确选择从已完成 snapshot 继续 fine-tune，或从头 restart，但训练、推理和
结果激活始终由用户手动发起。

## Entry Gate — Phase 5.4 Audit Closure

5.5 实现前必须先关闭本轮复核发现的 5.4 验收债务；它们不是 5.5 新功能：

1. 让 `serialize_refinement_state()` 按 ADR-0014 写出 `series_id → ValidationSeries` 映射；继续
   兼容读取已落盘的 list 形式，不迁移或重写旧项目。
2. 补“两次 train run 复用同一 validation series”以及“不同 series 不直接比较”的测试证据。
3. 补齐 Task history/details 对 training/validation label 数、review summary、prediction coverage、
   remaining candidates 与不可比较原因的展示和 GUI 断言。
4. 同步 `docs/spec/project-format.md`、5.4 Result/Verification 与 review 索引。GitHub Issue #21 从未
   创建，只按事实记录，不补造历史 Issue；旧 Issue #18 的关闭由用户另行决定。

以上门槛与 5.5 Slice 1 在同一开发分支先后执行；门槛未全绿时不进入 Advisor 实现。新增的历史
详情展示纳入 5.5 最终 Human Review，不重复举行一轮独立人工验收。

## Scope

**做**：

- 新增 Qt-free 规则型 Advisor，只消费当前 Track 的 manual labels、fixed validation 状态、
  completed/failed train runs、对应 infer review/prediction summary 与现有 evaluation；不调用 DLC、
  不读视频、不修改项目。
- Advisor 输出单一下一步动作、建议参数、证据与限制。动作收敛为 `review_candidates`、
  `label_more`、`resume`、`restart`、`stop_and_compare` 或 `fix_prerequisite`，不返回模糊自由文本决策。
- 规则按固定优先级执行：前置条件/无效 validation → 最近一次 OOM → 未审核候选/新增标签 →
  同一 validation series 的 RMSE 趋势 → 无可比验证数据的保守建议。
- 跨轮 RMSE 只比较同一有效 `validation_series_id`，且只比较同名、同单位的 fixed-validation
  指标。以相对变化 `±5%` 区分 improved / plateau / worsened；仅作为第一版可解释阈值，进入
  evidence，不伪装成统计显著性或通用物理精度标准。
- generalization gap 只在 fixed-validation RMSE ≥ train RMSE 的 `1.5×` 时触发，并同时展示原值；
  不使用绝对像素阈值，因为不同视频分辨率和目标尺度不可直接共用一个“合格 RMSE”。
- “再标多少帧”使用有限档位 `3 / 5 / 10`：结合未审核候选数、当前批次 correction yield 与
  working zone 四等分中缺少 training label 的区段选择，且不超过可用候选数；无证据时默认 5。
- additional epochs 只给 `25 / 50` 两档；batch size 沿用最近成功值，最近失败明确匹配 OOM 时
  才减半（下限 1），从不在无硬件证据时自动增大。
- Resume/fine-tune 只接受当前 Track/Video 的 completed train run，snapshot 与 config 必须存在且
  通过既有文件身份校验；把该 snapshot 显式传给 DLC `train_network(snapshot_path=...)`。
- Resume 的 `epochs` 定义为“本次追加 epochs”。DLC 3.0.1 会从 snapshot metadata 的 epoch 继续
  计数；UI 使用 `Epochs this run`，避免误解为目标总 epoch。
- Restart 不传 snapshot，并继续使用现有“每个 train run 独立 DLC 工作目录”路径；不会覆盖或
  删除旧 run、旧 snapshot、评价或日志。
- 复用现有模型列表作为 resume source 选择器，在 Training 区增加 Restart / Resume 选择和
  Advisor 摘要；`Apply Suggestion` 只填入 mode、source、epochs、batch size，不点击 Start Training。
- 训练历史显示实际 mode、resume source、requested/additional epochs 与 produced snapshot；建议
  本身不进入项目持久化，真正执行的参数与 lineage 才随 train run 保存。

**不做**（防止范围蔓延）：

- 不自动开始训练、推理、挖掘、激活结果或循环迭代。
- 不做 HPO/Bayesian optimization、early-stopping 搜索、自动 learning rate/scheduler/optimizer、
  网络结构、augmentation 或 batch-size 探测。
- 不声称 RMSE 变化具有统计显著性，不用 confidence/coverage 代替人工 fixed-validation 精度。
- 不跨 Track/Video resume，不从外部任意路径选择 checkpoint，不支持 TensorFlow checkpoint。
- 不实现 Phase 7 模型库、snapshot 重命名/删除/清理、跨项目 lineage 或模型发布。
- 不把 DLC snapshot 的“继续加载权重”描述成必然恢复完整 optimizer/scheduler 状态；是否包含这些
  状态由 DLC snapshot 决定，第一版产品语义统一称 **Resume / fine-tune**。
- 不在本 Subphase 完成单摆端到端改善证明；真实完整闭环与 AC-9 留给 5.6。

## Persistence and Behavior Contract（待批准）

不提升 `project.json` schema version。扩展既有
`train TrackingRun.extra_fields["refinement_iteration_v1"]`：

```text
training_mode                 # "restart" | "resume"
resume_from_training_run_id   # UUID | null；仅 resume 使用
```

- `resume_from_training_run_id` 指向不可变的 completed parent run；source snapshot 由 parent run 的
  `model_snapshot` 唯一确定，produced snapshot 仍使用当前 run 的 `model_snapshot`，不重复存路径。
- `TrackingRun.config` 保存实际 `training_mode`、本次 epochs、batch size、device 等执行参数；旧 run
  没有新字段时按 `restart` + 无 resume source 读取，因为 5.5 前不存在产品级 resume 入口。
- Advisor recommendation 是可重新计算的界面建议，不写入 `project.json`；这样不会把过时建议当成
  历史事实，也不新增第二套状态机。只有用户点击 Start Training 后，实际选择进入新 train run。
- 该扩展属于稳定持久化约定。mini-plan 获批后先新增 ADR-0015，并同步
  `docs/spec/project-format.md` / `docs/spec/phase5-requirements.md`，再开始 Slice 1；若实现需要顶层
  schema 或迁移，立即暂停并重新请求批准。

## Advisor Rule Contract（待批准）

规则返回第一条命中的建议，确保同一输入始终得到同一输出：

1. 活动 validation 无效、必需产物缺失或任务正在运行：`fix_prerequisite`。
2. 最近 train 失败且错误明确匹配 OOM：保持用户原 mode/source，batch size 减半后建议重试。
3. 当前 infer 尚有 pending candidates：`review_candidates`；不跳过人工审核直接训练。
4. 没有 completed train run：`restart`；使用当前/默认参数，不虚构 resume source。
5. 相对最近训练快照存在新增 active manual labels：优先从兼容 snapshot `resume`，追加 25 epochs；
   若 validation 已恶化或 source 不兼容则 `restart`。
6. 同一 series 最近两轮 fixed-validation RMSE 改善至少 5%：`resume` 追加 25 epochs；若 train 与
   validation 都仍改善，可建议 50，但最多一档且不自动循环。
7. validation 恶化至少 5% 或出现 1.5× generalization gap：有候选时 `label_more`，无候选时
   `restart`；evidence 必须列出 train/validation 原值、delta 和 series。
8. 最近两轮落在 ±5% plateau：有未覆盖时间区段则 `label_more`，否则 `stop_and_compare`。
9. 没有同一 series 的可比评价：只可基于新增标签建议 resume/latest compatible，或建议先冻结
   validation；limits 明示“不能判断精度是否改善”，不得选择所谓 best snapshot。

## Acceptance Criteria

- [x] Advisor 为 Qt-free 纯函数/不可变值对象；同一输入得到相同 action、参数、evidence 与 limits，
  不读文件、不修改 ProjectSession、不启动后台任务（R7 / AC-8）。
- [x] 规则优先级覆盖 prerequisite、OOM、pending review、first train、new labels、improved、
  generalization gap、worsened、plateau 与 no fixed validation；表驱动测试固定全部分支。
- [x] 只有相同有效 validation series、同名同单位 RMSE 可做 delta/“更好”判断；无可比验证数据时
  明示限制，coverage/confidence 只作辅助证据（R5 / R7）。
- [x] 建议标注数量只取 3/5/10 且有上限，能解释 pending candidates、correction yield 与时间多样性
  缺口；additional epochs 只取 25/50，OOM 仅减小 batch size（最小 1）。
- [x] Restart 不传 snapshot；Resume/fine-tune 只接受当前 Track/Video 的 completed train run，并在
  worker 启动前验证 model/config 路径归属与文件身份；失败零写入活动 session（R6 / R8）。
- [x] DLCAdapter 与 MockEngineAdapter 都支持可选 `snapshot_path`；真实 DLC smoke 证明 restart 生成
  初始 snapshot、resume 从该 snapshot 追加 epoch 并在新 run 目录产出新 snapshot。
- [x] 每个新 train run 可追溯 `training_mode`、resume source、实际参数、固定 validation series、
  training labels、source/produced snapshot 和 evaluation；保存重开与旧 run 读取正确（R5）。
- [x] Training UI 可手选 Restart/Resume source，也可 Apply Suggestion 填表；Apply 不启动训练，训练
  完成后仍不自动推理或激活结果（R6.5 / R7）。
- [x] 取消、失败、迟到结果、Track/Video/项目切换与 parent snapshot 被替换/缺失均有自动化覆盖，
  不污染当前项目；旧 run 和旧 snapshot 永不被 restart/resume 删除或覆盖。
- [ ] 定向测试、全量 offscreen pytest、compileall、真实 DLC restart/resume smoke 与独立 review
  通过；因新增可感知 GUI 交互，随后发起 macOS Human Review，用户通过前不合并、不关闭 Issue、
  不 push。

## Relevant Context

- `docs/spec/phase5-requirements.md` R5–R8、AC-7/AC-8/AC-11
- `docs/status/phase-5-plan.md` §3 Phase 5.5、§5
- `docs/status/phase-5.4-plan.md` Result
- `docs/decisions/0011-deeplabcut-integration-architecture.md`
- `docs/decisions/0012-gui-tracking-task-boundaries.md`
- `docs/decisions/0014-result-activation-and-fixed-validation-history.md`
- `docs/spec/project-format.md` TrackingRun / refinement extensions
- `docs/research/open-source-project-map.md` §3.4
- `docs/research/raw/deeplabcut-notes.md` “Refinement、fixed split 与 retraining”
- `CODE_STANDARD.md` §4–§8、§10、§14–§15
- `src/ai_physics_tracker/application/refinement_history.py`
- `src/ai_physics_tracker/application/training_job.py`
- `src/ai_physics_tracker/application/tracking_job.py`
- `src/ai_physics_tracker/infrastructure/engine_adapter.py`
- `src/ai_physics_tracker/infrastructure/dlc_adapter.py`
- `src/ai_physics_tracker/gui/task_panel.py`
- `src/ai_physics_tracker/gui/tracking_actions.py`

## Slices

- [x] **Slice 0 — Close Phase 5.4 audit gaps**：完成 Entry Gate 的 writer 对齐、双轮/跨 series
  证据与完整 history details；运行 5.4 定向回归并更新其 AC/Result，未闭环前不进入 Slice 1。
- [x] **Slice 1 — Contract + deterministic Advisor**：新增 ADR-0015 与
  `application/training_advisor.py`，扩展 refinement iteration tolerant reader/writer；用表驱动纯单元
  测试固定规则优先级、同 series 比较、有限参数档位和旧 run 默认语义。
- [x] **Slice 2 — Explicit restart/resume pipeline**：给统一 training request、EngineAdapter、DLC/mock
  adapter 接入可选 parent snapshot；在 worker 前完成 parent/run/file 身份校验，记录实际 lineage；
  用 application/integration 测试与真实 DLC 两段 smoke 证明追加 epoch 和旧产物隔离。
- [x] **Slice 3 — Advisor + retraining GUI**：复用现有 Training/Task history 控件增加 mode、resume
  source、Advisor 摘要与 Apply Suggestion；覆盖手选、应用但不启动、启动参数快照、禁用原因、任务
  互斥与上下文切换。
- [x] **Slice 4 — Reliability matrix + review gate**：覆盖 OOM、缺失/被替换 snapshot、无/失效
  validation、不同 series、取消/失败/迟到、保存重开与旧 run；完成独立 review、修复与复审，运行
  全回归和真实 DLC smoke 后发起 Human Review，等待用户反馈再收尾。

## Verification

```bash
# 定向：Advisor、iteration persistence、restart/resume、统一 runner 与 GUI
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest \
  tests/test_training_advisor.py \
  tests/test_refinement_history.py \
  tests/test_training_job.py \
  tests/gui/test_tracking_activation_actions.py \
  tests/test_tracking_job.py \
  tests/test_dlc_training.py \
  tests/gui/test_task_panel.py \
  tests/gui/test_training_advisor_actions.py -v

# 全回归、编译与真实 DLC restart/resume smoke
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest
.venv/bin/python -m compileall src scripts tests
.venv/bin/python scripts/smoke_test_dlc_train.py
```

Human Review 在自动化、真实 DLC smoke 与独立 review 全绿后进行，最多 5 项：查看 Advisor 证据与
限制、Apply Suggestion 不自动训练、手选 Restart、手选 Resume source 并追加 epochs、保存重开后
history 的 mode/source/produced snapshot 可追溯。

## Result（收尾时填写）

- 完成日期 / 合并 commit：实现 2026-09-04（分支 `feat/p5.5-training-advisor-retraining`，
  Slice 0 `d830afd`、Slice 1 `94f67b0`、Slices 2–4 `9c64416` + smoke 提交）；合并 commit 待
  Human Review 通过后补记
- AC 勾选结果：9/9 勾选（独立 review 与 Human Review 证据收集中）
- 偏离计划之处及原因：
  - 真实 DLC smoke 验证 resume 的 epoch 编号从 snapshot 元数据延续
    （001 → 002），证实"epochs = 本次追加"语义与实现一致
  - ReviewBatchSummary 字段名为 total_reviewed（非 reviewed_count），Advisor
    输入采集按实际字段对接
- 遗留问题：R2 复审延期项（崩溃恢复死锁、shuffle 编号分配、指纹策略）不在本
  Subphase 范围，仍待用户批复
- 独立 review 结论：进行中（多 subagent 并行审查后补充）
