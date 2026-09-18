# Development Workflow — AI Physics Tracker

开发循环的完整说明书：Phase / Subphase / Slice 如何运转、如何测试与 review、GitHub 怎么用、Agent 会话之间如何交接。

- `AGENTS.md` 第 6 节只保留规则摘要，**细节以本文件为准**。
- 读者：人类开发者（可照着执行）与 Coding Agent（按规则执行）。

---

## 1. 三个层级

| 层级 | 是什么 | 规模 | GitHub 对应 |
| --- | --- | --- | --- |
| **Phase** | roadmap 中的大阶段（0–10），目标与验收标准在 `docs/roadmap.md` 中固定 | 数周–数月 | milestone（可选） |
| **Subphase** | Phase 内一个可独立验收的子目标，编号 `<phase>.<序号>`（如 1.1、1.2）；开始前写 mini-plan | 1–5 个开发会话 | Issue |
| **Slice** | 一次小步实现：单个会话内可完成、可独立验证的最小单元 | 数十–数百行改动，1–3 个 commit | commit |

一句话原则：**Subphase 是计划与验收的单位，Slice 是实现与提交的单位。**

## 2. 核心循环

```text
Phase（roadmap 定义，验收标准固定）
 │
 ├─ Subphase 开始：写 mini-plan（Goal / Agent Context Pack / Scope / AC / Slices / Review Gate）
 │    │
 │    ├─ Slice 循环：Implement → Verify → Self-review → Commit
 │    │   （重复，直到 mini-plan 的 Acceptance Criteria 满足）
 │    │
 │    └─ Subphase 收尾：独立 review（必要时）→ Integrate → Record → 更新 status
 │
 ├─ 下一个 Subphase …
 │
 └─ Phase 收尾：按 AGENTS.md §11（核对验收 → 同步文档 → 提交推送 → 停止等待指令）
```

## 3. 一个 Subphase 如何开始

1. 确定编号与主题，如 `Phase 1.1 — data model core`。编号一旦使用不复用；废弃的 subphase 在 Issue / status 中注明废弃原因。
2. 用 `docs/templates/subphase-plan.md` 写 **mini-plan**，内容放 GitHub Issue 正文（纯调研类 subphase 也可以是 `docs/` 下的计划文档，如 `docs/research/software-spec-plan.md`）。
3. 建工作分支：`feat/p<phase>.<sub>-<topic>`（如 `feat/p1.1-data-model`）。
4. Agent 可在征得用户同意的范围划分内自行完成以上动作；subphase 的**范围划分**（做/不做）不确定时先问用户。

**mini-plan 的要求**：

- 结构固定：Goal / **Agent Context Pack** / Scope / Acceptance Criteria / Slices / Verification / **Review Gate** / Result（模板：`docs/templates/subphase-plan.md`）。花在计划上的时间是十几分钟，不是半天；执行中发现计划错了可以改，并在 Result 里注明。
- Acceptance Criteria（AC）每条都必须**可独立验证**："测试 X 通过"、"文档 Y 存在且覆盖 Z 问题"、"能在演示中做到 W"。禁止"更合理""优化一下"这类无法判定的表述。
- Scope 的"不做"列表同样重要——它是防止范围蔓延的主要工具。
- **Review Gate 在计划期声明**：本 subphase 是否触发 Independent Review、是否建议 PR、是否适用 Human Review；不等实现完以后才临时决定（判定标准见 §6.2、§5.1、§10.2）。

### 3.1 Agent Context Pack

mini-plan 中的固定区域，充当**相关历史的索引与导航入口**，不是历史百科。目标：让没有本仓库记忆的 Agent 在几分钟内找到与本任务真正相关的文档、finding 与契约，而不需要通读 `docs/reviews/` 或全部 ADR。

| 小节 | 放什么 | 不放什么 |
| --- | --- | --- |
| Authoritative Docs | 当前 Phase requirements、master plan、相关 ADR / spec 路径 | 与本任务无关的文档清单 |
| Relevant Historical Findings | 与本任务真正相关的 Finding ID / Review Record，每项一句"为什么仍相关" | 全部历史 findings；无关 Phase 的记录 |
| Scientific / Data / Product Invariants | 本任务不能破坏的契约 | 整份 spec 的复制 |
| Known Deferred / Accepted Items | 影响本任务边界的已延期 / 已接受事项 | 已解决且不再相关的历史 |
| Explicit Non-goals | 本 Subphase 不应顺手解决的内容 | — |

