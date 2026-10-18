# R04分析主干职责重构 — 实施计划

- 2026-10-18用户明确“启动重构”，授权[整体方案](architecture-next-round-plan.md)A–D；基线main `2edf0b9`。
- Worktree `/Users/leonis/.codex/worktrees/analysis-workflow/ai-physics-tracker`；branch `codex/analysis-workflow`。
- 状态：S0已冻结；产品实现与Gate尚未完成，不能提前标已完成。

## Goal / Scope

完整贯通同步 / 后台线性与角运动计算、自动源准备、拟合 / 重复间隔发布，以及应用事实与GUI交付；保留AI候选、解码及保存各自协议。计算只持有冻结输入，Session保留事务；现有数值 / 配方 / JSON / 未知扩展 / Undo语义及R01–R03体验保持。

不实施R05/R06、不新增依赖、不改算法、不改格式，不启动6.4/6.5。兼容Session.compute_*及既有prepare/run/apply入口；内部job不再携带Session。detached()仍服务其他既有用途，不全局删除。

## Agent Context Pack

- AGENTS / CODE_STANDARD / architecture / architecture-progress；整体方案A–D。
- phase6-requirements、phase-6-plan；ADR0012/0017/0019/0020/0021/0023/0024/0025/0026及本轮0027。
- fit-linked-source-review F1–F3：轨迹设置归属 / 未知与损坏配方 / 内部冲突保护。
- recurrence-linked-review F1：自动反馈不能抢页面scroll；历史 / 当前草稿 / 正式结果区分。
- pre-phase6-project-review P6R-01及undo_run_integrity：事务不回滚运行进展，保存 / 自动保存历史规则保持。
- research/open-source-project-map §3.3；领域术语以data-model及GLOSSARY为准。

## Slices / Acceptance

- [x] S0：范围 / owner / 调用关系与Review Gate冻结，ADR0027。
- [ ] A：motion_computation只读计算 / 结果构造；job只含AnalysisInputs和参数 / 目标版本；删除snapshot.compute_*，同步 / 后台共用。
- [ ] B：同步compute_*经同一prepare/run/apply核对；四类正式结果仍由Session原子提交；未知扩展 / 失效 / 取消 / 双版本回归。
- [ ] C：源准备 / 当前资格事实由application统一提供给GUI；冻结相关应用事实一次读取，自动显示不触发显式定位，草稿 / 历史 / 预览与正式任务保持隔离；退出旧路径。
- [ ] D自动Gate：数值 / 同步后台等价 / 无写入 / 分层 / GUI相关与全量；独立完整复审，双平台CI；同步当前架构与完成标记。
- [ ] D真人Gate：涉及GUI连接或反馈归属变化时，以独立副本≤5步HR验收，再集成 / push；若只有内部实现变化，在Review明确免新增HR依据。

## Review Gate

High-risk（科学输入、结果构造、事务与后台交付）。Independent Reviewer只读完整diff并定向验证，finding由实现方修复闭环；建议PR提供完整diff / CI。用户已授权实施，无需再次问是否开始；新交互 / 超范围 / 不兼容外部数据契约按项目规则处理。

先定向，再全量和macOS / Windows Python3.11 CI。已经通过的检查无新改动 / 问题不重复扩大。Human Review按项目§7，不以自动化截图代替体验判断。所有Gate通过后--no-ff集成main，更新本计划、Review、architecture-progress/current/architecture/README/roadmap/AGENTS，push并停止。

## Verification / Handoff

待实现。完整证据将记录于docs/reviews/analysis-workflow-review.md。每批标明已实现 / 自动验证 / 待HR / 已合并，不能只因搬出文件便算R04完成。
