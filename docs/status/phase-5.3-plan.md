# Subphase Plan — Phase 5.3 Suggested Frame Review & Correction

- Issue：待创建（计划确认后同步到 GitHub）
- 分支：`feat/p5.3-suggested-frame-review`
- 日期 / 状态：2026-09-03 · 📝 Draft，等待用户确认

## Goal

把 5.2 的困难帧结果变成可恢复的人工审核队列：用户选择一个 completed infer run 后，可按
`查看 → Accept / Correct / Skip → 下一帧` 完成审核；保存重开、撤销/重做、切换上下文后，
已提交状态与人工修正仍保持一致。

## Scope

**做**：

- 复用 Task history 当前选中的 completed infer run，启动 5.2 mining；不再增加一套 run 选择器。
- 在 AI task panel 增加困难帧审核区：当前帧、原始 prediction、原因/分量/总分、进度、
  Previous/Next、Accept/Correct/Skip 与完成统计。
- Accept 只记录本 infer run 已接受；Skip 只记录跳过；两者均不创建 `TrackPoint`。
- Correct 进入一次性修正模式，复用现有 screen→pixel、manual last-wins、marker 刷新与
  时序门禁；用户真正点击画面后才原子写入 manual point 和 `corrected` disposition。
- 保存/重开恢复活动审核批次和已提交 disposition；同一 infer run 后续 mining 抑制已
  Accept/Skip 的帧，新 infer run 可重新评估，Correct 的 manual point 长期保留。
- 增加“删除当前帧人工点”交互：只允许删除当前 Track/当前帧的 active manual point，
  恢复被该点遮蔽的 AI observation；若该点来自 Correct，同时把对应候选恢复为 pending。
- Accept/Skip/Correct/删除均进入同一 Undo/Redo 历史边界；点、disposition 和 marker 一起恢复。
- 完成 5.2 遗留 F4/F6：代表帧与 mining 都有可见取消入口，取消显示 `Cancelled` 而非
  `Failed`；算法下拉使用 item data 显式保存算法 ID。

**不做**（同样重要，防止范围蔓延）：

- 不改 `project.json` 顶层 schema version，不迁移历史项目，不新增数据库或依赖。
- 不实现 5.4 的 AI 结果 clear/activate/replace、跨 iteration history 或 fixed validation。
- 不实现 5.5 的 Training Advisor；本阶段只提供结构化完成统计，供 5.5 消费。
- 不自动接受、自动修正、自动训练，也不把 prediction 直接变成 manual label。
- 不允许逐点删除 AI observation；删除交互仅作用于 active manual point。
- 不在 5.3 引入 `confidence_threshold` 分位数自适应：5.2 已用 `screening` 补齐避免空队列；
  现在改阈值会重开 5.2 算法范围。只有真实 Human Review 证明候选质量有问题时再立项。
- 不为普通标注事务整体纳入全部 `TrackingRun` 历史，避免 Undo 意外回滚后台任务状态。

## Persistence and Transaction Contract（待批准）

不新增顶层字段，而是在对应 infer run 的既有可扩展字段中写入版本化对象：

```text
TrackingRun.extra_fields["suggested_frame_review_v1"]
  ├── active_batch          # 当前 mining request、参数快照、候选及 prediction/reasons/scores
  └── reviewed_frames       # frame_index → disposition、时间、request、prediction、manual_point_id
```

- `disposition` 只允许 `accepted | corrected | skipped`；未出现的帧即 pending，不持久化临时选择。
- 原始 prediction 快照随 disposition 保存；即使它低于 Phase 4 导入阈值、没有对应 AI
  `TrackPoint`，Correct 的来源仍可追溯。缺测保存为 `null`，不写 NaN。
- 状态归属 infer run，因此 Accept/Skip 只抑制同一 run；新 run 使用自己的独立状态。
- 新 mining 替换 `active_batch`，但保留本 run 的 `reviewed_frames`；传给 5.2 的 excluded
  frames 来自 Accept/Skip，加上现有 manual 点的既有排除逻辑。
- ProjectSession 使用“仅审核事务携带 review state”的历史快照。普通落点、标定和后台
  TrackingRun 更新不因此开始回滚全部任务历史；审核事务则保证 point/disposition 原子撤销。
- 项目保存仍沿用 schema v1 的 tolerant `extra_fields` 读写；旧项目没有该 key 时等价于空队列。

该结构是新增的持久化数据约定，计划批准后在实现前新增 ADR-0013，并同步
`docs/spec/project-format.md`；若实现中发现必须改顶层 schema，立即停下重新请求批准。

## Acceptance Criteria

- [ ] 只有当前 Track 的 completed infer run 可启动 mining；非 infer、未完成、跨 Track、产物
  缺失或上下文已变化时明确禁用/拒绝，取消与迟到结果不修改活动项目（R8）。
- [ ] 审核区显示当前候选帧、可用的 AI prediction、reason/component/score、`当前位置/总数`
  和前后导航；跳帧后仍指向用户实际看到的帧（R3.1）。