示例（Phase 6 数值算法 subphase）：引用 ADR-0008、Pre-Phase 6 review 的 NaN 分段与 raw/derived 分离规则；不引入 Phase 5 的 AI 交互 finding。

维护规则：实现中发现新的相关 invariant / finding，随收尾回写本节与 `docs/status/current.md`；subphase 结束后 Context Pack 随 mini-plan 归档，不另行维护。

**Publication task 变体**：发布线上的任务不使用 Subphase mini-plan，而用同样思想的轻量 **Publication Context**（可写在任务描述或 `publication/STATUS.md` 的 Current Work 内）：Relevant manuscript / scientific goal、Relevant source commits、Scientific invariants、Required evidence、Non-goals。同样保持短小，只指向真正相关的历史与文档，不要求阅读整个 Review Archive。

## 4. 一个 Slice 多大比较合理

满足以下全部条件即为合适：

- 一个会话（Agent 约 1–2 小时工作量）内可完成**并验证**；
- 可以用一句话描述："实现 X，并让它通过测试 Y"；
- 典型形态：1 个新模块 + 对应测试，或 2–3 个文件的小改动。

**过大的信号**：一句话说不清；需要同时改动多个互不相关的模块；AC 里出现多个"并且"。拆分即可，拆分不需要请示。

## 5. Implement → Verify → Commit

- **Implement 前**：确认已读相关 spec / ADR / `docs/research/open-source-project-map.md` 对应小节（AGENTS.md §5 的要求）；写代码的任务另读 `CODE_STANDARD.md`。
- **Verify**：按 AGENTS.md §7 与 `docs/development.md` §5 执行——单元测试、解析合成数据（匀速/匀加速/单摆小角度）、GUI 项列出手动验收步骤。验证必须真实运行，不允许"应该能过"。
- **Commit**：Conventional Commits（AGENTS.md §9）。一个 Slice 通常 1 个 commit；提交前完成 §6 的 self-review。

### 5.1 GUI 交互的 Human Review

触发条件：本次交付包含**用户可感知的交互行为**——新增交互模式（点击、拖拽、快捷键）、体验质量属性（播放流畅度、缩放手感、视觉效果）、以及任何"自动化测试只能证明功能存在、无法判定好不好用"的场景。仅涉及数据结构、持久化、纯命令行行为时不触发。

Agent 动作（在自动化验证全绿之后、合并/收尾之前）：

1. 输出 Human Review 请求，包含三部分：
   - **启动命令**：从当前环境到可操作状态的最短路径（macOS 仓库已有 `.venv` 时直接给 `.venv/bin/python -m ai_physics_tracker` 这类命令，不要求重建环境）；
   - **验收步骤**：逐条"操作 → 预期看到什么"，只列本次增量相关的项，控制在 5 条以内；
   - **封闭式问题**：需要用户判断的事项用"是/否"或选项形式提问（例："缩放速度 1.25 倍/档是否偏慢？A 合适 B 偏慢 C 偏快"），减少用户输入成本。
2. **停止后续工作，等待用户亲自测试的反馈**。用户回复"通过"→ 继续收尾（合并/文档同步）；指出问题 → 修复并重跑自动化验证后，再次发起 Human Review，直到通过。
3. 用户明确表示"跳过本次"时，可在 Result 中记录"Human Review 被用户跳过"后继续。

硬性约束：

- **不得用 computer-use、截图或任何自动化手段替代真人测试**——目的之一是节省 token，且交互体验质量只有用户能判定；
- offscreen 自动化测试（pytest）照常执行，Human Review 是其**之上的补充关卡**，不替代它；
- Human Review 未通过且涉及代码改动时，走正常的 Slice 流程（含 self-review 与回归测试）。

## 6. Review

### 6.1 Self-review（每个 commit 前必做）

- [ ] diff 只包含本 Slice 范围内的改动
- [ ] 验证真实运行过，结果与声称一致
- [ ] 遵守 `CODE_STANDARD.md`（领域词汇表命名、分层依赖方向、错误处理语义）
- [ ] 遵守 `docs/development.md` §1.1 可移植性规则（`pathlib`、显式 UTF-8、无 symlink、Windows 保留名…）
- [ ] 新增公开接口/数据结构有 docstring 或文档说明
- [ ] 暂存区中没有视频/模型/大文件

