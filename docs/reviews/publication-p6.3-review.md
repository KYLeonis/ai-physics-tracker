# Publication P6.3 Independent Review

## S3 inference artifact follow-up — 2026-10-03

- Reviewer：`/root/p6_3_csv_review`，gpt-6-luna/max，只读；主实现root。
- 范围：`2b77d2e..146c6a3`；两个infer入口的CSV交付、worker日志读取、native CSV smoke及回归测试。不是P6.3完整S6发行审查。
- Verdict：**Approve**；无开放finding。
- 保留：worker仍声明同一CSV的路径/size/SHA，host身份/路径/scorer/四角色/逐帧/summary校验未削弱；缺CSV不回退未声明HDF5。HDF5旧入口未移除，但旧HDF5-only产物在无PyTables host中仍不能读取，不能声称本次修复迁移了旧产物。
- 日志：legacy、explicit与external worker路径兼容，resolved-root越界保护不变。
- Reviewer定向 **52 passed**，diff check通过；native smoke仅代码审查，由root执行原生构建验证。
- Root **80 passed（22.52s）**；旧基线回归2例失败，新实现通过。私有工程副本/真实MPS36帧/无PyTables host候选校验通过；新DMG native CSV读取/外部hello/host不导入AI栈通过，114份随包worker源码与源码相同。
- 真人HR待用户替换App并重试推理；Windows实机/学生pilot及P6.3整体审查保持未完成，无合并/发布。

## S6 Mac development delivery closeout — 2026-10-03

- Reviewer：`/root/p6_3_close_review`，gpt-6-luna/max，只读；范围9d40eb3..199bc52完整代码/test/packaging与当前证据。主代理负责文档同步、CI和集成。
- Verdict：**Approve with limitations**。允许按用户本轮授权将当前Mac开发交付带发行待补项集成；不是完整R01–R12发行通过。无开放Blocking/Major；有F2 Open-Minor，已接受延期。

| ID | Severity | Finding | Disposition / Evidence |
| --- | --- | --- | --- |
| F1 | Blocking | 空目标目录验证后再次扫描并无条件unlink，可删掉并发新增真实文件 | Closed，199bc52。Reviewer/root均确定性复现；entries固定校验清单，仅清理其元数据，rmdir拒绝新内容且保留staging。Reviewer新回归1passed；root仓储/工作流/向导57passed，旧回归DID NOT RAISE |
| F2 | Minor | pendulum_setup.py:271称missing folders可创建，但父目录必须存在；:392起相对路径提示“目标不得存在”与允许空目录矛盾 | Open / Accepted deferral至P6.4 UX/发行材料。安全校验仍拒绝、原数据保留，不阻止本次集成。最小修正：说明父目录必须已存在并删去“目标不得存在” |

- Reviewer修复前定向5文件86passed，修复后新增安全回归1passed；完整CSV边界沿用此前S3审查，未发现其他Blocking/Major。
- Reviewer审查时最终CI在跑，**root随后核实199bc52**：[tests37133406052](https://github.com/KYLeonis/ai-physics-tracker/actions/runs/37133406052) Mac1455passed/4skipped/1既有strict xfail、Windows1453passed/6skipped/1既有strict xfail；[packaging37133407052](https://github.com/KYLeonis/ai-physics-tracker/actions/runs/37133407052)两平台success。不将ADR-0020 xfail计科学通过。
- 用户HR明确关联146c6a3旧功能修复包/SHA37ce972d…28a0ac2；安全修复后199bc52最终包/SHA4429e016…71a93e57没有同artifact真人HR。新包native smoke通过，worker114源码字节一致；GUI与科学/AI行为不改，新安全路径通过确定性回归/审查。
- 原工程只读证明两轮MPS训练、36帧CSV推理/采用、SG9/3与7/3结果保存，manifest SHA前后相同。teacher-import、非开发学生pilot、完整安装版科学/导出/恢复证据仍待补；Windows实机/CUDA/跨平台重开not_run；签名/公证与正常下载启动属P6.4。用户收尾授权不冒充这些项已验证。
