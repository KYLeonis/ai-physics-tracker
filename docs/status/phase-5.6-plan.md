# Subphase Plan — Phase 5.6 Refinement Loop Integration & Acceptance

- Issue：待计划确认后创建
- 分支：`feat/p5.6-loop-acceptance`
- 日期 / 状态：2026-09-05 · 📝 Draft，等待用户确认

## Goal

把 5.1–5.5 串成一次**真实、可复现、量化**的单摆 refinement 闭环（AC-9），并完成 Phase 5
总验收（AC-1–AC-11 逐项证据核对）。闭环定义：

```text
（已完成于 AI_test2）建议帧 → 标注 → 冻结 validation series → train(iter0) → infer
（本 Subphase 完成）        mine → review/Correct → Advisor → retrain(同 series) → reinfer
                           → 三类 delta 比较 → 用户显式激活 → 证据归档
```

**AC-9 的"三类 delta"**（同一 validation series 上，同指标同单位）：

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

## Slice 1 — 迭代比较报告（AC-9 的"报告三类 delta"）

- 新增 Qt-free 纯函数模块（如 `application/iteration_compare.py`）：输入当前 track 的
  completed train/infer runs，输出同 series 相邻两轮的 delta 摘要值对象（精度/覆盖/工作量，
  附不可比原因说明）；**不写盘、不新增 GUI 窗口**。
- `scripts/benchmark_difficult_frames.py` 风格的 CLI 或最小入口（`scripts/compare_iterations.py`）
  打印/写出 markdown 报告（进 `docs/benchmarks/phase-5-loop-report.md`，人工证据归档）。
- 表驱动测试：改善/恶化/持平、不同 series 不可比、指标名/单位不一致拒绝、单轮无 delta。

## Slice 2 — 真实单摆闭环执行（用户参与的半自动流程）

**测试床**：继续用 `experiment/AI_test2`（148 帧、30 manual、series `f13d5bbd`、
iter0=test RMSE 3.3 已在盘）。理由：AC-9 前半段（建议帧→标注→冻结→train→infer）在该项目
已有真实证据，重开新项目要用户重复标注 ~30 帧且不产生新信息；本 Slice 补齐后半段。

执行序（Agent 驱动计算步骤，用户做人工判断步骤）：

1. 对当前 active infer run 发起困难帧挖掘（Top N=10，min_gap 默认）。
2. **用户**在审核队列逐帧 Accept/Correct/Skip（预计 ≤15 分钟；Correct 产生新训练标签）。
3. **用户**查看 Advisor 建议（预期：新增标签 → resume 25 epochs）并确认或手选参数。
4. Agent/用户启动 retrain（resume，同 series）→ reinfer 全视频。
5. Agent 运行 Slice 1 工具生成三类 delta 报告；**用户**确认后显式 Activate 新结果。
6. 若精度 delta 未改善：按 Advisor 证据决定再补一轮标注（循环上界 **2 轮**）；仍无改善则
   如实归档失败证据与原因分析（AC-9 允许），此时与用户讨论是否继续。

**产物**：`docs/benchmarks/phase-5-loop-report.md`（闭环各阶段 run id、三类 delta、
激活记录、结论），作为 AC-9 与"至少一次可复现改善"的证据。

## Slice 3 — Phase 5 总验收与收尾

1. AC-1–AC-11 逐项核对表（勾选 + 证据链接：测试/报告/review record/CI），写入本 plan Result。
2. 独立 review（多 subagent，聚焦 Slice 0 改动的数据语义 + 比较工具正确性 + 闭环证据链）。
3. 全量回归 + compileall + 真实 DLC smoke（restart/resume 已在 CI 外本地验证路径）。
4. Human Review：闭环操作体验（挖掘→审核→Advisor→再训练→激活）由用户在真机走一遍确认。
5. 文档全量同步（roadmap Phase 5 → ✅、README、AGENTS、phase-5-plan Result、各 review 索引）、
   合并 `--no-ff`、push、关闭 Issue；**Phase 5 收官后停止，等待 Phase 6 指令**。

## 不做

- 不新增 GUI 窗口/控件（闭环使用既有 5.1–5.5 交互；AC-11 的 HR 针对既有交互串联体验）。
- 不改 schema、不加新持久化字段（delta 报告消费既有 run 记录）。
- 不做 Windows/CUDA 真机验收（已批准延期至 Phase 9 前）。
- 不自动激活结果、不自动循环训练（每轮由用户显式启动/确认，Phase 5 硬性不变式）。

## 验收标准

- [ ] Slice 0 三项（A/B/C）落地并有测试；5.4 review record 状态更新
- [ ] 比较工具对同 series 两轮正确产出三类 delta；不可比场景拒绝并说明
- [ ] 真实闭环完成：Correct → retrain → reinfer → 报告 → 用户激活，全程 run id 可追溯
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
.venv/bin/python scripts/compare_iterations.py --project experiment/AI_test2   # Slice 2 报告
```

## Result（收尾时填写）

- 完成日期 / 合并 commit：
- AC 勾选结果（含 AC-1–AC-11 核对表）：
- 偏离计划之处及原因：
- 遗留问题：
- 独立 review 结论：
