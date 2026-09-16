# Subphase Plan — Phase 5.6 Refinement Loop Integration & Acceptance

- Issue：待计划确认后创建
- 分支：`feat/p5.6-loop-acceptance`
- Issue：[#22](https://github.com/KYLeonis/ai-physics-tracker/issues/22)
- 分支：`feat/p5.6-loop-acceptance`
- 日期 / 状态：2026-09-16 · 🚧 Slices 0–3 执行完毕；AC-9 以明示缺口归档；待 HR/合并

## Goal

把 5.1–5.5 串成一次**真实、可复现、量化**的单摆 refinement 闭环（AC-9），并完成 Phase 5
总验收（AC-1–AC-11 逐项证据核对）。闭环定义：

```text
（已完成于 AI_test2）建议帧 → 标注 → 冻结 validation series → train(iter0) → infer
（本 Subphase 完成）        mine → review/Correct → Advisor → retrain(同 series) → reinfer
                           → 三类 delta 比较 → 用户显式激活 → 证据归档
```

**呈现原则（2026-09-05 与用户确认）**：三类 delta **不设任何用户可见的报告/界面**，
全部由后台自动计算并汇入 Advisor——用户全程只看 Advisor 的"一行建议 + 证据行"。
收尾时由 Agent 生成归档报告（`docs/benchmarks/`，验收证据），用户无需阅读。

**AC-9 的"三类 delta"**（同一 validation series 上，同指标同单位；均为 Advisor 内部输入）：

| delta | 定义 | 来源（均已随 run 落盘，无新 schema） |
| --- | --- | --- |
| 精度 | fixed-validation RMSE 相对变化 | train run `evaluation.test.metrics.rmse` |
| 覆盖 | infer run 预测 coverage（eligible/row）相对变化 | `prediction_summary_v1.coverage` |
| 工作量 | remaining difficult frames（未审核候选数）与 review yield | `review_summary`（corrected/total_reviewed） |

AC-9 不假定必然改善：delta 如实记录；若未改善，按 Advisor 规则继续或如实停止。但 Phase 5
收尾前需**至少一次同 series 可复现的改善证据**（见 Slice 2 的循环上界约定）。

## Slice 0 — 批复决策落地（用户已批准，2026-09-04）

1. **A 崩溃恢复**：项目加载时把无进程对应的 pending/running TrackingRun 标记 failed
   （error_message 注明 "interrupted by app shutdown"）；GUI 与领域测试覆盖
   "保存了 running run → 重开 → 状态 failed、按钮恢复"。
2. **B 删除 DLC 目录复用**：`prepare_training` 移除 `dlc_{track_prefix}` 复用路径与
   fallback `data/engines/dlc` 目录，一律使用调用方传入的 per-run `working_dir`；
   更新受影响测试（含曾断言目录复用的用例，改为断言每次全新目录）。
3. **C 激活指纹放宽**：`_activate_or_replace_infer_run` 的 `observations_file_info`
   校验改为仅比对 size（丢弃 mtime 项）；同步测试与 ADR-0014 措辞注记（决策来源：
   5.4 R2 复审 M-2，用户选方案 2）。

验收：三项各有定向测试；全量回归 + compileall 通过；5.4 review record 对应行标记 Done。

## Slice 1 — delta 内化为 Advisor 输入 + 激活引导（无新用户界面）

- **输入扩展**（`_build_advisor_input`）：补采集同一 series 相邻两轮的 coverage 对
  （经 infer run `config.training_run_id` 关联 train run，再取两个 infer run 的
  `prediction_summary_v1.coverage`）；9 条规则合同**不变**，coverage 仅入证据行，
  绝不作决策依据（规范：coverage 不是精度）。
- **激活引导**（证据行增强，非新 action）：improved 时证据附"iteration N 优于 N-1
  （同 series），可激活 run xxxxxxxx"；worsened 时明示"建议保留当前激活结果"。
  仅陈述事实与建议，**绝不自动激活**（硬性不变式）。
- **Agent 侧归档工具**（`scripts/generate_loop_report.py`，开发工具不进产品）：从
  project.json 读取闭环各 run，产出三类 delta 的 markdown 归档（AC-9 验收证据）。
- 测试：coverage 证据行出现/不出现、激活建议指向正确 run、worsened 时不建议激活、
  9 条规则回归全部不变。

## Slice 2 — 真实单摆闭环执行（用户参与的半自动流程）

**测试床**：继续用 `experiment/AI_test2`（148 帧、30 manual、series `f13d5bbd`、
iter0=test RMSE 3.3 已在盘）。理由：AC-9 前半段（建议帧→标注→冻结→train→infer）在该项目
已有真实证据，重开新项目要用户重复标注 ~30 帧且不产生新信息；本 Slice 补齐后半段。

执行序（Agent 驱动计算步骤，用户做人工判断步骤）：

1. 对当前 active infer run 发起困难帧挖掘（Top N=10，min_gap 默认）。
2. **用户**在审核队列逐帧 Accept/Correct/Skip（预计 ≤15 分钟；Correct 产生新训练标签）。
3. **用户**查看 Advisor 建议（预期：新增标签 → resume 25 epochs）并确认或手选参数。
4. Agent/用户启动 retrain（resume，同 series）→ reinfer 全视频。
5. delta 后台自动汇入 Advisor；**用户**只看 Advisor 建议（含激活引导），显式 Activate
   新结果（worsened 时按建议保留现结果，回到补标注路径）。
6. 若精度 delta 未改善：按 Advisor 证据决定再补一轮标注（循环上界 **2 轮**）；仍无改善则
   如实归档失败证据与原因分析（AC-9 允许），此时与用户讨论是否继续。

**产物**：`docs/benchmarks/phase-5-loop-report.md` 由 Agent 在闭环完成后生成归档（用户
无需阅读），含闭环各阶段 run id、三类 delta、激活记录与结论，作为 AC-9 证据。

## Slice 3 — Phase 5 总验收与收尾

1. AC-1–AC-11 逐项核对表（勾选 + 证据链接：测试/报告/review record/CI），写入本 plan Result。
2. 独立 review（多 subagent，聚焦 Slice 0 改动的数据语义 + 比较工具正确性 + 闭环证据链）。
3. 全量回归 + compileall + 真实 DLC smoke（restart/resume 已在 CI 外本地验证路径）。
4. Human Review：闭环操作体验（挖掘→审核→Advisor→再训练→激活）由用户在真机走一遍确认。
5. 文档全量同步（roadmap Phase 5 → ✅、README、AGENTS、phase-5-plan Result、各 review 索引）、
   合并 `--no-ff`、push、关闭 Issue；**Phase 5 收官后停止，等待 Phase 6 指令**。

## 不做

- 不新增 GUI 窗口/控件，**不设用户可见的 delta 报告**（三类 delta 仅为 Advisor 内部输入
  与 Agent 归档证据；AC-11 的 HR 针对既有交互串联体验）。
- coverage 不进入 Advisor 决策规则（仅证据行）；Advisor 不自动激活结果（只给事实性建议）。
- 不改 schema、不加新持久化字段（delta 报告消费既有 run 记录）。
- 不做 Windows/CUDA 真机验收（已批准延期至 Phase 9 前）。
- 不自动激活结果、不自动循环训练（每轮由用户显式启动/确认，Phase 5 硬性不变式）。

## 验收标准

- [ ] Slice 0 三项（A/B/C）落地并有测试；5.4 review record 状态更新
- [ ] 三类 delta 后台自动汇入 Advisor（coverage 仅证据、不入规则）；improved/worsened
  的激活引导正确且绝不自动激活；归档工具可从 project.json 复现三类 delta
- [ ] 真实闭环完成：Correct → retrain → reinfer → 用户按 Advisor 建议显式激活，
  全程 run id 可追溯
- [ ] `phase-5-loop-report.md` 归档三类 delta 与结论；若改善未达成，含原因分析
- [ ] AC-1–AC-11 全部勾选且有证据链接；Phase 5 收官文档同步、合并、push、Issue 关闭
- [ ] 全量回归 + compileall + 独立 review + Human Review 通过

## 风险与边界

- 用户人工步骤（审核 ~10 帧、确认 Advisor、点激活）是必要投入，无法代理；预计总投入
  30–45 分钟，跨 1–2 次会话均可。
- resume 后 DLC 评价的 test RMSE 与 iter0 的可比性依赖同 series 同成员：series 未动即成立
  （领域层已校验失效；如用户中途改标签导致 series 失效，需重建 series 并重跑 iter0 作基线）。
- 循环上界 2 轮：防止为凑改善证据无限调参（违背"不通过调参覆盖结果"的规范）。

## Verification

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest \
  tests/test_tracking_job.py tests/test_result_activation.py \
  tests/test_iteration_compare.py -v   # Slice 0/1 定向
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest           # 全量
.venv/bin/python -m compileall src scripts
.venv/bin/python scripts/generate_loop_report.py --project experiment/AI_test2  # 归档证据
```

## Slice 2 执行记录（2026-09-16）

闭环后半段在 AI_test2 真实执行完毕（iter1 resume → iter2 resume+10 → iter3 restart → iter4 restart+10）；
同 series 11 帧冻结基准 val RMSE = 3.30 / 4.80 / 3.19 / 4.71 → **AC-9 改善证据未达成**
（最佳 −3.3%，±5% 内；三轮预算用尽）。三类 delta 与判定见
[phase-5-loop-report.md](../benchmarks/phase-5-loop-report.md)；三项 findings（F1 screening 假困难帧、
F2 冻结 series 从 project.json 消失但可重建、F3 基准分辨率不足）见
[phase-5.6-review.md](../reviews/phase-5.6-review.md)。

**AC-9 处置待用户在以下选项中决定**（Slice 3 之前）：
① 如实归档"未达成"并作为明示缺口处置；② 采信进行中的方差实验结果再定论；
③ 追加更大规模实验（新项目、更大标签集、重复训练）后再判定。

## Slice 3 — AC-1~AC-11 总验收核对表（2026-09-16）

| AC | 结论 | 证据 |
| --- | --- | --- |
| AC-1 DLC uniform/K-means 在 working zone 返回去重帧号、排除 manual、不自动造标签 | ✅ | `tests/test_frame_selection.py::test_dlc_adapter_uniform_synthetic` / `kmeans_synthetic`；`tests/gui/test_frame_selection_actions.py::test_suggest_frames_not_creating_track_points_invariant`；5.1 HR |
| AC-2 挖掘消费指定 infer run 全帧原始预测，低置信/缺测不丢 | ✅ | `tests/test_difficult_frames.py::test_keeps_low_confidence_and_missing_rows`、`test_hdf5_roundtrip_keeps_low_confidence_and_missing_rows`；真实 run `cffbed09` 148 行 × 0 缺测 |
| AC-3 pipeline 顺序被测试固定；连续异常段不垄断 Top N | ✅ | `test_consecutive_low_confidence_burst_does_not_monopolize_top_n`、`test_min_gap_seconds_rounds_up_to_frames` |
| AC-4 每帧可解释原因；同输入/参数/seed 可复核 | ✅ | `test_same_inputs_same_outcome`、`test_component_scores_finite_and_normalized`；5.3 HR（候选原因真机核对） |
| AC-5 Accept 不加 label；Correct 保留 provenance；Skip 不造坐标；保存重开一致 | ✅ | `tests/test_suggested_frame_review.py`（11 例）、`tests/gui/test_suggested_frame_review_actions.py`（21 例）；5.3 HR |
| AC-6 completed run 可显式激活；clear/replace 不丢 manual/旧产物，原子、可撤销、派生 stale | ✅ | `tests/test_result_activation.py::test_activate_replace_clear_lifecycle_and_undo_redo`（8 例）、`tests/gui/test_tracking_activation_actions.py`（5 例）；5.4 HR；本轮真实激活 `cffbed09`（98 AI / 50 manual 保留 / 50 superseded） |
| AC-7 至少两轮使用同一 fixed validation；RMSE 与 coverage 分栏展示 | ✅ | iter1–iter4 全部记录 `validation_series_id=f13d5bbd`；详情面板与 [loop report](../benchmarks/phase-5-loop-report.md) 分列 RMSE / coverage |
| AC-8 Advisor 覆盖 labels/resume-restart/epochs/batch/snapshot，建议有限且不自动训练 | ✅ | `tests/test_training_advisor.py`（20 例表驱动）、`tests/gui/test_training_advisor_actions.py`（Apply 不启动）；5.5 HR |
| AC-9 单摆完成建议→Correct→再训练→再推理→比较→激活闭环，报告三类 delta | ⚠️ **部分达成** | 闭环与三类 delta 全部真实完成并归档（[loop report](../benchmarks/phase-5-loop-report.md)、4 轮真实 DLC run、激活 `cffbed09`）；**"同一冻结基准上 ≥5% 可复现改善"未达成**（最佳 −3.3%），按用户决定（2026-09-16）如实归档为明示缺口，成因见 [review](../reviews/phase-5.6-review.md) F1/F4/F5 |
| AC-10 冻结人工审计集报告 Precision@N / review yield 并优于最低置信度基线 | ✅ | [phase-5.2-report.md](../benchmarks/phase-5.2-report.md)：policy 0.800 / 0.300 vs baseline 0.600 / 0.000 |
| AC-11 单一任务生命周期；全回归与独立 review 通过；有可感知交互变化时 HR | ✅ | 5.0 统一 runner（`tests/test_tracking_job.py`）；全回归 **698 passed**；各 Subphase 独立 review + HR 记录见 `docs/reviews/` |

**AC-9 缺口说明（供 Phase 5 收官与后续决策）**：闭环本身（流程、数据、产物、可追溯性）完整可复现；
缺的是"改善幅度 ≥5%"。根因：①挖掘在饱和模型上无信号（F4），screening 补齐把非困难帧推给用户（F1，
已修正）；②该 11 帧基准被反复用于模式选择，存在选择性污染（F5，用户提出）；③残差已接近人工
标注精度下限。建议后续以"未参与决策的保留帧/第二个视频"重建基准再评估改善。

## Result（收尾时填写）

- 完成日期 / 合并 commit：Slice 0 `ec4ae0c`、Slice 1 `3d9de31`/`f3f2743`、语义修正 `228e1ab`、
  Blocker 修复 `0d639e1`、记录 `be28162`/`f527f66`；**合并 commit 待 HR 确认后补记**
- AC 勾选结果：AC-1~AC-8、AC-10、AC-11 ✅；**AC-9 部分达成**（闭环与三类 delta 完成，
  "≥5% 可复现改善"未达成，按用户决定 ① 作为明示缺口归档）——逐项证据见上表
- 偏离计划之处及原因：①第三轮 10 个候选均为 screening 补齐（模型饱和、无真实困难帧），
  其标注不产生新信息且可复现地损害基准 → **已按用户批准移除 screening 补齐**，饱和时明示
  "未发现困难帧"；②原计划的"独立比较工具 + 用户可见报告"按用户要求改为**Advisor 内部输入 +
  Agent 归档**（不增加用户理解负担）
- 遗留问题（移交）：AC-9 改善证据缺失（成因 F1/F4/F5，建议以"未参与决策的保留帧/第二视频"重建基准）；
  交互体验重构待立项（[docs/notes/interaction-experience.md](../notes/interaction-experience.md)）
- 独立 review 结论：**自查**（用户指示不使用 subagent；两次 subagent 尝试因 Flash 配额失败）
  发现并修复 2 项缺陷（含 1 项 Blocker），详见 [phase-5.6-review.md](../reviews/phase-5.6-review.md) §5
