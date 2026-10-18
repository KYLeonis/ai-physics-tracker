# R04分析主干职责重构 — 实施计划

- 2026-10-18用户明确“启动重构”，授权[整体方案](architecture-next-round-plan.md)A–D；基线main `2edf0b9`。
- Worktree `/Users/leonis/.codex/worktrees/analysis-workflow/ai-physics-tracker`；branch `codex/analysis-workflow`。
- 状态：S0 / A–C及D自动Gate完成（最终产品bd848f1）；独立Approve、F1 Closed、本机1316 / 双平台通过。2026-10-18用户本轮HR明确“通过”，全部Gate完成，085219e已集成main。

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
- [x] A：motion_computation只读计算 / 结果构造；job只含AnalysisInputs和参数 / 目标版本；删除snapshot.compute_*，同步 / 后台共用。583ce05。
- [x] B：同步compute_*经同一prepare/run/apply核对；四类正式结果仍由Session原子提交；未知扩展 / 失效 / 取消 / 双版本回归。583ce05，原有signal发布路径保留。
- [x] C：源准备 / 当前资格事实由application统一提供给GUI；冻结相关应用事实一次读取，自动显示不触发显式定位，草稿 / 历史 / 预览与正式任务保持隔离；退出旧路径。10f6887；bd848f1闭环自动补源定位F1。
- [x] D自动Gate：数值 / 同步后台等价 / 无写入 / 分层 / GUI相关与全量；独立完整复审，双平台CI；同步当前架构与完成标记。bd848f1本机1316 / 双平台各1314 + 2既有skip；独立Approve，F1 Closed。
- [x] D真人Gate：涉及GUI连接或反馈归属变化时，以独立副本≤5步HR验收，再集成 / push；本轮用户2026-10-18确认5项通过，085219e已集成main。

## Review Gate

High-risk（科学输入、结果构造、事务与后台交付）。Independent Reviewer只读完整diff并定向验证，finding由实现方修复闭环；建议PR提供完整diff / CI。用户已授权实施，无需再次问是否开始；新交互 / 超范围 / 不兼容外部数据契约按项目规则处理。

先定向，再全量和macOS / Windows Python3.11 CI。已经通过的检查无新改动 / 问题不重复扩大。Human Review按项目§7，不以自动化截图代替体验判断。所有Gate通过后--no-ff集成main，更新本计划、Review、architecture-progress/current/architecture/README/roadmap/AGENTS，push并停止。

## Verification / Handoff

最终产品bd848f1；修复自动补源跳顶F1，58项定向及独立增量通过。最终本机1316 passed（142.73s），[双平台CI39119607020](https://github.com/KYLeonis/ai-physics-tracker/actions/runs/39119607020)各1314 passed / 2个既有可选skip，全部步骤success；完整独立复审Approve，F1 Closed。首版数值 / 发布93、相关GUI70、新回归12、工作流 / AI / 保存 / Undo75也通过。[PR #37](https://github.com/KYLeonis/ai-physics-tracker/pull/37)是完整diff / CI容器，完整证据见[Review](../reviews/analysis-workflow-review.md)。C涉及GUI指导与缓存连接，本轮用户已完成真人回归并回复“通过”；085219e以--no-ff集成main，R04已完成 / 已合并。

## Human Review（自动Gate全部通过后执行）

独立副本：主工作区`experiment/analysis-workflow-human-review/project`，从现有R03试用副本复制，原manifest SHA256 `ebae7a1ce5ffc3daf456c43789daebc8676ac703f29ba5bbbfa0f9f866559306`；复制前后所有原文件hash一致。复用外部视频，两个旧试用副本不覆盖。

```bash
zsh /Users/leonis/Documents/ai-physics-tracker/experiment/analysis-workflow-human-review/start.command
```

1. 启动后进入Fit a formula，切换x / vx / theta：源曲线、单位和提示对应所选量；可准备的来源自动准备，未点击Fit不新增正式拟合。
2. 选择vx，点击Show source，调整SG window并回到Fit a formula：预览按新设置更新；顶部提示与按钮状态一致，等待准备后可Fit。不要把更改草稿支点当作已Apply。
3. 在公式框输入`a*t+b`并点击Fit，再查看Latest applied result并Return to my draft：正式结果和草稿区分，回看不会清空当前编辑；本步骤检查操作与结果显示，不要求直线准确描述振荡。
4. 切Measure repeat intervals，选x，Center reference，滚动至图及控件可见处，连续拖橙线并松手：候选点更新，页面位置和缩放保持；点击Measure才产生正式测量。
5. 在此新副本Save，关闭后用同一命令重开：保存结果可查看，源和单位正确；自动预览不会冒充新正式结果。

验收口径：上述5项是否全部通过（通过 / 第N项未通过）。2026-10-18用户明确回复“通过”，本轮HR完成。

## Result

2026-10-18全部实现 / 自动Gate / 独立复审 / 本轮HR完成，085219e集成main，合并树与53c2886一致，源码 / 测试与已验收bd848f1一致。本轮收尾仅同步文档，不修改已验收产品或用户试用内容。下一轮方案见[工程变更与界面更新](change-notification-proposal.md)，未开始其实现。
