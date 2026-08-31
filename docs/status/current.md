# Current Status

> 项目"现在在哪、下一步做什么"的**唯一权威入口**——不知道该做什么时先读这个文件。
> 每个开发会话结束时由 Agent 更新（规则见 `docs/workflow.md` §11）；人类可随时手写修改，人类改动优先于 Agent 的判断。

- 最后更新：2026-08-31（Phase 4.1 Engine Adapter & Task Framework 完成）

---

## Current Phase

**Phase 4 — Deep Learning Tracking** 🔄 进行中

## Current Subphase

**4.1 — Engine Adapter & Task Framework** ✅ 已完成（[Issue #12](https://github.com/KYLeonis/ai-physics-tracker/issues/12) 已关闭；331 tests 全部通过，Review Agent 审查通过）

下一 Subphase 为 **4.2 — Training Pipeline**：实现标注导出到 DLC 项目、后台训练任务启动/监控/取消、以及 ProjectSession 级联。

## Current Slice

N/A（等待进入 4.2）。

## Current Goal

在软件内接入 DeepLabCut 3.x（PyTorch 引擎），实现从手工标注到 AI 自动跟踪的完整闭环。

## Recently Completed

- **Phase 4.1 — Engine Adapter & Task Framework**（✅ 2026-08-31）：
  - 领域模型 `TrackingRun`：记录训练与推理运行的溯源元数据，支持 project.json 序列化与校验，`Registries.sources` 默认支持 `"dlc"`。
  - 后台多进程任务框架 `BackgroundTaskRunner`：采用 `multiprocessing.get_context("spawn")` 模式，实现流式进度与日志传输、异常安全捕获与取消。
  - 引擎适配器 `EngineAdapter` 协议、`DLCAdapter`（DLC 项目创建、标注 PNG 抽帧/MultiIndex CSV 导出与 DataFrame 推理导入）及 `MockEngineAdapter`。
  - 331 项测试全部通过（新增 21 项测试），Review Agent 审查通过。
- **Phase 4.0 — Research & ADR**（✅ 2026-08-31）：ADR-0011 与 phase4-requirements.md。
- **Phase 3 — Calibration & Physics Engine**（✅ 2026-08-31）：全部 3.0–3.4 完成，310 tests + 双平台 CI + 整体 Human Review 通过。
- **Phase 2 — Video Analysis MVP**（✅ 2026-08-30）。
- **Phase 1 — Project & Data Foundation**（✅ 2026-08-29）。

## Current Decisions / Blockers

**已定决策**

- DeepLabCut 集成架构（ADR-0011）：适配器隔离 + 后台子进程 (spawn 模式) + 单 bodypart 先行
- License：MIT 兼容（DLC LGPL-3.0 动态链接合规），中国软著不受影响
- 任务执行：非 daemon 子进程避免 PyTorch DataLoader 多 worker 限制，进程异常捕获与 EOFError 隔离
- 测试策略：CI 与单元测试使用 `MockEngineAdapter`，真机/真实 DLC 测试本地进行

**延后项**：Windows 真机验收。

## Next Recommended Action

进入 **Subphase 4.2 — Training Pipeline**：在 `ProjectSession` 中编排训练准备（导出手工标注至 DLC 项目）、启动后台训练任务、实时查询进度与取消训练，记录 `TrackingRun`。