### 6.2 Independent Review（独立审查，用全新的 Agent 会话）

**何时需要——按风险分级，在 mini-plan 的 Review Gate 中提前声明**：

High-risk（默认触发 Independent Review）：

- project schema / 持久化 / 公共数据契约的改动；
- timeline / 坐标 / 时间语义；
- 数值算法与科学计算——Phase 6 起明确包括：angular semantics、unwrap 与数值微分、周期检测、generalized derived-data 公共契约、拟合算法、拟合统计、参数不确定度、科学数据解释；
- Undo/Redo 事务语义；
- AI 结果激活、后台任务生命周期与并发；
- 打包与数据迁移。

Normal-risk（不默认触发）：

- 局部 GUI 改动、文案、小型内部重构、明确 bugfix、测试改进。

补充规则：

- Normal-risk 改动核心逻辑超过约 500 行、或 subphase 收尾包含关键设计决策时，仍考虑触发。
- 普通 UI 排版、文案、小型 glue code 不自动升级为完整 Independent Review。
- 拿不准时按触发处理，在 Review Gate 写一句理由；多一次 review 的成本低于漏检。
- **Publication 线加严**：发布线上任何可能改变论文所依据的数值、图表或科学结论的改动（θ/ω/α、filtering/smoothing、period、fitting、statistics、figure-source transformations 等）默认属 high-risk scientific change，触发 Independent Review + 重新验证；纯文档修改不加重流程。

**角色分工**：

- **Independent Reviewer 默认只读**：只产出 Findings 与结论，不修改产品代码（`src/`、`tests/`、`scripts/`），也不亲自修复自己提出的问题再自行宣布通过。"只读"不约束 Review Record 本身——Checklist、Findings、Review Log 与复审结论由 Reviewer 填写。
- **Main / Implementation Agent**：对每条 Finding 做 triage（修 / 不修）、实施修复、运行验证，并同步更新 Review Record。

**流程**：

```text
Implementation Agent
  → Independent Review Agent（新会话，只读）→ Findings
  → Main / Implementation Agent：逐条 Decision（Fix Now / Fix Before Close / Defer / Accept / Not Reproducible）
  → Fix + Verification
  → Independent Re-review（新的独立会话）
  → Final Verdict
```

**Review Record（长期可追溯记录）**：

- 首轮 review 会话开始时，以 `docs/templates/review.md` 为基础建立 `docs/reviews/phase-X.Y-review.md`；**一个 subphase 一个文件**，贯穿 Scope → Findings → Triage → Fixes → Verification → Re-review → Final Verdict 整个生命周期，不随轮次新建文件。索引见 `docs/reviews/README.md`。
- Reviewer 会话的输入保持最小：Review Record 模板路径 + diff 范围 + 相关 spec/ADR/plan 路径，**不给实现过程的叙述**（避免确认偏误）。
- Finding 使用稳定 ID（F1、F2…，按发现顺序编号，不复用；判定不成立的同样保留编号并记 Not Reproducible），逐条记录 Finding / Severity / Evidence / Impact / Recommendation / Decision / Status / Fix commit / Verification / Re-review result，字段定义见模板。
- **提出问题不等于必须修复**：理论性、低影响、低概率，或修复会明显过度工程的问题，明确记 `Accept` / `Defer` 并写一句理由。本项目是本地桌面科学软件，review 服务于工程质量，不做安全审计或 adversarial audit。
- 记录只保存工程轨迹——发现了什么、为什么修/不修、采用什么修复、对应哪个 commit、运行了什么验证、复审结果；不保存 Agent 思考过程或对话记录。
- 收尾对接：subphase Issue 的 Result 只链接 Review Record 并总结最终 Verdict，不复制完整 findings；`docs/status/current.md` 只记录是否通过与文档路径。
- PR 保持可选；High-risk subphase 建议以 PR 作为完整 diff 的观察与集成容器（§10.2），不做形式审批。

### 6.3 Historical Findings 的继承（Relevant-history inheritance）

