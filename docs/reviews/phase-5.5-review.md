# Review Record — Phase 5.5 Training Advisor & Retraining

> **用法**：一个 subphase 一个文件，贯穿整个审查生命周期。流程规则见 `docs/workflow.md` §6。

- Subphase / Issue：5.5 — Training Advisor & Retraining · [#21](https://github.com/KYLeonis/ai-physics-tracker/issues/21)
- Review 范围（分支 `feat/p5.5-training-advisor-retraining`）：
  - Slice 0（Entry Gate）：`d830afd`
  - Slice 1（ADR-0015 + Advisor 引擎）：`94f67b0`
  - Slices 2–4（restart/resume 管线、GUI、可靠性测试）：`9c64416`
  - 真实 DLC smoke + 文档：smoke 提交、`e61db13`、`d450974`
  - R2 修复：`1c8aafe`（Advisor 引擎）、`15d7be4`（GUI/管线）
- Context：`docs/status/phase-5.5-plan.md`（Advisor Rule Contract、AC）、`docs/decisions/0015-training-advisor-and-resume-retraining.md`、ADR-0014、`CODE_STANDARD.md`
- 轮次：R1 2026-09-04（三路 GLM-5.3-Flash 并行）· R2 同日修复与回归

## 1. 执行方式披露

R1 计划三路 subagent 并行；其中 **resume 管线 Reviewer 因 GLM-5.3-Flash 周用量上限中途失败**
（重置时间 2026-09-05 17:28），该区域由主 agent 按同一审查清单自查补位（含探针验证），
结论以"自查"标注，可信度等级低于独立 subagent 审查，已在下表注明。

## 2. R1 Findings 与处置

### A 路 — Advisor 引擎（approve-with-comments，9 条全部修复，`1c8aafe`）

| # | Severity | 问题 | 修复 |
| --- | --- | --- | --- |
| A1 | Medium | pending 候选未抢占 fix_prerequisite（建议文本教用户"冻结后 retrain"） | 抢占集合加入 FIX_PREREQUISITE + 组合用例 |
| A2 | Medium | correction_yield 越权触发 label_more（0 候选时建议标 1 帧，低于最小档） | 触发收窄为 pending>0；yield 保留为档位输入 |
| A3 | Low | gap-only 证据错误写 "worsened"（delta 处于 plateau 区间甚至为负） | 仅真正恶化时用 worsened 措辞 |
| A4 | Low | ±5%/1.5× 边界与 pending 组合无测试固定 | 三组参数化/组合用例（inclusive 语义验证） |
| A5 | Low | training_mode 无白名单（"banana" 可构造，GUI 静默映射为 restart） | 限定 None/restart/resume |
| A6 | Nit | available=max(pending,1) 静默钳位 | 由 A2 修复消除该路径 |
| A7 | Nit | 未用 Any import；OOM 标记与 GUI 双份清单漂移 | 删 import；提为共享 OOM_MARKERS 常量 |
| A8 | Nit | 数值校验 bool/字符串可过，TypeError 违反 §8 | 前置 isinstance 校验统一 ValueError |
| A9 | Nit | 测试死代码（del ACTIONS）与弱断言 | 清理 + 强断言 |

### B 路 — GUI 生命周期（request-changes，11 条全部修复，`15d7be4`）

| # | Severity | 问题（均经 Reviewer offscreen 实证） | 修复 |
| --- | --- | --- | --- |
| B1 | **Blocker** | Restart + 模型列表自动选中项 → train() 携带 source 被 prepare 拒绝：迭代闭环中最常见的"再训一次"路径被堵死 | 仅 Resume 模式携带 source；补回归测试 |
| B2 | **Blocker** | `rev_sum.reviewed_count` 属性不存在（实际 total_reviewed）：激活 infer 后训练必在 worker 内 AttributeError 崩溃 | 字段修正 + "激活后训练"回归测试 |
| B3 | Major | timeline 查找误用 track_id 比较 video_id → uncovered 恒 False，plateau 规则 8 静默失效 | 按 track.video_id 对齐 + 采集层守卫 |
| B4 | Minor | working_zone None 解包被吞导致 Advisor 整体消失；zone 外帧索引为负绕过缺段判断 | zone 守卫 + 索引钳位 [0,3] |
| B5 | Minor | Apply Suggestion 未填 source 与 plan 文字不符 | 记录偏离并修正 Scope 措辞（Advisor 不越权选模型） |
| B6 | Minor | 切换 track 后 Resume 模式残留 | modelList 为空时复位 Restart |
| B7 | Minor | context key 不含 mining/选帧/project busy，禁用原因有过期窗口 | 三个 busy 位纳入 key（getattr 守卫兼容裸窗口） |
| B8 | Nit | 函数内死导入 | 删除 |
| B9 | Nit | units 变量赋值误导 | 内联 isinstance |
| B10 | Nit | coverage 格式化缺类型守卫（损坏 JSON 可中断 history 刷新） | isinstance 数值守卫 |
| B11 | Nit | Advisor 采集失败与未选 track 同文案 | 区分文案 |

### C 路 — resume 管线（**自查补位**，3 项）

| # | Severity | 问题 | 修复 |
| --- | --- | --- | --- |
| C1 | Medium | prepare→spawn 窗口内 resume snapshot 被 TOCTOU 篡改仅有存在性检查 | worker 侧复核 (size, mtime_ns) 指纹（`15d7be4`） |
| C2 | Low | DLC 跨项目加载 snapshot 依赖 bodyparts/网络结构一致（config 来自新项目） | 已知限制：产品限定单 bodypart "target" 且 per-run 项目结构一致；真实 smoke 已覆盖基本路径；多 bodypart 属 Phase 10 |
| C3 | Low | resume 训练与 activate/replace 的并发：5.4 的 track 级 pending/running 互斥已覆盖（resume 产生 train run） | 验证无需改动 |

自查另确认：GUI 侧校验（跨 track/非 completed/快照缺失/指纹不符）有集成测试覆盖；
lineage 在失败/取消路径的 run 状态由统一 runner 既有语义处理；restart/resume 均不删除或覆盖旧产物。

## 3. 验证

- 全量回归 **693 passed**（5.4 收口 658 → 5.5 新增 35），`compileall` 通过。
- 真实 DLC 3.0.1 两段 smoke：restart（1 epoch，fixed split 3/2）→ resume（新 per-run 项目，
  `train_network(snapshot_path=...)`）→ 新 snapshot-002，epoch 编号延续，parent 未覆盖。
- 定向：advisor 20 项、advisor GUI 7 项、tracking_job 11 项、refinement 9 项、repository 20 项。

## 4. Human Review（合并前关卡，等待用户）

按 plan AC，以下 5 项请用户真机验证（启动：`.venv/bin/python -m ai_physics_tracker`，打开 AI_test2 项目）：

1. 查看 Advisor 摘要：证据与限制是否可解释（不同 track/状态下的建议变化）。
2. Apply Suggestion 只填 mode/epochs/batch，**不自动开始训练**。
3. 手选 Restart 并启动训练（模型列表有选中项时，验证 B1 修复）。
4. 手选 Resume source 并追加 epochs 启动；确认新 run 的 history 详情显示
   training_mode=resume、resume source、produced snapshot。
5. 保存重开项目：history 的 mode/source/snapshot/evaluation 可追溯。

**通过前不合并、不关闭 Issue #21、不 push。**

## 5. Final Verdict

- [x] 修改后通过（R1 findings 全部处置；C 路为自查补位，已在 §1 披露）
- [ ] 通过（首轮无 finding）
- [ ] 需要重做

- 最终结论：Advisor 引擎、resume 管线与 GUI 经 R1 + R2 后无已知 Blocker/Major；
  693 tests + 真实 DLC smoke 通过；待 Human Review 后收尾合并。
- 日期 / 依据轮次：2026-09-04 · R1（A/B subagent + C 自查）+ R2
