# AGENTS.md

本文件面向在本仓库工作的 Coding Agent（以及人类开发者），帮助其快速理解项目并按统一规范继续开发。请保持本文件简洁、随项目进展持续更新。

**架构接手必读**：[当前架构总览](docs/architecture.md#当前架构总览接手先读) → [重构进度与已淘汰做法](docs/status/architecture-progress.md) → [本轮状态 / 下一步](docs/status/current.md)。每次重构完成须同步对应计划 / Review、进度表及受影响架构关系；实现完成、待HR、已合并分开标记。历史HTML / notes不覆盖当前代码、ADR和此入口。

## 1. 项目长期目标

AI Physics Tracker 是一个面向物理实验、运动学分析、视频测量和科学教育的**桌面视频跟踪与数据分析平台**：

- 技术基础：DeepLabCut 3.x（PyTorch 路线）+ 传统运动学分析工作流
- 核心体验：用户标注少量代表帧 → AI 训练/微调 → 自动跟踪整段视频 → 修正困难帧 → 再训练 → 高质量运动轨迹 → 物理量计算与导出
- 首次 GUI 学习需当前轨迹 20 个不同人工帧；默认选帧 20 / K-means，推荐框可自定义算法；推荐标注沿真实选帧结果连续推进。已有成功训练的轨迹沿用原再训练门槛，教师模型自检 / 推理不要求先训练（2026-10-13 Human Review 通过，已集成 main）。
- 最终形态：面向普通 Windows 用户的桌面安装程序（无需配置 Python 环境）
- 通用分析口径：**用户提供方程 / 公式，平台完成计算与后续分析**；论文线硬编码 ODE 只作复现参考（ADR-0017），不直接作为 main 的分析架构。
- 基准实验：**单摆**（早期重点测试案例，用于建立算法、数据处理与工作流基准）

## 2. 当前 Roadmap（概要）

| 阶段 | 名称 | 一句话目标 |
| --- | --- | --- |
| Phase 0 | Project Initialization | 仓库、文档、Git 初始化（✅ 已完成） |
| Phase 1 | Project & Data Foundation | Project / Video / Track / Annotation / Calibration 数据体系（✅ 已完成） |
| Phase 2 | Video Analysis MVP | 可用的 GUI + 视频播放 + 手工标记 + 项目保存（✅ 已完成，2026-08-30；Windows 真机验收延后） |
| Phase 3 | Calibration & Physics Engine | 标定、坐标系、运动学计算、基础图表（✅ 已完成，2026-08-31） |
| Phase 4 | Deep Learning Tracking | 接入 DeepLabCut/PyTorch：标注→训练→跟踪（✅ 已完成，2026-09-01；Windows/CUDA 延期至 Phase 9 前） |
| Phase 5 | AI-assisted Annotation & Refinement | 代表帧、困难帧、人工修正、迭代比较、交互重构（✅ 已完成，2026-09-18；AC-9 改善目标明示归档） |
| Phase 6 | Advanced Physics Analysis | θ/ω/α、相图、周期分析、拟合、误差分析（🔄 6.1 / 6.2 完成并集成 main；独立复审 / 双平台 CI / 全部 Human Review 通过，2026-10-15；6.3已按 ADR-0017 完成计划冻结，S0–S4已实现，S5自动Gate及整体HR已通过（2026-10-16），已以92d00a2集成main；6.3.1已完成并于2026-10-17通过用户HR，以c0d1461集成main；本机1232项 / 双平台CI / R6独立复审通过；公式拟合联动维护增量于2026-10-18通过HR，以aa86d79集成main（全量1271 / 独立复审 / 双平台CI通过）；计算配方统一解释内部整理于2026-10-18以26af812集成main（全量1276 / 独立复审 / 双平台CI通过）；重复间隔联动R03于2026-10-18通过全部HR并以2600f2a集成main（独立复审 / 双平台CI通过，拖线跳顶F1 Closed）；R04分析主干于2026-10-18本轮HR通过，以085219e集成main（本机1316 / 独立 / 双平台通过，F1 Closed）；R07工程变更与界面更新方案已由用户搁置、未实施，R08历史查看于2026-10-20本轮HR通过，以f34d3b8集成main（本机1329 / 独立R2 / 双平台通过，F1 Closed）；P6.4 v1.1于2026-10-26全部HR通过，以e31a4ac集成main（最终源码9c1aa63 / 独立R3 / 双平台各1412 passed、2个既有可选skip，F1–F8 Closed）；6.5未开始） |
| Phase 7 | Model Library | 模型保存、版本管理、应用到新视频 |
| Phase 8 | Export & Scientific Workflow | CSV/Excel/图表/视频导出、项目归档 |
| Phase 9 | Optimization & Packaging | 性能优化、GPU、Windows 打包发布 |
| Phase 10 | Extended Capabilities | 多目标/多关键点/多相机/3D/插件等（范围待定） |

完整版本（目标、交付物、验收标准、技术风险）见 `docs/roadmap.md`。

**首个可交付目标已冻结（2026-10-26）**：[Mac教学试用目标](docs/spec/first-deliverable-target.md)为跨阶段优先级入口。文档 / MIT收口已完成；随后按6.5→最小科学导出与四类合成核查→Mac试用包 / 教程 / 离线验证→一名独立用户完成真实单摆任务推进，完整模型库随后排。目标冻结不等于已实施，6.5未开始。

**P6.5待整体确认（2026-10-26）**：[mini-plan v0.4](docs/status/phase-6.5-plan.md)的Q1–Q10设计分支已闭合，Q11共同理解待答，未冻结 / 实施。双线验收、周期各自≤5%、用户人工标注 / 必要修正、新AI最终轨迹达标、最多两次训练及拟合 / 首训配置均已明确，本期Stabilization Mode；原P011冻结参考保持。

## 3. 预期技术栈

```text
OS:          首轮 Mac arm64 教学试用；长期 Windows 10/11 64-bit；开发亦可在 Linux
Python:      3.11–3.12（CI 3.11，本机开发3.12.13）
AI:          PyTorch（先装 PyTorch 再装 deeplabcut）
Tracking:    DeepLabCut 3.x，PyTorch 引擎
GUI:         PySide6 / Qt（已采用）
Video:       OpenCV、FFmpeg
Sci Comp:    NumPy、SciPy、Pandas
Plotting:    PyQtGraph（交互）、Matplotlib（导出）
Packaging:   PyInstaller / Nuitka + Inno Setup / NSIS（Phase 9 决定）
```

版本依据与安装注意事项见 `docs/development.md`。

## 4. 项目目录说明

```text
.
├── README.md            # 面向所有人的项目介绍
├── AGENTS.md            # 本文件：Agent 开发指南
├── CODE_STANDARD.md     # 代码规范（写任何代码前先读）
├── LICENSE              # 原创软件 MIT；第三方边界见 docs/licensing.md
├── docs/                # 项目文档
│   ├── roadmap.md       # 详细路线图（各阶段目标/交付物/验收标准/风险）
│   ├── architecture.md  # 高层架构设计
│   ├── development.md   # 开发环境、版本选择、跨平台规则
│   ├── workflow.md      # 开发循环说明书（Phase/Subphase/Slice，细则）
│   ├── status/current.md # 当前状态：阶段/任务/下一步（会话先读、收尾必更）
│   ├── templates/       # subphase 计划与 review 模板
│   ├── reviews/         # 独立 review 记录（每 subphase 一个 Review Record）
│   ├── notes/           # 交互与体验记录、改进草案（非规范类观察）
│   └── decisions/       # 架构决策记录（ADR）
├── src/                 # 源代码（Phase 1 起填充）
├── tests/               # 测试（Phase 1 起填充）
├── scripts/             # 开发辅助脚本
├── resources/           # 应用资源（图标、UI 文件等）
├── examples/            # 示例工程/用法（不含大型视频）
└── packaging/           # Mac教学试用 / 后续Windows打包入口
```

## 5. 文档位置

- **当前状态（不知道做什么先读这个）**：`docs/status/current.md` —— 由每个开发会话结束时更新
- **论文发布线（publication worktree 内）**：`publication/README.md`（策略 / scope / 发布流程）、`publication/STATUS.md`（论文线当前状态入口）
- **代码规范（写代码前必读）**：`CODE_STANDARD.md` —— 命名（含领域词汇表）、分层、类型、错误处理、数值代码、跨平台、测试风格
- 开发循环细则（Phase/Subphase/Slice、review、GitHub、Agent 交接）：`docs/workflow.md`
- 路线图：`docs/roadmap.md`
- 已冻结首发目标：`docs/spec/first-deliverable-target.md`（Mac教学试用、交付范围 / 顺序 / 完成标准）；许可边界：`docs/licensing.md`；取舍记录：`docs/notes/first-deliverable-interview.md`
- 架构设计：`docs/architecture.md`
- 开发环境与工作流：`docs/development.md`
- Phase 1 数据体系规范（**实现前必读**）：`docs/spec/data-model.md`（领域模型/时间语义/标定/最小接口）、`docs/spec/project-format.md`（持久化与项目目录）、`docs/spec/phase1-requirements.md`（Phase 1 需求与验收标准）
- Phase 2 视频/GUI 规范：`docs/spec/phase2-requirements.md`；技术栈与分层决策见 ADR-0005
- Phase 5 规划入口：`docs/spec/phase5-requirements.md`（需求与边界）、`docs/status/phase-5-plan.md`（Subphase 顺序与验收）
- Phase 6 规划入口：`docs/spec/phase6-requirements.md`、`docs/status/phase-6-plan.md`、`docs/status/phase-6.1-plan.md`、`docs/status/phase-6.2-plan.md`、`docs/status/phase-6.3-plan.md`（6.1 / 6.2已集成main；6.3计划已获用户认可，显式函数拟合 / 通用重复间隔工具，S0–S4已实现，S5自动Gate及整体HR已通过（2026-10-16），已以92d00a2集成main。ADR-0019/0020为既有数据契约；ODE / 单位管理 / 参数置信区间后续）
- Phase 6.3.1 新手分析计划：`docs/status/phase-6.3.1-plan.md`（Q1–16已认可，英文 / 图表优先；自动预览 / 初值建议 / 解释 / 尝试日志及就地准备，S0–S4实现、S5已完成并于2026-10-17通过用户HR，以c0d1461集成main；本机1232项 / 双平台CI / R6独立复审通过；不设固定响应或新手完成时限）。访谈事实见`docs/notes/analysis-onboarding-interview.md`。
- Phase 6.4 参数误差解释：`docs/status/phase-6.4-plan.md`（v1.1已完成，2026-10-26全部用户HR通过，e31a4ac集成main并push；Issue #42 Closed / PR #43 Merged；独立R3 / 最终产品9c1aa63双平台各1412 passed、2个既有可选skip通过，F1–F8 Closed。仅未平滑位置 / 角度源支持参数SE及95%局部t区间，四列 / 可拖动面板 / hover / Fixed整格及空格交互；换算结果仅数值、重复间隔仅补解释，新增两轨迹比较取消。6.5完整单摆验收仍未开始；证据以current为准）。
- 后续回移档案：`docs/status/main-backport-backlog.md`（含执行触发点，后续会话必须随相关阶段核对）
- 当前维护补丁：`docs/status/automatic-timing-plan.md`（2026-10-17用户授权取消Review timing / Yes；ADR-0024将原合格Near-CFR的人工接受改为自动，保留探测与来源；2026-10-17独立review / 双平台CI / 本轮HR均通过，已集成main，详情以current.md为准）。
- 分析主干职责重构R04：`docs/status/analysis-workflow-plan.md`（全部实现 / 自动Gate / 本轮HR完成，085219e集成main；ADR-0027，源码 / 测试与bd848f1一致，本机1316 / 独立Approve / 双平台通过，F1 Closed）。
- 下一轮架构建议R07：`docs/status/change-notification-proposal.md`（工程变更与界面更新链路，含T01–T08；用户认为使用无必要已搁置，不实施；历史剩余项复核见`docs/notes/glm-remaining-review-2026-10-18.md`；后续R08状态以current.md及专用方案为准）。
- 历史查看R08：`docs/status/signal-history-plan.md`（2026-10-20用户本轮HR“通过”，f34d3b8集成main；源码 / 测试与703ac81一致，定向121 / 全量1329 / 独立R2 Approve / 双平台 / HR通过，F1 Closed；SignalHistory生命周期集中、两个执行器及ADR-0023保留，试用启动器保留；完成状态以current.md / Review为准）。
- 草稿上下文R09：`docs/status/draft-context-plan.md`（2026-10-24 c14c78a集成main；源码 / 测试与ad00f9c一致，定向124 / 全量1337 / 两独立Agent Approve / 双平台通过，无新交互不设HR；analysis_draft_context拥有草稿导航事实与迟到判定，分析簇私有穿越清零；signal_history六个遗留panel私有访问待后续清理）。
- 计算配方统一解释内部整理：`docs/status/source-recipe-plan.md`（2026-10-18以26af812集成main；source_recipe共用事实 / 读写，chart_recipe保留图表策略与兼容导入；旧 / 未知源保护不变）。
- 公式拟合联动维护增量：`docs/status/fit-linked-source-plan.md`（2026-10-18本轮HR通过，aa86d79已集成main；ADR-0025，所选轨迹源自动补齐 / 预览联动；后续计算配方统一已以26af812集成，重复间隔联动已以2600f2a集成；各项完成证据见architecture-progress.md）。
- GLM派工前读`docs/notes/glm-collaboration-playbook.md`：项目内协作约束、可复现问题与接管证据；原始运行日志不入库。
- 模板：`docs/templates/`（subphase 计划、review）
- 独立 review 记录（Review Record）：`docs/reviews/`（索引见其 README；生命周期规则以 `docs/workflow.md` §6 为准）
- 实现参考与前期调研（开源生态地图）：`docs/research/open-source-project-map.md` —— 实现任何模块前先读其对应小节；各项目源码级细节见 `docs/research/raw/`，仓库快照与校验规则见 `docs/research/README.md`
- 架构决策记录（ADR）：`docs/decisions/NNNN-*.md`（模板见 `docs/decisions/0001-record-architecture-decisions.md`）
- 各顶层目录内有 `README.md` 说明该目录的用途与约定

## 6. 开发循环与 Agent 交接（细则见 `docs/workflow.md`）

**会话进入协议（Cold-start Protocol 2.0，细则见 `docs/workflow.md` §11.1）**：

0. **确认 worktree**：`pwd`、`git branch --show-current`、`git status`，与本任务指派的 Worktree / Expected branch / Role 一致（dual-worktree 规则见 `docs/workflow.md` §10.4）；身处错误 worktree 时停下询问用户，不自行切分支继续工作。
1. 顺序阅读：本文件 → 状态入口（main 线 `docs/status/current.md`；发布线 `publication/STATUS.md`）→ 当前 Phase requirements → Phase master plan → 当前 Subphase mini-plan（含 **Agent Context Pack** 与 **Review Gate**）→ Context Pack 引用的 ADR / finding → 检查仓库（`git status`、`git log --oneline -15`、未提交改动）。
2. 涉及写代码的任务：动手前再读 `CODE_STANDARD.md` 并延续改动点附近代码的既有模式（规范与附近代码冲突时按 CODE_STANDARD.md §1 处理）。
3. 不要求默认通读全部历史 Review Records / ADR——由 mini-plan 的 Context Pack 指向真正相关的材料；轻量任务（局部 bugfix、文案、文档小改）可裁剪为 current.md → 相关文件 → 仓库检查。
4. 执行 status 文件中的 "Next Recommended Action"；若 status 与仓库实际状态矛盾，以仓库为准并先修正 status。

**开发循环**：

```text
Explore → 需要时 Plan（subphase mini-plan：Goal / Context Pack / Scope / AC / Slices / Review Gate）
→ 以 Slice 小步实现 → Verify（测试）→ Self-review
→ Review Gate 声明的 review（Independent / PR 容器 / Human，按风险分级，workflow §10.2）
→ Commit / Integrate → 更新 status → Next
```

**不变式**：数据先行（手工/AI 跟踪统一数据体系，Phase 1 核心目标）；代码进 `src/`、测试进 `tests/`、大文件不入库；重大选型记 ADR（§10）；mini-plan 必含 Agent Context Pack 与 Review Gate，流程强度按 Development Mode 调节（`docs/workflow.md` §13，当前模式以`docs/status/current.md`为准）；独立 review 的 Reviewer 默认只读，findings 由实现方处置并记入 `docs/reviews/`（细则见 `docs/workflow.md` §6）；完成当前 Phase 后暂停等待下一条指令。

**何时必须暂停并询问用户**：

- 超出当前 Phase/Subphase 范围的改动，或需要修改验收标准本身
- 引入新依赖、替换技术选型、不兼容的接口/数据格式变更（通常同时需要 ADR）
- 删除数据、重写 Git 历史、影响 License 的操作
- spec/roadmap 中已有预期结论，而实际调研结论相反时

**何时可自行决定**（在既有 ADR/spec/roadmap 约束内；执行口径见 `docs/workflow.md` §11.2）：

- 实现细节、命名、文件组织、测试写法、文档措辞、bug 的具体修复方式、Slice 拆分

**会话退出协议**（每次会话结束必须完整执行）：

1. 运行验证（测试 / 验收标准核对）；2. 向用户总结变更（交付可运行增量时，附运行方式与新功能体验步骤，细则见 `docs/workflow.md` §8.1）；3. 更新 `docs/status/current.md`（必做）；4. 同步相关文档；5. 记录决策（必要时 ADR）；6. 按规则提交（subphase/phase 收尾须 push）；7. 在 status 中写出确切的"下一步建议动作"。

## 7. 测试和验证要求

- Phase 1 起引入 pytest；核心数据结构（project/track/annotation/calibration）与物理计算（坐标转换、微分、平滑）必须有单元测试。
- 涉及数值计算的模块测试需使用已知解析解的合成数据（如匀速/匀加速/单摆小角度）。
- GUI 功能以手动验收为主，逻辑尽量从 GUI 层剥离以便测试。
- **GUI 交互的 Human Review**：交付增量包含用户可感知的交互行为（新增交互模式、播放/缩放手感、视觉效果等自动化测试无法判定体验的场景）时，Agent 必须在合并/收尾前发起 Human Review：给出从零启动命令（macOS 已有 `.venv` 时直接给最短命令）、逐条测试步骤（操作 → 预期）、需要用户回答的封闭式问题，然后**停止并等待用户亲自测试的反馈**。不得用 computer-use 或截图自检替代真人测试（节省 token；体验质量只有用户能判定）；offscreen 自动化测试照常执行，Human Review 是其上的补充关卡。细则见 `docs/workflow.md` §5.1。
- Phase 1 领域模型与持久化已有 pytest 覆盖；验证命令为 `python -m pytest`，GitHub Actions 使用 macOS/Windows Python 3.11 双平台运行。

## 8. Git 工作方式

- 默认分支：`main`
- 远程：`origin` → `KYLeonis/ai-physics-tracker`（GitHub，Public；2026-09-18 核实，早期为 Private）
- 认证已配置完成（2026-08-27）：HTTPS 凭据存于 macOS 钥匙串（OAuth token，scope: repo/workflow），`git push` / `git pull` 可直接使用；如凭据失效，通过 GitHub OAuth 设备授权流程重新获取（在 GitHub → Settings → Applications 中可查看/撤销）。
- 提交到 `main` 前在工作分支开发（`feat/p<phase>.<sub>-<topic>`，如 `feat/p1.1-data-model`；杂项用 `fix/<topic>` / `docs/<topic>`）；小规模文档同步可直接提交到 `main`。分支生命周期 = 一个 Subphase，收尾时 `--no-ff` 合并回 `main`（见 `docs/workflow.md` §10）；唯一例外是论文发布线 `publication/*`（长期分支，策略以 `publication/README.md` 为准）。
- 改动按风险分两档流程（判定与细则见 `docs/workflow.md` §10.2，在 mini-plan 的 Review Gate 提前声明）：**Normal-risk**（局部 GUI、文案、小型内部重构、明确 bugfix、测试改进）走 branch → slices → verify → `--no-ff` merge；**High-risk**（schema/持久化、公共数据契约、坐标/时间语义、数值算法与科学计算、拟合/不确定度、Undo/Redo 事务、AI 结果激活、后台生命周期/并发、打包/迁移）预声明 Independent Review，并建议以 PR 作为完整 diff 的观察容器。PR 始终可选，不做强制审批。
- 项目有两个长期 worktree：`ai-physics-tracker/` → `main`（通用产品线），`ai-physics-tracker-ejp/` → `publication/ejp-damped-pendulum`（论文线）。main → publication 用 **cherry-pick** 受控同步（先在 main 修复验证），每次同步在 `publication/STATUS.md` 记录 source commit / 为什么论文需要 / 重新做了什么验证；不默认 merge 整个 main，不用文件复制充当同步。细则见 `docs/workflow.md` §10.4。
- main 分支保护：当前未启用（2026-09-18 核实）；建议最低配置为 prohibit force push / prohibit branch deletion，Release Mode（Phase 9）再评估 required CI / required PR。修改 GitHub settings 由用户人工执行，Agent 不代改。
- **每个 Phase 的收尾提交完成后必须 push 到 origin**，保证远程始终反映最新项目状态。
- 提交信息使用 Conventional Commits（见第 9 节）。
- 严禁提交：视频、模型权重、训练数据集、虚拟环境、构建产物（`.gitignore` 已覆盖，新增大文件类型时同步更新 `.gitignore`）。

## 9. 提交规范

Conventional Commits：`<type>: <description>`，例如：

```text
feat: add project data model and persistence layer
fix: correct frame index off-by-one in timeline
docs: expand Phase 1 roadmap acceptance criteria
chore: initialize AI Physics Tracker project
refactor: extract coordinate transform from calibration module
test: add pendulum synthetic data tests for kinematics
```

常用 type：`feat` / `fix` / `docs` / `refactor` / `test` / `chore` / `perf`。描述使用英文或中英混合均可，但需清晰表达意图。

## 10. 如何记录新的架构决策

重要技术选型（框架替换、数据格式、模块划分变更、打包方案等）需要新增 ADR：

1. 复制 `docs/decisions/_template.md`（或参照 0001）创建 `docs/decisions/NNNN-kebab-title.md`（编号递增）。
2. 内容包含：Status / Context / Decision / Consequences。
3. 在相关文档（README、architecture.md）中链接新 ADR。
4. ADR 一旦接受（Accepted）不再修改内容，推翻时新增 ADR 并将旧的状态改为 Superseded。

## 11. 阶段收尾流程（每完成一个阶段必做）

**每完成一个 Phase（或一个可交付的开发周期），必须按以下顺序收尾，全部完成后才算该阶段结束：**

### 第一步：核对验收标准

1. 打开 `docs/roadmap.md` 中当前 Phase 的验收标准清单。
2. 逐项真实验证后将 `[ ]` 改为 `[x]`；无法完成的项目保留 `[ ]` 并在下方用一行文字说明原因与后续处理方式。
3. 收尾总结须附**交付说明**：阶段成果如何从零运行（环境要求 + 完整命令序列）、新增功能如何体验（具体操作步骤与预期结果）；无可运行变化时免附（细则见 `docs/workflow.md` §8.1）。

### 第二步：同步文档

文档更新是阶段交付物的一部分，不是可选项：

| 文件 | 更新内容 |
| --- | --- |
| `docs/status/current.md` | 更新 Current Phase / Subphase / Slice 标记、Recently Completed、Next Recommended Action（subphase 级收尾也应更新，见 `docs/workflow.md` §8） |
| `docs/roadmap.md` | 顶部"当前阶段 / 最近完成"标记；各 Phase 标题后的状态符号；验收标准勾选 |
| `README.md` | "当前开发阶段"横幅、Roadmap 状态表、"当前项目状态"一节 |
| `AGENTS.md` | 第 2 节概要表中的"当前阶段"标记；如技术栈/工作方式有变，同步第 3、8 节 |
| `docs/architecture.md` | 仅当架构或模块关系有变化时更新 |
| `docs/development.md` | 仅当环境、依赖版本或工具链有变化时更新 |
| `docs/decisions/` | 有新的重要技术决策时新增 ADR 并在相关文档中链接 |

### 第三步：Git 提交并推送

1. 阶段的代码/功能变更与文档同步可以分开提交，但**每次开发周期结束前必须包含一次明确的文档同步提交**，不要让仓库停留在"代码已完成而文档过期"的状态过夜。
2. 提交信息示例：
   - 阶段功能收尾：`feat: complete Phase N — <名称> core deliverables`
   - 文档同步收尾：`docs: close out Phase N — sync roadmap, README and AGENTS status`
3. 收尾提交后执行 `git push`。如果被拒绝且本地领先，先 `git pull --rebase` 再推送。

### 第四步：停止

- 阶段收尾完成后**停止开发，等待下一条指令**再进入下一阶段；不自行开始下一阶段的任何实现工作。
- 下一次开发会话开始时，按第 6 节"会话进入协议"执行：本文件 → `docs/status/current.md` → 相关文档 → 仓库检查 → 从上次停下的位置继续。

## 12. 其他注意事项

- 本仓库刻意**不预生成**未来可能被修改的空 Python 文件；代码文件在需要实现时再创建。
- 原创软件采用MIT，已落实根LICENSE及包元数据；依赖 / 二进制 / 模型权重与素材各自按原条款核对，见[许可与分发边界](docs/licensing.md)。DeepLabCut 3.0.1为LGPL-3.0-or-later，不沿用旧AGPL说法。试用包不附第三方权重，首次准备下载；具体发行材料尚未完成。
- 开发与交付顺序是 **macOS (Apple Silicon) 开发 → Mac arm64小范围教学试用 → 后续Windows x64正式交付**。本轮Mac试用接受未公证包的单应用手动放行，不要求关闭全局保护；新安装包仍需验证。PyInstaller/Nuitka 不支持交叉编译，Windows 构建走 GitHub Actions Windows runner，Windows / CUDA真机边界保持；跨平台规则见 `docs/development.md` §1.1。
