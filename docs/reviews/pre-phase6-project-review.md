# Pre-Phase 6 Independent Engineering Review

- Reviewer：Codex，fresh-context independent engineering review；未参与 Phase 1–5 实现。
- 日期：2026-09-16（Asia/Shanghai）。
- 审查对象：完整 `main @ daad086f1af6ae48180b2cef284608755abb5981`，不是单个提交的 diff。
- 范围：correctness、reliability、scientific validity、recoverability、maintainability；不含安全审计，不设计或扩大 Phase 6 产品范围。
- 修改边界：本次只新增本 Review Record；未修改产品代码、正式测试、spec、ADR、status 或历史 Review Record。未提交或推送。

## 1. Executive Summary

**结论：READY AFTER BLOCKERS。** Phase 1–5 的主要工程基础仍可用，但必须先关闭 **P6R-01、P6R-02** 两项明确问题。

1. **P6R-01：Undo/Redo 的数据快照与 TrackingRun 注册表失去引用一致性。** 已保存项目中新建轨迹、启动训练后，撤销到创建轨迹会抛异常，并留下 `Project.tracks` 与 Session 的 `TrackStore.tracks` 不一致的状态。另一个同源路径是删除已激活轨迹后 Undo：恢复了 active run 指针和观测，却没有恢复 run；该悬空状态还能保存重开。
2. **P6R-02：固定验证集只隔离本轮标签，没有隔离 Resume 模型的训练历史。** 切换验证集后，已经训练过这些帧的父模型仍可 Resume，后续评价仍以该 series 参与比较。本次不仅复现请求与建集接受该组合，还从现有 `AI_test2` 的实际 DLC 切分产物核实：首个 Resume 轮次的父模型已经训练过后来 11 个验证帧中的 **7 个**。

这些问题需要局部事务与 lineage 修复，**没有证据要求先重写 ProjectSession、迁移数据库、替换 extra_fields 或拆除 GUI Actions**。当前候选/活动结果隔离、raw/derived 分离、坐标变换、缺测分段、输入变化拒绝迟到计算等基础仍成立。

另有两项非 blocker：**P6R-03**（删除 series 后历史验证标签无法从项目事实恢复）、**P6R-04**（Advisor 输入采集与当前事实不符）。最新 Windows CI 已通过，旧崩溃不作为当前 blocker；本地全量测试也通过。测试通过与两项新 blocker 同时成立：现有测试没有覆盖这些组合，部分测试还固定了早期、如今不再完整的撤销语义。

## 2. Baseline Reviewed

### 2.1 基线与方法

进入时读取了 [Evidence Package](pre-phase6-evidence-package.md)，仅将其用作导航。随后核查当前代码、相关 spec/ADR、测试、历史 review、CI 日志及本地真实实验产物。没有把历史 finding 的“已关闭”当作当前实现正确的证明。

