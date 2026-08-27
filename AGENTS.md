# AGENTS.md

本文件面向在本仓库工作的 Coding Agent（以及人类开发者），帮助其快速理解项目并按统一规范继续开发。请保持本文件简洁、随项目进展持续更新。

## 1. 项目长期目标

AI Physics Tracker 是一个面向物理实验、运动学分析、视频测量和科学教育的**桌面视频跟踪与数据分析平台**：

- 技术基础：DeepLabCut 3.x（PyTorch 路线）+ 传统运动学分析工作流
- 核心体验：用户标注少量代表帧 → AI 训练/微调 → 自动跟踪整段视频 → 修正困难帧 → 再训练 → 高质量运动轨迹 → 物理量计算与导出
- 最终形态：面向普通 Windows 用户的桌面安装程序（无需配置 Python 环境）
- 基准实验：**单摆**（早期重点测试案例，用于建立算法、数据处理与工作流基准）

## 2. 当前 Roadmap（概要）

| 阶段 | 名称 | 一句话目标 |
| --- | --- | --- |
| Phase 0 | Project Initialization | 仓库、文档、Git 初始化（✅ 已完成） |
| Phase 1 | Project & Data Foundation | Project / Video / Track / Annotation / Calibration 数据体系（**当前阶段**） |
| Phase 2 | Video Analysis MVP | 可用的 GUI + 视频播放 + 手工标记 + 项目保存 |
| Phase 3 | Calibration & Physics Engine | 标定、坐标系、运动学计算、基础图表 |
| Phase 4 | Deep Learning Tracking | 接入 DeepLabCut/PyTorch：标注→训练→跟踪 |
| Phase 5 | AI-assisted Annotation & Refinement | 代表帧选取、困难帧发现、快速修正与再训练 |
| Phase 6 | Advanced Physics Analysis | θ/ω/α、相图、周期分析、拟合、误差分析 |
| Phase 7 | Model Library | 模型保存、版本管理、应用到新视频 |
| Phase 8 | Export & Scientific Workflow | CSV/Excel/图表/视频导出、项目归档 |
| Phase 9 | Optimization & Packaging | 性能优化、GPU、Windows 打包发布 |
| Phase 10 | Extended Capabilities | 多目标/多关键点/多相机/3D/插件等（范围待定） |

完整版本（目标、交付物、验收标准、技术风险）见 `docs/roadmap.md`。

## 3. 预期技术栈

```text
OS:          Windows 10/11 64-bit（目标平台）；开发亦可在 macOS/Linux
Python:      3.11（DeepLabCut 3.x 支持 3.10–3.12）
AI:          PyTorch（先装 PyTorch 再装 deeplabcut）
Tracking:    DeepLabCut 3.x，PyTorch 引擎
GUI:         PySide6 / Qt（优先评估）
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
├── LICENSE              # 许可证（当前 TBD）
├── docs/                # 项目文档
│   ├── roadmap.md       # 详细路线图（各阶段目标/交付物/验收标准/风险）
│   ├── architecture.md  # 高层架构设计
│   ├── development.md   # 开发环境、版本选择、跨平台规则
│   ├── workflow.md      # 开发循环说明书（Phase/Subphase/Slice，细则）
│   ├── status/current.md # 当前状态：阶段/任务/下一步（会话先读、收尾必更）
│   ├── templates/       # subphase 计划与 review 模板
│   └── decisions/       # 架构决策记录（ADR）
├── src/                 # 源代码（Phase 1 起填充）
├── tests/               # 测试（Phase 1 起填充）
├── scripts/             # 开发辅助脚本
├── resources/           # 应用资源（图标、UI 文件等）
├── examples/            # 示例工程/用法（不含大型视频）
└── packaging/           # Windows 打包相关（Phase 9 起填充）
```

## 5. 文档位置

- **当前状态（不知道做什么先读这个）**：`docs/status/current.md` —— 由每个开发会话结束时更新
- 开发循环细则（Phase/Subphase/Slice、review、GitHub、Agent 交接）：`docs/workflow.md`
- 路线图：`docs/roadmap.md`
- 架构设计：`docs/architecture.md`
- 开发环境与工作流：`docs/development.md`
- 模板：`docs/templates/`（subphase 计划、review）
- 实现参考与前期调研（开源生态地图）：`docs/research/open-source-project-map.md` —— 实现任何模块前先读其对应小节；各项目源码级细节见 `docs/research/raw/`，仓库快照与校验规则见 `docs/research/README.md`
- 架构决策记录（ADR）：`docs/decisions/NNNN-*.md`（模板见 `docs/decisions/0001-record-architecture-decisions.md`）
- 各顶层目录内有 `README.md` 说明该目录的用途与约定

