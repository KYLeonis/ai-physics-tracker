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
- [ ] S1：共用预览 / 源准备支持两个工具；交叉预览纯计算移到application，用已有算法。
- [ ] S2：只显示当前候选事件、不自动Measure；保持参考线操作，正确处理失败 / 取消 / 历史 / 保存忙 / 换上下文。
- [ ] S3自动Gate：定向 / 全量 / 双平台CI / 独立完整复审，处理finding；给出独立试用副本和≤5步操作 → 预期。
- [ ] S3真人Gate：用户亲自HR通过后才合并main，更新进度为已完成。

## Review Gate

High-risk（后台生命周期 / 科学输入 / 自动触发），Independent Review只读完整diff；数值复用既有解析 / 段内 / wrapped角 / 迟到 / 原子拒绝回归。GUI可感知交叉预览必须Human Review；自动Gate通过后提供最短启动命令与封闭式反馈问题并停止等待，不以截图或computer-use代替真人。所有Gate后`--no-ff`集成 / 文档同步 / push，再停止。

## Verification

待实现。证据写入`docs/reviews/recurrence-linked-review.md`；进度统一写architecture-progress.md，代码完成与合并完成分开。
