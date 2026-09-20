# Independent Review — Publication P0.3

- Date：2026-09-20；Scope：[runtime contract](../../publication/spec/runtime-boundary.md)、disposable host/worker、smoke修复、tests、[实测证据](../../publication/evidence/runtime/README.md)。
- Reviewer：fresh-context read-only agent `/root/p0_contract_review`。
- Verdict：合同范围 **PASS，无未关闭blocking finding**；**Windows G1–G4 not_run，经用户批准延期至P6前，P0.3按调整后的安排收尾**。

## Findings / disposition

| Finding | 处置 | 状态 |
| --- | --- | --- |
| R1 result identity之外缺config/payload/output验证（Blocking） | canonical request digest包含worker SHA；按op检查payload；声明输出size/SHA及root containment；负例覆盖 | CLOSED：原Reviewer最终复审确认 |
| R2 cuda:0与backend比较错误 | 允许同backend数字后缀，保留actual device；拒绝其他backend | CLOSED：原Reviewer最终复审确认 |
| R3 terminal status/exit矛盾 | success/cancelled=0、failed=1；host forced cancellation独立，不采用迟到结果；负例覆盖 | CLOSED：原Reviewer最终复审确认 |
| R4 fallback/metadata口径 | 明确spike无自动fallback，产品未来必须记录；spike条件metadata与产品全字段要求分别列出 | CLOSED：原Reviewer最终复审确认 |

## Actual verification

最终v3 PyInstaller冻结host真实运行8场景，详见results.json与归档日志：Unicode hello、CPU selftest、MPS tensor selftest、CPU DLC 1 epoch/10帧infer/显式Activate保留5manual/保存重开成功；协作取消、强制树取消和DLC启动期取消均cancelled；故意失败保留traceback。强制测试child PID已不存在。初次DLC跑到推理后因旧smoke断言失败，修复过期自动激活假设后重跑；未修改产品src。

20项publication tests通过，3个源码hash与8个场景日志hash复核通过。协议tests使用source host，不能冒充frozen测试；frozen证据单独记录。MPS不是DLC完整训练验收；启动期取消不是GPU epoch内取消；复用旧venv不是first-run clean install。Windows命令已准备，无可访问Windows主机，用户已批准延期，进入P6前必过。不得从Mac或mock推断Windows通过。

最终独立复审：Reviewer只读运行7项runtime/legacy tests，全部通过；复核最终v3的8场景与证据边界。合同无剩余blocking finding，Windows技术证据gate仍未通过，用户已明确批准延至P6前。
