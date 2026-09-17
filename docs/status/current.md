# Current Status

> 项目"现在在哪、下一步做什么"的**唯一权威入口**——不知道该做什么时先读这个文件。
> 每个开发会话结束时由 Agent 更新（规则见 `docs/workflow.md` §11）；人类可随时手写修改，人类改动优先于 Agent 的判断。

- 最后更新：2026-09-17（**Phase 5.7 Human Review Round 1 的 7 项反馈已修复，全量 797；下一步 Human Review Round 2——通过前 5.7 不关闭**）

---

## Phase / Subphase / Slice

| Level | Name | Status |
| --- | --- | --- |
| Current | Phase 5.7 — Interaction Flow Redesign | 🔄 HR1 修复完成（2026-09-17），**待 Human Review Round 2** |
| Phase | Phase 5 — AI-assisted Annotation & Refinement | 🔄 5.0–5.6 完成；5.7 待 HR 后收官 |
| Subphase | 5.0 — Tracking Pipeline Consolidation | ✅ 已完成 (2026-09-02) |
| Subphase | 5.1 — Representative Frame Selection | ✅ 已完成 (2026-09-02, Human Review 通过) |
| Subphase | 5.2 — Difficult Frame Mining | ✅ 已完成 (2026-09-03) |
| Subphase | 5.3 — Suggested Frame Review & Correction | ✅ 已完成 (2026-09-03, Human Review 通过) |
| Subphase | 5.4 — Iteration History & Result Activation | ✅ 已完成 (2026-09-03, HR 通过；复核收口完成) |
| Subphase | 5.5 — Training Advisor & Retraining | ✅ 已完成 (2026-09-04, Human Review 通过) |
| Subphase | 5.6 — Refinement Loop Integration & Acceptance | ✅ 已完成 (2026-09-16, HR 通过；AC-9 明示缺口归档) |
| Subphase | 5.7 — Interaction Flow Redesign | 🔄 实现+R1/R2 CLOSED；HR1 修复完成，待 HR2 |

## Recently Completed

- **Phase 5.7 Human Review Round 1 修复（2026-09-17，分支
  `fix/p5.7-hr1-followup`）**：完成右侧面板 300–400px 自适应、控制栏拆行与单列高级设置、未采用候选的
  独立橙色预览层、Correct 光标跨帧保持、检查卡直接动作与 Finish checking、像素单位
  限制和标定入口、train→infer lineage 判据、关键事务自动保存。同步修复已有审核批次
  被重复挖掘覆盖、Accept/Skip 污染标注 autosave 计数、预览产物边界校验及 autosave
  清空 undo/redo 的隐藏问题。`compileall` 通过；全量 **797 passed**。处置详情见
  [HR1 分析](../notes/phase-5.7-hr1-analysis.md) 与
  [Phase 5.7 Review Record](../reviews/phase-5.7-review.md)。

- **Phase 5.7 — Interaction Flow Redesign（2026-09-17，分支 `feat/p5.7-interaction-redesign`）**：
  - 交付（详见 [phase-5.7-plan](phase-5.7-plan.md) 与 [phase-5.7 review](../reviews/phase-5.7-review.md)）：
    **三个工作区**（实验设置/获取轨迹/分析与图表；MainWindow 工作区栈 + ChartPanel 转分析页主体 +
    视频参照窗重挂父）；**常驻状态头**（项目/视频/目标/范围/保存 + 当前轨迹 vs 预览候选 +
    分析四态 chip + 限制行）；**状态驱动任务卡**（Qt-free
    `application/workflow_projection.py` 投影执行/轨迹/分析三维修量，卡片按 §9 优先级选择主动作；
    原三列表单折叠为"调整本次设置"，历史折叠为"结果与历史"，全部控件/信号兼容）；
    **C1** 固定检查帧预选确认（ADR-0016，确定性规则 + 用户确认才 freeze，失效集重建卡）；
    **C2** 推荐计划显式执行（写表单走既有 train()/infer()，Advisor Apply 语义不变）；
    **候选比较结论**（better/flat/worse/incomparable，P6R-02 资格门控，±5% 档位，永附边界）；
    **[采用此轨迹]**（单次影响确认 + 既有原子事务，history 只 preview）；**分析交接**（来源条 +
    采用与更新两步）；**失败 UX**（`user_messages` 三问文案接线 12 类结论）。
  - 质量：新增/更新测试后全量 **790 passed**；stabilization R1 F1（GUI teardown 模态挂起）
    以会话级模态桩**根治**（三个记录配方 27/55/117 通过）；Independent Review R1（NEEDS-FIX：
    F1 检查绑定/F2 失效集死循环两个 Blocker + 5 Suggestions）→ 全部修复 → R2（仅 N1 导入缺失）
    → 补验 **CLOSED**（按 R2 豁免条款）；ADR-0016 记录 C1/C2。
  - **未关闭**：Human Review 待用户实测（清单见本文件 Next Recommended Action）；
    通过前不宣布 5.7/Phase 5 收官，不开始 Phase 6。

