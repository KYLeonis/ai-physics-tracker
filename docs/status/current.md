# Current Status

> 项目"现在在哪、下一步做什么"的**唯一权威入口**——不知道该做什么时先读这个文件。
> 每个开发会话结束时由 Agent 更新（规则见 `docs/workflow.md` §11）；人类可随时手写修改，人类改动优先于 Agent 的判断。

- 最后更新：2026-09-02（5.1 运行时审查补漏已合并本地 main；5.2 Mini-plan 待确认）

---

## Phase / Subphase / Slice

| Level | Name | Status |
| --- | --- | --- |
| Phase | Phase 5 — AI-assisted Annotation & Refinement | 🚧 进行中 |
| Subphase | 5.0 — Tracking Pipeline Consolidation | ✅ 已完成 (2026-09-02) |
| Subphase | 5.1 — Representative Frame Selection | ✅ 已完成 (2026-09-02, Human Review 通过) |
| Subphase | 5.2 — Difficult Frame Mining | 📝 规划待确认 |

## Recently Completed

- **5.1 运行时审查补漏**（✅ 2026-09-02，Issue [#18](https://github.com/KYLeonis/ai-physics-tracker/issues/18)）：独立全面审查（报告见 [phase-5.0-5.1-runtime-review.md](../reviews/phase-5.0-5.1-runtime-review.md)）后修复 4 项——选帧对打不开/损坏视频显式报错（F1）、选帧运行中禁止启动训练/推理（F2）、pyproject 显式声明 scikit-learn（F3a）、`detect_device` 异常写法（F5）；全回归 **497 passed**。F3b/F4/F6 作为顺带项记入 5.2 plan §Deferred Findings。
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

已完成 **Phase 5.2 — Difficult Frame Mining** Mini-plan 草案；尚未创建 Issue、开发分支或产品代码，
等待用户确认范围、默认评分语义和人工审计集约定。

## Current Decisions / Deferred Checks

**已定决策**

- DeepLabCut 集成架构（ADR-0011）：适配器隔离 + 后台子进程 (spawn 模式) + 单 bodypart 先行
- K-means 选帧：自适应抽帧步长（维持 ~100 帧候选池）+ 流式 Grab 快速跳帧解码，不写磁盘
- `FrameSelectionResult` 只含帧号，不创建 TrackPoint（Phase 5.1 R1 核心约束）

**已批准延期**：Windows 真机/CUDA 延期到 Phase 9 打包前。

## Next Recommended Action

请用户审阅并确认 [Phase 5.2 Mini-plan](phase-5.2-plan.md)，重点确认：

1. 第一版四信号权重与 `0.25 s` 时间去重默认值。
2. 开发集调参、冻结审计集只做最终评估的数据隔离规则。
3. 审计表最小字段：`frame_index / needs_review / needs_correction / note`。
4. 新增的 §Deferred Findings 顺带项安排（F3b 随 Slice 3；F4/F6 随 5.3）。

确认后才创建 GitHub Issue、建立 `feat/p5.2-difficult-frames` 分支并执行 Slice 1；确认前不写产品代码。
注意：`fix/p5.1-frame-selection-robustness` 已合并本地 main，**尚未 push 到 origin**（push 需用户确认）。
