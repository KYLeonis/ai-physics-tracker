# Review — <对象：commit 范围 / Subphase 编号>

> 给独立 review 用的 Agent 会话：只依据 diff 与下列 Context 文档判断，不提供实现过程叙述。

- Review 范围（commits / 分支 / 文件）：
- 相关 Context（spec / ADR / subphase plan 路径）：

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

- **Blocker（必须修）**：
- **Suggestion（可延后）**：

## Verdict

- [ ] 通过
- [ ] 修改后通过（列出 Blocker）
- [ ] 需要重做（说明理由）
