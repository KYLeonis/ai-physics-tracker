# Current Status

> 项目"现在在哪、下一步做什么"的**唯一权威入口**——不知道该做什么时先读这个文件。
> 每个开发会话结束时由 Agent 更新（规则见 `docs/workflow.md` §11）；人类可随时手写修改，人类改动优先于 Agent 的判断。

- 最后更新：2026-08-31（Phase 4.4 其余方案已认可，哈希策略简化，待确认 K-means 范围）

---

## Current Phase

**Phase 4 — Deep Learning Tracking** 🔄 进行中

## Current Subphase

**4.4 — GUI & Integration** 📝 其余方案已获认可；按用户反馈简化 AI 哈希校验，待确认基础 K-means 选帧是否前移。尚未开始实现。

计划草案：[phase-4.4-plan.md](phase-4.4-plan.md)。4.3 已完成（[Issue #14](https://github.com/KYLeonis/ai-physics-tracker/issues/14) 已关闭；[验收记录](phase-4.3-plan.md)）。

## Current Slice

N/A（完成 K-means 范围确认后，从 Slice 1：轻量校验与后台准备/提交边界开始）。

## Current Goal

在软件内接入 DeepLabCut 3.x（PyTorch 引擎），实现从手工标注到 AI 自动跟踪的完整闭环。

## Recently Completed

- **4.4 进入检查与计划**：`main` / `1ca5bee` 与实时查询远程一致，进入时工作区干净；重新验证 **405 passed in 52.40s**。计划识别并覆盖同步准备/哈希、真实训练指标、保存替换 session、全量 marker 重建、中断任务恢复与基本模型评价缺口；只写计划，不改实现。
- **4.3 — Inference Pipeline & Track Integration**（✅ 2026-08-31）：真实推理、严格解析、模型 hash 校验、spawn 取消/错误/晚到消息处理、原子导入与 Undo/Redo、人工/AI 生效观测和运动学已接通；405 tests 通过。真实 CPU 合成视频 10 帧推理，5 点导入/5 个人工点保护，保存重开通过；重复推理 0 点导入/10 点跳过，既有派生不变。精简依赖模拟 74 passed / 1 HDF5 测试因无 pandas 跳过。独立审查发现的模型/视频身份、快照索引竞态、legacy 归档引用问题均已修复并复审通过。未改依赖、CI、schema。集成提交 `e58b28d` 已推送；[该提交的 CI](https://github.com/KYLeonis/ai-physics-tracker/actions/runs/33380207408) 在 macOS/Windows Python 3.11 上均通过，Issue #14 已关闭。
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
- 测试策略：CI 与单元测试使用 `MockEngineAdapter`，本地真实训练/推理闭环通过（`scripts/smoke_test_dlc_infer.py`）

**延后项**：Windows 真机/CUDA 验收。4.4 按用户反馈取消 AI 链路重复全文件哈希和缺历史 hash 门禁，保留轻量文件检查及数据正确性/任务归属校验；抽帧、建集和解析仍后台化。此为已确认的设计修订，现有 4.3 代码尚未改变。

**4.3 计划边界**：先做 Qt-free 推理/导入/混合观测分析；任务面板、AI 视觉样式、窗口生命周期接线与自动刷新留给 4.4。真实 snapshot 选择、帧进度与输出完整性已验证。现有 4.2 模型路径移动兼容风险在草案中说明，不自动迁移。

**前置缺口已修复**：训练快照通过 DLC loader 定位，只接受本次真实产出的权重；新增训练 run 保存项目内相对 config/model 引用和模型 hash。不自动修写历史 run。失效/被覆盖的旧模型明确拒绝推理。

## Next Recommended Action

仅确认是否将基础 K-means 选帧从 Phase 5 提前至 4.4，其余方案用户已认可，哈希策略按最新反馈简化。范围确定后同步规范、创建 Issue/工作分支、写 ADR-0012，再按计划实施。GUI Human Review 与 Windows/CUDA 条件保留；不默认前移困难帧/主动学习，也不推送未授权的 4.4 改动。
