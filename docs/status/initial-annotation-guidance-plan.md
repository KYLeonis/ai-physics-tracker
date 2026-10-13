# Initial Annotation Guidance Plan

- 日期：2026-10-13；分支 `fix/initial-annotation-guidance`，base `d7b9161`。
- Issue：[#26](https://github.com/KYLeonis/ai-physics-tracker/issues/26)。
- 用户授权：首次学习标注 20 帧、默认 K-means、推荐框直达自定义选帧算法。
- 状态：S1–S3 完成，S4 Human Review 待反馈；不进入 Phase 6.2 实现，不越过前置增量 Human Review。

## Goal / Scope

首次学习需当前轨迹 20 个不同的人工标注帧；推荐框、高级训练和批次完成提示一致。
已有成功训练的轨迹仍沿用再训练门槛；教师自检 / 推理不需要先训练。
建议帧默认请求 20 帧、K-means；自定义直接选择 K-means / Uniform，确认选帧，取消不改变设置或数据。
复用现有选帧信号、后台与算法，不改变引擎至少 3 个训练帧的技术契约（检查帧仍可能从 20 个标注中留出）。
不迁移项目、不新增依赖、不改数值算法；视频少于 20 个可标帧时保持实际数量，不降低首轮门槛。

## Agent Context Pack

- AGENTS.md §6–8；CODE_STANDARD.md；workflow.md §5.1 / §10.2。
- phase5-requirements.md R1；open-source-project-map.md §3.4 / §3.5。
- workflow_projection、TrackingActions、TaskPanel、BatchAnnotationActions 及对应测试。
- 现有选帧只建议源帧号、排除人工帧、不写标签；教师模型可直接推理；候选仍需显式采用。

## Acceptance Criteria / Slices

- [x] S1：首次学习 19 帧不放行，20 帧就绪；批次 / 高级入口一致，再训练不被重设首轮门槛。
- [x] S2：默认 20 / K-means；推荐框自定义可选 Uniform，确认走同一选帧路径，取消不启动任务；切换项目重置默认。
- [x] S3：定向 / 全量回归、自检、文档与分支提交 / push。
- [ ] S4：Human Review 通过后按前置增量 → 6.1 → 本分支顺序集成 main。

## Review Gate

- Normal-risk：局部工作流条件 / GUI 入口；不改变训练器、数据格式、后台生命周期或科学算法。
- Independent Review / PR：不要求。
- Human Review：必须，给出启动命令、操作与预期及封闭问题，停止等待真人反馈。

## Result

代码 `b9267e3`；首次定向 **118 passed**，补充项目切换默认值后定向 **58 passed**，最终全量 **933 passed（56.79 s）**，`git diff --check` 通过。新增 4 个 GUI 回归覆盖 19/20 边界、重复修正不累计、批次 / 高级 / C2 一致、同轨迹再训练、自定义确认 / 取消 / 后续沿用 / 新项目重置；既有首次训练测试改用真实生成的 20 帧视频与 20 标签，未绕过 UI 门槛。检查帧流程仍可从 20 标签留出 4 帧，既有 C1/C2 测试通过。

Self-review：全部 GUI 训练入口共享同一标签条件；推荐框与高级表单共用选帧信号，算法仍由现有 adapter 执行；未改数据格式、训练器、教师模型路径、数值算法或依赖。候选不足时仍返回实际数量，无法凑足 20 个不同人工帧时不降低首轮门槛。

分支已提交 / push；`85be73e` [CI 38349426753](https://github.com/KYLeonis/ai-physics-tracker/actions/runs/38349426753) macOS / Windows Python3.11 均 success（代码 / 测试与 `b9267e3` 相同）。真人体验按[本轮验收](../notes/initial-annotation-guidance-human-review.md)反馈后，才可在前置三项增量及 6.1 集成后合入 main / 关闭 Issue。未运行真实 DLC 完整训练，未操作用户工程或论文 worktree。
