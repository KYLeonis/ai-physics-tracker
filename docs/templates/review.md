# Review Record — Phase <N.M> <主题>

> **用法**：触发 Independent Review 时，首轮 review 会话把本模板复制为 `docs/reviews/phase-X.Y-review.md`；一个 subphase 一个文件，贯穿整个审查生命周期，不随轮次新建。
> **分工**：Reviewer 只读（不修改产品代码）——填写 Scope、Checklist、Findings、Review Log 与复审结论；Decision、Fix commit、Verification 由 Implementation Agent 维护；Final Verdict 依据最后一轮复审结论收口。
> **审查依据**：diff 与 Context 文档判断，不参考实现过程叙述。流程规则见 `docs/workflow.md` §6。

- Subphase / Issue：
- Review 范围（commits / 分支 / 文件）：
- Context（spec / ADR / plan 路径）：
- 轮次：R1 <日期>（首轮）· R2 <日期>（复审）…

## Checklist

**正确性**

- [ ] 实现与 subphase plan 的 AC / 相关 spec 一致
- [ ] 边界情况处理正确（空数据、缺测值、越界、异常输入）
- [ ] 数值逻辑有合成数据验证（如适用）

**质量**

- [ ] diff 无范围外改动
- [ ] 遵守 `docs/development.md` §1.1 可移植性规则（pathlib / UTF-8 / 无 symlink / Windows 保留名）
- [ ] 公开接口与数据结构有说明，命名与既有代码一致
- [ ] 测试真实覆盖新逻辑，而非只覆盖 happy path

**流程**

- [ ] 提交信息符合 Conventional Commits
- [ ] 属于 ADR 级别的决策是否已记录（`docs/workflow.md` §7 判断句）

## Findings

> 按 F1、F2… 顺序编号，一经分配不复用；判定不成立的问题同样保留编号并记 `Not Reproducible`。
> 提出问题不等于必须修复：理论性、低影响、低概率，或修复会明显过度工程的问题，明确记 `Accept` / `Defer` 并写一句理由。

### F1 — <一句话标题>

- **Severity**：Blocker（不修复不能通过）/ Suggestion（可延后）
- **Evidence**：<文件:行号 / 复现步骤 / 输出片段>
- **Impact**：<不处理会怎样>
- **Recommendation**：<Reviewer 建议>
- **Decision**：Fix Now / Fix Before Close / Defer / Accept / Not Reproducible ——<一句话理由>（Implementation Agent 填）
- **Fix commit**：<hash 或 N/A>
- **Verification**：<实际运行的命令与结果，或 N/A>
- **Re-review**：<Rn 确认修复 / Rn 未通过及原因 / N/A>
- **Status**：Open / Closed

<!-- F2 起复制以上结构。-->

**Decision 取值**：

| Decision | 含义 |
| --- | --- |
| Fix Now | 立即修复，先于后续 Slice |
| Fix Before Close | subphase 收尾前必须修复，排序可与后续 Slice 并行 |
| Defer | 明确推迟，注明目标（Phase / Issue / 触发条件） |
| Accept | 不修；理由为理论性 / 低影响 / 修复成本与收益不成比例 |
| Not Reproducible | 按所述条件复现失败，记录尝试方式后关闭 |

## Review Log

> 每轮 review 追加一节：只写结论与 finding 变化，不记录对话或思考过程。

### R1 — <日期> · 首轮

- 范围 / 基线：
- 结论（一句话）：
- Findings 变化：新增 F1、F2；关闭 —

### R2 — <日期> · 复审

- 结论：
- Findings 变化：

## Final Verdict（收口时填写）

- [ ] 通过（无未处置 Blocker）
- [ ] 修改后通过（findings 按 Decision 处置完毕，复审确认）
- [ ] 需要重做（说明理由）

- 最终结论（一句话）：
- 日期 / 依据轮次：
