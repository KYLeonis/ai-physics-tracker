# Pre-Phase 6 Stabilization — Mini-Plan

- 日期：2026-09-16。分支：`fix/pre-phase6-stabilization`。
- 输入：[pre-phase6-project-review.md](../reviews/pre-phase6-project-review.md)（P6R-01…04）、
  [pre-phase6-evidence-package.md](../reviews/pre-phase6-evidence-package.md)、AGENTS.md、CODE_STANDARD.md、workflow.md。
- 性质：有限、可验证的 stabilization；不立项新 Phase，不改产品范围。

## Goal

关闭进入 Phase 6 的两个 blocker（P6R-01 Undo/Redo 事务完整性、P6R-02 Resume
ancestry × 固定验证集暴露），同时修复 Phase 5.7 前必须处理的 Advisor 输入采集错误
（P6R-04），并在同一 lineage/validation 改动内低成本关闭 P6R-03（若实施成本不再是
Low 则 defer）。完成后交付经独立复核的干净工程 baseline。

## Scope（做）

1. **P6R-01**：应用层 Undo/Redo 事务原子性与 Track↔TrackingRun 引用一致性；
   GUI undo/redo 路径的拒绝反馈。
2. **P6R-02**：Resume 完整 ancestry 训练暴露 vs 当前固定验证集的 eligibility 计算
   （clean / contaminated / unknown）；Resume 入口校验；Advisor 比较资格。
3. **P6R-04**：Advisor 输入采集器（timeline 用 track 的真实 video_id；
   last-train-failure 表示"最近一次相关训练"的状态）+ 组合行为测试。
4. **P6R-03（条件实施）**：被 train run 引用的 validation series 拒绝物理删除
   （保留对象、允许停用），前提是改动保持小范围。
5. 文档同步与 Review Record 补充（不改写原始 Finding）。

## Non-goals（不做）

- 拆分 ProjectSession、迁移 project schema、引入数据库、重写 extra_fields；
- 重写 GUI Actions 架构、开始 Phase 5.7 UI redesign 或 Phase 6 实现；
- 泛化 Physics Engine / 新 DerivedData framework；
- 修复 Astra 报告中的 Later / Accepted Risk 项；
- Windows CUDA / packaging 提前；
- 重跑 Phase 5 大型实验、改写历史 RMSE / benchmark 数字；
- 为任何 AC"制造通过结果"。

## 关键设计决策（实现前锁定）

### P6R-01 — Undo/Redo 依赖政策

- **快照携带 run registry**：`_SessionDataSnapshot` 由 6 元组扩为 7 元组
  （追加 `tracking_runs`），使历史转换能感知结构依赖。
- **按 track 存在性合并 registry**：撤销/重做到目标快照时，
  - **被恢复的 track**（当前不存在、目标快照存在）：其 TrackingRun 一并从目标
    快照 registry 恢复（remove_track 级联删除的对称恢复；active pointer、
    observations、refinement state 与 run 重新一致，可保存重开）；
  - **存续 track**：run registry 保持当前状态——pending/running/completed 的
    生命周期演进不被 Undo 回滚（无关或既有事实不倒退）；
  - **被移除的 track**：其当前 run 从合并 registry 中移除。
- **原子拒绝越过历史外依赖**：undo 方向上，若被移除 track 存在**目标快照之外登记**
  的 run（如 `record_tracking_run` 直接登记、不在任何快照中），拒绝该次 undo 并抛
  `ProjectSessionError`；拒绝后 Project / TrackStore / Undo 栈 / Redo 栈 /
  run registry 全部不变。redo 方向不存在此问题（被移除 run 必来自快照恢复）。
- **`record_tracking_run` 清空 redo 栈**：新 run 登记是一次前向写入，与其他写入
  一致地使 redo 失效；否则"remove → undo → record → redo"会经 redo 复现同源半提交。
- **先构造完整 candidate 再提交**：undo/redo 在校验（含聚合 `replace()` 的
  `validate_project`）全部通过后才 pop/push/赋值，任何异常不产生半提交。
- 旧契约 `test_remove_track_with_runs_succeeds_and_undo_keeps_runs_deleted` 的
  更新理由：该测试固定的是 Phase 4 时代"run 注册表是审计日志、不进撤销快照"的
  政策（`domain/project.py delete_track` docstring）；Phase 5.4 起 Track 的
  refinement state 含 active run pointer，"恢复 track 不恢复 run"必然产生悬空
  引用（P6R-01 复现 B），旧契约在当前模型下不再完整。

### P6R-02 — validation comparison eligibility

- **纯函数 lineage 暴露计算**（`application/refinement_history.py`）：
  `validation_training_exposure(runs, root_run_id, validation_frames)` 沿
  `resume_from_training_run_id` 链累加每代 `training_labels`，与验证帧求交：
  - `clean`：链完整（每代均有 `refinement_iteration_v1`）且交集为空；
  - `contaminated`：交集非空（记录暴露帧与祖先 run）；
  - `unknown`：链中存在无训练成员记录的 run（5.4 前 legacy）、缺失 run 或环路
    ——**不默认"没记录=没训练过"**。
