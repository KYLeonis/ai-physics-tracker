# Pre-Phase 6 Evidence Package

> 用途：为后续 GPT-6-Astra 工程审查与交互设计审查提供事实索引。
>
> 本文件收集仓库已经留下的实现、测试、CI、真实运行、Human Review、决策和历史审查记录。它不替后续 Reviewer 做架构结论、严重度判断、重构建议或 Phase 6 readiness 判断。

## 0. 报告范围与证据标记

### 生成时点

- 生成日期：2026-09-16（Asia/Shanghai）。
- 仓库：`KYLeonis/ai-physics-tracker`，remote `origin` 指向 `https://github.com/KYLeonis/ai-physics-tracker.git`。
- `main` commit：[`daad086f1af6ae48180b2cef284608755abb5981`](https://github.com/KYLeonis/ai-physics-tracker/commit/daad086f1af6ae48180b2cef284608755abb5981)。
- `origin/main` 在最终读取时与本地 `main` 相同。
- 本报告生成期间的工作区位于 `main`，且写入前无未提交改动；本文件是本次唯一新增的 tracked file。

### 证据标签

- `[Observed in code]`：由当前仓库源代码、目录或静态检索直接观察到。
- `[Verified by test]`：由自动化测试或本次执行的验证命令支持。
- `[CI evidence]`：由 GitHub Actions job/run 支持。
- `[Human Review evidence]`：由用户实际操作反馈或归档的 Human Review 支持。
- `[Documented decision]`：由 ADR、spec、status 或 roadmap 明确记录。
- `[Historical finding]`：由历史 Review Record 记录，状态按原记录保存。
- `[Benchmark evidence]`：由 benchmark 或真实数据报告支持。
- `[Not currently verified]`：仓库目前没有本项所需的真实验证，或本次没有重新执行该项。

本文件使用以下状态词并分别记录：

| 状态 | 本报告中的含义 |
| --- | --- |
| `implemented` | 当前源代码中存在对应实现或接口。 |
| `tested` | 有自动化测试证据；不表示所有运行环境都已覆盖。 |
| `real-world validated` | 有真实视频、真实 DLC 运行或用户 Human Review 记录。 |
| `documented` | 事实、边界或决策写入了文档。 |
| `deferred` | 文档明确放到之后的 Phase 或后续节点。 |
| `unverified` | 没有相应的当前真实验证证据。 |

### 已读取的基线资料

- 项目规则：[`AGENTS.md`](../../AGENTS.md)、[`CODE_STANDARD.md`](../../CODE_STANDARD.md)、[`workflow.md`](../workflow.md)。
- 状态与范围：[`current.md`](../status/current.md)、[`roadmap.md`](../roadmap.md)、[`architecture.md`](../architecture.md)、[`phase-5-plan.md`](../status/phase-5-plan.md)、[`phase-5.6-plan.md`](../status/phase-5.6-plan.md)。
- Phase 1–5 spec：[`data-model.md`](../spec/data-model.md)、[`project-format.md`](../spec/project-format.md)、[`phase1-requirements.md`](../spec/phase1-requirements.md)、[`phase2-requirements.md`](../spec/phase2-requirements.md)、[`phase3-requirements.md`](../spec/phase3-requirements.md)、[`phase4-requirements.md`](../spec/phase4-requirements.md)、[`phase5-requirements.md`](../spec/phase5-requirements.md)。
- ADR：`0003`–`0015`，重点为 persistence、GUI/video/timing、numerical pipeline、charts、DLC integration、task boundaries、review state、activation/validation、Advisor/retraining。
- Review / benchmark / interaction：[`docs/reviews/README.md`](README.md)、Phase 4.5、Phase 4 reliability、Phase 5.0–5.6 review records、[`benchmarks/README.md`](../benchmarks/README.md)、Phase 5.2/5.6 reports、[`interaction-experience.md`](../notes/interaction-experience.md)。
- 当前仓库与外部状态：最近 git log、`gh issue list --state open`、GitHub Actions workflow/run/job/log、`src/`/`tests/` 静态统计。

## 1. 最新 Baseline

### 1.1 Git、Phase 与 Issues

| 项目 | 当前事实 | 证据 |
| --- | --- | --- |
| `main` | `daad086`：记录 Windows CI 崩溃取证、修复和验证的文档提交；修复代码来自已合并的 `f32fa4c`，其代码提交为 `8cd8621`。 | `[Observed in code]` Git log；[`f32fa4c`](https://github.com/KYLeonis/ai-physics-tracker/commit/f32fa4c9f97565a31d262bb81b547fd8080a9430)、[`8cd8621`](https://github.com/KYLeonis/ai-physics-tracker/commit/8cd86214517119e1a2480e8c25de9eeb96c156ce)、[`daad086`](https://github.com/KYLeonis/ai-physics-tracker/commit/daad086f1af6ae48180b2cef284608755abb5981) |
| 当前状态文件 | `docs/status/current.md` 记录：Phase 5（5.0–5.6）已收官，5.6 Human Review 通过；AC-9 的“≥5% 可复现改善”作为明示缺口归档；下一步为 Pre-Phase 6 Review / Phase 6 立项。 | `[Documented decision]` [`current.md`](../status/current.md) §Phase / Current Goal |
| 当前 Subphase | 5.6 — Refinement Loop Integration & Acceptance，status 文件记录为完成。 | `[Documented decision]` [`current.md`](../status/current.md) 表格、[`phase-5.6-plan.md`](../status/phase-5.6-plan.md) |
| Phase 6 | `docs/status/current.md` 将其列为下一步；`docs/roadmap.md` 的 Phase 6 标题为 `Advanced Physics Analysis ⬜`。 | `[Documented decision]` [`current.md`](../status/current.md) §Next Recommended Action、[`roadmap.md`](../roadmap.md) §Phase 6 |
| Open Issues | 最终读取 GitHub open Issues 返回 `[]`，当前没有 open Issue。历史 Phase 5 Issue #18/#19/#21/#22 均有关闭记录。 | `GitHub query` / `[Documented decision]` `gh issue list --state open`；[`current.md`](../status/current.md) |
| 文档状态差异 | `docs/roadmap.md` 顶部仍写 Phase 5 `🔄`、5.6 `🚧`，其 Phase 5 验收表仍有若干未勾选行；`AGENTS.md` 概要也保留了 5.4“复核收口后进入 5.5”的旧表述。`docs/status/current.md` 是较新的收官记录。 | `[Observed in code]` 各文件当前内容；此处只记录来源差异，不合并或解释其含义。 |

### 1.2 最近 commits 与 CI

最近 `main` 的相关提交顺序为：

1. `daad086` — `docs: record Windows CI crash root cause, fix and verification`。
2. `f32fa4c` — merge `fix/windows-ci-crash`，合并 decode delivery queue bridge。
3. `8cd8621` — `fix: route decode deliveries through a thread-safe queue with argless wakeup signal`。
4. `a963c21` — Phase 5 wrap-up 文档同步。
5. `d428338`、`3943f1d` — Phase 5.6 合并与功能收尾。

最终重新读取的最新 `main` Actions：

| Run | Commit | macOS | Windows | 结果 |
| --- | --- | --- | --- | --- |
| [`35080085627`](https://github.com/KYLeonis/ai-physics-tracker/actions/runs/35080085627) | `daad086` | `Python 3.11 / macos-latest`：`702 passed, 2 skipped` | `Python 3.11 / windows-latest`：`702 passed, 2 skipped` | `[CI evidence]` completed / success |

workflow 当前明确执行：Python 3.11 双平台、`QT_QPA_PLATFORM=offscreen`、安装 `requirements.txt`、安装 checksum-verified FFprobe、运行 `python -m pytest`。见 [`.github/workflows/tests.yml`](../../.github/workflows/tests.yml)。

此前同日的 main run [`35071803064`](https://github.com/KYLeonis/ai-physics-tracker/actions/runs/35071803064) 曾失败；诊断分支捕获了 GUI decode queued signal 的 Windows heap corruption 路径。修复合并后，上表的最新 main run 已恢复成功。`docs/status/current.md` 中仍链接较早的 `35079898823`，该链接与最新 run 编号不同；本报告采用 Actions 实际最新结果。

平台状态分别为：

- macOS：最新 Actions job 通过；本次本地全量测试也在当前 macOS 工作区通过。历史记录包含 macOS GUI Human Review 和 macOS 真实 DLC/单摆工作流证据。
- Windows：最新 Actions job 通过；历史取证分支、合并修复和回归测试已记录。Windows 真实机器与 CUDA 不属于已完成验证，文档明确延期至 Phase 9 前的专门节点。

### 1.3 本次本地验证

本次实际执行：

```text
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q
704 passed in 60.91s (0:01:00)
```

另外执行了：

```text
QT_QPA_PLATFORM=offscreen .venv/bin/python -m compileall -q src
git diff --check -- docs/reviews/pre-phase6-evidence-package.md
```

两条命令均以 exit code 0 完成且无错误输出。

该结果对应当前 checkout 的 `main @ daad086`。它与 CI 的 `702 passed, 2 skipped` 是不同运行环境下的结果，不能互相替换。`docs/status/current.md` 中的 `699 passed` 是 Phase 5.6 收尾时的历史本地计数。

本次没有重新运行真实 DLC 训练/推理、用户 GUI Human Review、Windows 真实机器/CUDA 或打包程序；这些入口在后文单独标为 `real-world validated`、`deferred` 或 `[Not currently verified]`。

### 1.4 Phase 6 是否已开始

- `implemented`：当前 `src/` 中没有以 Phase 6 交付物命名的模块；对 `theta`、`omega`、`angular`、`phase space`、`period` 等关键词的检索主要命中文档中的 Phase 6 计划和 Phase 3 的延期说明，另有通用 `video_timing.py` 的 period 字样。
- `documented`：Phase 6 的目标是 θ/ω/α、相图、周期/模型拟合、多目标和误差分析；Phase 6 验收项在 roadmap 中仍未勾选。
- 因此，本报告把“Phase 6 尚未进入产品实现记录”作为仓库事实索引，不把它转换为 readiness 结论。

## 2. Repository Map

### 2.1 分层地图

架构文档描述四层：domain、application、infrastructure、GUI。当前代码的主要入口如下。

| 区域 / 文件 | 职责 | 主要调用关系与公共接口 | 相关测试 / 文档 | 值得进一步打开的事实入口 |
| --- | --- | --- | --- | --- |
| `domain/project.py`, `domain/track.py`, `domain/track_store.py` | Project 聚合、Track/TrackPoint 数据、manual/engine observation 存储和 effective projection。 | `Project` 持有项目对象；`TrackStore.add_manual()`、`add_engine()`、`resolve_effective_point(s)`、`clear_engine_run()`、`replace_track_engine_points()` 被 `ProjectSession` 使用。 | `tests/test_project.py`、`tests/test_track_store.py`、`docs/spec/data-model.md`、ADR-0003。 | Phase 1 数据边界、来源优先级与删除/恢复操作集中在这里。 |
| `domain/timeline.py`, `domain/calibration.py`, `domain/derived.py` | 帧—时间映射、像素/世界坐标转换、派生数据和 stale 标记。 | `Timeline.frame_to_time()` / `time_to_frame()`；`CalibrationTransform`；`DerivedData`；被 session、kinematics 和 chart 输入使用。 | `tests/test_timeline.py`、`tests/test_calibration.py`、`tests/test_kinematics.py`、ADR-0008/0009。 | Phase 6 物理量从现有坐标与派生数据管线进入。 |
| `domain/kinematics.py` | 稠密帧网格、NaN 分段、Savitzky–Golay 平滑、微分和单位计算。 | `smooth_savgol()`、`differentiate_savgol()`、`segment_by_nan()`、`derive_unit()`；被 `kinematics_job` 和 session 使用。 | `tests/test_kinematics.py`、`tests/test_kinematics_session.py`、ADR-0008。 | 现有基础运动学的输入、边界和 NaN 语义在此处集中。 |
| `domain/tracking_run.py` | 训练/推理 run 的身份、状态、配置、产物引用和 `extra_fields`。 | `TrackingRun`；`create_tracking_run()`、`mark_run_running/completed/failed/cancelled()`；被任务、serializer、history 使用。 | `tests/test_tracking_run.py`、`tests/test_project_repository.py`、`docs/spec/project-format.md`。 | 训练、推理、review、validation 和 activation 的 lineage 通过 run 关联。 |
| `application/project_session.py` | 活动 Project 的事务边界、代际/dirty、undo/redo、持久化协调、观测导入、validation 和 activation。 | `ProjectSession.start/load/save/detached()`；`mark_point()`、`import_engine_points()`；`accept/skip/correct_suggested_frame()`；`activate_infer_run()`、`replace_active_infer_run()`、`clear_active_ai_observations()`；`compute_kinematics()`。 | `tests/test_project_session.py`、`test_project_operations.py`、`test_result_activation.py`、`test_suggested_frame_review.py`、`docs/spec/phase5-requirements.md`。 | Phase 5 多个事务通过该模块协调，worker 结果和 GUI 操作都在此处汇合。 |
| `application/tracking_job.py` | 统一 tracking / frame-selection runner、不可变 request、worker 结果读取和 candidate。 | `TrackingRequest`、`TrackingCandidate`、`prepare_tracking_request()`、`TrackingJobRunner.start()`、`FrameSelectionRunner.start()`。 | `tests/test_tracking_job.py`、`tests/test_frame_selection.py`、`tests/gui/test_frame_selection_actions.py`。 | 5.0 后训练、推理和建议帧任务共享生命周期入口。 |
| `application/training_job.py` | 训练 request、manual 导出、fixed split、restart/resume 参数、iteration metadata。 | `prepare_training()`；`TrainingRequest` / `TrainingResult` 等；由 tracking worker 进入，使用 `EngineAdapter`。 | `tests/test_training_job.py`、`tests/test_training_session.py`、`tests/test_dlc_training.py`、`tests/gui/test_training_advisor_actions.py`。 | fixed validation、resume snapshot、per-run working directory 和 training lineage 在此连接。 |
| `application/inference_job.py` | 推理 request、模型/视频/配置身份校验、结果交换文件和 raw prediction 导入。 | `prepare_inference()`、`read_inference_result()`、`read_observation_exchange()`。 | `tests/test_inference_job.py`、`tests/test_inference_session.py`、`tests/test_dlc_inference.py`。 | completed infer 结果先作为 candidate，不直接成为 active projection。 |
| `application/difficult_frames.py`, `difficult_frame_job.py` | 原始预测的四信号评分、候选池、时间去重/多样性和后台挖掘。 | `mine_difficult_frames()`；`DifficultFrameMiningRequest/Result`；`DifficultFrameRunner` / worker。 | `tests/test_difficult_frames.py`、`tests/gui/test_suggested_frame_review_reliability.py`、Phase 5.2 review、Phase 5.6 review。 | 真实 AI_test2 记录了模型饱和时 pool 为空和“未发现困难帧”的路径。 |
| `application/suggested_frame_review.py` | Suggested frame review 的 Qt-free 值对象、保存格式、候选 disposition 和队列控制器。 | `ReviewCandidate`、`ReviewRecord`、`ActiveReviewBatch`、`SuggestedFrameReviewState`、`ReviewQueueController`；`accept/skip/correct` 由 session 执行。 | `tests/test_suggested_frame_review.py`、`tests/gui/test_suggested_frame_review_actions.py`。 | 同一 infer run 的候选状态、prediction provenance、scoped Undo/Redo 由此保存和读取。 |
| `application/refinement_history.py` | validation series、activation history、iteration metadata、prediction summary 的序列化和一致性检查。 | `ValidationSeries`、`ActivationRecord`、`RefinementState`、`RefinementIterationInfo`；`attach/extract/serialize/deserialize_*()`。 | `tests/test_refinement_history.py`、`tests/test_result_activation.py`、ADR-0014。 | Track/TrackingRun 的 `extra_fields` 与原始 JSON 顶层合并约定在这里有读写入口。 |
| `application/training_advisor.py` | 规则型、无 IO 的训练动作建议。 | `RoundMetrics`、`AdvisorInput`、`AdvisorRecommendation`、`recommend_training_action()`。 | `tests/test_training_advisor.py`、`tests/gui/test_training_advisor_actions.py`、ADR-0015。 | Advisor 的内部 action 名称、证据行和 UI Apply 入口在此分界。 |
| `application/kinematics_job.py`, `chart_data.py` | 后台运动学计算、结果身份和图表数据适配。 | `KinematicsJob`、`analysis_inputs()`、`run_kinematics_job()`、`validated_derived()`；`build_chart_data()`。 | `tests/test_kinematics_job.py`、`tests/test_chart_data.py`、`tests/gui/test_charts.py`、ADR-0009/0010。 | 图表只消费匹配的输入/代际；当前 PNG 快照和科学导出边界在此对接。 |
| `infrastructure/project_repository.py`, `project_serializer.py` | project.json schema、load/save/save-as、路径解析、原子写入和 backup；Track/Run 序列化。 | `ProjectRepository.create/load/save/save_as()`；`project_to_payload()` / `project_from_payload()`。 | `tests/test_project_repository.py`、`test_project_workflow.py`、`test_video_session.py`、ADR-0003/0004。 | save/reopen、schema v1、外部视频 locator、extra_fields 和 artifact 引用在此实现。 |
| `infrastructure/engine_adapter.py`, `dlc_adapter.py`, `dlc_predictions.py` | DLC/PyTorch 的唯一基础设施适配边界、标注导出、训练/推理/评价、raw prediction 严格解析。 | `EngineAdapter` Protocol；`DLCAdapter.create_project/export_annotations/train/infer/evaluate/suggest_frames/read_raw_predictions()`；`read_raw_predictions()` / `parse_predictions()`。 | `tests/test_dlc_adapter.py`、`test_dlc_predictions.py`、`test_dlc_training.py`、`test_dlc_inference.py`、ADR-0011。 | DLC 文件格式、confidence/missing 行为和 per-run 产物身份由此进入 application。 |
| `infrastructure/task_runner.py` | `multiprocessing` spawn 后台进程、消息队列、TaskHandle、cancel/join。 | `BackgroundTaskRunner.start_task()`；`TaskHandle.poll_messages/is_alive/cancel/join()`。 | `tests/test_task_runner.py`、`tests/test_tracking_job.py`、GUI reliability tests、ADR-0011/0012。 | 任务的进程边界、取消、late result 和 shutdown 守卫在此连接。 |
| `infrastructure/opencv_video_reader.py`, `ffprobe_timing.py` | 视频读取、帧解码、FFprobe timing 验证和媒体状态。 | `VideoReader`、`FFprobeTimingProbe` 等；由 video session、frame selection、main window 使用。 | `tests/test_opencv_video_reader.py`、`test_ffprobe_timing.py`、`test_project_media.py`、ADR-0005/0006/0007。 | 时间门禁、文件状态和异步解码路径是跨平台执行入口。 |
| `gui/main_window.py`, `video_view.py` | 主窗口、视频播放/标注/导航、GUI 线程合并异步解码交付。 | `MainWindow.seekFrame/jumpToFrame/startPlayback/closeEvent`；`_DecodeDeliveryBridge` 通过无参 Qt signal 唤醒 GUI 线程 drain queue。 | `tests/gui/test_main_window.py`、`test_playback_ui.py`、`test_decode_delivery_bridge.py`、`test_annotation_ui.py`。 | Windows CI 修复直接涉及该模块的 decoder delivery 和窗口生命周期。 |
| `gui/task_panel.py`, `tracking_actions.py` | AI 任务控件、活动/历史展示、参数采集、启动/取消/激活/validation 的 GUI action。 | `TaskPanel` 的 `trainingParameters/inferenceParameters/setActivity/setRuns/setRefinementInfo`；`TrackingActions.train/infer/cancel/activateRun/replaceRun/clearActivation/manageValidation`；`FrameSelectionActions`。 | `tests/gui/test_task_panel.py`、`test_tracking_actions.py`、`test_tracking_activation_actions.py`、`test_training_advisor_actions.py`。 | 当前 training/inference/mining/activation/advisor 的主要用户入口集中于此。 |
| `gui/suggested_frame_review_actions.py`, `validation_dialog.py`, `chart_actions.py` | Suggested-frame 审核操作、fixed validation 管理、图表请求和结果展示。 | `DifficultFrameReviewActions`；`ManageValidationDialog`；`ChartActions`。 | `tests/gui/test_suggested_frame_review_actions.py`、`test_suggested_frame_review_reliability.py`、`test_chart_request_identity.py`、`test_charts.py`。 | Human Review 反馈涉及候选、Correct 导航、activation、validation 和 chart entry 的组合路径。 |

### 2.2 关键公共接口索引

| 接口 | 位置 | 当前行为入口 |
| --- | --- | --- |
| Project aggregate | `domain/project.py:56` | Project、Video、Track、Calibration、TrackingRun registries。 |
| TrackStore | `domain/track_store.py:67` | manual / engine 写入、effective resolution、run-level clear/replace、manual 删除后的 AI 恢复。 |
| TrackingRun | `domain/tracking_run.py:14` | run identity、status、config、artifact reference、extra fields。 |
| ProjectSession | `application/project_session.py:136` | 活动 session、事务、save/load、derived、review、validation、activation。 |
| TrackingJobRunner | `application/tracking_job.py:365` | 统一 spawn 任务启动入口；`prepare_tracking_request()` 在同文件 `:55`。 |
| Training / inference preparation | `application/training_job.py:34`、`application/inference_job.py:88` | 在 worker 中创建本次 run 的输入和参数快照。 |
| EngineAdapter / DLCAdapter | `infrastructure/engine_adapter.py:19`、`infrastructure/dlc_adapter.py:59` | application 依赖 Protocol，DLC 依赖在 infrastructure。 |
| BackgroundTaskRunner / TaskHandle | `infrastructure/task_runner.py:49,110` | spawn、消息轮询、取消、join 和退出码。 |
| ReviewQueueController | `application/suggested_frame_review.py:438` | current candidate、next/previous、Accept/Skip/Correct/Delete 的 Qt-free 状态操作。 |
| TaskPanel / TrackingActions | `gui/task_panel.py:38`、`gui/tracking_actions.py:69` | 控件、信号、参数、后台动作与结果刷新。 |

## 3. Critical Contracts / Invariants

下表只记录 spec、ADR、实现和测试中已经出现的契约；“Verification status”描述证据覆盖，不对契约做质量评价。

| Contract | Authoritative docs | Relevant implementation | Relevant tests | Verification status |
| --- | --- | --- | --- | --- |
| raw observation 与 derived data 分层；平滑/微分/分析产生 DerivedData，不覆盖原始 TrackPoint。 | [`data-model.md`](../spec/data-model.md)；[`architecture.md`](../architecture.md) §2/§4；ADR-0008/0009 | `domain/track.py`、`track_store.py`、`derived.py`；`ProjectSession.compute_kinematics()` | `tests/test_track_store.py`、`test_kinematics.py`、`test_kinematics_job.py` | `implemented`；`tested`；Phase 3 Human Review 记录了基础图表/运动学。 |
| manual 与 AI observation 的 effective 优先级：同帧 manual wins；AI 仍保留为来源记录，manual 删除可恢复 AI。 | [`data-model.md`](../spec/data-model.md) §TrackStore；ADR-0013/0014 | `TrackStore.resolve_effective_*()`；`ProjectSession.mark_point()`、`delete_active_manual_point()` | `tests/test_track_store.py`、`test_project_session.py`、`test_result_activation.py`、`test_suggested_frame_review.py` | `implemented`；`tested`；5.3/5.4 Human Review 记录了 manual 保留与恢复操作。 |
| prediction 不等于 ground truth；Accept/Skip 不创建 manual，Correct 才提交 manual point，并保留 prediction provenance。 | [`phase5-requirements.md`](../spec/phase5-requirements.md) R2/R3；ADR-0013 | `suggested_frame_review.py`；`ProjectSession.accept/skip/correct_suggested_frame()` | `tests/test_suggested_frame_review.py`、`test_project_session.py`、`tests/gui/test_suggested_frame_review_actions.py` | `implemented`；`tested`；5.3 Human Review 记录通过。 |
| completed infer result 与 active AI projection 分离；推理完成不自动覆盖 Track；Activate/Replace/Clear 需要显式操作。 | [`phase5-requirements.md`](../spec/phase5-requirements.md) R4；ADR-0014 | `ProjectSession.activate_infer_run()`、`replace_active_infer_run()`、`clear_active_ai_observations()`；`TrackingActions` activation methods | `tests/test_result_activation.py`、`tests/gui/test_tracking_activation_actions.py` | `implemented`；`tested`；5.4 Human Review 记录通过。 |
| fixed validation membership 为显式、可追溯的成员快照；train/test indices 互斥传给 DLC；series 修改/删除后有有效性记录。 | [`phase5-requirements.md`](../spec/phase5-requirements.md) R5/R6；ADR-0014 | `refinement_history.py`；`prepare_training()`；DLC training config 的 `trainIndices/testIndices` | `tests/test_refinement_history.py`、`test_result_activation.py`、`test_training_job.py`、`test_dlc_training.py` | `implemented`；`tested`；5.4/5.5 文档含真实 fixed-split smoke 记录。 |
| training / inference lineage 通过 run identity、parent/source infer、validation series、snapshot 和实际 config 追踪。 | ADR-0014/0015；[`project-format.md`](../spec/project-format.md) | `TrackingRun`；`RefinementIterationInfo`；`prepare_training()` / `prepare_inference()` | `tests/test_training_session.py`、`test_inference_session.py`、`test_refinement_history.py`、`test_result_activation.py` | `implemented`；`tested`；5.5 真实 DLC restart/resume smoke 记录了 snapshot 与 parent。 |
| Suggested-frame Accept/Skip/Correct/Delete 的事务与 Undo/Redo 有边界；review state 按 infer run 保存；save 后应用内 undo 不恢复。 | ADR-0013；[`phase5-requirements.md`](../spec/phase5-requirements.md) R3 | `ProjectSession` review methods；`ReviewQueueController`；session undo stack | `tests/test_suggested_frame_review.py`、`test_project_session.py`、`tests/gui/test_suggested_frame_review_reliability.py` | `implemented`；`tested`；5.3 Human Review 记录通过。 |
| worker 使用 request/project/media identity 快照，与 active session 隔离；主进程在 commit 前验证上下文。 | ADR-0011/0012；[`architecture.md`](../architecture.md) §3 | `prepare_tracking_request()`；`TrackingJobRunner`；worker 内 detached session；`ProjectSession.import_engine_points()` | `tests/test_tracking_job.py`、`test_project_session.py`、`test_task_runner.py`、`tests/gui/test_suggested_frame_review_reliability.py` | `implemented`；`tested`；5.3/5.4 reliability tests 覆盖会话切换和交错操作。 |
| cancellation 与 late result 不应提交半批数据；失败/取消后的 GUI task state 会恢复，run 状态会保留。 | ADR-0011/0012；[`phase5-requirements.md`](../spec/phase5-requirements.md) R8 | `BackgroundTaskRunner`、`TaskHandle.cancel()`；`TrackingActions` / `DifficultFrameReviewActions`；session commit guards | `tests/test_task_runner.py`、`test_tracking_job.py`、`tests/gui/test_tracking_actions.py`、`test_suggested_frame_review_reliability.py` | `implemented`；`tested`；5.1–5.3 review records 有取消/迟到结果证据。 |
| 时间语义：frame 0 起算；`frame_to_time = frame / fps`；`time_to_frame` 使用约定舍入；working zone 不重置时间基准；缺帧用稀疏/NaN 语义处理。 | [`data-model.md`](../spec/data-model.md) 时间语义；ADR-0006/0007 | `domain/timeline.py`；`application/video_timing.py`；`ffprobe_timing.py` | `tests/test_timeline.py`、`test_timing_approximation.py`、`test_ffprobe_timing.py`、`test_project_media.py` | `implemented`；`tested`；real-world video timing gate 有文档记录。 |
| 坐标空间与单位：原始像素使用 y-down；world 使用 y-up；screen 坐标不持久化；标定转换为纯函数；无 active calibration 时不生成 calibrated world。 | [`data-model.md`](../spec/data-model.md) 坐标；ADR-0008 | `domain/calibration.py`；`kinematics.py`；GUI 只提交视频/像素点击 | `tests/test_calibration.py`、`test_kinematics.py`、`tests/gui/test_calibration_ui.py` | `implemented`；`tested`；Phase 3 Human Review 记录通过。 |
| calibration、FPS 或 raw observation 变化会使相关 derived stale；图表/测量按输入和 generation 匹配后才合并。 | ADR-0008/0009；[`data-model.md`](../spec/data-model.md) | `DerivedData.mark_stale()`；`ProjectSession` calibration/observation methods；`kinematics_job`、`chart_data` | `tests/test_project_session.py`、`test_kinematics_job.py`、`test_chart_data.py`、`tests/gui/test_chart_request_identity.py` | `implemented`；`tested`；图表输入身份测试存在。 |
| save/reopen round-trip 使用 schema v1 manifest、atomic write/backup、外部视频 locator；load 时无对应进程的 pending/running run 标记 failed。 | ADR-0003/0004/0012；[`project-format.md`](../spec/project-format.md) | `ProjectRepository`、`project_serializer.py`；`ProjectSession.save/load()` | `tests/test_project_repository.py`、`test_project_workflow.py`、`test_video_session.py`、`test_tracking_job.py` | `implemented`；`tested`；5.3/5.4 Human Review 记录保存重开路径。 |
| AI 状态变化要求用户显式动作：训练、推理、审核、激活/替换/清除、validation freeze 均由 GUI action 触发；Advisor 只给建议，不自动启动无限训练。 | [`phase5-requirements.md`](../spec/phase5-requirements.md) R4/R6/R7；ADR-0015 | `TrackingActions`、`DifficultFrameReviewActions`、`ManageValidationDialog`、`training_advisor.py` | `tests/gui/test_tracking_actions.py`、`test_tracking_activation_actions.py`、`test_training_advisor_actions.py`、`test_suggested_frame_review_actions.py` | `implemented`；`tested`；5.5 Human Review 记录通过。 |
| DLC training workspace 按 run fresh 创建；artifact 引用绑定 run，并使用文档规定的文件状态检查。 | ADR-0012；5.6 Slice 0 decision B/C；[`phase-5.6-review.md`](phase-5.6-review.md) §1 | `prepare_training()` 的 `working_dir`；`data/engines/<run_id>`；inference prediction file info 校验 | `tests/test_training_job.py`、`test_dlc_training.py`、`test_result_activation.py`、`test_inference_job.py` | `implemented`；`tested`；5.5 real DLC smoke / 5.6 self-check 有记录；指纹策略是文档化的 size-only 选择。 |

## 4. Phase 1–5 Engineering History

以下是历史记录中实际出现过的问题类别和入口。`Closed`、`Accepted`、`Deferred` 等状态均为原 Review/ADR 的记录，不表示本报告重新判断。

| 类别 | 历史 finding / 事实 | 处置记录与入口 |
| --- | --- | --- |
| persistence / session commit | Phase 4 review F1：删除带 TrackingRun 的 Track 曾有静默失败路径；F2：AI 结果曾无法清除/替换；Phase 5.3/5.4 增加事务和回归矩阵。 | `[Historical finding]` [`phase4-architecture-reliability-review.md`](phase4-architecture-reliability-review.md) F1/F2；[`phase-5.3-review.md`](phase-5.3-review.md) D/G；[`phase-5.4-review.md`](phase-5.4-review.md)。当前入口：`ProjectSession`、`TrackStore`、`test_result_activation.py`。 |
| 生命周期双轨 | Phase 4 review F3 记录旧 Training/Inference coordinator 与新路径并存；5.0 记录统一为 `TrackingJobRunner` + `BackgroundTaskRunner` + `TrackingActions`。 | `[Historical finding]` [`phase4-architecture-reliability-review.md`](phase4-architecture-reliability-review.md) F3；[`phase-5.0-review.md`](phase-5.0-review.md)；merge `5569e93`。 |
| stale / late background result | Phase 4 review F12/F13、Phase 5.1 F2/F3/F4、Phase 5.3 G-02/G-07/C-03 记录了取消、窗口关闭、会话切换、late result、shutdown 和 undo 边界。 | `[Historical finding]` [`phase-5.1-review.md`](phase-5.1-review.md)、[`phase-5.3-review.md`](phase-5.3-review.md)；测试入口 `test_task_runner.py`、`test_tracking_job.py`、`test_suggested_frame_review_reliability.py`。 |
| artifact identity | Phase 4 review F6/F7/F8、5.2 R1/R2、5.4 post-merge records 记录了标注/视频/产物身份、raw prediction 保留和文件状态校验。 | `[Historical finding]` [`phase4-architecture-reliability-review.md`](phase4-architecture-reliability-review.md)、[`phase-5.2-review.md`](phase-5.2-review.md)、[`phase-5.4-review.md`](phase-5.4-review.md)；ADR-0012；`ec4ae0c`。 |
| Undo/Redo 事务 | Phase 4 review F13 将 save 清空 undo 作为记录的接受行为；5.3/5.4 review 增加 scoped undo、review 操作边界和 activation 事务测试。 | `[Historical finding]` [`phase4-architecture-reliability-review.md`](phase4-architecture-reliability-review.md) F13；[`phase-5.3-review.md`](phase-5.3-review.md)、[`phase-5.4-review.md`](phase-5.4-review.md)；`tests/test_project_session.py`。 |
| AI result activation | Phase 4 review F2 是 Phase 5.4 的来源之一；5.4 初始 review 和 post-merge review 记录了 candidate/active、跨 Track、空状态、旧 run 和 GUI recovery 入口。 | `[Historical finding]` [`phase4-architecture-reliability-review.md`](phase4-architecture-reliability-review.md) F2；[`phase-5.4-review.md`](phase-5.4-review.md)；ADR-0014；`test_result_activation.py`。 |
| validation split / lineage | 5.2/5.4 review 记录显式 train/test split、series shape、empty split、duplicate frame、iteration metadata 和 validation diagnostics；5.6 F5 记录同一冻结集被多轮模式选择使用的事实。 | `[Historical finding]` [`phase-5.2-review.md`](phase-5.2-review.md)、[`phase-5.4-review.md`](phase-5.4-review.md)、[`phase-5.6-review.md`](phase-5.6-review.md) F5；ADR-0014；`test_refinement_history.py`、`test_training_job.py`。 |
| DLC per-run workspace | 5.6 Slice 0 B 记录原目录复用和 shuffle 编号问题，之后 `prepare_training` 要求 fresh per-run `working_dir`；5.5 真实 smoke 记录 restart/resume 的 snapshot 路径。 | `[Historical finding]` [`phase-5.6-review.md`](phase-5.6-review.md) §1；`ec4ae0c`；[`phase-5.5-review.md`](phase-5.5-review.md)；`test_training_job.py`。 |
| Windows assumptions | Phase 4/5 多处记录 Windows 真机/CUDA 不由 macOS 或 CI 代替；2026-09-16 main 曾出现 `0xc0000374`，cdb 取证定位到 decode queued Python object 的 GUI 路径，之后以 queue bridge 修复。 | `[Historical finding]` / `[CI evidence]` [`current.md`](../status/current.md) Recently Completed；[`8cd8621`](https://github.com/KYLeonis/ai-physics-tracker/commit/8cd86214517119e1a2480e8c25de9eeb96c156ce)、[`f32fa4c`](https://github.com/KYLeonis/ai-physics-tracker/commit/f32fa4c9f97565a31d262bb81b547fd8080a9430)、最新 run `35080085627`。 |
| numerical boundaries | Phase 4.5/5.2 records 包含 round/ceil、missing/NaN、overflow、有效段、timing approximation 和 low-confidence parsing 的边界测试；ADR-0008 固化 SG 处理顺序和 NaN 分段。 | `[Historical finding]` [`phase-4.5-review.md`](phase-4.5-review.md)、[`phase-5.2-review.md`](phase-5.2-review.md)；ADR-0008；`test_timeline.py`、`test_kinematics.py`、`test_ffprobe_timing.py`。 |
| difficult-frame semantics | 5.2 review 建立 raw prediction 全帧输入、uncertainty/jump/residual/prior、多信号 ranking、时间去重、多样性和 benchmark；5.6 F1/F4 记录真实饱和模型时 screening 候选不对应困难帧，随后实现空候选提示。 | `[Historical finding]` `[Benchmark evidence]` [`phase-5.2-review.md`](phase-5.2-review.md)、[`phase-5.6-review.md`](phase-5.6-review.md) F1/F4；commit `228e1ab`。 |
| real-data findings | AI_test2 148 帧单摆四轮结果为 validation RMSE `3.30 / 4.80 / 3.19 / 4.71`；最佳相对基准改善 `-3.3%`，没有达到 AC-9 文档中的 `≥5%` 目标；训练复跑 snapshot sha256 相同。 | `[Benchmark evidence]` [`phase-5-loop-report.md`](../benchmarks/phase-5-loop-report.md)、[`phase-5.6-review.md`](phase-5.6-review.md) §3–§4；用户决定将该缺口如实归档。 |
| Human Review findings | 5.1、5.3、5.4、5.5、5.6 均留下用户实际操作记录；5.6 用户确认饱和模型挖掘时显示 `No difficult frames found`，交互重构范围暂不讨论并留作后续输入。 | `[Human Review evidence]` [`phase-5.1-review.md`](phase-5.1-review.md)、[`phase-5.3-review.md`](phase-5.3-review.md)、[`phase-5.4-review.md`](phase-5.4-review.md)、[`phase-5.5-review.md`](phase-5.5-review.md)、[`phase-5.6-review.md`](phase-5.6-review.md) §4.1。 |

这些记录用于回答“以前真实出现过哪些问题、应打开哪些证据入口”。本节不推断同一位置当前仍存在相同问题。

## 5. Test & Verification Map

### 5.1 按能力分类

| 能力 | 当前证据入口 | 状态区分 |
| --- | --- | --- |
| domain unit tests | `tests/test_project.py`、`test_track_store.py`、`test_timeline.py`、`test_calibration.py`、`test_tracking_run.py`、`test_derived` 相关 session 测试。 | `implemented`、`tested`；本次 macOS 全量 704 passed。 |
| persistence / session | `test_project_repository.py`、`test_project_workflow.py`、`test_project_operations.py`、`test_project_session.py`、`test_video_session.py`、`test_project_media.py`。 | `implemented`、`tested`；save/load、atomic write、locator、dirty/undo 有测试。 |
| numerical / scientific | `test_kinematics.py`、`test_kinematics_job.py`、`test_kinematics_session.py`、`test_chart_data.py`、`test_chart_request_identity.py`、`test_timing_approximation.py`、`test_ffprobe_timing.py`。 | `implemented`、`tested`；当前覆盖基础 x/y/v/a、SG、NaN、calibration/timing；Phase 6 θ/ω/α/period fitting 不在当前实现地图中。 |
| GUI offscreen | `tests/gui/test_main_window.py`、`test_playback_ui.py`、`test_annotation_ui.py`、`test_task_panel.py`、`test_tracking_actions.py`、`test_tracking_activation_actions.py`、`test_suggested_frame_review_actions.py`、`test_training_advisor_actions.py`、`test_decode_delivery_bridge.py` 等。 | `implemented`、`tested`；workflow 使用 `QT_QPA_PLATFORM=offscreen`。不等同真人体验。 |
| concurrency / lifecycle | `test_task_runner.py`、`test_tracking_job.py`、GUI reliability tests、decode bridge tests；涉及 process cancel、late result、shutdown、session switch、FIFO delivery。 | `implemented`、`tested`；Windows bridge 的 4 项回归在 status 与 CI 中有记录。 |
| real DLC smoke | `scripts/smoke_test_dlc_train.py`、`smoke_test_dlc_infer.py`、`smoke_test_gui_tracking.py`；5.5 Review 记录 restart/resume/fixed split；5.6 loop report 记录 AI_test2 四轮。 | `real-world validated` 为历史 macOS/CPU 及真实项目记录；本次未重跑。Windows CUDA 另列为 deferred/unverified。 |
| real pendulum workflow | Phase 4.4 Human Review 记录从标注到训练/评价/推理/显示/重算/保存重开；Phase 5.6 `experiment/AI_test2` 记录 148 帧 refinement loop。 | `real-world validated` 有历史记录；这不是本次生成 package 的新验证。 |
| difficult-frame benchmark | `docs/benchmarks/phase-5.2-development.csv`、[`phase-5.2-report.md`](../benchmarks/phase-5.2-report.md)、`application/benchmark.py`、`scripts/benchmark_difficult_frames.py`。 | `[Benchmark evidence]` Precision@N `0.800` vs baseline `0.600`；review yield `0.300` vs `0.000`；指标来自 Phase 5.2 归档。 |
| refinement-loop benchmark | [`phase-5-loop-report.md`](../benchmarks/phase-5-loop-report.md)；[`phase-5.6-review.md`](phase-5.6-review.md)。 | `[Benchmark evidence]` 四轮 RMSE 和 snapshot 复现性均有归档；AC-9 的 ≥5% 改善未达成，按用户决定保留缺口。 |
| Human Review | 5.1、5.3、5.4、5.5、5.6 Review Record 的 HR 小节；交互体验另见 [`interaction-experience.md`](../notes/interaction-experience.md)。 | `[Human Review evidence]` 已有多次用户确认；不替代自动测试，也不代表本 package 本身经过新的 UI HR。 |
| macOS CI | 最新 run `35080085627`，`macos-latest` Python 3.11：`702 passed, 2 skipped`。 | `[CI evidence]` 当前 latest main 通过。 |
| Windows CI | 最新 run `35080085627`，`windows-latest` Python 3.11：`702 passed, 2 skipped`；前一失败 run 有 cdb 诊断和 queue bridge 修复记录。 | `[CI evidence]` 当前 latest main 通过；不等同 Windows 真实机器/CUDA。 |

### 5.2 仍未真实验证或本次未重跑的事项

- Windows 真实机器上的 GUI、MP4/H.264 全流程和 CUDA/PyTorch GPU：`deferred` 到 Phase 9 前的专门验收节点；GitHub Actions Windows 通过不等同该验证。[`roadmap.md`](../roadmap.md) Phase 2/4、[`current.md`](../status/current.md) §Current Decisions。
- Windows CUDA 版 DLC 训练/推理：`[Not currently verified]`。
- packaged executable、安装包、Windows 发布链：Phase 9 交付物，当前 `packaging/` 只有 README。[`roadmap.md`](../roadmap.md) §Phase 9、[`packaging/README.md`](../../packaging/README.md)。
- Phase 6 的 θ/ω/α、phase space、周期/模型拟合、多目标和误差分析：roadmap 中为未开始交付物；当前测试没有这些新物理量的实现证据。[`roadmap.md`](../roadmap.md) §Phase 6。
- Phase 8 CSV/Excel、Matplotlib 科学图、跟踪后视频导出和完整归档：明确延期；ADR-0010 只把当前 PNG 作为 Qt 显示快照，不能当作科学数据导出。
- 本 package 生成期间未重新运行真实 DLC、未重新走用户 Human Review、未重新运行 Windows 真实机/CUDA；对应证据均为历史记录或文档记录。
- `docs/status/current.md` 记录的原 Windows cdb 取证细节可供打开；本报告没有重新捕获原始 cdb 调试日志，当前状态判断采用最新 main CI 结果和已合并的取证文档。

## 6. Code Hotspots / Inspection Seeds

以下是只读统计和调用事实，作为 Reviewer 的打开顺序入口，不是问题判定。

### 6.1 当前核心模块行数

| 文件 | 当前行数 | 导航事实 |
| --- | ---: | --- |
| `src/ai_physics_tracker/application/project_session.py` | 1901 | 集中提供 ProjectSession 生命周期、事务、review、validation、activation、derived API。 |
| `src/ai_physics_tracker/gui/main_window.py` | 1364 | 视频、标注、播放、窗口关闭、异步 decode delivery 和快捷操作入口。 |
| `src/ai_physics_tracker/infrastructure/dlc_adapter.py` | 1060 | DLC project、annotation export、train/evaluate/infer、frame suggestion 和 raw prediction 适配。 |
| `src/ai_physics_tracker/gui/task_panel.py` | 1052 | AI 任务控件、运行状态、history、review、activation、validation/advisor 展示。 |
| `src/ai_physics_tracker/gui/tracking_actions.py` | 1022 | Tracking、training/inference actions、任务轮询/取消、activation 和 validation action。 |
| `src/ai_physics_tracker/infrastructure/project_serializer.py` | 698 | Project/Track/Run manifest payload 和 extra_fields 序列化。 |
| `src/ai_physics_tracker/application/refinement_history.py` | 559 | Validation/activation/iteration/prediction summary contract。 |
| `src/ai_physics_tracker/application/difficult_frames.py` | 484 | 纯策略评分、候选池、去重、多样性和结果。 |
| `src/ai_physics_tracker/application/suggested_frame_review.py` | 616 | review contract、状态序列化、队列 controller。 |
| `src/ai_physics_tracker/infrastructure/task_runner.py` | 193 | 后台进程和 TaskHandle 生命周期。 |

### 6.2 测试密集区域

| 测试文件 | 当前行数 | 覆盖入口 |
| --- | ---: | --- |
| `tests/gui/test_suggested_frame_review_actions.py` | 1018 | review GUI、快捷键、Accept/Skip/Correct/Delete、状态和错误恢复。 |
| `tests/test_difficult_frames.py` | 961 | mining signals、排序、去重、多样性、空池和候选状态。 |
| `tests/test_project_session.py` | 831 | session、观测、事务、derived、review、validation/activation。 |
| `tests/test_project_repository.py` | 688 | persistence、schema、round-trip、artifact/path。 |
| `tests/test_frame_selection.py` | 646 | representative frame selection request/worker/adapter。 |
| `tests/test_ffprobe_timing.py` | 539 | media timing probe 和边界。 |
| `tests/gui/test_suggested_frame_review_reliability.py` | 495 | save/reopen、交错 undo、cancel/late result、失败恢复。 |
| `tests/test_tracking_job.py` | 492 | request、runner、worker、identity、cancel 和结果。 |
| `tests/test_result_activation.py` | 501 | candidate/active、replace/clear、validation、history。 |
| `tests/test_refinement_history.py` | 429 | fixed series、activation/iteration serialization。 |

### 6.3 跨层和高频调用入口

- `ProjectSession` 同时被 `MainWindow`、`TrackingActions`、`ProjectActions`、`TimingActions`、chart/kinematics actions 使用；Phase 5 review/activation/validation 事务也由它协调。
- `TrackingJobRunner` 被 training、inference、frame selection 和 GUI action 使用；`BackgroundTaskRunner` 为底层 process/handle 入口。
- `EngineAdapter` Protocol 在 application/infrastructure 之间传递公共值对象；DLC/Qt/OpenCV 的层边界由 `tests/test_layer_boundaries.py` 的 AST 检查覆盖。
- `TaskPanel` 与 `TrackingActions` 共同承载 training、inference、mining、activation、validation、Advisor 入口；`DifficultFrameReviewActions` 另行承载逐帧审核。
- `refinement_history.py`、`project_serializer.py`、`TrackingRun.extra_fields` 共同承载 Phase 5 的 history/validation/activation/review 元数据。
- `domain/kinematics.py` → `application/kinematics_job.py` → `application/chart_data.py` → `gui/chart_actions.py/chart_panel.py` 是当前基础物理分析和图表链路。

## 7. Known Deferred / Accepted / Unverified Items

### 7.1 已明确延期

| 项目 | 当前记录 | 入口 |
| --- | --- | --- |
| Windows 真实机 / CUDA | 延期到 Phase 9 打包前专门节点。 | `[Documented decision]` ADR-0012；[`current.md`](../status/current.md) §Current Decisions；[`roadmap.md`](../roadmap.md) Phase 4 |
| Phase 6 高级物理分析 | θ/ω/α、相图、周期/拟合、误差分析列为 Phase 6 deliverables。 | `[Documented decision]` [`roadmap.md`](../roadmap.md) §Phase 6 |
| Model Library | 模型保存、版本、复用列为 Phase 7。 | `[Documented decision]` [`roadmap.md`](../roadmap.md) §Phase 7 |
| CSV/Excel/科学图/视频导出 | 列为 Phase 8；当前 PNG 快照边界由 ADR-0010 保留。 | `[Documented decision]` ADR-0010；[`roadmap.md`](../roadmap.md) §Phase 8 |
| 打包发布 | Windows installer、PyInstaller/Nuitka、CUDA runtime 策略列为 Phase 9。 | `[Documented decision]` [`architecture.md`](../architecture.md) §6、[`roadmap.md`](../roadmap.md) §Phase 9 |
| 多目标、多 bodypart、多相机/3D | 当前单 bodypart 先行；扩展能力列在 Phase 10 或后续。 | `[Documented decision]` ADR-0011、ADR-0015、[`roadmap.md`](../roadmap.md) §Phase 10 |

### 7.2 已明确接受或按记录保留

- ADR-0012：AI artifact identity 使用轻量文件状态；5.6 Slice 0 C 记录用户选择 size-only 指纹检查。[`Documented decision]`
- Phase 4 review F7：反复 full hash 的事项记录为 accepted/later；当前实现不在每次打开时重复全文件 hash。[`Historical finding]`
- ADR-0011/0012：训练/推理使用 spawn 子进程；异常退出后的恢复由 load 状态路径处理，Windows/CUDA 不因该架构记录而被视为已验证。[`Documented decision]`
- Phase 4 review F13 / ADR-0013：save 会清除应用内 undo 历史；save 后的 review undo 不通过应用内历史恢复。[`Historical finding]` / `[Documented decision]`
- Phase 5.3/5.4 记录的 non-active validation series deletion/accumulation、legacy refinement state keys、某些旧 helper/import 形态按 review 记录保留为后续或兼容范围。[`Historical finding]`
- 5.5 review 记录当前 single-bodypart/per-run same-structure 的 resume 限制，multi-bodypart 扩展列入更后阶段。[`Historical finding]`

### 7.3 Phase 5 已归档但没有达到预期指标的实验结果

`experiment/AI_test2` 的固定 11 帧 series `f13d5bbd` 和四轮训练记录如下：

| iteration / train run | mode | train labels | validation RMSE | 相对基准 |
| --- | --- | ---: | ---: | ---: |
| iter1 `f8d5fe67` | resume 25 | 19 | 3.30 | 基准 |
| iter2 `e976e5dc` | resume 25 | 29 | 4.80 | +45.5% |
| iter3 `18d1f638` | restart 50 | 29 | 3.19 | −3.3% |
| iter4 `b80fbd68` | restart 50 | 39 | 4.71 | +42.7% |

归档还记录：iter3 推理 `cffbed09` 在 148/148 帧 confidence ≥ 0.915；四轮同 series 中最高改善为 −3.3%；独立 headless 复跑 run `d5792750` 与 iter4 产出相同 snapshot sha256。用户决定不追加实验、不重定义 AC-9，将“≥5% 可复现改善”作为明示缺口保留。[`Benchmark evidence`] [`phase-5-loop-report.md`](../benchmarks/phase-5-loop-report.md)、[`phase-5.6-review.md`](phase-5.6-review.md) §4。

## 8. Interaction Evidence

本节只描述当前用户界面、当前必须操作的选择、已经暴露的内部概念和用户实际报告；不提出新 UI 方案。

### 8.1 当前 workflow 与用户可见入口

| 当前场景 | 用户当前必须看到/选择的内容 | 代码入口 |
| --- | --- | --- |
| 项目 / Track 上下文 | 当前 video、Track、frame、标注模式、活动任务和错误/取消状态。 | `gui/main_window.py`、`gui/video_view.py`、`gui/task_panel.py`。 |
| 建议代表帧 | `Frames to suggest`、`K-means/Uniform`、结果帧列表；用户可双击跳转，但列表本身不创建 TrackPoint。 | `TaskPanel` suggest controls；`FrameSelectionActions`；`application/tracking_job.py`。 |
| Training | Track/上下文、`Restart/Resume`、本轮 epochs、batch size、device、Advisor summary/Apply。 | `TaskPanel.trainingParameters()`；`TrackingActions.train()`；`prepare_training()`。 |
| Inference | 可用 training run/model、minimum confidence、任务状态和结果完成状态。 | `TaskPanel.inferenceParameters()`；`TrackingActions.infer()`；`prepare_inference()`。 |
| Difficult-frame mining | 选择 completed infer run、Top N、Min Gap、进度/取消/失败状态。 | `TaskPanel` mining controls；`DifficultFrameReviewActions`；`mine_difficult_frames()`。 |
| Suggested-frame review | 当前候选帧、AI prediction marker、reason label、Accept / Skip / Correct / Delete、上一帧/下一帧和完成统计。 | `suggested_frame_review.py`、`suggested_frame_review_actions.py`。 |
| Result activation | 选择 run，执行 Activate / Replace / Clear，并看到 Active AI、Candidate、validation/history 相关状态。 | `TrackingActions.activateRun/replaceRun/clearActivation()`；`ProjectSession` activation methods；`TaskPanel` activation controls。 |
| Validation | 打开 Manage Validation，选择帧、freeze & activate series；看到 series 名称、成员和有效性。 | `gui/validation_dialog.py`；`ProjectSession.create_validation_series()` / `set_active_validation_series()`。 |
| Advisor | 当前状态、规则建议、内部 action（例如 resume、label more、stop and compare）和 Apply 入口。 | `application/training_advisor.py`；`TaskPanel.setAdvisorSummary()`；`tests/gui/test_training_advisor_actions.py`。 |
| Charts | 从当前分析入口进入 x/y/v/a 图表，显示输入/状态/时间联动；当前 PNG 是显示快照。 | `chart_actions.py`、`chart_panel.py`、`chart_data.py`、ADR-0009/0010。 |

### 8.2 当前直接暴露的内部技术概念

当前界面和状态展示中出现或需要用户理解的词包括：`run id`、training run、infer run、Candidate、Active AI、Activate/Replace/Clear、validation series、fixed validation、`Restart/Resume`、snapshot、epochs、batch size、device、minimum confidence、Top N、Min Gap、reason key（`screening`、`low_confidence`、`jump_outlier`、`residual_outlier`、`prior_correction_neighborhood`）、coverage、prediction、manual、superseded、Advisor action。

这些词的来源分别位于 `TaskPanel` 控件、`TrackingActions` 的状态/信号、`TrackingRun`、`RefinementState`、`ReviewCandidate` 和 `training_advisor.py`；它们不是本报告新增的命名。

### 8.3 当前 Human Review 记录的用户行为与困惑

- 5.1：用户确认建议帧列表、双击跳转、不自动打标等行为。[`Human Review evidence`] [`phase-5.1-review.md`](phase-5.1-review.md)。
- 5.3：用户确认困难帧挖掘发起、候选浏览、A/S/C/Delete、一次性 Correct、保存重开和后台互斥。[`Human Review evidence`] [`phase-5.3-review.md`](phase-5.3-review.md)。
- 5.4：用户确认推理候选隔离、显式激活、原子替换/清除、manual 优先、固定 validation、Undo/Redo。[`Human Review evidence`] [`phase-5.4-review.md`](phase-5.4-review.md)。
- 5.5：用户确认 Advisor/retraining 相关真实路径和 Human Review；记录还包含 mode/source 信息补充。[`Human Review evidence`] [`phase-5.5-review.md`](phase-5.5-review.md)。
- 5.6：用户在当前激活模型的饱和状态下确认显示 `No difficult frames found`、队列不再用 screening 凑数；交互改进方向和呈现层重构范围暂不讨论，作为后续输入。[`Human Review evidence`] [`phase-5.6-review.md`](phase-5.6-review.md) §4.1。
- `docs/notes/interaction-experience.md` 的用户总结是：即使有 DLC 使用经验，完整 training/inference 交互仍让人难以判断当前阶段和下一步；用户希望知道“是否还要继续训练、是否应画图”，而不希望先理解较多内部术语和选择。该文件同时含有一份“改进草案”；草案不是当前实现。[`Human Review evidence`] / `[Documented decision]` [`interaction-experience.md`](../notes/interaction-experience.md)。

## 9. Suggested Inspection Seeds

### 9.1 Engineering Reviewer

#### Persistence / Session

- Files: `application/project_session.py`、`domain/track_store.py`、`domain/project.py`、`infrastructure/project_repository.py`、`infrastructure/project_serializer.py`。
- Classes/functions: `ProjectSession`、`ProjectRepositoryPort`、`TrackStore`、`ProjectSession.save/load/detached/import_engine_points`、`project_to_payload/project_from_payload`。
- Tests: `tests/test_project_session.py`、`test_track_store.py`、`test_project_repository.py`、`test_project_workflow.py`、`test_project_operations.py`、`test_result_activation.py`。
- Docs/reviews: [`data-model.md`](../spec/data-model.md)、[`project-format.md`](../spec/project-format.md)、ADR-0003/0004/0013/0014、[`phase4-architecture-reliability-review.md`](phase4-architecture-reliability-review.md)、[`phase-5.3-review.md`](phase-5.3-review.md)、[`phase-5.4-review.md`](phase-5.4-review.md)。

#### Concurrency / Lifecycle

- Files: `infrastructure/task_runner.py`、`application/tracking_job.py`、`application/difficult_frame_job.py`、`gui/tracking_actions.py`、`gui/suggested_frame_review_actions.py`、`gui/main_window.py`。
- Classes/functions: `BackgroundTaskRunner`、`TaskHandle`、`TrackingJobRunner`、`DifficultFrameReviewActions`、`_DecodeDeliveryBridge`、`MainWindow.closeEvent`、`TrackingActions.cancel/shutdown`。
- Tests: `tests/test_task_runner.py`、`test_tracking_job.py`、`tests/gui/test_tracking_actions.py`、`test_suggested_frame_review_reliability.py`、`test_decode_delivery_bridge.py`。
- Docs/commits: ADR-0011/0012、[`phase-5.1-review.md`](phase-5.1-review.md)、[`phase-5.3-review.md`](phase-5.3-review.md)、[`current.md`](../status/current.md) Windows CI 记录、[`8cd8621`](https://github.com/KYLeonis/ai-physics-tracker/commit/8cd86214517119e1a2480e8c25de9eeb96c156ce)。

#### Scientific semantics

- Files: `domain/timeline.py`、`domain/calibration.py`、`domain/kinematics.py`、`domain/derived.py`、`application/kinematics_job.py`、`application/chart_data.py`。
- Classes/functions: `Timeline`、`CalibrationTransform`、`smooth_savgol`、`differentiate_savgol`、`segment_by_nan`、`run_kinematics_job`、`validated_derived`、`build_chart_data`。
- Tests: `test_timeline.py`、`test_calibration.py`、`test_kinematics.py`、`test_kinematics_job.py`、`test_kinematics_session.py`、`test_chart_data.py`、`test_chart_request_identity.py`、`test_ffprobe_timing.py`。
- Docs/decisions: [`data-model.md`](../spec/data-model.md)、[`phase3-requirements.md`](../spec/phase3-requirements.md)、ADR-0008/0009/0010、[`roadmap.md`](../roadmap.md) §Phase 6。

#### AI lineage / activation

- Files: `domain/tracking_run.py`、`application/training_job.py`、`application/inference_job.py`、`application/refinement_history.py`、`application/suggested_frame_review.py`、`project_session.py`、`infrastructure/dlc_predictions.py`。
- Classes/functions: `TrackingRun`、`prepare_training`、`prepare_inference`、`read_inference_result`、`RefinementState`、`ValidationSeries`、`RefinementIterationInfo`、`ReviewCandidate`、`activate_infer_run/replace_active_infer_run/clear_active_ai_observations`。
- Tests: `test_training_job.py`、`test_inference_job.py`、`test_training_session.py`、`test_inference_session.py`、`test_refinement_history.py`、`test_result_activation.py`、`test_suggested_frame_review.py`、`test_dlc_predictions.py`。
- Docs: ADR-0011/0013/0014/0015、[`phase5-requirements.md`](../spec/phase5-requirements.md)、[`phase-5.5-review.md`](phase-5.5-review.md)、[`phase-5.6-review.md`](phase-5.6-review.md)、[`phase-5-loop-report.md`](../benchmarks/phase-5-loop-report.md)。

#### Tests / CI

- Files: `.github/workflows/tests.yml`、`tests/test_layer_boundaries.py`、`tests/conftest.py`、`tests/gui/conftest.py`。
- Tests: current local `704 passed`; latest main Actions `702 passed, 2 skipped` on each OS。
- Runs: [`35080085627`](https://github.com/KYLeonis/ai-physics-tracker/actions/runs/35080085627)；历史失败 run [`35071803064`](https://github.com/KYLeonis/ai-physics-tracker/actions/runs/35071803064)；合并修复 commit [`f32fa4c`](https://github.com/KYLeonis/ai-physics-tracker/commit/f32fa4c9f97565a31d262bb81b547fd8080a9430)。

#### Phase 6 extension points

- Files: `domain/kinematics.py`、`application/kinematics_job.py`、`application/chart_data.py`、`gui/chart_actions.py`、`gui/chart_panel.py`、`ProjectSession.compute_kinematics()`。
- Docs: [`roadmap.md`](../roadmap.md) §Phase 6、[`phase3-requirements.md`](../spec/phase3-requirements.md) 的延期项、ADR-0008/0009/0010。
- Existing data inputs: `TrackStore.effective_points()` → calibration → derived kinematics → chart data；当前代码和测试索引到基础 x/y/v/a，不索引为 Phase 6 交付物。

### 9.2 Interaction Reviewer

#### Current workflow

- `gui/main_window.py`、`gui/video_view.py`、`gui/task_panel.py`、`gui/tracking_actions.py`。
- [`interaction-experience.md`](../notes/interaction-experience.md) §当前界面、[`architecture.md`](../architecture.md) §3/§4、[`phase5-requirements.md`](../spec/phase5-requirements.md)。
- Tests: `tests/gui/test_main_window.py`、`test_playback_ui.py`、`test_task_panel.py`、`test_tracking_actions.py`。

#### TaskPanel

- `TaskPanel` at `gui/task_panel.py:38`。
- Public state/entry methods: `setContext()`、`setRuns()`、`setActivity()`、`setRunDetails()`、`setRefinementInfo()`、`setSuggestResult()`、`setMineStatus()`、`setReviewBatch()`、`trainingParameters()`、`inferenceParameters()`。
- Tests: `tests/gui/test_task_panel.py`、`test_training_advisor_actions.py`、`test_tracking_activation_actions.py`。

#### Training

- UI controls: Restart/Resume、epochs、batch size、device、Advisor summary/apply。
- Code: `TaskPanel.trainingMode/trainingParameters/setAdvisorSummary`、`TrackingActions.train`、`prepare_training`、`training_advisor.recommend_training_action`。
- Docs/tests: ADR-0015、[`phase-5.5-review.md`](phase-5.5-review.md)、`test_training_job.py`、`test_training_session.py`、`tests/gui/test_training_advisor_actions.py`。

#### Inference / Activation

- UI: training run/model selection、minimum confidence、completed status、Activate/Replace/Clear、Active AI label。
- Code: `TrackingActions.infer/activateRun/replaceRun/clearActivation`、`ProjectSession` activation methods、`read_inference_result`。
- Docs/tests: ADR-0014、[`phase-5.4-review.md`](phase-5.4-review.md)、`test_result_activation.py`、`tests/gui/test_tracking_activation_actions.py`。

#### Suggested frames / Review / Validation

- UI: `Top N`、`Min Gap`、candidate list、reason labels、Accept/Skip/Correct/Delete、next/previous、Manage Validation、freeze & activate series。
- Code: `application/difficult_frames.py`、`application/suggested_frame_review.py`、`gui/suggested_frame_review_actions.py`、`gui/validation_dialog.py`。
- Docs/tests: ADR-0013/0014、[`phase-5.2-review.md`](phase-5.2-review.md)、[`phase-5.3-review.md`](phase-5.3-review.md)、[`phase-5.6-review.md`](phase-5.6-review.md)、`test_difficult_frames.py`、`test_suggested_frame_review.py`、`tests/gui/test_suggested_frame_review_actions.py`、`test_suggested_frame_review_reliability.py`。

#### Advisor

- Code: `application/training_advisor.py`、`TaskPanel.setAdvisorSummary()`、`tests/gui/test_training_advisor_actions.py`。
- Docs: ADR-0015、[`phase-5.5-review.md`](phase-5.5-review.md)、[`interaction-experience.md`](../notes/interaction-experience.md) §Advisor。
- Current exposed terms: action name、coverage、remaining labels、snapshot、resume/restart、additional epochs、batch size。

#### Charts entry

- Code: `gui/chart_actions.py`、`gui/chart_panel.py`、`application/chart_data.py`、`ProjectSession.compute_kinematics()`。
- Docs/tests: ADR-0009/0010、`tests/test_chart_data.py`、`tests/gui/test_chart_request_identity.py`、`test_charts.py`、[`interaction-experience.md`](../notes/interaction-experience.md) §图表入口。

#### Failure / recovery states

- Code: `TaskPanel.setActivity/setMineStatus`、`TrackingActions.cancel/shutdown`、`DifficultFrameReviewActions` error/cancel paths、`MainWindow.closeEvent`、`ProjectSession.load` run recovery。
- Tests: `tests/gui/test_tracking_actions.py`、`test_suggested_frame_review_reliability.py`、`test_decode_delivery_bridge.py`、`test_tracking_job.py`。
- History: Phase 5.1 F1–F4、Phase 5.3 G-02/G-07/C-03、Windows CI diagnostic record in [`current.md`](../status/current.md)。

## 10. Package 自身的可确认性

- 已确认：本文件写入前 `main @ daad086`、open Issues、最新 Actions run、当前本地测试结果和文件统计均重新读取；本地与 Actions 命令输出已记录。
- 已确认：本次只新增本文件，没有修改其他 tracked file。
- 仍需后续 Reviewer 直接打开确认的内容：源代码细节、测试断言的完整语义、历史 Review 中所链接的外部真实项目/`/tmp` 产物，以及用户 Human Review 的原始操作上下文。本文件只提供仓库内索引，不替代这些材料。
- 未发现本报告内无法由仓库/Actions/本次命令确认而被写成当前事实的数据；凡历史记录、延期、未重跑或文档来源不一致，均已分别标注。
