# Current Status

> 项目"现在在哪、下一步做什么"的**唯一权威入口**——不知道该做什么时先读这个文件。
> 每个开发会话结束时由 Agent 更新（规则见 `docs/workflow.md` §11）；人类可随时手写修改，人类改动优先于 Agent 的判断。

- 最后更新：2026-09-01（Phase 4 / Subphase 4.4 完成，双平台 CI 通过）

---

## Current Phase

**Phase 4 — Deep Learning Tracking** ✅ 已完成（2026-09-01）

## Current Subphase

**4.4 — GUI & Integration** ✅ 已完成：`17ae493` 合并到 `main`，Issue #15 已关闭；433 tests、真实 CPU GUI 组件冒烟、独立 review、macOS Human Review 及 macOS/Windows CI 均通过。

验收记录：[phase-4.4-plan.md](phase-4.4-plan.md)。4.3 已完成（[Issue #14](https://github.com/KYLeonis/ai-physics-tracker/issues/14) 已关闭；[验收记录](phase-4.3-plan.md)）。

## Current Slice

N/A（Phase 4 已完成，停止并等待下一阶段指令）。

## Current Goal

Phase 4 目标已交付：软件内完成手工标注、训练/评价、推理、AI 轨迹显示与运动学重算闭环。

## Recently Completed

- **Phase 4 — Deep Learning Tracking**（✅ 2026-09-01）：Subphase 4.0–4.4 全部完成；最终 `main` 集成 CI [run 33504579667](https://github.com/KYLeonis/ai-physics-tracker/actions/runs/33504579667) 在 macOS/Windows Python 3.11 通过。首轮 Windows CI 暴露两个平台相关测试假设，`51e05b1` 修复为按平台尺寸验证后复跑全绿。Issue #15 已关闭。经用户明确批准，Windows 真机/CUDA 验收延期到 Phase 9 打包前的专门关卡。
- **4.4 macOS Human Review 通过**（2026-09-01）：用户确认完整 GUI 工作流与最终聚焦复验通过。Main/Chart/AI 可缩放，Chart/AI 可分离为独立窗口并重新停靠，Chart 动态状态消息为英文；无其他交互问题。
- **4.4 本地实现与自动化验证**（2026-09-01）：Task Panel、真实训练指标/基本评价、推理、异步取消/保存/切换、AI 菱形及 marker 复用已接通；最终本地全回归 **433 passed in 47.47s**。真实 GUI 组件 CPU 冒烟完成 1 epoch 训练/评价/推理，5 AI 插入/5 manual 保留并保存重开；独立 review 的两个 finding 已修复并复审通过；`--no-ff` 合并提交为 `17ae493`。
- **独立 review 存档机制**（2026-09-01，main）：新增 `docs/reviews/`（每 subphase 一个 Review Record，索引见其 README），`docs/templates/review.md` 升级为生命周期记录模板，流程规则收敛到 `docs/workflow.md` §6；纯文档变更，未改实现代码。
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

## Current Decisions / Deferred Checks

**已定决策**

- DeepLabCut 集成架构（ADR-0011）：适配器隔离 + 后台子进程 (spawn 模式) + 单 bodypart 先行
- 会话切换/关闭策略（D1）：关闭或切换会话时强制取消活动训练任务，避免产生孤儿后台进程
- 训练默认参数（D2）：`epochs=50, batch_size=8, device=auto(cuda→mps→cpu)`，4.4 GUI 已提供配置控件
- 测试策略：CI 与单元测试使用 `MockEngineAdapter`；真实 CPU GUI 组件闭环通过（`scripts/smoke_test_gui_tracking.py`）

**已批准延期**：Windows 真机/CUDA 尚未验证；用户明确批准延期到 Phase 9 打包前的专门验收节点。GitHub Actions 的 Windows mock/GUI 测试已通过，但不等同 CUDA 真机验证。

**4.4 已实现取舍**：AI 链路取消重复全文件哈希和缺历史 hash 门禁，保留轻量文件状态、实际模型引用、数据正确性与任务归属校验；抽帧、建集和解析后台化。基础 K-means 选帧留 Phase 5，直接调用 DLC。

## Next Recommended Action

停止开发，等待用户下一条指令。下一阶段为 Phase 5 — AI-assisted Annotation & Refinement；进入时先规划，基础 K-means 选帧直接调用 DLC，不自行开始实现。
