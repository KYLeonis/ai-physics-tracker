# ADR-0020 — 分析批次的目标结果版本与计算配方一致性

## Status

Accepted，2026-10-13。Phase 6.1 完整复审的修复，沿用 ADR-0009/0019 原子提交，不改变持久化 schema。

## Context

仅比较 raw / 标定 / 时序不足以拒绝迟到任务：同一观测上先计算新支点或新 SG 窗口，旧任务
仍可覆盖它。批次数量一致也不证明结果引用和计算规格一致。6.2 将允许配置参数和角量，
需要先补齐这些边界。

## Decision

- prepare 捕获将被替换的 `(track_id, kind)` 集合的当前 `derived_id` 元组，随 Job / Result 传递。
  提交时目标结果身份须仍相同；重算 / 清除后的旧任务拒绝。其他分析族、参考轨迹自己的结果、
  未选轨迹和未知 kind 不进入该版本比较，避免无关计算互相阻止。
- Result 携带本次 SmoothingParameters，核对 SG 窗口、阶数、导数阶、mode 与物理 delta；
  angular 同时核对 specs、目标+参考实际输入集合、每条 input 引用与 pipeline 参考配方。
  linear 结果不能声称具有第二参考轨迹；calibration_ref 与唯一标定 pipeline step 必须对应当前输入，
  无标定的 pixel 结果不得声称经过标定。完整性及输入未变校验继续由共同 validated_batch 负责。
- 同步 / 后台计算均需当前时序授权；缓存结果仍可只读查看。Angular 结果统一保存
  fps / working_zone / 近似授权来源，后台不再额外拼装一套溯源。
- working_zone 改变使该视频相关派生 stale，不改观测、冻结时间或源帧编号；不引入区间编辑 UI。
- GUI 的参数修改仍须取消其拥有的任务 / 核对上下文；目标结果版本不能代替用户当前设置和取消 token。

## Consequences

补丁只追加应用层 DTO 字段，保留旧构造的前部参数；持久化仍为 v1 additive。无法证明基线或
配方的批次 fail-closed 并可重新准备。现有未知字段合并、非目标结果保留和一个批次一个 Undo
步不变。这里提供确定的提交策略，未建立完整历史版本库或通用计算框架。