- **Phase 5.7 交互架构设计（2026-09-16，仅研究与设计）**：完成
  [phase-5.7-interaction-redesign.md](../design/phase-5.7-interaction-redesign.md)。建议以
  “实验设置 → 获取轨迹 → 分析与图表”工作区和上下文任务卡替代 AI Tasks 总表；
  明确普通／高级职责、逐状态主动作、失败恢复、可分析条件、科研契约和实施验收。
  收尾已对齐 stabilization 的已关闭事项；没有修改产品代码。下一步先由用户批准设计，
  再由 Sol / implementation Agent 制定 mini-plan 并实现。

- **Pre-Phase 6 Stabilization（2026-09-16，分支 `fix/pre-phase6-stabilization` 已合并 main）**：
  - 依据 [pre-phase6-project-review.md](../reviews/pre-phase6-project-review.md)（P6R-01…04）与
    [pre-phase6-stabilization-plan.md](../status/pre-phase6-stabilization-plan.md) 实施；
    完整审查生命周期见 [pre-phase6-stabilization-review.md](../reviews/pre-phase6-stabilization-review.md)
    （R1 PASS → findings 处置 → R2 **CLOSED**）。
  - **P6R-01（Undo/Redo 事务完整性）**：历史快照携带 run registry；撤销删除的 Track
    时其 run 随快照恢复（active pointer/observations/refinement 引用一致，save/reopen
    一致）；undo 越过快照外登记的 run 依赖改为**原子拒绝**（Project/Store/双栈/registry
    完全不变，GUI 给可见反馈）；`record_tracking_run` 清空 redo；存续 Track 的 run
    生命周期不被 Undo/Redo 回滚。旧契约"undo 后 run 保持删除"为 Phase 4 时代
    （无 refinement state）产物，已按 P6R-01 更新并记录理由。
  - **P6R-02（Resume ancestry × 固定验证集）**：新增纯函数
    `validation_training_exposure`（沿 resume 链累加各代 training_labels 与验证帧求交，
    三态 clean/contaminated/unknown；legacy 无记录/缺失祖先/环路一律 unknown，不默认
    clean）；存在 active series 且资格非 clean 时 Resume 入口**阻止**（消息给出暴露帧
    与出路：restart/换源/停用 series）；`RoundMetrics.comparison_qualification` 显式
    fail-closed 字段，Advisor 同 series 比较要求两轮均 clean，contaminated/unknown
    轮次不再产生 improved/worsened；资格为 compute-on-read，**历史 RMSE/benchmark
    未改写**（AI_test2 的真实历史污染现在会被如实标记为不可独立比较）。
  - **P6R-04（Advisor 输入采集）**：采集器提升为 Qt-free
    `application/advisor_collection.py`；timeline 按所选 Track 的真实 video_id 解析
    （uncovered-zone/plateau 分支恢复工作）；last_train_failed 取"最近一次相关训练"
    状态（OOM 后成功重训不再永久报失败）；新增 collector → AdvisorInput →
    recommendation 全链组合测试。
  - **P6R-03（按条件实施）**：被本 track train run iteration 引用的 validation series
    拒绝物理删除（提示改用停用），未引用 series 删除行为不变；无 schema 变更。
    保存重开后历史 validation 标签仍由 series 第一方快照解析。
  - 验证：新增 29 项测试（undo 完整性 9 + lineage 16 + collector 1 + GUI 1 + advisor
    门控 2），全量 **733 passed**（基线 704），`compileall` 通过，双平台 CI 绿。
  - R1 附带 F1（GUI 测试在人为文件排序下 teardown 模态挂起——**main 上既有隐患**，
    已复现并记录配方，Defer 至 Phase 5.7 测试刷新）。