- [ ] Accept 只产生 accepted disposition；Skip 只产生 skipped disposition；二者不新增、删除
  或修改任何 `TrackPoint`（R3.2、AC-5）。
- [ ] Correct 在用户点击有效画面坐标后一次提交 manual point + corrected disposition；原 AI 点
  按 manual last-wins 保留为 superseded，低置信度/缺测 prediction 也能从审核记录追溯（R3.2–3）。
- [ ] 保存并重开后恢复 active batch、已提交 disposition、完成统计与 Correct 点；只进入
  Correct 模式但尚未点击时不改变 dirty 状态、不落盘（R3.4）。
- [ ] Undo/Redo 对 Accept、Skip、Correct 与删除人工点均保持原子：disposition、manual/AI
  生效关系、DerivedData stale 状态和 marker 一致，不回滚无关 TrackingRun 生命周期。
- [ ] 删除操作只删除当前 Track/当前帧 active manual point并恢复其直接遮蔽的 AI 点；没有
  manual 点时禁用；删除 Correct 点会把其候选恢复为 pending，且可 Undo。
- [ ] 同一 infer run 的后续 mining 不再建议已 Accept/Skip 帧；新 infer run 可重新建议；现有
  manual 帧（包括 Correct）继续由 5.2 规则排除（R2.8）。
- [ ] 代表帧选取与困难帧 mining 都可由用户取消，取消态不显示为失败；算法 ID 不依赖显示文本。
- [ ] 定向测试、全量 offscreen pytest、compileall 与独立 review 通过；随后发起 macOS Human
  Review，并在用户反馈前停止，不合并、不关闭 Issue、不 push。

## Relevant Context

- `docs/spec/phase5-requirements.md` R2.8、R3、R8、AC-4/AC-5/AC-11
- `docs/status/phase-5-plan.md` §3 Phase 5.3、§5
- `docs/status/phase-5.2-plan.md` Result / Deferred Findings
- `docs/reviews/phase-5.0-5.1-runtime-review.md` F4/F6
- `docs/spec/data-model.md` §3.5–3.6、§4（manual last-wins / superseded）
- `docs/spec/project-format.md` Phase 4 引擎产物与 `TrackingRun.extra_fields`
- `docs/decisions/0003-project-persistence-format.md`
- `docs/decisions/0012-gui-tracking-task-boundaries.md`
- `CODE_STANDARD.md` §4、§8–§9、§14–§15
- `src/ai_physics_tracker/application/difficult_frame_job.py`
- `src/ai_physics_tracker/application/project_session.py`
- `src/ai_physics_tracker/domain/track_store.py`
- `src/ai_physics_tracker/gui/task_panel.py`
- `src/ai_physics_tracker/gui/tracking_actions.py`
- `src/ai_physics_tracker/gui/main_window.py`

## Slices

- [ ] **Slice 1 — Review contract + atomic session transactions**：新增 ADR-0013 与 Qt-free review
  值对象/校验；在 ProjectSession 实现 Accept/Skip/Correct/删除的原子事务及 scoped Undo/Redo；
  用 session、持久化和旧项目兼容测试证明 AC-3–AC-8。
- [ ] **Slice 2 — Mining entry + queue controller**：复用 Task history 的 run 选择，接入 5.2
  background mining、身份复核、保存 active batch、同 run suppression、取消和上下文切换；
  用 application/GUI offscreen 测试证明 AC-1、AC-2、AC-8、AC-9，并顺带关闭 F4/F6。
- [ ] **Slice 3 — Review/Correct/delete GUI**：实现审核区、导航、一次性 Correct 模式、完成统计
  和当前帧 manual 删除；刷新 dirty/Undo/Redo/marker/autosave 状态，用 GUI 测试证明 AC-2–AC-7。
- [ ] **Slice 4 — Reliability matrix + review gate**：覆盖保存重开、中途退出、项目/video/track/run
  切换、候选已手工修改、取消/失败/迟到、Undo/Redo 交错；运行全回归与独立 review，修复并
  复审后发起 Human Review，等待用户通过再做 subphase 收尾。

## Verification

```bash
# 定向：review contract/session/persistence/mining/GUI
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest \
  tests/test_suggested_frame_review.py \
  tests/test_project_session.py \
  tests/test_project_repository.py \
  tests/test_difficult_frames.py \
  tests/gui/test_suggested_frame_review.py \
  tests/gui/test_task_panel.py -v

# 全回归与编译
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest
.venv/bin/python -m compileall src scripts
```

Human Review 在自动化与独立 review 全绿后进行，最多 5 项：选择 completed infer run 并 mining、
三种 disposition 与自动前进、Correct 落点/撤销重做、删除当前 manual 点、保存重开恢复。

## Result（收尾时填写）

- 完成日期 / 合并 commit：
- AC 勾选结果：
- 偏离计划之处及原因：
- 遗留问题：
- 独立 review 结论：