| 项目 | 本次核实结果 |
| --- | --- |
| 工作分支、HEAD | `main`，`daad086f1af6ae48180b2cef284608755abb5981` |
| 本地 `origin/main` 引用 | 同上；这是本地 remote-tracking ref，未以此代替 CI 查询 |
| 初始工作区 | tracked files 无修改；`docs/reviews/pre-phase6-evidence-package.md` 已存在且为 untracked，保留原状 |
| 本地环境 | macOS / arm64，`.venv/bin/python` 为 Python **3.12.13**，不同于 CI 的 3.11 |
| 本地全量验证 | `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q`：**704 passed, 1 warning in 55.41s** |
| warning | joblib 无法识别 physical core count，退回 logical cores；本次未造成失败 |
| 最新 main CI | [35080085627](https://github.com/KYLeonis/ai-physics-tracker/actions/runs/35080085627)，HEAD=`daad086`，macOS/Windows 均成功 |
| 最新 CI 实际日志 | Python 3.11：macOS **702 passed, 2 skipped, 2 warnings / 54.24s**；Windows **702 passed, 2 skipped, 2 warnings / 90.61s** |
| 修复前 Windows | [35071803064](https://github.com/KYLeonis/ai-physics-tracker/actions/runs/35071803064)，HEAD=`a963c21`，日志有 `Windows fatal exception: code 0xc0000374`；另一个前序 main run `35071748595` 也失败 |

实际执行的只读查询包括 `git status --short`、`git log --oneline -15`、`git rev-parse HEAD origin/main`、`gh run list --branch main` 和上述通过/失败 run 的日志读取。未重跑 CI，未发起新的训练/推理，也未要求用户重复 Human Review。

临时 probe 使用 `/tmp` 和 `TemporaryDirectory`，没有新增正式测试。其关键步骤、输出与复现方法保留在 Findings 中；临时脚本已清理。

### 2.2 证据强度

- **Observed**：本次直接读到代码/产物或执行 probe 得到结果。
- **Inferred**：根据已核实调用链推断用户影响；没有把未运行的 GUI 场景说成真机复现。
- **Historical evidence**：已有 review、smoke、Human Review、benchmark 记录，明确与本次执行区分。
- 对未验证路径的保留不自动构成 finding 或 blocker。

## 3. Current Architecture Assessment

**四层仍有有效边界，复杂度增长主要集中在跨对象事务与证据采集，而不是整个架构失效。**

| 边界 | 当前判断与证据 |
| --- | --- |
| domain | `Project`、`TrackPoint`、`Timeline`、`Calibration`、`TrackStore`、数值函数不依赖 Qt/DLC/OpenCV；聚合构造检查主要跨对象引用。`tests/test_layer_boundaries.py` 的 AST 检查本次通过。 |
| application | `ProjectSession` 拥有活动 Project/TrackStore，作写入、失效、历史与持久化协调；jobs 使用快照。application 与 infrastructure 的公共符号双向依赖是 [architecture.md §1](../architecture.md) 已明确的务实边界，并非严格六边形架构。 |
| infrastructure | JSON、OpenCV、FFprobe、spawn、DLC 适配集中在该层；DLC 特定 snapshot 选择与评价补丁仍在 `dlc_adapter.py`。 |
| GUI | MainWindow 和 Actions 负责控件、导航、轮询、确认与提交。数值计算不在 widget 内展开；但 Advisor 所需的业务证据是在 `TrackingActions._build_advisor_input()` 中拼装，P6R-04 表明这里已有真实维护问题。 |

`ProjectSession` 约 1900 行本身不是 blocker。它仍能被解释为“一个实验会话的事务入口”，没有直接持有 QWidget 或调用训练循环。P6R-01 指向的是其**事务边界不完整**，不需要先把它拆成多个服务才能修复。把事务分散到更多类反而可能扩大修复面。

`Project` 和 `TrackStore` 是聚合快照与写入服务/投影的组合，正常写入在 `_commit_store/_commit_project` 收敛，并非必然重复 source of truth。但这要求任何失败都不能留下两份不同的状态；Undo/Redo 恰好没有遵守这一点。

`TrackingRun.extra_fields` 仍是适当的版本化扩展机制。`refinement_history.py`、`suggested_frame_review.py` 已提供类型化读写函数，serializer 将未知键保真写回。无需仅因字段多而升级顶层 schema。真正缺口是 **run → series / parent / active pointer 的引用生命周期**；换成显式 dataclass 字段也不会自动解决它。

应用层仍知道 DLC 的 config 路径、shuffle 和 snapshot 契约；这是单引擎实现的耦合成本，但基础运动学不读取这些格式。未发现它已经阻碍 Phase 6 安全实现的证据。`_selected_snapshot/_selected_evaluation_snapshot` 对 DLC 内部 API 的依赖值得在升级 DLC 时跑真实 smoke，当前不要求预先设计通用引擎插件系统。

## 4. Data / Persistence Reliability

**manifest 的保存机制可信；跨历史操作的语义完整性尚有缺口。**

- `ProjectRepository.save()` 先序列化（拒绝 NaN），通过临时文件与 `os.replace` 发布；backup 发布失败有旧 manifest 恢复路径。`tests/test_project_repository.py` 覆盖主文件替换失败、备份发布失败、损坏 JSON 和未知键 round-trip。本次全部通过；没有把该保证扩大为断电时的 fsync 级持久性或多进程同时编辑保证。
- `save_as()` 先写 staging，再发布新目录；失败保留恢复位置，活动会话在 IO 成功后才改变绑定。`accept_saved_snapshot()` 保留保存期间产生的编辑，不用旧快照覆盖活动 session。
- `ProjectSession.load()` 将遗留 pending/running run 标记为 interrupted failure，避免重开后被无进程的任务永久锁住。这是可恢复状态降级，不是自动续训。
- 原始像素观测与 DerivedData 分开。有效观测由 manual 优先的 `effective_points()` 决定；AI 激活保留被 manual 遮蔽的同帧 AI 点，删除 manual 后可恢复。
- completed infer 只是候选；激活/替换/清除才改变 observations、active pointer、activation history 与 stale 状态。`test_result_activation.py` 的事务、失败不改原状态和 Undo/Redo 测试有实际行为价值。
- 保存清空 Undo 是已有明确约定，不在本次重新列为缺陷。与之不同，**保存前 Undo 发生异常并留下半提交**是 P6R-01；**恢复轨迹但不恢复它引用的 run**也是同一历史边界缺口。
- 验证集创建会冻结 label ID、frame、坐标和 modified_at；修改标签后训练前一致性校验会拒绝旧 series。正常路径成立，但删除 series 可以使历史 run 只剩无目标的 ID（P6R-03）。

没有发现必须换持久化后端的证据。当前 JSON 规模上限、整项目快照成本仍应以实际大项目测量决定，不能借 Phase 6 提前引入数据库。

## 5. Lifecycle / Concurrency Reliability

**通常路径的所有权、取消和迟到结果隔离成立；Undo 与正在登记的 run 组合是已复现例外。**

- `TrackingRequest` 携带项目快照；spawn worker 独占 DLC 和 reader，只写自己 run 的产物。GUI 根据 session、delivery generation、video/timeline、根目录和时序授权检查结果上下文。
- `prepare_tracking_candidate()` 在独立会话中准备，`apply_tracking_candidate()` 检查 `base_project is current_project`；当前 Project 已改变时重新准备候选。这避免后台整包回写吞掉手工编辑。
- `TaskHandle.cancel()` 有 cooperative event、join、terminate、kill 退路；训练产出模型后评价失败/取消能通过 model-ready 产物保留模型。现有 spawn 测试证明 mock worker 进程能回收，不等于真实 CUDA/DataLoader 子树所有退出条件都已覆盖。
- playback 将 OpenCV 读写约束在一个 decoder 线程；request ID 与 delivery generation 分别隔离同项目的新旧请求、跨项目结果。标注使用 presented frame，不使用尚未显示的 requested frame。
- 最新 `_DecodeDeliveryBridge` 用 `SimpleQueue` 承载 Python 对象，无参 Qt signal 唤醒 GUI。检查了实现及四项回归测试，并重新读取最新 Windows CI 通过日志。**未把旧 heap corruption 当成未修复问题，也未宣称一次成功证明永不复发。**
- 图表计算在 detached session 中运行，提交前重新比较 AnalysisInputs，取消或输入变化不提交部分 batch；窗口关闭后丢弃 worker 结果。
- 选帧、挖掘、训练入口已有 busy 互斥及切换/关闭回收。挖掘的即时“取消”会先解除 UI busy、后台再回收进程，和训练的 cancelling 状态并不完全相同；本次没有复现由此造成的数据损坏，不升级为架构 finding。

P6R-01 表明：worker 隔离做对了，不代表所有用户编辑都能安全跨越任务登记边界。修复应守住同一事务入口，而不是仅在某个按钮上加 try/except。

## 6. Scientific / Numerical Reliability

**当前基础 x/y/v/a 管线没有被本次发现为普遍错误；主要科学 blocker 在模型验证的 lineage。**

| 项目 | 结论与边界 |
| --- | --- |
| frame/time | 使用 0-based 源帧，`Timeline.frame_to_time()` 为 `frame_index / fps_nominal`；working zone 不重置时间原点。图表按源帧转换时间，不把稀疏数组行号当时间。 |
| nominal/container FPS | 视频 probe 不是只读一个容器 FPS 就授予分析权限；`ProjectMediaService._probe()` 对齐帧数与 FPS，near-CFR 需显式授权和误差预算。当前是 nominal 时间模型，不是 VFR 逐帧时间引擎。 |
| 像素/世界坐标 | raw 存像素；标定是比例、原点、y 翻转、旋转的派生变换。无标定结果以 `px` 保留，并有像素坐标提示。 |
| 单位 | m/cm/mm 按所选标定单位计算，导数为该单位/s、该单位/s²；不能把所有结果都假定为 SI 米制。 |
| 缺测 | 展开稠密网格时用 NaN，按连续段分别滤波；不足窗口按既定规则缩窗，过短段不造导数。图表在源帧间断处断线。当前没有偷偷跨缺帧插值。 |
| 平滑/微分 | `deriv=0/1/2` 分别对同一位置输入进行 SG 运算；一/二阶显式传 `delta=1/fps_nominal`。这是 SG 一步求导，不是把平滑位置再次平滑两次；不能把 ADR 的箭头图误读成必须串联三次 SG。 |
| manual/AI 融合 | 物理计算消费有效投影；人工点覆盖 AI，但 AI 原值可被保留为 superseded；训练只用 active manual，Accept 不变成 ground truth。 |
| confidence | DLC parser 校验有限值、范围、重复帧和全帧计数；缺测与低置信度分开统计。coverage 是阈值通过率，不是物理误差或精度。 |
| stale | 标注、激活/替换/清除、标定变化会失效现有结果；GUI 对 stale 或标定不匹配给出明确状态，单位不兼容时不混绘。后台结果还做输入匹配。 |

数值测试覆盖匀速、匀加速、标定变换、NaN 断段、短段窗口和小角度单摆。`test_pendulum_small_angle_synthetic()` 验证 60 fps、window=7 下的内区间 v/a；它**不证明所有采样率、噪声、端点、窗口和真实单摆都达到同样精度**。当前显式参数与 pipeline 留痕足以支持后续验证，不必预先换滤波器。

固定验证成员本轮确实进入 testIndices；但 parent weights 已见过这些帧时，本轮互斥不能消除历史泄漏。P6R-02 属于“程序成功运行、评价语义却误导”的真实问题，与 Phase 5.6 已记录的反复依据同一验证集选择模型（model-selection bias）不同，不能由后者的接受决定一并豁免。

## 7. Phase 5 AI Refinement Architecture

完整链条已存在：代表帧只给帧号 → manual 标注 → per-run 训练 → raw prediction → 多信号困难帧筛选 → run-scoped Accept/Skip/Correct → 新训练 → candidate inference → 显式激活 → DerivedData 重算。

关键 source of truth 分配总体合理：

| 事实 | 当前归属 |
| --- | --- |
| 当前人工坐标、活动轨迹 | Project observations / TrackStore effective projection |
| 某次模型输出 | immutable run 产物与 TrackingRun 引用；不以当前 manual 修正覆盖 raw prediction |
| 当前使用哪个 AI run | Track 的 `refinement_state_v1.active_infer_run_id`，与投影一起提交 |
| 审核 disposition 与当时 prediction | infer run 的 `suggested_frame_review_v1` |
| 固定验证标签 | Track 的 versioned validation series |
| 实际训练标签、mode、parent | train run 的 `refinement_iteration_v1` 与 config |
| Advisor 建议 | 重新计算的界面状态，不持久化成历史事实 |

这些字段不是天然重复；active pointer、投影和 history 是同一选择的不同用途，事务必须共同维护。P6R-01/P6R-03 是该约束在删除/撤销路径缺失，P6R-02 是跨轮关系缺少科学校验。

fresh per-run 工作目录已经消除了旧目录建集导致 shuffle 错位的主要路径。Resume snapshot 在 prepare 和 worker 执行前有文件状态复核；父 run、mode 与 snapshot 引用可追溯。局限是**可追溯不等于该 parent 对当前验证集是合法的**。

困难帧算法允许触发池为空，当前不再为凑满 N 把普通帧补成“困难帧”。[5.6 review](phase-5.6-review.md) 的饱和模型案例因此得到合理处理。该启发式仍可能漏掉高置信度的系统性偏移，不能以“没有困难帧”推断物理结果正确。

历史 review 的反复问题集中在上下文关联、字段/调用方契约与状态组合，并非证明所有复杂模块都必须重构。一个明确例子是 [5.5 review B3](phase-5.5-review.md)：记录称 timeline 的 track/video 关联已修复，**当前 main 仍有同样错误**，见 P6R-04；本次以代码和 probe 为准，不沿用关闭标签。

## 8. Test & Verification Assessment

**测试基线可信，但覆盖的是具体行为集合，不是整个工作流状态空间。**

| 证据 | 真正证明什么 | 不证明什么 |
| --- | --- | --- |
| domain/session/repository tests | 聚合校验、manual 优先、失败原子性、JSON round-trip、部分 Undo/stale 语义 | 所有后来新增 run/series 关系在旧历史操作中都完整 |
| numerical tests | 解析信号、NaN/短段、坐标变换、单位和指定容差 | 真实视频上的绝对物理误差、任意参数与端点质量 |
| spawn/mock tests | 真实进程 IPC、取消、失败传播与 candidate 提交边界 | DLC/CUDA 实际资源回收、训练数学行为 |
| DLC adapter tests | 参数传递、所选 snapshot、评价解析、预测格式 | 多数通过 fake `deeplabcut`/loader 验证，不能替代真实依赖兼容性 |
| GUI offscreen | 事件、导航、上下文、按钮与回调组合；decode bridge 线程交付 | 真机绘制、点击手感、Windows GPU/codec/安装包 |
| 最新双平台 CI | 当前 HEAD 在 Python 3.11 和该 runner 环境可完整通过 | Windows 真机/CUDA，以及未安装依赖的路径 |
| historical real DLC smoke | [5.5 review §3](phase-5.5-review.md) 记录 restart → resume、新 snapshot、parent 未覆盖，证明当时实际 API 能跑通 | 重新冻结验证帧后的祖先泄漏检查、所有真实工程迁移路径 |
| Human Review | 5.4/5.5/5.6 记录了实际操作确认 | 不穷举 Undo 到 track 创建、不同 validation series 与任意 resume parent 的组合 |

两个 CI skip 对应 optional HDF 读取依赖入口（`tests/test_dlc_predictions.py`、`tests/test_difficult_frames.py` 使用 `pytest.importorskip("tables")`）；本地环境这些入口执行通过。不能把 CI 702 和本地 704 说成两个相同环境下的矛盾计数。

值得保留的行为测试包括：`test_kinematics_job.py` 的部分失败/取消/输入改变拒绝提交，`test_project_repository.py` 的替换失败恢复，`test_result_activation.py` 的 manual 保留与可逆投影，GUI 的同帧旧错误隔离及 review 导航取消。

明确的 implementation-locking 例子是 `tests/test_project_session.py:134` 的 `test_remove_track_with_runs_succeeds_and_undo_keeps_runs_deleted`：它要求 Undo 后 runs 仍为空，但未构造 Phase 5 的 active pointer。这个测试在早期政策下有解释，在当前模型下不能作为引用一致性的证明。修复 P6R-01 时应更新其行为契约，而非为了让旧断言继续通过保留悬空引用。

### 8.1 Benchmark 证据复核

- [Phase 5.2 report](../benchmarks/phase-5.2-report.md) 实际写的是 **148 帧**视频、17 帧审计表、policy/baseline 的 Precision@N 为 0.800/0.600，review yield 为 0.300/0.000。Evidence Package 的部分叙述提到 2767 帧，不能把选帧性能样本与该报告的评价样本混为一谈。此处只采用原报告可直接支持的范围，未重做盲评。
- [Phase 5 loop report](../benchmarks/phase-5-loop-report.md) 的四轮 RMSE 为 3.30/4.80/3.19/4.71，≥5% 目标未达成的归档决定保留；本次没有重写验收标准。
- 本次读取 `experiment/AI_test2/project.json` 和五轮 DLC `Documentation_data-*.pickle`、同目录 `CollectedData_*.h5`，按真实 split indices 映射图像源帧。四个带 series 的轮次各自本轮 train/test 互斥，但其前置 parent 的训练集与冻结验证集有 7 帧重叠，详见 P6R-02。
- “某次复跑 snapshot hash 相同”的历史证据只支持该配置/数据/环境的重复结果；不证明整个训练系统在任意设备/版本下确定，也不消除数据泄漏。

## 9. Phase 6 Extension Readiness

当前 Physics Engine 由纯数值函数、session 编排、后台 job 和 chart adapter 组成，能够在关闭 blockers 后继续扩展。没有发现必须先引入通用 pipeline 框架或新持久化架构的理由。

后续实现时必须沿用、并按实际新功能补齐的边界：

- 从 effective observations 取输入，保留源帧、单位、缺测和标定上下文；不要从屏幕曲线反推科学数据。
- 结果走输入快照验证与原子 batch 提交，不能只按 track ID 接收后台结果。
- `KINEMATICS_KINDS`、`validated_derived()` 的“四种结果完整性”与 `chart_data.py` 的两列 x/y 是**当前 x/y/v/a 的具体契约**，不是任意高级物理量的现成通用接口。新增量时需显式调整适用路径，无需先泛化所有现有代码。
- `set_active_calibration()` 首次标定对未标定结果的失效目前特判 `KINEMATICS_KINDS`；新增依赖标定的 derived kind 时需增加相应失效规则。当前已实现的四种量受保护，不能把尚不存在的新量漏洞算作当前 blocker。
- `update_timeline()` 的 FPS 变化会 stale；仅 working-zone 变化时当前主要是显示筛选。若新分析把区间当成计算输入，需明确重算/缓存身份；这属于 Phase 6 的具体实现验证，不是现在要求重写 timeline。
- 当前 pipeline 记录算法与参数，calibration_ref 指向可更新标定；它不是所有历史输入版本的永久快照。当前会将相关结果标 stale；不能把缓存当不可变实验档案。

这些是现有边界的使用条件，不是新增 Phase 6 deliverables。Roadmap 的 θ/ω/α、相图、周期/拟合、多目标、误差分析范围保持不变。

## 10. Findings

### P6R-01 — Undo/Redo 未维护 Track、run 与其引用的一致事务

- **Finding**：Undo/Redo 恢复 tracks/observations/refinement metadata，却沿用当前 TrackingRun 注册表；同时在新 Project 验证成功前就修改历史栈与 `_store`。新建轨迹的撤销和后台 run 登记组合会留下半提交，删除轨迹的撤销又会产生悬空 active run。
- **Evidence**：`application/project_session.py:1029`（undo）、`:1081`（redo）、`:1132`（快照未含相关 run）、`:258`（remove_track）；`domain/project.py:290` 附近的 `delete_track()` 级联删除 runs；GUI `main_window.py:695` 直接调用 undo，`:725` 只按 can_undo 使能，没有任务依赖守卫。`tests/test_project_session.py:134` 明确固定“Undo 不恢复 run”的旧行为。
- **Observed / Inferred**：**Observed**，应用层 probe 复现以下两条；GUI 可达性由按钮/快捷键与训练入口的调用链确认，未声称复现 native 进程崩溃。
- **复现 A**：已保存项目 → 新建 track → 标注 4 帧 → `prepare_tracking_request(..., TrainingParams())` → `record_tracking_run(request.run)` → Undo 四次标注 → 再 Undo 新建 track。返回异常 `every tracking run must reference a registered track`，随后输出 `project_tracks=1, store_tracks=0, project_unchanged=True, can_redo=True`；继续 mark_point 报 `unknown track_id`。run 为 pending 已足够，running 同样持有引用。
- **复现 B**：构造 completed infer 产物，activate、save → `remove_track(track_id)` → `undo()`。输出 `activation=('active', old_run_id, None), runs=0, effective_points=3`；save/load 后仍为 active 且 runs=0。B 是公开应用接口 probe；不把它描述成当前 GUI 已暴露的轨迹删除按钮路径。
- **Impact**：会话内 source of truth 分裂，后续标注/刷新/任务结果可能失败；或保存缺少 run provenance 的活动轨迹。即使用户能通过重开或重做部分恢复，也不满足失败原子性。
- **Realistic trigger**：先保存实验，再新增目标、标几个点启动训练，训练未完成时连续撤销以重做标注；无须损坏文件或恶意输入。
- **Likelihood**：Medium。
- **Severity**：High。
- **Recommended Action**：先构造并验证完整 candidate（Project、Store、历史操作结果），成功后一次替换状态与栈；为撤销涉及的 track/run 依赖建立明确政策，例如安全拒绝越过有任务依赖的结构性操作，或按作用域恢复/移除相关 run。不得整体回滚无关后台任务。删除/恢复轨迹时，active pointer、观测和被引用 run 必须共同有效；必要时增加应用层引用一致性验证。
- **Fix Cost**：Medium。
- **Decision**：Fix Before Phase 6。
- **Phase 6 Blocker**：Yes。
- **关闭条件**：A 路径要么合法撤销，要么明确拒绝且 Project、Store、Undo/Redo 栈完全不变；B 恢复后引用可解析，保存重开保持一致；无关 run 的异步完成状态仍不被撤销；覆盖 pending/running/completed 的相关边界和 GUI 快捷键路径。

### P6R-02 — Resume 缺少祖先训练集与当前固定验证集的隔离校验

- **Finding**：固定 train/test indices 只约束本轮数据；`prepare_tracking_request()` 的 Resume 验证只检查父 run 状态、track、snapshot 与文件指纹，没有检查父模型及祖先已经学习过哪些帧。`prepare_training()` 仍记录当前 validation_series_id，Advisor 仍按同 series 比较。
- **Evidence**：`application/tracking_job.py:56` 的 prepare/resume 分支、`:194` 附近的 `_train()`；`application/training_job.py:127` 起的 fixed split 和训练标签快照；`application/training_advisor.py` 的 `_same_series_comparison()` 只比较 series ID、metric name/unit。对照 [ADR-0014 §Decision 5](../decisions/0014-result-activation-and-fixed-validation-history.md) 和 [phase5-requirements R5/R6](../spec/phase5-requirements.md)。
- **Observed / Inferred**：**Observed** 请求与建集接受泄漏组合，且真实实验产物存在祖先重叠；**Inferred** 其评价不再具有独立留出含义。未测定泄漏使 RMSE 改善/恶化多少，也没有假称所有轮次数字都是错算。
- **最小 probe**：manual frames `[0,1,2,3]`；series A=`[0]` 训练 parent，其 `training_labels=[1,2,3]`；创建 series B=`[1]`；选择 parent Resume。prepare 成功，child split 为 `train=[0,2,3], test=[1]`，但 `parent_training_frames ∩ child_validation_frames = [1]`。Mock 只替代引擎建集，执行的是生产请求与划分代码，不用 mock 假定防泄漏结论。
- **真实产物复核**：`experiment/AI_test2` 的 parent `9d310620` 实际 split 为 train=19/test=1（test frame 62）；与冻结 series `f13d5bbd` 的 11 帧交集为 **`[1,6,26,60,110,129,143]`**。`f8d5fe67` 的 `resume_from_training_run_id=9d310620`，下一轮 `e976e5dc` 又 Resume 自 `f8d5fe67`。这两轮自身 train/test 无重叠，仍继承该 parent 暴露。`18d1f638`、`b80fbd68` 是 restart，其本轮训练集与该 series 无交集；本次未发现同类父模型泄漏。
- **Impact**：跨轮固定验证指标可被当成独立精度改善证据，进而影响模型/活动结果选择；“相同 series”并不足以证明比较具有同样的训练暴露条件。该问题不会自动改写像素或物理公式，但会污染选择这些输入的科学依据。
- **Realistic trigger**：先训练、后冻结验证集；或因修正/重选标签创建新 series，再 Resume 任意旧模型。当前真实闭环已经发生前一种情况。
- **Likelihood**：High。
- **Severity**：High。
- **Recommended Action**：在执行入口验证当前验证帧与完整 Resume 祖先训练帧不相交。对缺少训练成员信息的 legacy parent，不能默认“未见过”；用明确 restart 或标记不可独立比较的受控处理。Advisor/历史展示必须使用该比较资格。先阻止新泄漏并界定既有评价，不能靠相同 series ID 或 fresh DLC 目录代替校验。
- **Fix Cost**：Medium。
- **Decision**：Fix Before Phase 6。
- **Phase 6 Blocker**：Yes。
- **关闭条件**：新增/更换 series、无 series 的 legacy parent、同 series 但更早祖先有污染、干净同 series Resume 四类路径均有行为验证；污染/未知路径不得继续无提示地产出“可独立比较”评价。为上述真实 Resume 历史增加可审计的资格说明，不改原始 RMSE，也不要求为达成 AC-9 重跑大型实验。

**真实证据定位与复核方式**（产物位于 gitignored 实验目录，不是 main 的版本化文件）：

```text
experiment/AI_test2/project.json
sha256 = cf8197daeb9185717b07ed42115c687f6c17c9e2979a24dd4f57cae4e795b52a

data/engines/9d310620-97c4-4d73-9a20-288c52d9b8c9/dlc_7f423430/
  training-datasets/iteration-0/UnaugmentedDataSet_dlc_7f423430Sep02/
  Documentation_data-dlc_7f423430_95shuffle1.pickle
sha256 = 658c16f84222fbfe479fe2d73e8af548a47f56b5472b54977b4caf5313e88ae4
```

从该 DLC 文档 pickle 的第 1/2 索引项读取 train/test indices，在同目录 `CollectedData_*.h5` 的 DataFrame index 中取相应 `imgNNN.png` 源帧；与 manifest 中 Track 顶层 `refinement_state_v1.validation_series[active_validation_series_id].label_snapshots` 比较。serializer 将 extra_fields 展平在 JSON 对象顶层，**不能误读 `track["extra_fields"]`**。本次五轮的 train/test 数分别为 `19/1、19/11、29/11、29/11、39/11`。未使用训练文件行号直接当视频帧号。

### P6R-03 — 删除已被历史 run 引用的 validation series 会丢失项目级验证标签溯源

- **Finding**：series 是历史 validation labels 的唯一第一方快照，删除它时不检查已有 train run 的引用，也未将快照归档至这些 run。
- **Evidence**：`application/project_session.py:1598` 的 `delete_validation_series()` 直接从 Track 移除 series；`gui/validation_dialog.py` 的 Delete Active Series 可调用此路径；`training_job.py` 仅把 `validation_series_id` 和训练标签放进 iteration；[project-format §3.5 附近的 refinement 约束 4](../spec/project-format.md) 明确验证标签由 series 给出。
- **Observed / Inferred**：**Observed** 临时项目建立使用 series 的 train run 后删除该 series、save/load，run 的 series ID 仍在，`get_series(id)` 返回 None。**Inferred** 历史指标的第一方标签快照无法再单靠 project.json 解释。
- **Impact**：历史评价失去可读、可验证的 validation membership/标签版本；DLC 数据集文件可能还可辅助恢复，但不能替代宣称的项目事实契约。不会立即改变已有活动轨迹或历史 RMSE 数值。
- **Realistic trigger**：验证集标签需要修正，用户在 Manage Fixed Validation Series 中删除旧 active series，之后新建、保存并继续工作。
- **Likelihood**：Medium。
- **Severity**：Medium。
- **Recommended Action**：对已引用 series 保留历史对象，仅取消激活/从可选列表归档；或在删除前确保历史 run 已持有完整冻结快照。未被引用的 series 可以继续删除。补一条“训练完成 → 删除/停用 → save/reopen → 历史标签仍可追溯”的行为测试。
- **Fix Cost**：Low。
- **Decision**：Fix During Phase 6。
- **Phase 6 Blocker**：No。
- **不阻塞理由**：需要用户显式删除，当前物理输入不受影响，磁盘 DLC 产物仍可能恢复证据；是范围明确的历史维护问题。P6R-02 的修复必须对未知/缺失 lineage 采取保守资格判断，不能依赖此缺口已先修复。

### P6R-04 — Advisor 的 GUI 输入采集错误选择时间轴和“最近失败”

- **Finding**：规则函数本身是确定的，但 GUI 收集到的事实不正确：timeline 按 `video_id == track_id` 查找；last_train_failed 取“历史上最后一个失败 run 是否存在”，没有判断它之后是否已有成功训练。
- **Evidence**：`gui/tracking_actions.py:245` 的 `_build_advisor_input()`（`:246` 的 timeline 查找、`:250` 起 failed_train、`:352` 附近输入构造）。旁边的注释声称按 track.video_id 修复，但实际赋值没有这样做。[5.5 review B3](phase-5.5-review.md) 的已修复记录与当前 main 不符。
- **Observed / Inferred**：**Observed** 直接调用生产采集方法：working zone `[0,119]`，manual 仅 `[0,1,2,3]`，返回 `uncovered_zone_segments=False`；登记 OOM failed run 后再登记 completed train，返回 `last_train_failed=True, last_failure_is_oom=True`。未将该 probe 当作完整 UI 人工验收。
- **Impact**：plateau 时缺时段分支被跳过；已经成功恢复的训练仍可持续被建议因 OOM 减小 batch/retry。浪费操作与训练时间，削弱 Advisor 的证据可信度；不会自动训练或替换轨迹。
- **Realistic trigger**：标注集中在视频前段后比较两轮；或发生过一次 OOM，降低设置并已成功重训。
- **Likelihood**：High。
- **Severity**：Medium。
- **Recommended Action**：按选中 Track 的 video_id 取 timeline；按明确的最新训练状态构造 failure 输入。增加 session → AdvisorInput → recommendation 的组合测试，避免只测试手写 AdvisorInput。若需要移动采集函数，限定为小型应用层 helper，不借此拆分整个 TaskPanel/Actions。
- **Fix Cost**：Low。
- **Decision**：Fix During Phase 6。
- **Phase 6 Blocker**：No。
- **不阻塞理由**：Advisor 仅建议，Apply 只填表，用户仍显式启动；错误不修改 raw/derived 或活动模型。应尽早修正，但不构成开始高级物理分析的基础阻断。

## 11. Risk Matrix

| ID | 风险 | Likelihood | Severity | Fix Cost | Decision | Phase 6 Blocker |
| --- | --- | --- | --- | --- | --- | --- |
| P6R-01 | Undo/Redo 半提交、悬空 run 引用 | Medium | High | Medium | Fix Before Phase 6 | Yes |
| P6R-02 | Resume 祖先已训练固定验证帧 | High | High | Medium | Fix Before Phase 6 | Yes |
| P6R-03 | 删除 series 丢失历史标签溯源 | Medium | Medium | Low | Fix During Phase 6 | No |
| P6R-04 | Advisor 采集错误事实 | High | Medium | Low | Fix During Phase 6 | No |

未发现 Critical 级问题。没有用“所有本地项目都会损坏”或“全部数值结果不可信”描述这些限定触发的问题。

## 12. Recommended Pre-Phase 6 Stabilization

限定为两个可单独验证的稳定化改动，不开展架构重写：

1. **关闭 P6R-01**：修复 Undo/Redo 的异常原子性和受影响引用边界；覆盖新建 track 后 pending/running run、激活 track 的删除/恢复、无关任务状态不回滚、保存重开一致性。对 GUI 明确拒绝路径按项目规则做 Human Review。
2. **关闭 P6R-02**：补 Resume ancestry 与固定验证集隔离检查；将未知历史与明确污染从可比评价中区分；对本报告识别的真实历史作附加说明，保留原始实验数字。
3. 每项运行相称定向测试；集成后跑全量与最新 macOS/Windows CI，再独立复核具体关闭条件。不能仅用“704 tests passed”替代新增场景的断言。

不把“≥5% 改善”、Windows 真机/CUDA、UI 全面重构、模型库或科学导出提前塞进本稳定化范围。P6R-03/P6R-04 可顺手小修，但不是本门禁的隐含额外条件。

## 13. During-Phase-6 / Later Items

| 项目 | 建议时点 | 原因 |
| --- | --- | --- |
| P6R-03、P6R-04 | Phase 6 期间尽早 | 小而确定的历史/建议错误，无需大型设计 |
| 新 derived kind 的单位、维度、依赖与 stale 测试 | 相应 Phase 6 功能进入实现时 | 现有四种量的特判不可无检查照搬；不提前实现通用框架 |
| 状态与架构文档陈旧描述 | 下次获授权的文档同步 | AGENTS 概要仍在 5.4，architecture 仍有立即导入/screening 补齐等旧描述；本 review 依用户边界未修改 |
| DLC 内部 API / 项目迁移的真实 smoke | 改动适配器、升级依赖、移动工程支持验收时 | mocks 不能证明真实配置路径、文件指纹与 DLC 自身读取行为的组合 |
| 长视频、大轨迹集 UI/内存测量 | 出现实际规模需求时 | 当前数据不足以支持数据库、索引或异步激活重构 |
| Windows 真机/CUDA、发布包 | 既定 Phase 9 前节点 | 保留已批准延期，不将 CI 当真机证明 |
| 完整模型库、归档/导出、交互重构 | 按既有 roadmap/独立立项 | 本审查未发现必须为 Phase 6 先交付它们 |

## 14. Accepted Risks

以下是本审查接受为非 blocker 的边界，不表示已验证无限可靠：

- 轻量文件状态校验及 activation 的 size-only 政策；不重新发起针对同大小外部替换的安全加固。
- 保存清空应用内 Undo，backup 只轮转一份；本次不更改已约定的删除/恢复范围。
- Project frozen dataclass 内仍有 dict；当前快照共享依赖“复制后 replace、不原地写”的约定。未找到实际在所审关键写路径中原地改共享 dict 的复现，故不要求全量深拷贝或持久化容器。
- 单目标/单 bodypart DLC、nominal CFR 与显式 near-CFR 近似；不把尚未交付的 VFR、相机畸变/透视模型当 bug。
- SG 短段降窗、边界精度和 AI 置信度饱和；需要真实数据解释，不能保证普适物理精度。
- Phase 5.6 的 ≥5% 指标未达成已经明示归档；这不阻止基础物理扩展。但 P6R-02 是本次新确认的验证资格问题，不能靠“指标未达成已接受”掩盖。
- 当前 GUI 模块较大、application/infrastructure 有公共依赖；未证明其本身阻碍安全扩展，不以风格为由强制拆分。

## 15. Unverified Areas

- 本次没有重新训练/推理真实 DLC，未重新测量 RMSE、未重新运行确定性实验。真实产物检查是只读 split/label/lineage 核对，不是新训练验证。
- 没有 Windows 真机/CUDA、安装程序、不同 GPU 驱动或真实 DataLoader 多进程强制终止测试。
- 没有重新执行完整 GUI Human Review；所引用户反馈均为历史记录。本次不以截图、computer-use 或 offscreen 代替真人体验。
- 没有断电/磁盘硬件故障、两个应用实例同时保存同一项目的验证；原子 replace 测试不等同这些保证。
- 没有完整“真实训练工程 Save As/移动到新路径后再真实推理”的重跑。源码中存在 DLC config 路径修复与应用指纹校验交互，需真实 smoke 才能对该组合下结论；未将它列为已证实失败。
- 没有针对数十万点、超长视频、持续多小时任务的性能/资源压力测试。
- 未复现旧 Windows heap corruption；本次只核实修复代码、现有回归及当前最新 CI。历史 cdb 根因描述按取证记录引用，不声称本 reviewer 独立做过原始内存取证。
- Phase 6 未实现物理量没有被本次证明正确；本次只判断基础及其扩展边界，不承诺未来验收。

## 16. Phase 6 Entry Gate

**READY AFTER BLOCKERS**

必须先关闭且独立复核 **P6R-01、P6R-02**；具体可检查条件见各 finding。当前基础总体可用，问题能够通过有限的事务与 lineage 稳定化解决，没有系统性重建的证据。

P6R-03/P6R-04、已经批准的延期及 §15 的未验证范围不额外升级为门禁。未满足两项关闭条件前，不把本报告解释为批准开始 Phase 6 产品实现。

## 17. Pre-Phase 6 Stabilization 处置结果（2026-09-16 追记，原始 Findings 不改写）

实施分支 `fix/pre-phase6-stabilization`，完整生命周期与 R1/R2 记录见
[pre-phase6-stabilization-review.md](pre-phase6-stabilization-review.md)
（R1 Verdict PASS → findings 处置 → R2 Verdict **CLOSED**）。

| Finding | 处置 | fix commit | 关键验证 |
| --- | --- | --- | --- |
| P6R-01 | **已关闭**。快照携带 run registry；恢复 Track 时其 run 随快照恢复；undo 越过快照外登记的 run 依赖时原子拒绝（五项不变量不变）；`record_tracking_run` 清空 redo；GUI undo/redo 拒绝给出可见反馈 | `7c160b0` | `tests/test_undo_run_integrity.py`（9 测试：三态原子拒绝、恢复+save/reopen、redo 往返、无关 run 不回滚、F2 回归）、`tests/gui/test_undo_rejection_ui.py` |
| P6R-02 | **已关闭**。`validation_training_exposure` 纯函数三态资格（legacy/缺失/环路 → unknown，不默认 clean）；Resume 入口在 active series 存在且非 clean 时阻止；`RoundMetrics.comparison_qualification` 显式 fail-closed 字段 + Advisor 比较门控 + 采集器同口径；历史 RMSE 不重写（资格为 compute-on-read） | `c384cd8` | `tests/test_validation_lineage.py`（16 测试：clean/直系/祖先/换 series/legacy/缺祖先/cycle/restart/无 series/P6R-03）、advisor 门控测试 |
| P6R-04 | **已关闭**。采集器提升为 Qt-free `application/advisor_collection.py`；timeline 按 Track 真实 video_id 解析；last_train_failed 取最近一次相关训练状态 | `1c3769d` | `tests/test_advisor_collection.py`（session/runs → collector → AdvisorInput → recommendation 全链组合测试） |
| P6R-03 | **已关闭**（按条件实施：无 schema 变更、单一守卫）。被本 track train run iteration 引用的 series 拒绝物理删除（提示停用）；未引用可删 | `1c3769d` | 同上文件 `test_referenced_series_deletion_is_rejected_and_deactivation_preserves_trace` |

R1 附带 findings：F1（既有 GUI 测试排序挂起隐患，main 可复现，**Defer** 至
Phase 5.7 测试刷新，配方已记录）、F2/F3（Fix Now，`405b91b`）。全量回归
**733 passed**，`compileall` 通过；双平台 CI 见 status 记录。

**§16 Entry Gate 状态更新：两项 blocker（P6R-01、P6R-02）已按各 finding 的
关闭条件关闭并经独立复核（R1/R2），`READY AFTER BLOCKERS` 的 blocker 条件满足。**
