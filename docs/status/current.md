# Current Status

> 项目"现在在哪、下一步做什么"的**唯一权威入口**——不知道该做什么时先读这个文件。
> 每个开发会话结束时由 Agent 更新（规则见 `docs/workflow.md` §11）；人类可随时手写修改，人类改动优先于 Agent 的判断。

- 最后更新：2026-09-03（**5.3 Slice 2 已完成，全部 611 测试通过；下一步进入 Slice 3**）

---

## Phase / Subphase / Slice

| Level | Name | Status |
| --- | --- | --- |
| Phase | Phase 5 — AI-assisted Annotation & Refinement | 🚧 进行中 |
| Subphase | 5.0 — Tracking Pipeline Consolidation | ✅ 已完成 (2026-09-02) |
| Subphase | 5.1 — Representative Frame Selection | ✅ 已完成 (2026-09-02, Human Review 通过) |
| Subphase | 5.2 — Difficult Frame Mining | ✅ 已完成 (2026-09-03, AC-10 / review / HR / push 闭环) |
| Subphase | 5.3 — Suggested Frame Review & Correction | 🚧 进行中（Slice 1-2 已完成；下一步 Slice 3） |

## Recently Completed

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

**Phase 5.3 已规划并完成开工准备；按用户指令停在 Slice 1 实现之前。**

计划见 [phase-5.3-plan.md](phase-5.3-plan.md)，GitHub Issue
[#20](https://github.com/KYLeonis/ai-physics-tracker/issues/20)。

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

**已批准延期**：Windows 真机/CUDA 延期到 Phase 9 打包前。

## Next Recommended Action

1. 提交 Slice 2 变更（Conventional Commit: `feat: implement mining entry and review queue controller (Phase 5.3 Slice 2)`）。
2. 开始 Phase 5.3 Slice 3 — Review/Correct/delete GUI：实现审核工作区、一次性 Correct 模式与当前帧 manual 删除，刷新 dirty/Undo/Redo/marker 状态。
