# Current Status

> 项目"现在在哪、下一步做什么"的**唯一权威入口**——不知道该做什么时先读这个文件。
> 每个开发会话结束时由 Agent 更新（规则见 `docs/workflow.md` §11）；人类可随时手写修改，人类改动优先于 Agent 的判断。

- 最后更新：2026-08-31（Phase 4.3 计划草案完成，等待用户确认）

---

## Current Phase

**Phase 4 — Deep Learning Tracking** 🔄 进行中

## Current Subphase

**4.3 — Inference Pipeline & Track Integration** 📝 计划待确认，尚未开始实现。

计划草案：[phase-4.3-plan.md](phase-4.3-plan.md)。上一个 Subphase 4.2 已完成（[Issue #13](https://github.com/KYLeonis/ai-physics-tracker/issues/13) 已关闭）。

## Current Slice

N/A（等待确认 4.3 范围，确认后从 Slice 1：真实 DLC 契约核对与推理协议开始）。

## Current Goal

在软件内接入 DeepLabCut 3.x（PyTorch 引擎），实现从手工标注到 AI 自动跟踪的完整闭环。

## Recently Completed

- **4.3 进入检查与计划**（2026-08-31）：进入时 `main` 工作区干净，HEAD `7ecb4ea` 与实时查询的 origin/main 一致，对应 CI success；本轮重新运行 offscreen 全回归 **341 passed in 22.05s**。已读取 Phase 4 spec/ADR、数据语义、训练 Issue 与相关实现；确认现有融合规则可复用，但运动学计算及后台输入检查仍只读 manual，需在 4.3 接通 AI 生效观测。只新增计划文档，未改实现、依赖、CI 或 schema。
- **Phase 4.2 — Training Pipeline**（✅ 2026-08-31）：
  - 协议扩展：`EngineAdapter` 协议补齐 `create_training_dataset`、`train` 与 `engine_version`，新增 `TrainingParams` 与 `TrainOutcome` 数据类。
  - 应用层编排：`TrainingCoordinator` 实现 `prepare_training`（标注抽帧/CSV/H5 导出、DLC 项目目录复用、训练集生成）、`start_training`（spawn 子进程运行）、`poll_messages`（流式日志与进度转发、进程异常退出兜底）与 `cancel_training` / `cancel_all`（D1 策略：关闭或切换会话时安全回收子进程）。
  - 会话级联与持久化：`ProjectSession` 新增 `record_tracking_run`、`update_tracking_run`、`tracking_runs` 接口，全生命周期随 `project.json` 序列化。
  - 依赖与真实验证：`deeplabcut>=3.0,<4.0` 落地为 pyproject 依赖，在 macOS Apple Silicon 上通过真实合成视频单摆训练冒烟测试（1 epoch 生成 snapshot）。
  - 341 项测试全部通过（新增 10 项测试），Review Agent 审查通过。
- **Phase 4.1 — Engine Adapter & Task Framework**（✅ 2026-08-31）：`TrackingRun` 模型、`BackgroundTaskRunner`、`DLCAdapter` 与 `MockEngineAdapter`。
- **Phase 4.0 — Research & ADR**（✅ 2026-08-31）：ADR-0011 与 phase4-requirements.md。
- **Phase 3 — Calibration & Physics Engine**（✅ 2026-08-31）：全部 3.0–3.4 完成，310 tests + 双平台 CI + 整体 Human Review 通过。
- **Phase 2 — Video Analysis MVP**（✅ 2026-08-30）。
- **Phase 1 — Project & Data Foundation**（✅ 2026-08-29）。

## Current Decisions / Blockers

**已定决策**

- DeepLabCut 集成架构（ADR-0011）：适配器隔离 + 后台子进程 (spawn 模式) + 单 bodypart 先行
- 会话切换/关闭策略（D1）：关闭或切换会话时强制取消活动训练任务，避免产生孤儿后台进程
- 训练默认参数（D2）：`epochs=50, batch_size=8, device=auto(cuda→mps→cpu)`，后续在 4.4 GUI 中提供配置控件
- 测试策略：CI 与单元测试使用 `MockEngineAdapter`，本地真实 DLC 冒烟通过（`scripts/smoke_test_dlc_train.py`）

**延后项**：Windows 真机验收。

**4.3 计划边界**：先做 Qt-free 推理/导入/混合观测分析；任务面板、AI 视觉样式、窗口生命周期接线与自动刷新留给 4.4。真实 snapshot 选择、帧进度与输出完整性在首个 Slice 优先核对。现有 4.2 模型路径移动兼容风险在草案中说明，不自动迁移。

## Next Recommended Action

等待用户确认 [4.3 计划草案](phase-4.3-plan.md)；确认后创建对应 Issue 和 `feat/p4.3-inference-pipeline` 工作分支，从 Slice 1 核对真实 DLC 推理的 snapshot/进度/输出契约开始。按草案完成各 Slice，不提前实现 4.4 GUI。推送、删除等红线动作另依用户授权执行。
