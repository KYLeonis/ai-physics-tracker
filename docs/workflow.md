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
 ├─ Subphase 开始：写 mini-plan（Goal / Scope / AC / Slices）
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

- 花在计划上的时间是十几分钟，不是半天；执行中发现计划错了可以改，并在 Result 里注明。
- Acceptance Criteria（AC）每条都必须**可独立验证**："测试 X 通过"、"文档 Y 存在且覆盖 Z 问题"、"能在演示中做到 W"。禁止"更合理""优化一下"这类无法判定的表述。
- Scope 的"不做"列表同样重要——它是防止范围蔓延的主要工具。

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

### Self-review（每个 commit 前必做）

- [ ] diff 只包含本 Slice 范围内的改动
- [ ] 验证真实运行过，结果与声称一致
- [ ] 遵守 `CODE_STANDARD.md`（领域词汇表命名、分层依赖方向、错误处理语义）
- [ ] 遵守 `docs/development.md` §1.1 可移植性规则（`pathlib`、显式 UTF-8、无 symlink、Windows 保留名…）
- [ ] 新增公开接口/数据结构有 docstring 或文档说明
- [ ] 暂存区中没有视频/模型/大文件

### 独立 review（用一个全新的 Agent 会话）

**何时需要**：

- 触及数据格式、持久化、公共接口的改动；
- 数值算法正确性（坐标转换、微分、平滑）；
- 核心逻辑改动超过约 500 行；
- Subphase 收尾时包含关键设计决策。

**怎么做**：开一个新会话，只给它 review 模板（`docs/templates/review.md`）+ diff 范围 + 相关 spec/ADR 路径，**不给实现过程的叙述**（避免确认偏误）。Review 结论写回 subphase Issue 或 plan 的 Result 节。

## 7. 什么时候写 ADR

**写**：数据格式与持久化方案、公共模块划分、依赖引入与版本锁定、打包方案、数值方法选择——即所有"推翻成本会随时间上升"的决定（模板见 `docs/decisions/_template.md`）。

**不写**：内部实现细节、命名、一行 revert 即可撤销的选择。

判断句：**"三个月后推翻这个决定，要改几处代码？"** 超过两三处 → ADR。

## 8. 一个 Subphase 如何结束

1. 逐条核对 mini-plan 的 AC（真实运行，不是读代码确认）。
2. 需要独立 review 的，先完成并处理 findings。
3. **Integrate**：分支合并回 `main`（用 `--no-ff` 保留 subphase 边界），关闭 Issue，`git push`。
4. **Record**：需要 ADR 的决策补 ADR；roadmap / architecture.md 有变化则更新。
5. **更新 `docs/status/current.md`**（必做）：完成项移入 Recently Completed，填写 Next Recommended Action。
6. 在最终总结里向用户说明：完成了什么、验证结果、下一步建议；交付了用户可运行增量时，另附**交付说明**（见 §8.1）。

### 8.1 交付说明（可运行增量必附）

"用户可运行的增量"指本次收尾包含以下任一项：新增功能、改变现有行为、改变构建/运行方式（GUI 里程碑、新脚本、新工作流、依赖变化等）。此类收尾的最终总结除第 6 条外必须包含：

1. **运行方式**：环境与依赖要求、从零启动的完整命令序列；启动方式相对上一版有变化时，单独指出差异。
2. **新功能体验**：用户可感知的新增/变更点清单，每项给出具体操作步骤（入口在哪、执行什么命令或点击、预期看到什么）。

纯文档、注释、内部重构等无可感知变化的收尾免附；但构建或运行方式有变化时仍须包含第 1 项。

## 9. 如何进入下一个 Subphase

- 上一个 subphase 收尾完成、status 已更新 → 直接按 status 的 "Next Recommended Action" 开始，无需用户重复指示。
- 当前 Phase 的最后一个 subphase 完成 → 执行 AGENTS.md §11 阶段收尾流程 → **停止，等待用户指令**再进入下一 Phase。

## 10. GitHub 工作方式（单人 + Agent）

| 单位 | 载体 | 规则 |
| --- | --- | --- |
| Phase | milestone（**可选**） | 一个 Phase 的 subphase 超过 3 个时再考虑创建，不强制 |
| Subphase | **Issue** | Agent 负责创建与关闭；标题 `Phase 1.1 — data model core`；正文 = mini-plan |
| Slice | commit | Conventional Commits，落在 subphase 工作分支上 |
| Subphase 集成 | merge `--no-ff` → `main` → push | PR **可选**：想在 GitHub 页面看 diff、或配合独立 review 时使用 |

**明确不使用**：Project Board、Git Flow、长期存活的分支、强制 PR。

原则：GitHub 帮我们保存历史和开发状态，而不是增加管理负担。单人项目中 `main` 即集成分支；分支的生命周期 = 一个 subphase。

## 11. Agent 交接协议

### 会话进入（新 Agent 冷启动）

```text
1. Read AGENTS.md
2. Read docs/status/current.md            ← 不知道做什么时永远先读这个
3. Read relevant Phase/Subphase docs      ← roadmap 对应节 + subphase Issue/plan + spec
4. Inspect repository                     ← git log --oneline -15、目录、未提交改动
5. Continue                               ← 执行 status 的 Next Recommended Action
```

status 与仓库实际状态矛盾时，**以仓库为准**，先修正 status 再继续。**涉及写代码的任务，动手前另读 `CODE_STANDARD.md`**（含领域词汇表与 Agent 使用规则），并延续改动点附近代码的既有模式。

### 会话退出（每次会话结束必须完整执行）

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

## 12. 速查（一屏版）

```text
开始会话   读 AGENTS.md → docs/status/current.md → 相关文档 → git log
计划       Subphase = Issue + mini-plan（Goal/Scope/AC/Slices）
实现       Slice：一句话说得清、一个会话做得完、可独立验证
提交前     self-review checklist（§6）；关键改动另做独立 review
收尾       核对 AC → merge --no-ff → push → 更新 status → 写下一步
Phase 末   AGENTS.md §11 → 停止等待指令
```