- **Windows CI 崩溃修复（2026-09-16，`fix/windows-ci-crash` 已合并 main）**：
  - 现象：9 月 16 日起 main 的 Windows job 在 GUI tests teardown 附近
    `0xc0000374`（heap corruption）退出，概率约 3/7 次（同代码分支 CI 绿、main 红，
    非 flaky 可跳过类问题）；macOS 从不触发。
  - 取证：临时 cdb 诊断分支捕获到 first-chance access violation——
    `PyObject_GenericGetAttrWithDict` 对垃圾指针（rdi=0x2）做 incref，发生在主线程
    qtbot 处理 queued `decodeCompleted` 回调时；崩溃点在测试文件间漂移。
  - 根因：decoder worker 线程直接 emit 携带 Python 对象（DecodeDelivery/DecodedFrame）
    的 queued Qt signal；PySide6 6.11 在 Windows 特定调度时序下对 queued 参数对象的
    引用管理产生损坏。GUI 测试进程窗口从不销毁（每文件堆积）+ runner 镜像 9 月更新
    改变时序，使长期潜伏的路径显形（5.6 改动未触碰 playback，只是时序扰动）。
  - 修复（`src/ai_physics_tracker/gui/main_window.py`）：新增 `_DecodeDeliveryBridge`——
    交付对象走 `queue.SimpleQueue`，Qt 信号只发**无参** `pending` 唤醒，GUI 线程 drain 后
    经原有 `frameDelivered/decodeFailed/decodeCompleted` 分发（这些信号现在只在 GUI 线程
    发出）。`AsyncVideoSession` 接口与其余调用方不变。
  - 验证：新增 4 项回归（FIFO drain、并发入队不丢、交付信号仅 GUI 线程、close 后无
    decoder/executor 线程残留的 lifecycle 守卫）；Windows CI 在 cdb 下全量
    **702 passed, 2 skipped** 完整跑通；合并后 main CI 双平台绿
    （[run 35079898823](https://github.com/KYLeonis/ai-physics-tracker/actions/runs/35079898823)）。
  - 诊断分支 `ci/diag-windows-crash` 保留作取证记录（含 cdb workflow），未合并。

- **Phase 5.6 真实闭环执行与验收（2026-09-16）**：
  - Slice 0：批复决策落地——A 核实为 Phase 4 已实现（无需改动）；B 强制 fresh per-run DLC 目录；
    C 激活指纹放宽为 size-only。
  - Slice 1：三类 delta 内化为 Advisor 输入（coverage 仅证据、激活引导指向未激活 run）+ 归档工具。
  - Slice 2：AI_test2 真实闭环四轮（resume+10 / resume / restart / restart+10），同 series 11 帧冻结
    基准 val RMSE = 3.30 / 4.80 / **3.19** / 4.71；**结论：AC-9 的 ≥5% 可复现改善未达成**（最佳 −3.3%），
    按用户决定如实归档为明示缺口；闭环本身（流程/产物/可追溯/激活）完整完成。
  - 根因：F1 screening 补齐把非困难帧推给用户（**已修正**：饱和即返回空并明示"未发现困难帧"）、
    F3 训练确定性（同配置复跑 sha256 相同 → delta 是真实效果）、F4 模型饱和（148/148 帧置信 ≥0.915）、
    F5 基准被反复用于模式选择存在污染风险（用户提出）。
  - 自查（无 subagent，配额所致）：修复 Blocker `is_complete` 属性错误（激活结果后训练必崩）与归档工具
    键错误；空候选端到端探针通过。全回归 **699 passed**。
  - 交互体验：新增 [docs/notes/interaction-experience.md](../notes/interaction-experience.md)，记录用户报告的
    交互混乱问题与改进草案（呈现层重构，待立项）。

- **Phase 5.4 完成状态复核（2026-09-03）**：4 个 Slice、独立 review finding 与 Human Review
  均有完成记录；本地全回归 **652 passed**，`main @ 13f48c2` 与
  `origin/main` 一致，[CI run 33771353773](https://github.com/KYLeonis/ai-physics-tracker/actions/runs/33771353773)
  的 macOS/Windows Python 3.11 均成功。但复核发现 2 项 AC 缺乏充分证据/展示、
  `validation_series` writer 与 ADR-0014 形态不一致、GitHub 实际不存在文档曾引用的 Issue #21，
  且数份收尾状态残留执行前文案。文案与 Issue 事实已纠正；技术缺口列为 5.5 Slice 0 Entry Gate。

- **Phase 5.4 收尾与 Human Review 通过（2026-09-03）**：
  - 经用户真人真机测试，确认推理候选隔离（推理后不自动覆盖）、结果显式激活与原子替换/清除、手工点优先保留与同帧 AI 复原、固定验证集冻结展示与 Undo/Redo 完全符合预期，正式批准通过验收。
  - 分支 `feat/p5.4-result-activation-history` 合并入 `main`，全量 652 项测试全绿，文档同步并推送到 GitHub 远程。

- **Phase 5.4 Slices 1–4 结果激活、迭代历史与固定验证集（2026-09-03）**：
  - **Slice 1 (ADR-0014 与数据契约)**：创建 ADR-0014，建立 `refinement_state_v1`（包含 `ValidationSeries`、`ValidationLabelSnapshot`、`ActivationRecord`、`RefinementIterationInfo` 与 `PredictionSummary`），实现标签一致性校验及 Undo/Redo 隔离。
  - **Slice 2 (Fixed split 与训练冻结)**：`DLCAdapter` 与 `prepare_training` 实现固定测试集划分，向 DLC 传入互斥显式 `trainIndices/testIndices`，杜绝验证集数据泄露；自动同步 DLC 配置的 `TrainingFraction`；冻结上轮/当前 infer 引用与 review 统计。
  - **Slice 3 (Candidate 隔离与激活事务)**：推理完成仅作为 Candidate 登记（`observations_changed=False`）；实现 `activate_infer_run`、`replace_active_infer_run` 与 `clear_active_ai_observations` 原子事务；支持 manual 点优先、同帧 AI superseded 保留与删除 manual 自动复原 AI；完备指纹篡改校验与旧项目兼容。
  - **Slice 4 (GUI 控制与独立 Review 闭环)**：在 `TaskPanel` 与 `TrackingActions` 增加激活/替换/清除/固定验证集管理按钮与确认对话框；完成 2 个并发子智能体审查并彻底闭环修复 9 项 GUI/并发/边界 finding（F-01~F-09 及领域边界 P1~P3）；全量 **652 tests passed**，真实 DLC fixed split smoke 成功通过。

- **Phase 5.3 完成状态复核（2026-09-03）**：10 项 AC 与 4 个 Slice 全部勾选，R1/R2 共
  18 项 finding 已关闭，Human Review 已通过；本地全回归 **631 passed**，`main @ f159410`
  与 `origin/main` 一致，[CI run 33753432647](https://github.com/KYLeonis/ai-physics-tracker/actions/runs/33753432647)
  双平台成功；遗漏的 GitHub Issue #20 已补关闭。
- **Phase 5.3 收尾与 Human Review 通过（2026-09-03）**：
  - 经用户真人真机测试，确认困难帧挖掘发起、候选队列浏览、快捷键 A/S/C/Delete、一次性 Correct 模式、当前帧 manual 点删除、保存重开恢复及后台互斥完全符合预期，用户正式批准通过验收。

- **Phase 5.3 Slice 4 — Reliability Matrix & R2 Review Closure (2026-09-03)**：
  - 构建可靠性与边界测试矩阵（`tests/gui/test_suggested_frame_review_reliability.py`），覆盖保存重开后继续审核、普通打点与审核操作交错 Undo/Redo、后台挖掘取消与迟到结果隔离、挖掘失败清理与按钮恢复、Correct 模式全导航矢量注销、已有 manual 点覆盖与纠偏。
  - 启动 2 个并发子智能体（Test & Spec Reviewer + Domain & Concurrency Reviewer）进行全面只读审查，识别并闭环修复 6 项 Finding（T-01 至 T-03，C-01 至 C-03）：
    - 修复已修正候选 Accept/Skip 按钮未禁用及缺少异常屏障缺陷（T-01）。
    - 修复 Correct 模式校验失败时穿透执行普通 mark_point 缺陷（T-02）。
    - 补齐困难帧挖掘、选帧与模型训练/推理之间的三方互斥及状态提示（C-01）。
    - 修复 seekFrame() 编程式跳帧未取消 active Correct 模式问题（C-02）。
    - 补齐 DifficultFrameReviewActions 的 `_closed` 标志与 shutdown 重置（C-03）。
    - 补齐参数框（Top N, Min Gap）正向传参及重开点坐标精度测试（T-03）。
  - 新增 10 个测试用例，全量测试 **631 passed**。
- **Phase 5.3 Slices 1–3 独立代码审查与健壮性加固（2026-09-03）**：
  - 启动 2 个只读 Reviewer 智能体（Domain & Session Reviewer、GUI & Concurrency Reviewer）并发审查。
  - 识别并彻底修复全部 12 项 finding（5 项领域/会话、7 项 GUI/并发）：
    - 修复 `accept`/`skip` 允许对已修正帧操作导致的 manual point 孤立问题（D-01）。
    - 修复跨 Track 选中 run 激活审核的上下文错乱（G-01）。
    - 修复异步解码在途时删除 manual point 竞态条件（G-02）。
    - 修复时间轴拖动/步进/播放未退出 Correct 模式导致的坐标错位（G-03）。
    - 修复空队列快捷键 `A`/`S` 崩溃隐患及输入框焦点屏蔽（G-04、G-08）。
    - 完善 Accept/Skip 脏状态与自动保存触发，完善取消 Correct 时的标注模式退出。
  - 新增 5 个自动化测试，全量测试 **621 passed**，归档 `docs/reviews/phase-5.3-review.md`。
- **Phase 5.3 Slice 3 — Review/Correct/delete GUI (2026-09-03)**：
  - 实现一次性 Correct 模式交互流：点击 Correct 按钮或按 C 键进入修正模式，画面点击即提交 manual point + 记录 `corrected` 状态 + 自动退出，按 Esc 或切换项干净取消且不产生脏状态。
  - 实现当前帧 manual 点删除交互：仅当当前帧存在 active manual 点时使能删除按钮，删除后恢复原 AI 观测并将对应候选回滚为 pending；支持 Undo/Redo 恢复；明确提示保存后不可恢复。
  - 实现完成统计展示（🎉 Review Complete）、候选状态与 AI 原始预测快照信息联动展示。
  - 增加 5 个 GUI offscreen 测试（`tests/gui/test_suggested_frame_review_actions.py`），验证 AC-2–AC-7；全量回归 **616 passed**。
- **Phase 5.3 Slice 2 — Mining entry + queue controller (2026-09-03)**：
  - 在 `TaskPanel` 与 `DifficultFrameReviewActions` 中实现挖掘发起与审核面板联动，支持 Top N 与 Min Gap 参数配置及中性取消（AC-9，F4）。
  - 实现基于 Task history 的 run 选中与合法性校验（仅限当前 Track 的 completed infer run，AC-1）。
  - 实现同一 infer run 挖掘时自动排除已 Accept/Skip 的帧（AC-8，R2.8），新 run fresh 挖掘。
  - 在挖掘产物中固化 AI 预测快照（x, y, confidence），并提供 `DifficultFrameResult.to_active_batch()`。
  - 实现纯 Python Qt-free 审核队列控制器 `ReviewQueueController` 与 `MainWindow` 快捷键（A/S/C，防输入框冲突）。
  - 顺带关闭 F4（中性取消不带 Failed 前缀）与 F6（算法 ComboBox 采用 `currentData()` 提取）。
  - 增加 10 个测试（`test_difficult_frames.py` 1 个 AC-8 测试 + 预测快照断言，`test_suggested_frame_review.py` 3 个控制器测试，`tests/gui/test_suggested_frame_review_actions.py` 6 个 GUI offscreen 测试），全量 **611 passed**。
- **Phase 5.3 Slice 1 — Review contract + atomic session transactions (2026-09-03)**：
  - 实现 Qt-free 值对象契约 `suggested_frame_review.py`（候选、快照、记录、批次、汇总、序列化）。
  - 在 `ProjectSession` 实现 `accept_suggested_frame`、`skip_suggested_frame`、`correct_suggested_frame`（原子 manual point + superseded AI 观测 + 预测保留）与 `delete_active_manual_point`（恢复原 AI 观测并回滚审核为 pending）。
  - 实现 scoped Undo/Redo，保证审核操作撤销时不回滚无关后台任务状态与跟踪 run。
  - 增加 20 个新单元/集成测试（`test_suggested_frame_review.py` 8 个、`test_project_session.py` 11 个、`test_project_repository.py` 1 个），全量测试 **601 passed**。
- **Windows CI flaky test 修复（2026-09-03，`351ea1b`）**：Windows runner
  无法保证“立即同尺寸重写文件”改变 mtime，导致 fingerprint tamper 测试偶发漏检；测试现改为
  确定性改变文件大小，不改变 ADR-0012 的生产校验策略。定向 60 passed，全回归 **581 passed**。
- **Phase 5.2 — Difficult Frame Mining（代码与基准工具链，2026-09-02，分支 `feat/p5.2-difficult-frames`）**：
  - Slice 1：`RawPrediction` + `read_raw_predictions` 全帧原始预测入口（低置信度/缺测不丢失，整批校验）；`prepare_difficult_frame_request` 绑定 run/产物身份（指纹基线 + run 从属目录校验）
  - Slice 2：`application/difficult_frames.py` 纯策略——四信号（uncertainty/jump/residual/prior）、池内 percentile rank、加权排名、贪心时间去重（ceil 间隔、放宽记录 effective_gap）
  - Slice 3：5.1 K-means 支持显式候选集；`run_difficult_frame_worker` + `DifficultFrameRunner`（取消、原子结果、不碰活动 session）；F3b 改名闭环
  - Slice 4：`application/benchmark.py` + `scripts/benchmark_difficult_frames.py`（emit-audit/score、盲评表、legacy 回填）；真实 2767 帧单摆 run 完成开发集调参与冻结审计集比较
  - 独立审查：R1–R4 四轮 review 全部修复闭环，见 [phase-5.2-review.md](../reviews/phase-5.2-review.md)
  - 最终全回归：**581 passed**
- **5.1 运行时审查补漏**（✅ 2026-09-02，Issue [#18](https://github.com/KYLeonis/ai-physics-tracker/issues/18)）：独立全面审查（报告见 [phase-5.0-5.1-runtime-review.md](../reviews/phase-5.0-5.1-runtime-review.md)）后修复 4 项——选帧对打不开/损坏视频显式报错（F1）、选帧运行中禁止启动训练/推理（F2）、pyproject 显式声明 scikit-learn（F3a）、`detect_device` 异常写法（F5）；F3b/F4/F6 作为顺带项（F3b 已随 5.2 Slice 3 完成，F4/F6 随 5.3）。
- **Phase 5.1 — Representative Frame Selection**（✅ 2026-09-02，开发、审查、性能优化与 Human Review 全闭环）：
  - S1：`FrameSelectionRequest` + `FrameSelectionResult` Qt-free 数据类（`application/tracking_types.py`）
  - S2：`EngineAdapter` Protocol 新增 `suggest_frames`；`DLCAdapter`（uniform / K-means + scipy fallback，流式 Grab 解码优化）；`MockEngineAdapter` 确定性实现
  - S3：`FrameSelectionRunner` + `prepare_frame_selection_request`（自适应降采样步长，保持 ~100 帧黄金候选池）+ `run_frame_selection_worker` + `read_frame_selection_result`（`application/tracking_job.py`）
  - S4：`TaskPanel` 新增建议帧控件组；`FrameSelectionActions`（实时进度回传透传、会话切换/窗口关闭取消守护）；`MainWindow.jumpToFrame`（跳帧后保持标注模式）
  - 独立审查：3 个并发子智能体审查识别 7 项 Finding 全部修复闭环（见 [phase-5.1-review.md](../reviews/phase-5.1-review.md)）
  - 性能优化：2767 帧 1080p 视频选帧耗时从 7 分钟降至 9 秒（提升约 46 倍），进度实时可见
  - 真机验收：Human Review 确认建议帧列表显示、双击跳转、不自动打标等交互均符合预期
  - 全回归：**495 passed in 38.52s**（新增 46 单元测试 + 16 GUI offscreen 测试，原 433 不退化）
- **Phase 5.0 — Tracking Pipeline Consolidation**（✅ 2026-09-02，merge `5569e93`）：TrackingJobRunner 统一，433 tests 通过，CI 双平台绿。
- **Phase 5 规划**（2026-09-01，只改文档）：新增 `phase5-requirements.md` + `phase-5-plan.md`。
- **Phase 4 — Deep Learning Tracking**（✅ 2026-09-01）：4.0–4.5 全部完成，CI macOS/Windows 双平台绿，Issue #15 已关闭。

## Current Goal

**Phase 5.7 Human Review gate**：实现、复核（R1/R2 CLOSED）与文档同步已完成；
等待用户按清单实测。HR 通过后：宣布 5.7 与 Phase 5 收官、roadmap/README 终态
同步、进入 Phase 6 立项。HR 发现的关键误解按 blocking interaction finding 处理。

## Current Worktree Note

`feat/p5.7-interaction-redesign` 已合并 main 并推送；工作区干净（除本文件）。

## Current Worktree Note

`fix/pre-phase6-review-followup` 按 `--no-ff` 合并 main；三项补漏、5 项新增回归和
审查追记一并交付。无 schema/ADR/产品范围变更，无真实项目数据改写。

## Current Decisions / Deferred Checks

**已定决策**

- DeepLabCut 集成架构（ADR-0011）：适配器隔离 + 后台子进程 (spawn 模式) + 单 bodypart 先行
- K-means 选帧：自适应抽帧步长 + 流式 Grab 快速解码；5.2 起支持显式候选集（视觉多样性复用）
- `FrameSelectionResult` 只含帧号，不创建 TrackPoint（5.1 R1 / 5.2 同约束）
- 挖掘策略：固定 pipeline（池→归一化加权→时间去重→多样性→Top N）；分数是筛查排名不是概率；
  min_gap 秒→帧用 ceil（不得低于请求最小间隔）；已有 manual 帧不进候选池
- 预测产物身份：`read_inference_result` 持久化 `prediction_file_info` 基线；挖掘只接受
  本 run `data/engines/<run_id>/` 内的产物引用（旧 run 无基线时容忍）
- Suggested Frame 审核状态（ADR-0013）：保存于对应 infer run 的
  `extra_fields["suggested_frame_review_v1"]`；schema v1 不迁移；审核事务使用 scoped
  Undo/Redo；manual 删除保存前可撤销，保存后不能通过应用内 Undo 恢复
- 结果激活与 fixed validation（ADR-0014）：completed infer result 与当前 Track 投影分离；
  Activate/Replace/Clear 为原子事务；固定验证成员真实传入 DLC train/test split

**已批准延期**：Windows 真机/CUDA 延期到 Phase 9 打包前。

**已批复的 5.6 Slice 0 决策（2026-09-04，源自 5.4 R2 复审）**

- A（High）崩溃恢复死锁：打开项目时自动把无进程对应的 pending/running run 标记为 failed。
- B（Medium）shuffle 编号错位：删除 prepare_training 的 DLC 目录复用路径，强制 per-run 全新目录。
- C（Medium）激活产物指纹：放宽为仅比对文件大小（放弃 mtime/纳秒比对，接受防篡改强度下降）。

**仓库记录**：GitHub Issue #18/#19/#21 均已关闭（2026-09-04/05），无未结 Issue。

## Next Recommended Action

**用户执行 Phase 5.7 Human Review Round 2**（通过前 5.7 不关闭）：

1. 启动：仓库根目录 `.venv/bin/python -m ai_physics_tracker`
2. 在约 1024×640 窗口确认右侧卡片可滚动、主动作可达，高级设置不横向裁切。
3. 生成轨迹后确认视频出现橙色 `Preview · not adopted`，进入 Check 后可直接
   Accept/Correct/Skip；Finish checking 保留剩余帧并回到采用决策，再次 Check 能续接。
4. Correct 跳帧完成后鼠标在视频上立即保持十字；Cancel placement/Esc 不落点。
5. 无标定时确认状态头/卡片说明单位为 pixels，`Set scale & units` 能进入标定；
   标定后限制消失。
6. 同一模型生成一次后不再重复提示 Generate；继续训练后才重新提示。
7. 采用、完成审核、确认检查帧或 Correct 后直接退出并重开，数据已保存；Correct 后
   Undo/Redo 仍可用。
8. 候选预览不得改变当前图表；采用后 Preview 消失，更新 Charts 后来源显示新版本。

反馈"通过"→ 收尾收官；指出问题 → 修复后重跑自动化再发起 HR。
