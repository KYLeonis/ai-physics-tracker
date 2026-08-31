# Current Status

> 项目"现在在哪、下一步做什么"的**唯一权威入口**——不知道该做什么时先读这个文件。
> 每个开发会话结束时由 Agent 更新（规则见 `docs/workflow.md` §11）；人类可随时手写修改，人类改动优先于 Agent 的判断。

- 最后更新：2026-08-31（Phase 4.2 Training Pipeline 完成）

---

## Current Phase

**Phase 4 — Deep Learning Tracking** 🔄 进行中

## Current Subphase

**4.2 — Training Pipeline** ✅ 已完成（[Issue #13](https://github.com/KYLeonis/ai-physics-tracker/issues/13) 已关闭；341 tests 全部通过，真实 DLC 冒烟通过，Review Agent 审查通过）

下一 Subphase 为 **4.3 — Inference Pipeline & Track Integration**：实现视频批量推理、置信度过滤、轨迹点导入 TrackStore 以及与手工标注的图层融合。

## Current Slice

N/A（等待进入 4.3）。

## Current Goal

在软件内接入 DeepLabCut 3.x（PyTorch 引擎），实现从手工标注到 AI 自动跟踪的完整闭环。

## Recently Completed

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

## Next Recommended Action

进入 **Subphase 4.3 — Inference Pipeline & Track Integration**：实现视频批量推理（`analyze_video`）、DLC 预测数据解析、按置信度阈值导入 `TrackStore`、以及与手工标注点共存时的观察值融合解析。