- Review Record 中的 `Closed` 表示"**在当时 commit 与证据下**关闭并经复审确认"，不是对当前代码的永久证明。
- 新 Agent 不需要重新审查所有 Closed findings；但当前工作再次触及同一 invariant 时，必须通过 mini-plan 的 Context Pack 引用相关 Finding ID / Review Record 作为审查输入。
- 避免两个极端：把历史全部忘掉；要求每个 Agent 重读全部历史。目标是**相关历史的继承**。
- 先例：Pre-Phase 6 review 曾核实 5.5 review B3 的"已修复"记录与 `main` 实际不符（P6R-04）——Closed 标签不能替代对当前代码的核查。

## 7. 什么时候写 ADR

**写**：数据格式与持久化方案、公共模块划分、依赖引入与版本锁定、打包方案、数值方法选择——即所有"推翻成本会随时间上升"的决定（模板见 `docs/decisions/_template.md`）。

**不写**：内部实现细节、命名、一行 revert 即可撤销的选择。

判断句：**"三个月后推翻这个决定，要改几处代码？"** 超过两三处 → ADR。

## 8. 一个 Subphase 如何结束

1. 逐条核对 mini-plan 的 AC（真实运行，不是读代码确认）。
2. 需要独立 review 的，先完成并处理 findings，Review Record 收口（全部 finding Closed、Final Verdict 已记录），并在 Issue Result 中链接该记录（§6.2）。
3. **Integrate**：分支合并回 `main`（用 `--no-ff` 保留 subphase 边界），关闭 Issue，`git push`。
4. **Record**：需要 ADR 的决策补 ADR；roadmap / architecture.md 有变化则更新。
5. **更新 `docs/status/current.md`**（必做）：完成项移入 Recently Completed，填写 Next Recommended Action；实现中确认的新 invariant / finding 写入 Active Constraints / Relevant Risks。status 是运行时入口不是历史日志——与当前工作无关的条目随手移出（历史已在 roadmap / reviews / git 中）。
6. 在最终总结里向用户说明：完成了什么、验证结果、下一步建议；交付了用户可运行增量时，另附**交付说明**（见 §8.1）。

### 8.1 交付说明（可运行增量必附）

"用户可运行的增量"指本次收尾包含以下任一项：新增功能、改变现有行为、改变构建/运行方式（GUI 里程碑、新脚本、新工作流、依赖变化等）。此类收尾的最终总结除第 6 条外必须包含：

1. **运行方式**：环境与依赖要求、从零启动的完整命令序列；启动方式相对上一版有变化时，单独指出差异。
2. **新功能体验**：用户可感知的新增/变更点清单，每项给出具体操作步骤（入口在哪、执行什么命令或点击、预期看到什么）。

纯文档、注释、内部重构等无可感知变化的收尾免附；但构建或运行方式有变化时仍须包含第 1 项。

## 9. 如何进入下一个 Subphase

- 上一个 subphase 收尾完成、status 已更新 → 直接按 status 的 "Next Recommended Action" 开始，无需用户重复指示。
- 当前 Phase 的最后一个 subphase 完成 → 执行 AGENTS.md §11 阶段收尾流程 → **停止，等待用户指令**再进入下一 Phase。

## 10. Git / PR / 分支保护（单人 + Agent）

### 10.1 载体

| 单位 | 载体 | 规则 |
| --- | --- | --- |
| Phase | milestone（**可选**） | 一个 Phase 的 subphase 超过 3 个时再考虑创建，不强制 |
| Subphase | **Issue** | Agent 负责创建与关闭；标题 `Phase 1.1 — data model core`；正文 = mini-plan |
| Slice | commit | Conventional Commits，落在 subphase 工作分支上 |
| Review | `docs/reviews/phase-X.Y-review.md` | 触发独立 review 的 subphase 一个文件（§6.2）；Issue Result 只链接并总结 Verdict |
| Subphase 集成 | merge `--no-ff` → `main` → push | PR 可选；High-risk 建议以 PR 作为完整 diff 容器（§10.2） |

**明确不使用**：Project Board、Git Flow、长期存活的分支（唯一例外见下）、强制 PR、CODEOWNERS、大量标签 / 状态管理。

原则：GitHub 帮我们保存历史和开发状态，而不是增加管理负担。单人项目中 `main` 即**通用产品线**的集成分支；产品分支的生命周期 = 一个 subphase（论文发布线见下与 §10.4）。

