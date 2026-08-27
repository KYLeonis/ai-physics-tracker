# ADR 0001: 以 ADR 方式记录架构决策

## Status

Accepted (2026-08-27)

## Context

AI Physics Tracker 是一个长期项目（Phase 0–10），开发将由多个开发周期（含 Coding Agent）接力完成。框架选择、数据格式、模块划分等技术决策如果只存在于对话或记忆中，后续开发者/Agent 无法追溯其背景与理由，容易无意推翻或重复讨论。

## Decision

1. 所有重要架构与技术选型决策以 ADR（Architecture Decision Record）形式记录在 `docs/decisions/`。
2. 命名：`NNNN-kebab-title.md`，编号四位、全局递增（0001, 0002, …）。
3. 每个 ADR 包含四节：Status / Context / Decision / Consequences。
4. 状态取值：`Proposed` / `Accepted` / `Superseded by NNNN` / `Rejected`。
5. ADR 一旦 Accepted 不再修改正文；需要推翻时新增 ADR 并把旧 ADR 状态改为 `Superseded by NNNN-…`。
6. 决策模板见 `_template.md`；新 ADR 应在 `docs/architecture.md` 的"决策记录"一节与相关文档中链接。

## Consequences

- 正面：决策可追溯，Agent 与人类开发者能快速理解"为什么这样设计"；避免重复论证。
- 负面：需要维护纪律——每个重要决策都要写 ADR；本文件本身即为此建立流程。
- 立即行动：本 ADR（0001）与 0002（Python 版本选择）作为首批记录。
