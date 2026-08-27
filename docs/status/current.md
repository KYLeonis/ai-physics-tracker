# Current Status

> 项目"现在在哪、下一步做什么"的**唯一权威入口**——不知道该做什么时先读这个文件。
> 每个开发会话结束时由 Agent 更新（规则见 `docs/workflow.md` §11）；人类可随时手写修改，人类改动优先于 Agent 的判断。

- 最后更新：2026-08-28

---

## Current Phase

**Phase 1 — Project & Data Foundation**（准备期：先完成 spec 调研，再开始实现）

## Current Subphase

**1.0 — Phase 1 Spec & Requirements**（依据 `docs/research/software-spec-plan.md` v2 的行动项 A1–A6；纯文档 subphase，不建代码分支）

## Current Slice

**A1 领域模型与数据分层语义**（未开始；建议 A1 → A2 → A3 同一会话完成）

## Current Goal

在写任何代码之前，产出 Phase 1 的三份 spec 文档（`docs/spec/data-model.md` / `docs/spec/project-format.md` / `docs/spec/phase1-requirements.md`）+ ADR-0003，满足 software-spec-plan.md §5 的全部 Phase 1 Readiness Criteria。

## Recently Completed

- **Phase 0 — Project Initialization**（2026-08-27）：仓库结构、基础文档、Git/GitHub 初始化 ✅
- 开源生态调研：project map + 14 份 raw notes（`docs/research/`）
- 跨平台开发模式确定：macOS 开发 → Windows 发布（`docs/development.md` §1.1）
- 软件规范设计准备计划收敛为 v2（`docs/research/software-spec-plan.md`）
- 开发工作流体系建立（`docs/workflow.md` + `docs/status/` + `docs/templates/`，2026-08-28）

## Current Decisions / Blockers

**已定决策**

- Python 3.11（ADR-0002）
- 持久化格式待定 → A4 将产出 ADR-0003
- Phase 1 前的设计只到字段级建议，**不写 Python class**（实现属 Phase 1）
- 数值微分/平滑方法 → Phase 3 前出 ADR

**Blockers**：无。

## Next Recommended Action

执行 software-spec-plan.md 的 **A1 → A2 → A3**（领域模型 / 时间语义 / 标定模型，三者同源，建议一次会话完成）：

- **输入**：project map §6 + raw notes（TrackLab / Kinovea / Tracker / SLEAP / DLC 五套模型范本）
- **产出**：`docs/spec/data-model.md` 的术语表、对象关系与字段级建议、四层数据语义、时间语义章节、标定章节
- **验收**：plan A1/A2/A3 各自列出的书面问题全部有明确结论
- 完成后更新本文件；之后依次 **A4（含 ADR-0003）→ A6 → 勾选 §5 Readiness Criteria**。

Phase 1 正式实现（建 Issue `Phase 1.1` + 分支 + `pyproject.toml` 骨架）在 Readiness Criteria 全部勾选后才开始。
