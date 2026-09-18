# Subphase Plan — Phase <N.M> <topic>

- Issue：#<n>
- 分支：`feat/p<N.M>-<topic>`
- 日期 / 状态：YYYY-MM-DD · 进行中｜已完成｜已废弃
- 风险等级：Normal-risk｜High-risk（判定标准见 `docs/workflow.md` §10.2；决定 Review Gate）

> 使用说明：Subphase 开始时填写 Goal 到 Review Gate 各节（十几分钟内完成，不求完美）；
> Result 在收尾时填写。AC 每条必须可独立验证；Context Pack 是相关历史的**索引**，
> 不是历史百科——只列真正相关的条目，没有内容的节写"无"，不要硬凑。

## Goal

一句话：这个 Subphase 完成后，项目多出什么**可验证**的能力 / 文档 / 修复。

## Agent Context Pack

> 让没有本仓库记忆的 Agent 在几分钟内找到与本任务相关的材料；
> 不要求通读 `docs/reviews/` 或全部 ADR。规则见 `docs/workflow.md` §3.1。

### Authoritative Docs

- 当前 Phase requirements：
- Phase master plan：
- 相关 ADR / spec（只列与本任务相关的，附一句为什么）：

### Relevant Historical Findings

- （Finding ID / Review Record 路径 — 一句话说明为什么本任务仍需知道它；无则写"无已知相关历史 finding"）

### Scientific / Data / Product Invariants

- （本 Subphase 不能破坏的契约，如数值 / 持久化 / 交互不变量；无则写"无特殊不变量"）

### Known Deferred / Accepted Items

- （影响本任务边界的已延期 / 已接受事项；无则写"无"）

### Explicit Non-goals

- （本 Subphase 不应顺手解决的内容；与 Scope 的"不做"重复时保留一处即可）

## Scope

**做**：

**不做**（同样重要，防止范围蔓延）：

## Acceptance Criteria

- [ ] （可验证的判定句：测试通过 / 文件存在且覆盖某问题 / 可演示某操作）
- [ ] …
- [ ] …

## Slices

- [ ] Slice 1：一句话描述（预期产出 + 验证方式）
- [ ] Slice 2：…

## Verification

如何证明 AC 满足：运行哪些测试 / 检查哪些文件 / 手动验收哪些步骤。

## Review Gate（计划期声明，不等实现完才决定）

- **Independent Review**：触发 / 不触发。High-risk 默认触发；触发时写明审查重点与 Context 材料（`docs/workflow.md` §6.2）。
- **PR**：建议 / 不需要。High-risk 建议以 PR 作为完整 diff 的观察与集成容器（`docs/workflow.md` §10.2）。
- **Human Review**：适用 / 不适用。交付含用户可感知交互行为时适用（`docs/workflow.md` §5.1）。

## Result（收尾时填写）

- 完成日期 / 合并 commit：
- AC 勾选结果：
- 偏离计划之处及原因：
- 遗留问题（移入 `docs/status/current.md` 或下一 subphase）：
- Review Gate 执行结果：Independent Review 结论（链接 Review Record 并总结最终 Verdict，不重复 findings 清单）／Human Review 结论／无
- 实现中发现的新 invariant / finding（回写本 plan 的 Context Pack 与 `docs/status/current.md`）：
