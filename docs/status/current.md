# Current Status

> 项目"现在在哪、下一步做什么"的**唯一权威入口**——不知道该做什么时先读这个文件。
> 每个开发会话结束时由 Agent 更新（规则见 `docs/workflow.md` §11）；人类可随时手写修改，人类改动优先于 Agent 的判断。

- 最后更新：2026-08-31（Phase 4.0 Research & ADR 完成）

---

## Current Phase

**Phase 4 — Deep Learning Tracking** 🔄 进行中

## Current Subphase

**4.0 — Research & ADR** ✅ 已完成

下一 Subphase 为 **4.1 — Engine Adapter & Task Framework**：实现 DLCAdapter、TaskRunner 后台任务框架和 TrackingRun 领域模型。

## Current Slice

N/A（等待进入 4.1）。

## Current Goal

在软件内接入 DeepLabCut 3.x（PyTorch 引擎），实现从手工标注到 AI 自动跟踪的完整闭环。

## Recently Completed

- **Phase 4.0 — Research & ADR**（✅ 2026-08-31）：
  - ADR-0011：DeepLabCut 集成架构（适配器隔离、后台子进程框架、标注导出/推理导入、设备三态、依赖管理、License 合规分析）
  - `docs/spec/phase4-requirements.md`：6 项功能需求、6 条验收标准、5 个 Subphase 划分
  - Phase 3 文档收尾同步（roadmap/AGENTS/README 状态标记统一更正为已完成）
- **Phase 3 — Calibration & Physics Engine**（✅ 2026-08-31）：全部 3.0–3.4 完成，310 tests + 双平台 CI + 整体 Human Review 通过。
- **Phase 2 — Video Analysis MVP**（✅ 2026-08-30）。
- **Phase 1 — Project & Data Foundation**（✅ 2026-08-29）。

## Current Decisions / Blockers

**已定决策**

- DeepLabCut 集成架构（ADR-0011）：适配器隔离 + 后台子进程 + 单 bodypart 先行
- License：MIT 兼容（DLC LGPL-3.0 动态链接合规），中国软著不受影响
- DLC 作为必需依赖（非可选），Phase 9 安装程序可提供轻量选项
- 单 bodypart 先行，多关键点留后续扩展
- 从零训练基础流程先行，预训练模型留 Phase 7

**延后项**：Windows 真机验收。

## Next Recommended Action

进入 **Subphase 4.1 — Engine Adapter & Task Framework**：创建工作分支，实现 DLCAdapter（infrastructure 层）、TaskRunner（后台子进程框架）和 TrackingRun 领域模型，编写单元测试（使用 mock adapter）。参照 ADR-0011 和 `phase4-requirements.md` R1。