## 6. 开发循环与 Agent 交接（细则见 `docs/workflow.md`）

**会话进入协议**：

1. 顺序阅读：本文件 → `docs/status/current.md` → 相关 Phase/Subphase 文档（roadmap 对应节、subphase Issue 或 plan、spec）→ 检查仓库（`git log --oneline -15`、未提交改动）。
2. 执行 status 文件中的 "Next Recommended Action"；若 status 与仓库实际状态矛盾，以仓库为准并先修正 status。

**开发循环**：

```text
Explore → 需要时 Plan（subphase mini-plan）→ 以 Slice 小步实现
→ Verify（测试）→ Self-review → 必要时独立 review
→ Commit / Integrate → 更新 status → Next
```

**不变式**：数据先行（手工/AI 跟踪统一数据体系，Phase 1 核心目标）；代码进 `src/`、测试进 `tests/`、大文件不入库；重大选型记 ADR（§10）；完成当前 Phase 后暂停等待下一条指令。

**何时必须暂停并询问用户**：

- 超出当前 Phase/Subphase 范围的改动，或需要修改验收标准本身
- 引入新依赖、替换技术选型、不兼容的接口/数据格式变更（通常同时需要 ADR）
- 删除数据、重写 Git 历史、影响 License 的操作
- spec/roadmap 中已有预期结论，而实际调研结论相反时

**何时可自行决定**（在既有 ADR/spec/roadmap 约束内）：

- 实现细节、命名、文件组织、测试写法、文档措辞、bug 的具体修复方式、Slice 拆分

**会话退出协议**（每次会话结束必须完整执行）：

1. 运行验证（测试 / 验收标准核对）；2. 向用户总结变更；3. 更新 `docs/status/current.md`（必做）；4. 同步相关文档；5. 记录决策（必要时 ADR）；6. 按规则提交（subphase/phase 收尾须 push）；7. 在 status 中写出确切的"下一步建议动作"。

## 7. 测试和验证要求

- Phase 1 起引入 pytest；核心数据结构（project/track/annotation/calibration）与物理计算（坐标转换、微分、平滑）必须有单元测试。
- 涉及数值计算的模块测试需使用已知解析解的合成数据（如匀速/匀加速/单摆小角度）。
- GUI 功能以手动验收为主，逻辑尽量从 GUI 层剥离以便测试。
- 当前阶段（Phase 0）无代码，无需测试。

## 8. Git 工作方式

- 默认分支：`main`
- 远程：`origin` → `KYLeonis/ai-physics-tracker`（GitHub，Private）
- 认证已配置完成（2026-08-27）：HTTPS 凭据存于 macOS 钥匙串（OAuth token，scope: repo/workflow），`git push` / `git pull` 可直接使用；如凭据失效，通过 GitHub OAuth 设备授权流程重新获取（在 GitHub → Settings → Applications 中可查看/撤销）。
- 提交到 `main` 前在工作分支开发（`feat/p<phase>.<sub>-<topic>`，如 `feat/p1.1-data-model`；杂项用 `fix/<topic>` / `docs/<topic>`）；小规模文档同步可直接提交到 `main`。分支生命周期 = 一个 Subphase，收尾时 `--no-ff` 合并回 `main`（见 `docs/workflow.md` §10）。
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
- License 尚为 TBD：引入 DeepLabCut（AGPL-3.0）等依赖后必须进行 license review（见 `docs/decisions/` 与 `LICENSE`）。
- 开发模式是 **macOS (Apple Silicon) 开发 → Windows x64 发布（exe）→ 未来 macOS dmg**：PyInstaller/Nuitka 不支持交叉编译，Windows 构建走 GitHub Actions Windows runner，Windows 真机验收（含 CUDA）在自有的 NVIDIA GPU Windows 笔记本上进行；路径分隔符（`pathlib`）、UTF-8 显式编码、Windows 文件锁/路径长度/保留名、Qt 平台差异等规则见 `docs/development.md` §1.1。
