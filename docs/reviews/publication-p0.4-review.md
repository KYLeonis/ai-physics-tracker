# Independent Review — Publication P0.4

- Date：2026-09-20；Scope：P0合同/证据收敛、后续phase入口与状态真实性。
- Reviewer：fresh-context read-only agent `/root/p0_contract_review`。
- Verdict：合同范围 **PASS，无未关闭blocking finding**；**整体P0按用户明确批准的Windows延期安排关闭；Windows仍not_run，进入P6前必过**。

## Closure scope

P0.1已接受的scientific profiles/source map/golden不改写；P0.2采用用户明确批准的schema2 Save As；P0.3按平台分别记录结果，未把Mac已有环境当双平台installer。后续P1使用数据合同，P2–P4继续使用Qt-free resolved profiles与golden来源；主线Phase6不作为依赖。

数据及runtime findings分别见[P0.2](publication-p0.2-review.md)、[P0.3](publication-p0.3-review.md)，不重复计数。20项contract tests与P0.1离线证据检查通过；没有开始P1、科学core、GUI或正式installer。

唯一外部关卡：无Windows主机，已准备可审查的PowerShell交接命令并询问用户执行或延期。未经明确选择，不修改原Windows验收要求、不宣称整个P0 PASS。P6还必须clean-machine setup/repair、签名/license与真实Windows/macOS整链验收。

最终独立复审：Reviewer只读运行7项runtime/legacy tests，全部通过；复核最终v3的8场景与证据边界。合同无剩余blocking finding，Windows external gate未关闭。

## Human decision / final closure

最终合同review后，用户明确回复：“明确延期 Windows 验证，作为 P6 前必须完成的门禁”。该决定只改变时点，不改变验证内容或伪造证据。P0.2–P0.4据此完成，下一阶段需新授权；Windows未验证不得进入P6。上方等待决定描述保留审查时序，以本节最终决定为准。