**论文发布线例外**：`publication/*`（当前 `publication/ejp-damped-pendulum`）是唯一许可的长期分支，用于论文复现基线、审稿修订与出版归档；其 scope、同步与发布策略以 `publication/README.md` 为 authoritative owner，运行时状态入口为 `publication/STATUS.md`。通用缺陷修复仍按正常流程在 `main` 上完成并验证，再按 §10.4 受控同步到发布线；发布线永不反向驱动 `main` 的范围。

### 10.4 Dual-worktree 与 main → publication 同步

项目有两个长期 worktree，各自绑定一条工作线：

| Worktree | 分支 | 角色 | 运行时状态入口 |
| --- | --- | --- | --- |
| `ai-physics-tracker/` | `main` | 通用产品开发线（Phase → Subphase → Slice） | `docs/status/current.md` |
| `ai-physics-tracker-ejp/` | `publication/ejp-damped-pendulum` | EJP 论文 / 复现线 | `publication/STATUS.md` |

**开工门（必须执行）**：

```bash
pwd
git branch --show-current
git status
```

- 任务指派应写明 `Worktree / Expected branch / Role`；三者与实际不符时**停下询问用户，不在错误 worktree 中自行切分支继续工作**。
- 两个 status 文件各管各的线，不互相覆盖、不机械同步（§6 的共享治理文档除外）。

**同步规则（main → publication，单向）**：

- 通用 bug 与核心算法修复**先在 `main` 修复并验证**（保持测试与 CI 覆盖），再同步到发布线。
- 优先使用可追踪的 Git 操作（**cherry-pick**）；不默认 merge 整个 `main`，禁止用 Finder 手工复制源码作为同步方式。
- 每次同步在 `publication/STATUS.md` 的 Relevant Source Commits 记录：**source commit**、**为什么论文需要**、**发布线上重新做了什么验证**。
- 两个 worktree 各自保持 clean；同步在发布线 worktree 内进行，不把 `main` worktree 切到发布分支。

### 10.2 风险分级流程

**Normal-risk**（局部 GUI、文案、小型内部重构、明确 bugfix、测试改进）：

```text
branch → slices → verify →（review 如 Review Gate 触发）→ --no-ff merge main → push
```

**High-risk**（schema / 持久化 / 公共数据契约、timeline / 坐标语义、数值算法与科学计算、拟合 / 不确定度、Undo/Redo 事务语义、AI 结果激活、后台生命周期 / 并发、打包 / 迁移）：

```text
branch → slices → verification → Independent Review → fixes → re-review
→（建议）PR 作为完整 diff 的观察与集成容器 → main → push
```

- PR 的角色：**高风险完整 diff 的观察与集成容器**，不是形式审批；不设 required approvals，不因 PR 引入多人流程。
- 风险等级在 mini-plan 的 Review Gate 声明（§3）；实现中发现风险升级（如顺带触及 schema）时，补触发相应 review 并在 Result 注明。

### 10.3 main 分支保护（建议记录，不自动改 settings）

- 现状（2026-09-18 核实）：`main` 无 branch protection。
- 建议保持的最低配置：**prohibit force push、prohibit branch deletion**。
- 现阶段不引入：required approvals、required signed commits、blanket required PR、CODEOWNERS。
- Release Mode（Phase 9 / release candidate）再重新评估 required CI + required PR。
- 修改 GitHub repository settings 属用户人工操作，Agent 不代为变更。

## 11. Agent 交接协议

### 11.1 冷启动协议（Cold-start Protocol 2.0）

```text
0. Confirm worktree                       ← pwd、git branch --show-current、git status
                                            （与本任务的 Worktree / Expected branch / Role 一致，§10.4）
1. Read AGENTS.md
2. Read docs/status/current.md            ← 现在在哪、下一步、Active Constraints
                                            （publication worktree 内改读 publication/STATUS.md）
3. Read current Phase requirements        ← docs/spec/phaseN-requirements.md
4. Read current Phase master plan         ← subphase 顺序与决策门
5. Read current Subphase mini-plan        ← Goal / Context Pack / Scope / AC / Review Gate
6. Read Context Pack 引用的材料           ← 只读被引用的 ADR / finding / spec 小节
7. Inspect repository                     ← git status、git log --oneline -15、未提交改动
8. Read CODE_STANDARD.md                  ← 写代码的任务，动手前
9. Implement                              ← 执行状态入口的 Next Action
```

