# P2 — Pendulum Reconstruction and Core Analysis

> 2026-09-30用户用途纠正：P2角运动默认student-default-v2，tip + fixed pivot驱动，辅助点仅诊断；覆盖原四点共同QC口径。见[ADR-0018](../../docs/decisions/0018-tip-fixed-pivot-angular-qc.md)与scientific-profiles §8。

> 2026-10-01：默认SG9/3保留，用户可显式调整窗口/阶数；见[ADR-0019](../../docs/decisions/0019-custom-angular-sg-settings.md)与scientific-profiles §9。短窗只改变导数估计，不跨缺口构造周期。

2026-09-30：用户授权在确认 P1 完成后进入 P2。P1 integration `100b955`，工作树干净且与 origin 一致；P1.1–P1.4 均合并，P1.4 十一条 AC、三道 Independent Review、六轮 Human Review、两类模型真实 lifecycle、1154 tests 和 macOS/Windows CI 均有存证。旧科研目录仅作只读参考；data_io / initial / metrics 字节匹配 source-map。

## Goal / Scope

采用tip + fixed pivot（其余landmark为辅助诊断）→ 可解释的 θ / ω / phase / period / reference energy。保留源帧、缺口、单位、来源及输入失效。无参数反演、自动插值、通用信号处理框架或新依赖。

## P1 completion audit

本轮核对 P1 master plan §9 的 15 项 phase-level matrix 及 P1.4 执行计划 S6；不是重新训练一次模型冒充验收。证据定位：

| 完成条件 | 已有证据 |
| --- | --- |
| v1/v2 Save As、角色绑定、单轨保护、setup/保存重开 | P1.1 review 三轮 + 两轮 Human Review；`publication-p1.1-review.md` |
| 同帧 4/4 manual、split/export、续标/Undo | P1.2 review/HR 闭环；`publication-p1.2-review.md`，merge `5cad79c` |
| 自训/教师导入、来源真实、mapping fail closed、external worker | P1.3 review 四轮/三路扫描、双路径真实 smoke、导入自检 HR；`publication-p1.3-review.md` |
| candidate 非自动采用、manual 优先、四轨事务/错误零变化、取消/stale/迟到结果 | P1.4 S3/S5/S6 review 与对应 tests；`publication-p1.4-review.md`，全部 11 AC 勾选 |
| trained/imported 两类模型真实完整 lifecycle | `publication/evidence/runtime/p14-lifecycle-smoke-trained.json` 和 `p14-lifecycle-smoke.json`（及同目录 worker 日志）；命令/版本/日志见 P1.4 执行计划 S6 |
| generic 兼容、P2 adopted snapshot 边界、CI | P1 最终 1154 tests/9 subtests；双平台 CI run 36674309852；merge `2ba7331` 与推送 HEAD `100b955` |

结论：P1 无未关闭 blocking gate，可进入 P2。Windows runtime 真机延期仍属既有 P6 前门禁。P2.1 开发中新检出的 int/float 摘要重开差异在本轮修复，不把原先测试计数当作此 bug 不存在的证明。

## Agent Context Pack

- `publication/PHASE_PLAN.md` §P2；`publication/spec/scientific-profiles.md` 全文；冻结 `profiles/student-default-v1.json`、`legacy-publication-v1.json`、`diagnostics-v1.json`。
- `publication/spec/experiment-run-derived-contracts.md` §2/6/7；ADR-0017；`docs/reviews/publication-p1.4-review.md` §P2 注意事项。
- `application/adopted_measurement.py`；domain pendulum / scientific_result；publication_serializer；ProjectSession 既有 revision / stale / Undo 事务。
- `publication/evidence/README.md`、source-map、golden；旧目录 `src/inversion/data_io.py` / diagnostics/metrics.py / preprocessing/prepare_initial_conditions.py；禁止运行旧脚本或改写原件。
- CODE_STANDARD；research map §3.1/3.3/7.2（既有分段处理，导数显式 dt）。

## Subphases / Acceptance

1. **P2.1 θ and QC core**：签名、绝对/相对时间、signed θ、分段 φ、共同 QC 及原因、body reference 支持帧、相对权重、pivot 位移。几何解析与边界测试；QC exclusions round-trip / Undo / stale；消费入口每次调用 assert 一次。细节见 p2.1 mini-plan。
2. **P2.2 derivative / phase / periods**：直接 SG9/3，连续且均匀 ≥9；分段/短段/边缘状态；各 diagnostic 独立 profile；过零周期、tail ≥10 完整周期。解析与 frozen E1 对照。
3. **P2.3 energy / analysis UI**：q=g/L 的 reference energy 明确单位 s⁻²，与未来 fitted energy 区分；scalar charts、源帧导航、missing/stale、immutable 保存。能量解析解和 Human Review。

## Review Gate

科学数值、QC 持久化与多输入失效为 High-risk：每个 subphase 完成后 fresh-context 只读 Independent Review，处置 findings 后集成；P2.3 新交互必须 Human Review，给启动命令/操作预期/封闭问题后等待用户。PR 可选。Windows runtime G1–G4 仍是 P6 前门禁，不阻断数值开发。

## Result

- P1 完成核对通过；P2.1 完成：1187 tests/9 subtests、Independent Review approve、QC与摘要保存重开验证通过。P2.2 完成（1207 tests/9 subtests，Independent Review approve）；P2.3 mini-plan实施、全部独立审查finding关闭且Approve；2026-10-01用户确认已有图、可交付并明确批准收尾，P2.3/P2整体验收接受。图表外观一般记为非阻断后续事项，不将本次确认冒称每个历史HR问题都有单独测试反馈。


## P2 final acceptance audit（2026-10-01）

- [x] θ符号、roll/fixed pivot、release/源时间与tip QC、辅助诊断：reconstruction解析/边界回归，P2.1与v2规则复审通过。
- [x] 默认SG9/3封存ω/信息extrema/period/tail容差对照；自定义SG解析导数、时间异常、branch、gap与edge：angular_analysis及evidence回归通过。
- [x] 无阻尼reference energy恒等式、代理单位s⁻²、缺测不造值：energy/analysis回归通过。
- [x] 多输入签名/stale、immutable结果、取消/迟到、Undo、保存重开/Save As与历史SG恢复：application/GUI回归及独立审查通过。
- [x] 用户确认图表已出现并明确接受当前subphase交付、授权收尾；图表外观改善非阻断保留，不虚构历史问题逐题现场实测。
- [x] 全量1251 tests/9subtests（80.80s）、evidence15/48/2、diff通过；全部Independent Review findings Closed。

P2.1–P2.3全部交付，按--no-ff集成并push后停止；P3尚未开始。运行与体验步骤见P2.3 mini-plan。Windows安装/运行门禁仍是P6前已批准延期项，未据此标记发行通过。
