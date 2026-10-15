# Main Backport Backlog

2026-10-11 用户要求其余值得吸收的内容存档，后续相关阶段顺带核对。来源固定于[全量区别文档](../notes/publication-main-feature-ui-differences.md)，主线方程口径以[ADR-0017](../decisions/0017-user-defined-equation-analysis-platform.md)为准。

2026-10-13：只读分析 / 连续修正 / 教师模型、6.1 基础与 20 帧代表帧引导均已按序集成 main；下表中的已实现 / Partial 以此为当前落点，Deferred 不变。

| 待办 | 何时必须重新核对 | 边界 / 来源 | 状态 |
| --- | --- | --- | --- |
| autosave `after` 续接 | 触及保存后训练 / 批次修正完成后的保存续接时 | `916adeb`，先复现 busy，同 session / 失败 / 换工程守卫 | 本轮纳入：busy autosave 完成后同 session 续接并再存新改动；失败不执行 after，定向回归 |
| tests 支持 codex/** | 下次 CI / branch 配置维护 | `.github/workflows/tests.yml`；当前 feat/** 已覆盖 | Deferred |
| 允许预建空工程目录 | 下次新建工程 / Save as UX | `2b77d2e` + `199bc52` 并发文件保护必须成套 | Deferred |
| 角量 / 相图 / 周期 / 可见参数 | 重规划 Phase 6 时 | 复用纯计算；SG 口径、α、参考定义按 main 决策 | Partial：6.1角量基础与6.2图表 / 相图 / 参考 / 可见配方已集成main（2026-10-15，独立复审 / 双平台CI / 全部HR通过）；周期纳入[6.3已冻结计划](phase-6.3-plan.md)，仅完成P011候选媒体准备，尚未实现 |
| 输入身份、历史结果、stale、可追溯参数 | Phase 6 结果契约实施时 | 不直接复制 publication schema v2 | Partial：6.1 输入 / 区间失效、结果版本和配方、时序来源已补齐（ADR-0020）；完整历史仍Deferred；6.3拟合 / 周期的additive来源与结果契约列入[已冻结计划](phase-6.3-plan.md)S0，待开发实施 |
| 通用方程 / ODE / 拟合 / 比较 | Phase 6 方程平台立项时 | 用户提供方程；论文 M0/M1 为示例，E3 30/48、E2 47/48 保留限制 | 2026-10-15：显式函数编辑 / 单标量拟合 / 可选结果公式已纳入6.3已冻结计划，用户最终认可；ODE / 联合拟合 / 模型比较仍Deferred，未实现 |
| 参数等价教学页 | 通用求解 / 拟合稳定后 | 不将条件目标谷当完整置信区间 | Deferred |
| 多点实验 / 四角色原子采用 | 后续多关键点模式立项 | 可选模式；不强迫通用单轨四点标注 | Deferred |
| 科学 CSV / JSON / PNG / PDF、portable copy | Phase 8 导出实施时 | 导出选定结果，保留历史配置 / stale，恢复验证 | Deferred |
| CSV 推理交付、host / worker 隔离、AI runtime / Repair | Phase 9 普通用户安装实施时 | 来源 / hash / 取消 / 原子激活 / 许可和 native 平台门禁 | Partial：本轮 teacher infer 已用 canonical 单轨 CSV；独立 runtime / Repair / 分发仍 Deferred |

每次触发相关工作时：核对本表 → 将必要子项纳入 mini-plan → 完成后在本表写 source / 验证 / 状态。不得把 Deferred 当作隐式批准下一阶段实施。
