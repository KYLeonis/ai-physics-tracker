# 重复间隔源联动与交叉点预览

- 2026-10-18；产品基线main `0afe9f9`；分支`codex/recurrence-linked`，worktree `/Users/leonis/.codex/worktrees/recurrence-linked/ai-physics-tracker`。
- 用户明确同意参考线 / 方向改变后自动预览交叉点、正式Measure仍显式；并要求重构完成标记及下个Agent可见的当前架构入口。

## Goal / Scope

重复间隔页复用现有源准备、配方事实与独立预览执行器。源缺失 / 过期 / 当前设置变化时自动准备所选轨迹的已知组；相关区间 / 量 / 源更新曲线、单位和说明。参考线 / 方向 / 抑噪设置编辑合并为后台预览，显示当前候选交叉点，不发布DerivedData / 尝试日志 / Undo结果事务。Measure仍走正式执行器与完整提交校验。

保留手动拖线与缩放，改线不重建未变的源曲线；候选事件与已保存事件明确区分。切目标 / 方法 / 工作区 / 工程 / 历史后旧预览丢弃；源任务核对方法 / 选择 / 输入及目标版本；保存忙时延后发布；取消 / 失败不自动无限重试。缺时序 / 标定 / 参考、未知 / 损坏 / 冲突配方沿用现有拒绝规则，不猜物理输入。旧测量保留并按源变化标stale。

本轮不改交叉算法、SG、时序换算、JSON、Undo规则、正式结果准确性口径；不开始纯计算 / 写入分离、全局任务统一、6.4 / 6.5。

## Agent Context Pack

- AGENTS.md、CODE_STANDARD.md、docs/architecture.md、architecture-progress.md（当前事实入口；旧扫描仅历史输入）。
- phase6-requirements、phase-6-plan；ADR-0019 / 0020 / 0021 / 0023 / 0025 / 0026。
- fit-linked-source-review F1–F3：轨迹设置归属、单条结构与组内一致性；source-recipe-review：共享事实不能合并不同资格策略。
- phase-6.3.1-review及signal_history_view回归：历史只读、草稿保护、迟到拒绝、显示实际配方；research/open-source-project-map §3.3。

## Slices / Acceptance

- [x] S0：记录已确认行为、当前架构与进度入口、ADR-0026。
- [x] S1：共用预览 / 源准备支持两个工具；交叉预览纯计算移到application，用已有算法。
- [x] S2：只显示当前候选事件、不自动Measure；保持参考线操作，正确处理失败 / 取消 / 历史 / 保存忙 / 换上下文。
- [x] S3自动Gate：定向 / 全量 / 双平台CI / 独立完整复审，处理finding；给出独立试用副本和≤5步操作 → 预期。
- [ ] S3真人Gate：用户亲自HR通过后才合并main，更新进度为已完成。

## Review Gate

High-risk（后台生命周期 / 科学输入 / 自动触发），Independent Review只读完整diff；数值复用既有解析 / 段内 / wrapped角 / 迟到 / 原子拒绝回归。GUI可感知交叉预览必须Human Review；自动Gate通过后提供最短启动命令与封闭式反馈问题并停止等待，不以截图或computer-use代替真人。所有Gate后`--no-ff`集成 / 文档同步 / push，再停止。

## Verification

产品实现0888297；定向源 / 交叉预览 / 数值59 passed（31.81s）。全量1289及补充31通过，独立完整复审Approve（独立50 / 先前51项）；完整证据见[Review](../reviews/recurrence-linked-review.md)。最终[CI39103525201](https://github.com/KYLeonis/ai-physics-tracker/actions/runs/39103525201) macOS / Windows Python3.11通过；HR待用户，未合并main。

## Human Review（自动Gate通过后执行）

独立试用副本：主worktree下`experiment/recurrence-linked-human-review/project`。从原fit-linked HR工程复制，仅本副本可保存；原文件SHA256为`6e740b82a6bd9b1f87af9be464a78d440fc20e7c3cbe5890161d8e2cd01482fb`，副本共用外部视频，不改原工程或视频。

从零启动（macOS已有.venv）：

```bash
zsh /Users/leonis/Documents/ai-physics-tracker/experiment/recurrence-linked-human-review/start.command
```

1. 启动后直接进入Measure repeat intervals：自动出现x源曲线、单位与区间说明，无需切Charts；尚未点击Measure时显示Crossing preview，不能冒称正式测量。
2. 点击Center reference，再拖橙色参考线或改Direction：候选竖线随之刷新，源曲线 / 缩放不跳动；图旁仍提示预览和显式Measure。
3. 改起止帧、切x/y或Source：曲线、单位、说明、交点随选择更新，没有旧交点残留；切回x并Center reference。
4. 点击Measure：看到正式事件及间隔；再改参考线：回到候选预览；Latest applied result仍可查看刚才的正式测量，Return to my draft回到可编辑预览。
5. 快速改几次参考线后切Fit a formula，再切回来：显示当前工具及当前设置，没有迟到旧图覆盖；窗口仍可正常操作。

封闭式反馈：上述5项是否全部通过（通过 / 第N项未通过）？本轮HR独立于上一批拟合及自动时序HR。

## HR返工 / 单项复测

2026-10-18用户反馈：其他项目通过；拖参考橙线松手后工具页滚回顶部未通过（Review F1）。4bd723a改为被动更新预览提示，不发显式反馈定位事件。保留原副本，不覆盖用户试用内容。

本次只复测：关闭旧试用窗口，用上述同一命令重开，滚动到参考线及控件可见处，连续上下拖线并松手 → 页面保持原滚动位置，交点仍自动更新，曲线缩放保持。回复“稳定，通过 / 仍会跳顶”。修复定向81 passed / 独立增量Approve（17项）通过；最新双平台CI39105765356通过。只要求本项HR；通过后再集成main。
