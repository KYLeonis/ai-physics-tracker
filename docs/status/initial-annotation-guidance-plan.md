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

### Human Review 反馈修复：建议帧入口顺序扫描（2026-10-13）

用户在 `experiment/20261013_test5` 实测发现：选择 K-means，最终人工标签却是前 20 帧。
只读核查两份 `frame-selection-result.json`，算法均为 kmeans、范围 0–147，结果均为
`1, 6, 26, 28, 39, 42, 44, 46, 47, 49, 59, 60, 62, 63, 64, 105, 110, 114, 129, 143`；
`project.json` 的 active manual 则为 0–19。
根因：推荐 `label_frame` 未消费选帧结果，遍历 working zone 寻找首个未标帧；零标签时选帧完成后推荐还停留在再次选帧。

修复范围：选帧完成后推荐 `Label suggested frames`，按当前 Track / working zone 内未标的实际算法结果启动既有连续标注队列；不顺序补帧、不覆盖已有 manual。新一轮选帧取代旧代表帧批次（含暂停队列）及已完成批次；选帧本身仍不写标签。旧项目已有 20 帧时也能显式选代表帧补标。数据、算法、worker 与教师路径不变，风险仍为 Normal-risk；Human Review 需重新验证本入口。

修复代码 `2fa955a`。新增 5 个回归：顶部 / 面板启动真实非连续 20 帧队列、排除已有 manual 且结果耗尽不顺序补帧、暂停 / 完成的旧代表帧批次被新选帧替换。定向 **88 passed（11.36 s）**，全量 **938 passed（63.02 s）**；diff 检查通过。原实验四个文件 SHA256 均未改变。Human Review 待反馈；未对用户视频重新运行 K-means，未重跑 DLC 训练，没有修改用户实验或删除已有标签。

首轮修复 CI `8153cb1` [38360297373](https://github.com/KYLeonis/ai-physics-tracker/actions/runs/38360297373)：macOS success，Windows 935 passed / 2 skipped / 1 failed，失败仅在既有检查集重建测试，新的 5 个代表帧回归均通过。根因为上轮添加的 train / infer fixture 缺少明确 lineage，粗时钟下同一 created_at 不满足 legacy 时序推断。测试修复 `81ac173` / `653e315` 改为显式 training_run_id，并强制相同 created_at 验证不依赖时间精度；未改产品时间 / lineage 语义。修复后定向 **34 passed（3.76 s）**、最终全量 **938 passed（59.72 s）**；`653e315` [CI 38361205836](https://github.com/KYLeonis/ai-physics-tracker/actions/runs/38361205836) macOS / Windows Python3.11 均 success。Human Review 仍待反馈，Issue #26 保持 open。

### 首轮自动交付（后续反馈不视为 HR 通过）

代码 `b9267e3`；首次定向 **118 passed**，补充项目切换默认值后定向 **58 passed**，最终全量 **933 passed（56.79 s）**，`git diff --check` 通过。新增 4 个 GUI 回归覆盖 19/20 边界、重复修正不累计、批次 / 高级 / C2 一致、同轨迹再训练、自定义确认 / 取消 / 后续沿用 / 新项目重置；既有首次训练测试改用真实生成的 20 帧视频与 20 标签，未绕过 UI 门槛。检查帧流程仍可从 20 标签留出 4 帧，既有 C1/C2 测试通过。

Self-review：全部 GUI 训练入口共享同一标签条件；推荐框与高级表单共用选帧信号，算法仍由现有 adapter 执行；未改数据格式、训练器、教师模型路径、数值算法或依赖。候选不足时仍返回实际数量，无法凑足 20 个不同人工帧时不降低首轮门槛。

分支已提交 / push；`85be73e` [CI 38349426753](https://github.com/KYLeonis/ai-physics-tracker/actions/runs/38349426753) macOS / Windows Python3.11 均 success（代码 / 测试与 `b9267e3` 相同）。真人体验按[本轮验收](../notes/initial-annotation-guidance-human-review.md)反馈后，才可在前置三项增量及 6.1 集成后合入 main / 关闭 Issue。未运行真实 DLC 完整训练，未操作用户工程或论文 worktree。
