# Independent Review — Publication P0.2

- Date：2026-09-20；Scope：[data contract](../../publication/spec/experiment-run-derived-contracts.md)、ADR-0017、legacy reader tests。
- Reviewer：fresh-context read-only agent `/root/p0_contract_review`；原Reviewer额度中断后按用户“继续”恢复。
- Implementer：主Agent；Reviewer只读，全部处置由实现方完成。
- Verdict：合同范围 **PASS，无未关闭blocking finding**；Windows执行gate不在本数据合同review中。

## Findings / disposition

| Finding | 风险与处置 | 状态 |
| --- | --- | --- |
| D1 active pointer约束不足 | 明确同experiment/video、completed infer、四members及当前role映射；加载也验证 | CLOSED：原Reviewer最终复审确认 |
| D2 calibration依赖缺失 | 复用唯一active Calibration；记录scale/unit/origin/rotation/height；部分setup用null，删除/编辑失效 | CLOSED：原Reviewer最终复审确认 |
| D3 L/g与方向语义 | L/g正有限、provenance非空；向下方向显式确认并绑定端点digest，编辑撤销确认 | CLOSED：原Reviewer最终复审确认 |
| D4 run membership/来源 | Pendulum run强制四role快照、同video现存成员；trained model引用completed train且产物manifest匹配 | CLOSED：原Reviewer最终复审确认 |
| D5 role变更追溯 | mutation history保留old/new bindings完整快照/revision，即使从未active；result引用revision | CLOSED：原Reviewer最终复审确认 |
| D6 单轨写入口绕过四轨事务（Blocking） | bound track旧单轨AI mutator显式拒绝或路由完整experiment事务；负例列入P1验收 | CLOSED：原Reviewer最终复审确认 |
| D7 collection key/id | 加载拒绝map key与对象ID不一致 | CLOSED：原Reviewer最终复审确认 |

## Verification / boundary

2项旧reader测试包含v1 unknown fields保留、v2在domain读取前拒绝、原manifest/backup不变；全部20项publication contract tests通过。没有实现schema2 loader/migration/四轨功能，合同中的未来验收不能宣称已测试。用户已明确批准schema2 + Save As副本；ADR Accepted。本轮无GUI，不触发GUI Human Review。

最终独立复审：Reviewer只读运行7项runtime/legacy tests，全部通过；复核最终v3的8场景与证据边界。合同无剩余blocking finding，Windows external gate未关闭。
