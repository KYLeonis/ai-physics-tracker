# Review Record — Phase 5.6 Refinement Loop Integration & Acceptance

> **用法**：一个 subphase 一个文件，贯穿整个审查生命周期。流程规则见 `docs/workflow.md` §6。

- Subphase / Issue：5.6 — Refinement Loop Integration & Acceptance · [#22](https://github.com/KYLeonis/ai-physics-tracker/issues/22)
- 分支：`feat/p5.6-loop-acceptance`
- 状态：🚧 Slice 0/1 完成；Slice 2 闭环执行完毕但 **AC-9 改善证据未达成**（见 Findings + 判定）；
  Slice 3（总验收/独立 review/HR/收官）待用户对 AC-9 处置作出决定后继续。
- Context：`docs/status/phase-5.6-plan.md`、`docs/spec/phase5-requirements.md` AC-9、ADR-0014/0015

## 1. Slice 0 — 批复决策落地（A/B/C）

| 项 | 结果 |
| --- | --- |
| A 崩溃恢复 | **已存在于 Phase 4**（`ProjectSession.load` 自 `0b1add2` 起把无进程对应的 pending/running run 标记 failed，`tests/test_tracking_job.py:359` 有断言）。5.4 R2 复审当时查错了层（GUI 按钮层而非加载层），本轮核实后无需改动 |
| B 删除 DLC 目录复用 | `prepare_training` 强制 fresh per-run 目录；同目录二次 prepare 与缺 working_dir 均显式拒绝（`ec4ae0c`，测试同步改写） |
| C 激活指纹 size-only | 用户选方案 2：仅比对文件大小（`ec4ae0c`） |

## 2. Slice 1 — delta 内化与激活引导

- Advisor 输入新增 coverage 证据对（仅证据行、9 条规则合同不变）与未激活 infer run 引导（`3d9de31`/`f3f2743`）。
- 归档工具 `scripts/generate_loop_report.py`（开发侧，不进产品）＋机械判定段（基准轮/最佳轮/最新轮 vs ±5% 阈值）。

## 3. Slice 2 真实闭环与 Findings

**执行链（AI_test2，148 帧单摆）**：iter1 resume（19 labels）→ iter2 resume +10（29）→ iter3 restart（29）
→ iter4 restart +10（39）；同 series `f13d5bbd` 的 11 帧冻结基准上依次 **3.30 / 4.80 / 3.19 / 4.71**。

### F1 — screening 补齐把"不困难"的帧当成困难帧推给用户 【High（产品语义，需决策）】

- **证据**：第三轮挖掘（`cffbed09`，09-16 10:50）10 个候选的 `reasons` 全为 `screening`（无任何
  low_confidence/jump/residual/prior 触发）；这些帧的模型置信度 0.95–1.00，用户"修正"点击与模型
  预测仅差 3–7px（见 `/tmp` 诊断脚本输出与 10 帧对照图）——即**模型本来就在这些帧上正确**。
- **影响**：用户 10 帧标注劳动未带来新信息；且这 10 帧全部落在摆最低点附近（y≈759–760，
  x 1019–1114 的窄区），使 28 帧训练集出现明显分布偏移，iter4 的 valid loss 达 iter3 的 20 倍
  （0.00886 vs 0.00042），冻结基准 val RMSE 由 3.19 恶化到 4.71。
- **根因**：5.2 的 screening 补齐语义（为避免"好模型上队列为空"而按连续分数补足 top_n）在模型
  确实干净时无法区分"值得看"与"随便看看"，却以同样的候选形态呈现给用户。
- **建议**（需用户批准，涉及 5.2 已批准语义）：触发池为空时明示"该模型上没有发现困难帧"，
  不用 screening 帧填满队列；或至少在 UI 标注这些候选"不确定是否值得审核"。

### F2 — 冻结验证集从 project.json 消失 【Medium（数据完整性）】

- **证据**：`track.extra_fields.refinement_state_v1` 现为空（`{}`），activation_history 也为空；
  磁盘上 project.json 与其轮转备份 `project.backup.json` 均无 series，而 iter1–iter4 的
  `refinement_iteration_v1.validation_series_id` 全部指向 `f13d5bbd`。
- **代码排查**：①合成 roundtrip（创建 series → save_as → load → save → load）保留 series；
  ②完整训练提交链（prepare → spawn worker → candidate → save）保留；③headless 推理提交链保留
  （iter4 在 11:12 的无头推理之后仍能读到 series）；④静态扫描未见重建 Track 对象丢 `extra_fields`
  的路径；⑤删除入口 `delete_validation_series` 需在对话框二次确认（默认 No）。
  → 未能证明为代码缺陷；最可能是 UI 中显式删除（亦无法完全排除未发现的路径，见下"建议"）。
- **可恢复性**：验证集成员 = 当时 manual 帧 − 该轮 training_labels = **11 帧**
  `[0, 1, 6, 13, 18, 26, 60, 73, 110, 129, 143]`；已用 `create_validation_series` 在副本上
  成功重建（演练通过），坐标取当前 manual 点（series 在 iter4 时仍有效，说明快照与 manual 一致）。
- **建议**：①为"AI 任务提交链 + 保存"补 series 存活回归测试（低成本、防未来回归）；
  ②删除 series 时给出影响警告（历史评价将不可比）；③按用户决定在 AI_test2 中重建 series
  （新 id 不影响帧成员可比性，但 Advisor 不会把旧轮与新轮视为同 series）。

### F3 — 训练是确定性的：delta 是真实效果，不是噪声 【结论性证据】

- **实验**：在项目副本（`/tmp/rt56`，仅复制 `project.json` 并重建同一 11 帧验证集）用
  `scripts/headless_train.py --epochs 50` 复跑与 iter4 完全相同的配置（39 labels、restart）。
- **结果**：新 run `d5792750` 的评估指标与 iter4 完全一致（val 4.71 / train 4.67），且
  **模型快照 sha256 相同**（`5784b6ab018d985b`，size 94319571）——两次独立启动（GUI 一次、
  headless 一次）产出字节相同的权重。
- **推论**：本流水线的训练与评价是**确定性**的（同一数据 + 同一配置 → 同一结果）。
  因此 3.30 / 4.80 / 3.19 / 4.71 的差异是**可复现的真实效果**，不是 run-to-run 噪声；
  AC-9 的"未达成"是可复现的结论，改变结论需要改变数据或配置，而不是重复实验。
- **原 F3 假设（"噪声主导、基准分辨率不足"）已被本实验推翻**，如实更正。
- 归档复现命令：`python scripts/generate_loop_report.py --project <副本>` 会输出各轮快照
  sha256（相同即确定性），见 [phase-5-loop-report.md](../benchmarks/phase-5-loop-report.md) §复现性。

### F4 — 模型在全部帧上饱和，挖掘无可用信号 【High（产品语义，与 F1 同源）】

- **证据**：iter3 模型（`cffbed09`）在 **148/148 帧**上置信度 ≥0.915（p5=0.978，中位 1.000），
  无任何低置信/缺测帧；冻结基准 11 帧的逐帧误差为 1.0–5.7px（均值 3.19，中位 2.66），
  分散而非集中于个别帧。
- **影响**：挖掘的触发信号（低置信、跳变、残差、Correct 邻域）在该模型上永远不会触发，
  队列只能靠 screening 补齐（F1），而补齐帧与模型预测仅差 3–7px——审核这些帧不产生新信息，
  反而因训练分布偏移而**可复现地**损害基准（3.19 → 4.71）。
- **建议**：①触发池为空时明确告知"该模型未发现困难帧"，不用 screening 填满（同 F1）；
  ②在 spec/AC 层面承认：当模型饱和时，闭环的收益来自标签**质量/一致性**而非数量，
  需要不同的评估设计（如重复标注一致性研究），而不是继续挖帧。

## 4. AC-9 判定

| 轮次 | 配置 | 训练标签 | 冻结基准 val RMSE | 相对基准 |
| --- | --- | --- | --- | --- |
| iter1 `f8d5fe67` | resume 25 | 19 | 3.30 | 基准 |
| iter2 `e976e5dc` | resume 25 | 29 | 4.80 | +45.5% |
| iter3 `18d1f638` | restart 50 | 29 | **3.19** | **−3.3%** |
| iter4 `b80fbd68` | restart 50 | 39 | 4.71 | +42.7% |

- **结论：未达成**（最佳改善 −3.3%，落在 ±5% plateau 内），三轮循环预算已用完；
  归档证据见 [phase-5-loop-report.md](../benchmarks/phase-5-loop-report.md)。
- AC-9 同时要求"闭环完成 + 报告三类 delta"——**闭环与报告已真实完成**（iter1→iter4 全部 run、
  三类 delta、激活历史在库），缺的是"≥5% 可复现改善"这一条。
- **性质**：训练确定性已证实（F3），因此"未达成"是可复现结论而非测量噪声；成因见 F1/F4
  （screening 补齐把非困难帧当困难帧；模型已饱和、无可用挖掘信号）。
- 处置需用户在以下选项中选择（Slice 3 前）：
  ① 以"未达成"如实归档，并作为明示缺口在 spec/roadmap 处置（推荐，含 F1/F4 成因与改进建议）；
  ② 重新定义 AC-9 的证据口径（例如：承认"改善"依赖标签质量、在饱和模型上不可达），属 spec 变更；
  ③ 追加更大规模实验（新项目 + 更大且更难的标签集），成本高且 F4 表明当前测试床可能无法产生 ≥5%。

## 5. 待补（Slice 3）

- AC-1–AC-11 总验收核对表；独立 review（多 subagent）；Human Review；文档同步/合并/push/关 Issue。