- **不要求默认阅读所有历史 Review Records / ADR**——由 mini-plan 的 Context Pack 指向真正相关的材料（§3.1）。
- **轻量任务允许裁剪**：局部 bugfix、文案、文档小改走"状态入口 → 相关文件 → 仓库检查"即可；不因当前 Phase 是高风险科学开发就被迫走完整 review / PR 流程。
- 身处**错误 worktree** 时停下询问用户，不自行切分支继续工作（§10.4）。
- status / mini-plan / 仓库状态矛盾时：**repository reality wins** → 先修正过期文档 → 继续。

### 11.2 Agent 自主权边界

- **Agent 可自行决定**：Slice 拆分、内部实现方式、测试组织、小型 helper / module 提取、finding 的技术修复实现。
- **必须由用户决定**：Phase scope、Acceptance Criteria 改变、产品行为重大改变、新 scientific meaning、新 dependency / framework、incompatible data format、accepted / deferred risk 改判、release policy。
- Agent 不应因为发现"可以更漂亮"就扩展范围。项目级清单见 `AGENTS.md` §6"何时必须暂停 / 何时可自行决定"，本节是同一原则的执行口径。

### 11.3 会话退出（每次会话结束必须完整执行）

```text
1. Run verification          ← 测试 / AC 核对
2. Summarize changes         ← 面向用户、可读懂的总结
3. Update docs/status/current.md
4. Update relevant docs
5. Record important decisions（必要时写 ADR）
6. Commit（subphase/phase 收尾须 push）
7. State the exact next recommended action
```

不允许"代码写完了但 status 没更新"就结束会话——status 过期等于交接断链。

## 12. Source of Truth 分工

一个事实尽量只有一个 authoritative owner；其他文档用链接与简要摘要引用，不复制完整内容。发现同一事实两处不一致时，按下表修正另一处，而不是两边各改一点。

| 信息 | 权威来源 |
| --- | --- |
| 长期产品路线 | `docs/roadmap.md` |
| 当前阶段科学 / 产品需求 | Phase requirements（`docs/spec/phaseN-requirements.md`） |
| Phase 内 Subphase 顺序 | Phase master plan（`docs/status/phase-N-plan.md`） |
| 当前正在做什么 / 下一步 | `docs/status/current.md`（main 线）；`publication/STATUS.md`（发布线） |
| Subphase scope / AC | mini-plan（Issue 或 `docs/status/phase-N.M-plan.md`） |
| 不可逆架构决策 | ADR（`docs/decisions/`） |
| Review finding 生命周期 | Review Record（`docs/reviews/`） |
| Slice 实现历史 | Git commits |
| 论文发布线（`publication/*`）策略 | `publication/README.md` |
| 自动验证 | CI / tests |
| GUI 真实体验 | Human Review |

## 13. Development Modes

流程强度随项目成熟度变化。这是指导性说明，**不新增状态机或持久化项目状态**；当前模式随 Phase 立项由用户宣布，记录在 `docs/status/current.md`。

| Mode | 何时 | 流程特征 |
| --- | --- | --- |
| **Build Mode** | Phase 6–8 主要模式（当前） | 快速 Slice、risk-based review、PR optional |
| **Stabilization Mode** | 大 Phase 收尾 / release 前 | regression 优先、不扩大 scope、fresh review |
| **Release Mode** | Phase 9 / release candidate | CI / 打包 / 迁移更严格；可启用 required PR / required CI；release checklist |
| **Maintenance Mode** | release 后 | bug / compatibility / hotfix，最小流程 |

Agent 不自行切换模式；发现当前工作性质与模式不符时（如 Build Mode 中进入 release 前回归集中期），向用户建议切换。

## 14. 速查（一屏版）

```text
开始会话   AGENTS.md → current.md → Phase spec/plan → mini-plan Context Pack → git log（轻量任务可裁剪）
计划       Subphase = Issue/mini-plan（Goal/Context Pack/Scope/AC/Slices/Review Gate）
实现       Slice：一句话说得清、一个会话做得完、可独立验证
提交前     self-review（§6.1）；High-risk 触发 Independent Review（§6.2，记录 docs/reviews/）
集成       Normal: --no-ff merge；High: review 收口后 merge，PR 作完整 diff 容器（§10.2）
收尾       核对 AC → Review Record 收口 → merge → push → 更新 status → 写下一步
Phase 末   AGENTS.md §11 → 停止等待指令
```
