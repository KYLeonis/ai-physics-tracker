# Current Status

> 项目"现在在哪、下一步做什么"的**唯一权威入口**——不知道该做什么时先读这个文件。
> 每个开发会话结束时由 Agent 更新（规则见 `docs/workflow.md` §11）；人类可随时手写修改，人类改动优先于 Agent 的判断。

- 最后更新：2026-08-28

---

## Current Phase

**Phase 1 — Project & Data Foundation**（准备期已全部完成，正式进入实现期）

## Current Subphase

**1.0 — Phase 1 Spec & Requirements** ✅ 已完成（2026-08-28，A1–A6 全部交付，software-spec-plan.md v2 转 Closed）
下一个：**1.1 — 数据模型核心实现**（编号已预留在本文件历史中，Issue 待建）

## Current Slice

无（subphase 1.0 已收尾；1.1 的 Slice 划分在其 mini-plan 中确定）

## Current Goal

Phase 1.1：按 `docs/spec/phase1-requirements.md` 落地数据模型核心（src-layout + `pyproject.toml` + 核心对象 + 持久化 + pytest），对照 AC-1…AC-10 验收。

## Recently Completed

- **Subphase 1.0 — Phase 1 Spec & Requirements**（2026-08-28）：`docs/spec/data-model.md`（领域模型/时间语义/标定/最小接口）、`docs/spec/project-format.md` + **ADR-0003**（JSON 清单优先持久化）、`docs/spec/phase1-requirements.md`（AC-1…AC-10，含 DLC 无损转换设计）；`docs/research/software-spec-plan.md` §5 Readiness Criteria 全部勾选，PLAN 转 Closed
- **Phase 0 — Project Initialization**（2026-08-27）：仓库结构、基础文档、Git/GitHub 初始化 ✅
- 开源生态调研：project map + 14 份 raw notes（`docs/research/`）
- 跨平台开发模式确定：macOS 开发 → Windows 发布（`docs/development.md` §1.1）
- 软件规范设计准备计划收敛为 v2（`docs/research/software-spec-plan.md`）
- 开发工作流体系建立（`docs/workflow.md` + `docs/status/` + `docs/templates/`，2026-08-28）

## Current Decisions / Blockers

**已定决策**

- Python 3.11（ADR-0002）
- 持久化格式：**JSON 清单优先混合方案**（ADR-0003）——`project.json` 单文件 + 引擎输出外置 `data/engines/`，`schema_version` + 迁移链，原子写入 + 滚动备份
- 数据模型核心结论（`docs/spec/data-model.md`）：帧号 0-based、CFR（VFR 显式拒绝）、raw 只存像素坐标、手工修正遮蔽 AI 预测不覆盖（superseded 链）、confidence 与 visibility 分立、source 开放注册表、标定变更仅派生层失效、裁剪不重置时间基准
- Phase 1 前的设计只到字段级建议，**不写 Python class**（自 Phase 1.1 起）
- 数值微分/平滑方法 → Phase 3 前出 ADR

**Blockers**：无。

## Next Recommended Action

开始 **Phase 1.1 — 数据模型核心实现**：

1. 用 `docs/templates/subphase-plan.md` 写 mini-plan，建 GitHub Issue `Phase 1.1 — data model core`；
2. 建分支 `feat/p1.1-data-model`；
3. Slice 划分建议：`pyproject.toml` + src-layout 骨架 → 核心值对象（Video/Timeline/Track/TrackPoint/Calibration，纯数据无 Qt）→ TrackStore 写入/遮蔽/解析语义 → ProjectRepository 持久化（ADR-0003）→ 测试补齐；
4. 验收对照 `docs/spec/phase1-requirements.md` AC-1…AC-10（AC-9 已完成）；实现前先读 `docs/spec/data-model.md` 与 AGENTS.md §5 列出的对应研究小节。

Phase 1.1 完成后再规划 1.2（预计为持久化/转换器收尾或按实现期实际情况拆分）。
