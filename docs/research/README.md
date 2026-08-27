# Research Notes

本目录保存 AI Physics Tracker 的开源项目源码调研结果。

## 目录约定

- `open-source-project-map.md`：面向 Coding Agent 的总索引、跨项目比较、License Map 与结论。
- `software-spec-plan.md`：**Phase 1 前最后一轮准备性调研行动计划**（收敛版 v2，**已 Closed/完成**）——6 个行动项（领域模型、时间语义、标定、持久化、最小接口、Phase 1 验收标准），产出 `docs/spec/` 三份规范 + ADR-0003；后续 Phase 的调研项统一在其 Later Research/Open Items 表中按启动时点取用。
- `raw/`：每个上游项目一份源码级 Code Map；只记录已检查的源码路径、类/函数、调用链和可借鉴点。
- `.upstream/`：仅供本地复核的浅克隆/部分克隆源码快照，已加入仓库忽略规则，不作为项目源码提交。

## 研究记录规则

- 活跃度数据以 GitHub REST API 的公开字段为准，并注明 `Checked on` 日期；stars/forks 只表示生态规模，不表示技术质量。
- 每份 notes 记录调研时的 commit SHA。上游代码会变化，未来 Agent 应先核对该 SHA 和当前默认分支。
- 许可证严格区分代码、模型权重、数据集、第三方依赖和示例媒体；无法确认时写 `Needs license review`。
- 结论中的“可借鉴”只表示架构/实现参考，不表示可以直接复制代码。