- **Resume 入口（`prepare_tracking_request`）**：当前 track 存在 active
  validation series 且 resume 源链 qualification ≠ clean 时，**阻止 Resume**
  （消息给出暴露帧/原因与出路：Restart、换源、或停用验证集）。无 active series
  时 resume 不受此门限制（没有独立比较要保护）。restart 无需检查（无继承权重）。
- **Advisor / 历史比较**：`RoundMetrics` 新增显式 `comparison_qualification`
  字段（由采集器按 run 自身 ancestry 计算；series 缺失/不可解析 → unknown）；
  `_same_series_comparison` 要求两轮均 clean 才可比，否则按"无可比评价"路径
  处理并明示原因。历史 RMSE 数字不重写、不删除；资格是计算态，不新增持久化。
- 选择"阻止 Resume"而非"允许但标记"：最少额外状态、与现有错误路径一致；
  需要不比较的用户已有既有出口（停用 series）。

### P6R-04 — Advisor 输入采集

- 采集逻辑自 `TrackingActions._build_advisor_input` 提升为 Qt-free 的
  `application/advisor_collection.py::collect_advisor_input(...)`（GUI 仅传
  panel 参数），修复：
  - timeline 按**所选 Track 的 video_id** 解析（不再 `video_id == track_id`）；
  - `last_train_failed`/OOM 取**最近一次相关训练 run**（completed/failed 中
    `created_at` 最新者）的状态，成功训练后不再永久报失败。
- 采集器同时负责 P6R-02 的 `comparison_qualification` 与 resume 源资格事实。

### P6R-03 — 条件实施（评估结论：Low cost，实施）

- 语义：**被本 track 任一 train run 的 iteration 引用的 series 拒绝物理删除**
  （抛错并提示改用停用）；未被引用的 series 删除行为不变。无 schema 变更、
  无 migration；validation dialog 已有异常捕获路径。保存重开后历史 run 的
  validation membership/label snapshot 仍由 series 第一方快照解析。

## Slices

| # | 内容 | 验证 |
| --- | --- | --- |
| 1 | P6R-01：失败复现测试（A：新建 track+run 后 undo；B：删除激活 track 后 undo + save/reopen）→ 政策落地 → GUI 拒绝反馈 → 更新旧契约测试 | targeted pytest |
| 2 | P6R-02：exposure helper → Resume 入口校验 → RoundMetrics 资格 + Advisor 门控 + 采集器接线 → 7 类场景测试 | targeted pytest |
| 3 | P6R-04：Qt-free 采集器 + 两处事实修复 + collector→AdvisorInput→recommendation 组合测试；P6R-03 守卫 + 追溯测试 | targeted pytest |
| 4 | 全量 pytest + `compileall` → Independent Review（fresh reviewer）→ findings 修复 → re-review → 双平台 CI → 文档同步 | 全量 + CI |

## Acceptance Criteria

（逐条对应用户指令中的 P6R-01/02/04/03 验收清单；收尾时在本文件与 Review Record
附录中逐项勾选，证据指向测试名与 CI run。）

### P6R-01

- [ ] Undo 不再留下 Project / TrackStore 半提交（复现 A 关闭）
- [ ] run 依赖情况要么合法 Undo，要么原子拒绝（拒绝后五项不变量逐一断言）
- [ ] active pointer 永远引用有效 run 或为空（复现 B 关闭，save/reopen 一致）
- [ ] 无关 TrackingRun 生命周期不被 Undo/Redo 回滚
- [ ] pending/running/completed 相关边界有测试
- [ ] GUI Undo 快捷键/按钮路径有相称验证（拒绝时给出可见反馈且状态不变）

### P6R-02

- [ ] clean Resume 正常工作（含无 active series）
- [ ] direct-parent contamination 被识别并阻止
- [ ] ancestor contamination 被识别并阻止
- [ ] 更换 validation series 后 Resume 老模型被正确处理
- [ ] legacy unknown lineage 不默认 clean
- [ ] restart 语义不受影响
- [ ] contaminated/unknown 轮次不再被无提示当成独立 validation comparison
- [ ] Advisor 比较使用资格状态而非仅 series ID
- [ ] 旧 RMSE / benchmark 不被篡改

### P6R-04

- [ ] Advisor 使用 Track 对应真实 video/timeline（uncovered 分支恢复工作）
- [ ] OOM 失败后出现成功训练时不再报 last_train_failed
- [ ] 至少一条 Project/Session/runs → collector → AdvisorInput → recommendation 组合测试

### P6R-03

- [ ] 被 train run 引用的 series 拒绝删除；停用后 save/reopen 历史标签仍可追溯
