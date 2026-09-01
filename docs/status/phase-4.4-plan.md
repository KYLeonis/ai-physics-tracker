# Subphase Plan — Phase 4.4 GUI & Integration

- Issue：[Issue #15](https://github.com/KYLeonis/ai-physics-tracker/issues/15)。
- 分支：`feat/p4.4-gui-integration`。
- 日期 / 状态：2026-09-01 · ✅ 完成；已合并、推送、通过双平台 CI，Issue #15 已关闭。
- 进入基线：`main` / `1ca5bee`，与实时查询的远程 main 一致，工作区干净；4.3 已收尾。

## Goal

在现有桌面界面内完成“人工标注 → 训练与基本评价 → 全视频推理 → AI/人工轨迹显示 → 运动学重算 → 保存重开”，准备、运行、必要的数据校验与取消均不阻塞 GUI，并以单摆项目完成 Phase 4 的整体验收。

## Scope

**做**：

- GUI 可安全调用的训练/推理异步入口、真实进度与日志、单活动 AI 任务、任务历史。
- Task Panel、训练/推理/取消按钮、最少的参数和模型选择、前置条件说明。
- 项目保存、切换、关闭、任务恢复显示与迟到结果保护。
- AI 来源样式、全视频轨迹的绘制成本控制、人工覆盖及图表数据刷新。
- roadmap 已要求的最小模型评价：同一训练快照的原生训练/验证指标与样本量摘要，不用训练 loss 冒充定位精度。
- 自动化回归、真实 DLC 验证、Human Review、Windows 条件核对和 Phase 4 收尾。

**不做**：

- 多视频队列、多任务并行调度、多 bodypart、多模型库/跨视频应用、训练恢复、困难帧挖掘与主动学习（Phase 5/7）。
- 改写 first-wins、自动覆盖/清除旧 AI 点、自动删除模型/原始结果、自动插值或新增物理算法。
- 改版整个主窗口、引入新依赖、修改 CI、迁移项目 schema 或修改许可证。
- 用合成视频的 1 epoch 冒烟替代真实单摆 GUI 验收，或把 Windows mock CI 视为 CUDA 真机验收。

## Relevant Context

- `AGENTS.md`；`CODE_STANDARD.md` §4/8/10/13/14/15；`docs/workflow.md` §5.1/6/8/11。
- `docs/spec/phase4-requirements.md` R2–R6 / AC-1…6；`docs/roadmap.md` Phase 4。
- `docs/status/phase-4.3-plan.md` Result；`docs/development.md`“4.4 接线前的性能关卡”。
- ADR-0011（引擎隔离与 spawn）；ADR-0007（时序授权）；ADR-0009（后台结果与主线程事务）。
- `docs/spec/data-model.md` §4/5；`docs/spec/project-format.md`；`docs/research/open-source-project-map.md` §3.4/9。
- `docs/research/raw/deeplabcut-notes.md` 训练 logger、评价与推理；本机 DLC 的 `runners/logger.py`、`apis/training.py`、`apis/evaluation.py`。

## Baseline Findings

1. 4.3 已有 `InferenceCoordinator`、严格结果解析、原子导入、`effective_points()`、混合观测运动学；不重写这些语义。
2. `prepare_training()` 同步抽帧/导出/调用 DLC 建训练集；4.3 的推理流程多次完整扫描视频/模型做 SHA-256，并同步读 JSON、构造观测。用户指出重复内容校验过度；4.4 将取消 AI 任务中的重复哈希，真正必要的耗时准备/解析仍后台化。
3. `dlc_train_worker()` 真实分支尚未持续转发 epoch/loss/lr；`TrainingParams.learning_rate/save_iters` 与真实调用存在未接线之处。训练导出还有解码失败生成占位图、HDF5 错误被吞、缺 DLC 模拟成功的旧逻辑，GUI 发布前需定向修复。
4. `ProjectActions._saveCandidate.accept()` 会把活动 session 替换为保存副本，而推理 job 按 session 对象验证身份。不能仅靠“保存后换引用”连接活动 AI 任务，否则会失联或丢失保存期间的更新。
5. 当前 overlay 只读 manual 点，且 `VideoView.set_markers()` 每次重建全部图元；全帧 AI 数据会放大播放成本。非当前帧的 manual 已是空心圆，AI 不能也只用空心圆区分。
6. 重开项目时磁盘可能保留 running/pending run，但没有对应 worker；任务面板不能假装它还在运行，也不能永久禁止后续任务。
7. roadmap 的“模型评价”还没有软件入口；仅显示训练 loss 不足以交付这一项。仓库没有受版本管理的真实单摆视频，验收前需用户指定本地素材。

## Proposed Design

### D0 校验强度修订（依据本轮用户反馈）

- 产品是本地实验工具，不把防篡改作为默认目标。取消 AI 准备/启动/完成/导入过程中的多轮全文件 SHA-256；缺少历史模型 hash 不再阻止使用模型。不增加校验级别开关或另一套安全框架。
- 保留路径/存在性、文件大小与修改时间、视频尺寸/帧数/时序、实际加载 snapshot 与所选模型的一致性检查；运行中用户通过应用切换/重连产生的代际变化仍必须识别。
- 保留结果结构、帧号范围、有限坐标、confidence 范围、完整输出、人工优先和原子提交；这些防止实验数据错用/丢失，不能随哈希一起取消。
- 旧 `sha256` / `model_sha256` 等可选字段兼容读取和保留，不迁移、不清洗旧项目；新 AI 流程不强制生成或复核它们。模型来源主要通过 run id、配置/快照引用和轻量文件信息记录。
- 明确接受的代价：无法检测“内容改变但大小、修改时间等轻量信息保持相同”的文件替换；用户应避免在任务运行中从外部覆盖视频/模型。新模型库/versioning 不借此提前实现。
- 仅调整 AI 任务链路；不顺手取消依赖下载的校验和，也不重做 Phase 2 已有的显式媒体重连规则。
- 实施时先在 ADR-0012、project-format/development 中注明这项取舍，再更新实现与测试。4.3 的历史验收记录保留，不将新取舍改写成旧实现从未存在。

### D1 后台边界与事务（先于面板实现）

- 在 ADR-0011/0009 基础上写 ADR-0012，明确 AI 请求快照、后台校验和主线程提交的职责；用户确认本计划后先写决策/接口约定，再改实现。不把现有同步 coordinator 整体搬到线程中并修改活动 session。
- GUI 主线程只捕获小型请求/当前版本、登记任务、处理有界消息和最终提交；DLC 导入、设备探测、训练集生成、训练/评价/推理仍在 spawn 子进程，worker 使用自己的视频 reader，不共享播放器 reader。
- 抽帧、结果文件读取/反序列化和批量候选数据准备走后台。取消不需要的哈希扫描后，GUI 用会话代际、输入版本、轻量文件信息和最新人工观测确认有效后原子合并；不是把原有多轮哈希原封不动搬进后台。
- 输入变化时拒绝过期候选或在后台重新合并，保留用户期间的人工标注；不把过期 Project 快照替换进活动会话。大批次候选验证也不在 QTimer 槽里重新全表处理。
- GUI 侧用一个轻量 `TrackingActions` 组合现有服务，与 `ProjectActions/ChartActions` 模式一致。复用任务 runner，不建立通用调度框架；一个窗口/项目一次只运行一个 AI 作业，避免目录和计算设备争用。
- 约 100ms 轮询只排空有界消息批次；进度合并为最新值。取消发请求后立即返回，join/terminate/kill 在后台回收；UI 显示 Cancelling，直到确认退出，不能同步等待数秒。

### D2 真实训练进度、参数和最小评价

- 通过 DLC 真实 logger/日志边界取得 epoch、loss、实际 lr；同一适配器内复用日志重定向，GUI 不 import DLC。启动/下载/建集/评价等没有可测分母的阶段显示不定进度，不伪造百分比。
- UI 第一版只开放 `epochs=50`、`batch_size=8`、`device=auto`（可选 CPU/MPS/CUDA）；高级 learning_rate/save_iters 不先做控件，但 API 参数与落盘的实际配置必须一致。修复未使用参数的传递/记录，并用真实短训练核对。
- 解码/图像写入/HDF5 生成/依赖缺失必须报告失败，不能使用黑色占位图或伪成功继续训练；错误指出失败阶段和恢复办法。该修复直接服务 R2/R3，不扩展为全仓清理。
- 训练后针对产出的确切 snapshot 执行最小 DLC 评价（关闭绘图）；记录引擎原生训练/验证误差、单位、有效样本量、阈值和快照身份。评价与模型可用状态分开：评价失败或取消不销毁已成功的模型，但明确显示“评价未完成”，Phase 4 的评价验收仍需补齐。
- 评价是训练工作流子步骤，复用 run 的可扩展元数据，不新增 `task_type` 或 schema；不做模型排名/跨运行精度比较。评价使用相同的模型引用、文件状态与任务归属检查，不重新增加哈希门禁。

### D3 Task Panel 与参数默认值

- 底部可停靠面板，默认与 Kinematics charts 并列为标签页，并接入 View 菜单；不重排视频、轨迹列表和时间轴。
- 面板显示当前视频/当前落点 Track。现有多选只用于叠加显示；Train/Infer 针对 current Track，不悄悄批量执行多选目标。
- 控件：训练参数、Start Training；同 Track 的完成模型列表、推理置信度、Start Inference；Cancel；任务历史和选中任务详情/日志。
- **提议 GUI 推理阈值默认 0.6**，范围 `[0,1]` 可调，`>=` 包含边界；仅是可调整的工程起点，不代表已证明的定位精度。4.3 adapter 默认 0.0 不改。低分原始结果仍保留，manual 的 None 不参与置信度过滤。
- 训练按钮要求项目已保存、视频/时序有效、current Track 至少 3 个人工点且无活动 AI 作业；3 点只是技术下限，UI 提示应覆盖摆动不同位置。推理还要求有可用的完成模型记录；静态条件即时判定，文件可用性和实际模型加载检查在后台完成。缺历史 hash 本身不是失败原因。
- 禁用原因必须可见（未保存、未授权时序、人工点不足、模型缺失、忙等）。重训不自动覆盖旧 AI；再次推理可能仅补缺帧，面板在启动前提示 first-wins。
- 用现有 TrackingRun 做历史事实源。Preparing/Validating/Importing/Cancelling 是临时显示阶段，不新增持久化状态；completed 只表示所需模型/观测提交已完成，不能拿 worker 的 100% 当作已导入成功。
- 结果显示导入/冲突跳过/低置信度/缺测数量、实际设备、模型及评价摘要。低样本/评价不可用必须明示；不把数据为空画成零。
- 完整日志保存为 `data/engines/<run_id>.log`，引用走现有扩展字段；不会提前创建 4.3 必须独占的新预测目录。UI 只保留最近一段日志，历史日志异步按需读取；旧任务没有日志就明确说明。实施前更新目录规范。

### D4 保存、切换、关闭和中断恢复

- 普通 Save 仍可用，但保存成功只更新**该保存快照对应的 clean 基线**，不替换活动 session、不覆盖之后的编辑/任务完成结果。保存期间新增内容仍应 dirty；Undo/Redo 与既有保存边界保持一致。
- AI 活动时允许播放、seek、选择和手工标注；另存、重连媒体、改变时序或删除活动目标等上下文破坏操作先禁用并提示取消任务。其他轨迹的普通查看不被误锁。
- 打开/新建/切换视频/关闭时整合现有 Save/Discard/Cancel 提示，明确操作会取消活动任务。用户选择返回则任务与会话不变；确认继续后先异步回收旧作业并落定 cancelled，再按所选保存策略操作，之后提交候选新项目。
- 不能在 projectChanged 已替换会话后才取消旧任务。打开/保存失败保留原项目；已按用户选择取消的任务不假装恢复。关闭后不接收任何访问已销毁 Qt 的回调。
- 同一次普通保存不得改变 session 身份/任务归属；切换则使用明确代际丢弃旧回调。取消与成功竞争只允许一个终态，不能先导入再显示 cancelled。
- 对从磁盘恢复、确无本进程 worker 的 pending/running 任务，载入候选会话时在内存标为 failed 并说明“上次执行已中断”；不自动续训、不删除产物、不改 completed run 的模型身份，只有后续正常保存才写回。这样旧状态不会永久锁住新任务。此项是拟批准的运行状态恢复规则，不迁移 schema。

### D5 AI 显示与图表

- `_refreshMarkers` 读取 `effective_points()`；manual 沿用圆形，AI 用空心菱形，沿用 Track 颜色并提供来源图例。当前帧另加高亮，不能只靠颜色/实心空心表达来源。修改人工点后立即显示人工优先结果，Undo/Redo 同步恢复。
- 轨迹几何按数据/选中 Track/显示范围变化缓存，当前帧只更新少量高亮；避免每个呈现帧删除并重建全部 AI 图元。具体采用批量绘制或稳定图元复用，由 Slice 5 的规模验证决定，不更换渲染库、不减少保存的数据。
- 推理完成后刷新 overlay、任务历史和 `analysisChanged`，使图表立即识别 stale。**默认沿用显式 Recompute**，显示“AI 数据已更新，请重算”；不在后台任务完成时擅自启动昂贵重算或抢走当前面板焦点。
- 重算继续走 ChartActions 的后台机制，使用人工/AI 生效观测；不跨缺测连接/插值，不自动跳帧。推理与旧运动学结果相遇时，旧结果必须被拒绝或重新计算。

## Acceptance Criteria

- [x] P44-1：AI 流程不再反复全文件哈希且不要求历史 hash；慢抽帧、DLC 初始化和结果解析均不在 GUI 线程执行；用事件屏障验证等待期间 Qt 仍能处理播放/取消，不用易抖动的耗时断言代替线程边界测试。
- [x] P44-2：真实训练转发 epoch/loss/lr，参数快照与真实调用一致；解码/依赖/建集失败不会训练占位数据；成功模型有一次可追溯的基本评价。
- [x] P44-3：Task Panel 的目标、参数、禁用原因、进度、错误和历史正确；取消在准备/运行/验证阶段可用，进程退出后才落终态，无重复终态或半批导入。
- [x] P44-4：保存期间编辑/任务完成不丢失，取消导航不取消任务；确认导航、另存限制、失败回退、关闭回收、旧回调以及重开中断任务均有回归测试。
- [x] P44-5：manual/AI 来源可区分且人工优先；多选 overlay、当前帧、缩放、Undo/Redo 正确；全帧轨迹不会逐帧重建全量图元。图表识别新数据并按显式重算展示混合结果。
- [x] P44-6：用户亲测真实单摆项目，从标注到训练/评价/推理/显示/重算/保存重开全程不离开软件；真实模型进度、取消和交互体验通过 Human Review。
- [x] P44-7：405 项基线及新增测试通过，交付提交的 macOS/Windows CI 通过，独立 review 通过；Windows 真机/CUDA 经用户明确批准延期到 Phase 9 打包前。
- [x] P44-8：Phase 4 所有 deliverables/AC 有证据，尤其模型评价和 GUI AC-5/6；相关文档、Issue 和 Git 状态已同步，Phase 4 完成后停止，不开始 Phase 5。

## Slices

| Slice | 可验证增量 | 主要影响范围 |
| --- | --- | --- |
| 1 | ADR-0012、请求/结果快照；拆开同步准备/验证/原子提交，Qt 响应性测试 | `training_job.py`、`inference_job.py`、必要的应用层请求模块、`task_runner.py`、相关测试 |
| 2 | 训练准备进程化、真实指标/日志、参数与错误修复、最小评价 | `dlc_adapter.py`、`engine_adapter.py`、mock adapter、训练测试、目录规范 |
| 3 | Task Panel + TrackingActions，接通按钮、目标/模型/参数、日志历史 | 新增 `gui/task_panel.py`、`gui/tracking_actions.py`，MainWindow 最小接线及 offscreen 测试 |
| 4 | 保存身份、取消/导航/关闭、重开中断恢复与竞争回归 | `project_actions.py`、`project_session.py`、MainWindow、TrackingActions、既有项目/时序测试 |
| 5 | AI 样式与绘制缓存、人工覆盖、图表通知和重算整合 | `video_view.py`、MainWindow、`chart_actions.py`、overlay/图表测试 |
| 6 | 自动化与真实 DLC 验证、独立 review、Human Review、Phase 4 收尾 | 测试/脚本和 docs；通过用户体验与平台关卡后才合并/推送 |

只创建当前 Slice 需要的模块；不因文件名提议预生成空文件。新公共接口先文档化，既有 4.2/4.3 脚本与测试用法尽量通过兼容入口保留。

## Verification and Human Review

- 本轮基线：`QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q` → **405 passed in 52.40s**；没有运行 GUI 或真实训练。
- 自动化：复用 `test_project_actions.py`、`test_timing_actions.py`、`test_chart_request_identity.py`、`test_charts.py` 和 4.3 推理/会话测试；补 mock Qt 任务流程、消息限流、同帧人工编辑、保存/切换竞争、缺依赖与日志恢复。
- 真实脚本冒烟继续验证适配器；真实 GUI 验收需要用户指定一段本地单摆视频。原视频只读、使用独立实验项目，视频/权重不提交 Git。
- 训练/评价耗时与模型精度不能从合成 1 epoch 推断。报告实际 epoch、设备、train/test 指标、样本量和过滤后覆盖情况；现有 spec 没有数值精度阈值，不临时杜撰“达到 N 像素即合格”。
- GUI 实现和自动化通过后，提供 `.venv/bin/python -m ai_physics_tracker`，发起以下至多五步 Human Review，然后停止等待反馈；不得用 computer-use/截图代替真人体验：

| 操作 | 预期 / 用户回答 |
| --- | --- |
| 新项目导入单摆视频、保存、标注不同摆动位置，在 Task Panel 选择当前 Track | 目标清楚、禁用理由正确；是/否 |
| GUI 启动训练，期间播放/seek；查看模型与评价摘要 | 进度/loss/lr 真实更新，界面可用；是/否 |
| 选择模型和阈值推理，检查 AI 来源样式、补一个人工修正并 Undo/Redo | 来源可区分、人工优先、计数解释得通；是/否 |
| 点击重算、保存并重开同一项目 | 混合轨迹、图表、confidence 和任务历史可恢复；是/否 |
| 新开短任务，测试 Cancel、关闭/打开的“返回”和“继续” | 返回不丢任务；确认取消后无残留进程/迟到结果；是/否 |

Windows 真机/CUDA 原为 Phase 4 收尾条件。用户于 2026-09-01 明确批准延期到 Phase 9
打包前的专门验收节点；GitHub Actions Windows 通过不等同 CUDA 真机验证，该待办继续保留。

## Approval and Result

- 用户批准 D0–D5；AI 链路采用轻量文件状态校验，基础 K-means 选帧留 Phase 5 并直接调用 DLC。
- 4.4 实现、真实 CPU GUI 组件冒烟、自动化、独立 review 与 macOS Human Review 均已完成。
- 没有修改项目 schema、依赖版本、CI 或许可证；原始媒体、模型和评价产物不进入 Git。
- Windows 真机/CUDA 未验证；用户批准延期到 Phase 9 打包前。集成 push/CI 已完成，Issue #15 已关闭。


## K-means 范围结论（用户不要求前移）

- 当前状态：仓库 `src/` 尚无自动选帧入口。DLC 已提供 `extract_frames(mode="automatic", algo="kmeans")` 及可返回帧号的底层选帧函数；本机 3.0.1 使用 MiniBatchKMeans 对缩小后的图像聚类，再从不同类别选帧，并非自动标注坐标。
- 建议最小范围：增加“自动选帧”、数量输入和“下一待标注帧”；后台返回源视频候选帧号，按原帧号跳转，用现有人工落点完成标注。不新建标注 schema、不换标注器、不写第二套 K-means，也不自动产生 TrackPoint。
- 默认可请求 20 帧（数量可改，仅是起点），限制在当前工作区间，排除当前 Track 已标注帧；候选不足时如实显示实际数量，不补重复帧。取消或切换项目不应用旧候选，选帧耗时过程也不能阻塞 GUI。
- 好处：第一轮训练前少手动拖时间轴，候选有更多外观差异。代价：多一次视频采样/聚类计算，仍需人工标注；画面变化不等于物理信息量，少见遮挡/模糊及很小的摆球可能需要手工补选。
- 样例：点击“自动选 20 帧” → 逐个跳转并标记摆球 → 训练。保持原规划则 4.4 仍手动选帧，Phase 5 再加此入口。
- 若批准：先同步 roadmap/spec 中基础选帧的阶段归属，再在现有 Slice 2/3 增加适配/GUI导航及取消、帧号映射测试；困难帧发现、主动学习和再训练策略继续留在 Phase 5。未批准前不改 Phase 5 的交付范围、不实现该功能。
- 依据：[DLC 选帧 API](https://deeplabcut.github.io/DeepLabCut/dev/latest-release/reference/deeplabcut/generate_training_dataset/frame_extraction/)；[DLC 标注指南](https://deeplabcut.github.io/DeepLabCut/docs/beginner-guides/labeling.html)。

- 实施确认：用户同意其余方案执行；基础 K-means 不前移，Phase 5 直接调用 DLC。ADR-0012 已记录本轮边界。
- 主要实现提交：`0b1add2`（后台任务、训练指标/评价、轻量校验）与 `1bb4c51`（Task Panel、生命周期、AI 轨迹）；Human Review 修复为 `0bd96c2`、`23275e9`；`--no-ff` 合并提交为 `17ae493`。
- 自动化：最终本地运行 `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q` → **433 passed in 47.47s**。新增测试覆盖响应性、取消竞争、模型保留、保存身份、导航、旧回调、marker 复用、评价、窗口缩放和面板独立窗口切换。
- 真实 GUI 组件冒烟：CPU、1 epoch 完成训练/原生评价/推理，得到 train RMSE 46.91 px（n=4）、test RMSE 17.33 px（n=1）；10 帧中 5 AI 插入/5 manual 保留，保存重开通过。指标只证明评价管线可用，不代表模型精度。
- 评价 CSV、模型、预测与完整日志均在各自 run 目录保留；重复训练使用独立目录，不影响旧模型。
- 绘制规模检查：10,000 个 AI marker 首次构建约 0.32s；1,000 次当前帧索引高亮约 0.03s。当前帧变化不再重建全部图元。
- 独立 review：首轮发现提交前遗漏模型/config 轻量复核，以及 mAP/mAR 单位错误；`102fe79` 修复并增加回归，复审确认关闭。当前无阻塞 finding。
- Human Review：主要工作流通过；窗口最小尺寸与 Chart 中文状态消息的反馈已修复，Chart/AI 保留可缩放独立窗口。用户于 2026-09-01 确认聚焦复验通过。
- 集成 CI：首轮 [run 33503920002](https://github.com/KYLeonis/ai-physics-tracker/actions/runs/33503920002) 的 Windows job 暴露窗口宽度和 viewport 中心的跨平台测试假设；`51e05b1` 改为按平台尺寸与已知像素映射验证。最终 [run 33504579667](https://github.com/KYLeonis/ai-physics-tracker/actions/runs/33504579667) 在 macOS/Windows Python 3.11 全绿。
- 最终状态：Issue #15 已关闭，Phase 4 完成。Windows 真机/CUDA 延期到 Phase 9 打包前；停止并等待用户指令，不开始 Phase 5。
