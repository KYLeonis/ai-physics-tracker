# Current Status

> 项目"现在在哪、下一步做什么"的**唯一权威入口**——不知道该做什么时先读这个文件。
> 每个开发会话结束时由 Agent 更新（规则见 `docs/workflow.md` §11）；人类可随时手写修改，人类改动优先于 Agent 的判断。

- 最后更新：2026-09-02（**5.2 全部完成，AC-10 达成**；GUI HR 第二轮进行中；合并提交待 push）

---

## Phase / Subphase / Slice

| Level | Name | Status |
| --- | --- | --- |
| Phase | Phase 5 — AI-assisted Annotation & Refinement | 🚧 进行中 |
| Subphase | 5.0 — Tracking Pipeline Consolidation | ✅ 已完成 (2026-09-02) |
| Subphase | 5.1 — Representative Frame Selection | ✅ 已完成 (2026-09-02, Human Review 通过) |
| Subphase | 5.2 — Difficult Frame Mining | ✅ 已完成 (2026-09-02, AC-10 达成；HR 第二轮修复待验收) |
| Subphase | 5.3 — Suggested Frame Review & Correction | ⬜ 未开始（含每帧删除标注交互） |

## Recently Completed

- **Phase 5.2 — Difficult Frame Mining（代码与基准工具链，2026-09-02，分支 `feat/p5.2-difficult-frames`）**：
  - Slice 1：`RawPrediction` + `read_raw_predictions` 全帧原始预测入口（低置信度/缺测不丢失，整批校验）；`prepare_difficult_frame_request` 绑定 run/产物身份（指纹基线 + run 从属目录校验）
  - Slice 2：`application/difficult_frames.py` 纯策略——四信号（uncertainty/jump/residual/prior）、池内 percentile rank、加权排名、贪心时间去重（ceil 间隔、放宽记录 effective_gap）
  - Slice 3：5.1 K-means 支持显式候选集；`run_difficult_frame_worker` + `DifficultFrameRunner`（取消、原子结果、不碰活动 session）；F3b 改名闭环
  - Slice 4：`application/benchmark.py` + `scripts/benchmark_difficult_frames.py`（emit-audit/score、盲评表、legacy 回填）；真实 2767 帧单摆 run 全链路验证并生成开发集审计表（17 帧，待标注）
  - 独立审查：两轮 code-reviewer subagent（R1 request-changes：H1 预测产物身份半套等 12 项；R2 approve-with-comments：MAD>0 覆盖/ceil 舍入等 6 项）全部修复闭环，见 [phase-5.2-review.md](../reviews/phase-5.2-review.md)
  - 全回归：**566 passed**（新增 69 测试：50 挖掘 + 13 基准 + 6 扩展）
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

**5.2 已收口**（AC-10：policy 0.800/0.300 vs baseline 0.600/0.000，报告
`docs/benchmarks/phase-5.2-report.md`）。当前等待：①用户完成 GUI HR 第二轮验收
（建议帧缓存恢复 / 自动保存 / 帧号正上方）；②确认 push。

## Current Decisions / Deferred Checks

**已定决策**

- DeepLabCut 集成架构（ADR-0011）：适配器隔离 + 后台子进程 (spawn 模式) + 单 bodypart 先行
- K-means 选帧：自适应抽帧步长 + 流式 Grab 快速解码；5.2 起支持显式候选集（视觉多样性复用）
- `FrameSelectionResult` 只含帧号，不创建 TrackPoint（5.1 R1 / 5.2 同约束）
- 挖掘策略：固定 pipeline（池→归一化加权→时间去重→多样性→Top N）；分数是筛查排名不是概率；
  min_gap 秒→帧用 ceil（不得低于请求最小间隔）；已有 manual 帧不进候选池
- 预测产物身份：`read_inference_result` 持久化 `prediction_file_info` 基线；挖掘只接受
  本 run `data/engines/<run_id>/` 内的产物引用（旧 run 无基线时容忍）

**已批准延期**：Windows 真机/CUDA 延期到 Phase 9 打包前。

## Next Recommended Action

1. **用户完成 GUI HR 第二轮**：重启应用（`.venv/bin/python -m ai_physics_tracker`）后验证
   ①建议帧在取消选择/切走再选回后恢复；②每 10 个标注点与 AI 任务完成后状态栏出现
   Autosaved 且无弹窗；③帧号位于圆圈正上方居中。反馈后处置并收尾。
2. **确认 push**：本地 main 领先 origin（5.2 全部提交 + HR 修复）。
3. push 后关闭 Issue #19，进入 5.3 规划（含每帧删除标注交互、Accept/Correct/Skip、
   `confidence_threshold` 分位数自适应候选）。
