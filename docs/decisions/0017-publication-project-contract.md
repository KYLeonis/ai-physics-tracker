# ADR-0017 — Publication schema and multi-track experiment boundary

## Status

Accepted（P0.2，2026-09-20）。用户明确选择“接受 schema v2 + 另存迁移副本”；本轮固定契约，不实施迁移。

## Context

现有schema1 serializer保留未知字段，但TrackingRun/DerivedInput/activation/stale/delete按单track解释。仅在extra_fields增加四点信息会让旧应用合法打开并执行破坏四轨一致性的操作。repository已经在domain decode前拒绝schema>1。

## Decision

publication project使用schema2、显式Save as迁移，旧v1原件保持；Track=物理点不变，run使用members，experiment持有唯一四轨active指针，publication typed results记录多输入依赖。继续单manifest原子保存与immutable外置产物。具体字段/invariants见[contract](../../publication/spec/experiment-run-derived-contracts.md)。

## Consequences

旧应用明确拒绝新publication项目，不能编辑后声称安全；generic v1仍可使用。需要P1实现migration及跨集合validation，不在P0抢先开发产品。拒绝无版本sidecar绕过reader guard和将tip作为假单track owner的方案。此决策仅本publication线，不自动升级main格式或替换既有Accepted ADR的历史语义。
