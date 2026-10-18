# AI Physics Tracker

**A desktop video tracking and physics analysis platform for experiments, kinematics, video measurement, and science education.**

AI Physics Tracker 结合现代深度学习视觉跟踪方法与传统运动学视频分析软件的使用方式，让用户能够从实验视频中快速获得准确的物体轨迹和物理数据。软件使用方式上对标 Tracker 等专业物理分析软件的桌面交互体验，技术上以 DeepLabCut 3.x（PyTorch 路线）作为核心跟踪基础。

---

## 项目希望解决什么问题

传统物理实验视频分析（如手工逐帧标记）费时费力，而通用 AI 姿态工具又不面向物理实验的标定、坐标系统和运动学计算需求。本项目希望提供一条完整工作流：

```text
导入实验视频
    ↓
设置时间、比例尺与物理坐标系
    ↓
定义需要跟踪的物体或关键点
    ↓
手工标注 20 个不同代表帧（默认 K-means 选帧）
    ↓
AI 训练 / 微调
    ↓
自动分析整段视频
    ↓
检查并修正低置信度或错误跟踪
    ↓
必要时继续训练
    ↓
得到高质量运动轨迹
    ↓
物理量计算（x/y、v、a、θ、ω、α …）
    ↓
运动图表 / 相图 / 数据分析
    ↓
导出实验结果（CSV / Excel / 图片 / 视频）
    ↓
保存模型并用于后续相似实验
```

核心价值：**用户针对当前实验场景，用少量标注即可获得高准确率的自动跟踪，并直接得到可导出的物理数据。**

## 主要使用场景

- 物理课堂教学与演示实验分析
- 大学物理实验课程的数据处理
- 科学研究和运动学测量
- 需要针对特定实验场景快速迭代提升识别精度的用户

前期重点实验场景（二维运动）：**单摆**（早期基准测试案例）、小车直线运动、自由落体、抛体运动、弹簧振子、圆周运动。

## 核心功能目标

- 视频导入、播放、暂停、逐帧查看、精确定位任意帧
- 长度比例尺标定、物理坐标原点与坐标轴方向/旋转设置
- 多跟踪目标定义、手工标注、AI 自动跟踪
- AI 训练 / 微调（少量标注 → 训练 → 跟踪 → 困难帧修正 → 再训练）
- 跟踪置信度显示、低置信度/异常帧快速定位
- 运动学物理量计算：x(t)、y(t)、vx(t)、vy(t)、ax(t)、ay(t)、θ(t)、ω(t)、α(t)
- 数据可视化：x-t / y-t / v-t / a-t 图、x-y 轨迹、相空间图、θ-ω 相图、多物体比较
- 数据导出：CSV、Excel、图片、图表、完整逐帧数据、跟踪后的视频
- 模型库管理：保存、命名、版本管理、继续训练、应用到新视频

## 技术方向

| 领域 | 技术选型 |
| --- | --- |
| 语言 | Python 3.11（DeepLabCut 3.x 支持范围 3.10–3.12 内的稳定版本） |
| AI 框架 | PyTorch |
| 视觉跟踪 | DeepLabCut 3.x（PyTorch 引擎） |
| 桌面 GUI | PySide6 / Qt（优先评估） |
| 视频 | OpenCV、FFmpeg |
| 科学计算 | NumPy、SciPy、Pandas |
| 交互式绘图 | PyQtGraph（优先评估） |
| 科学图表导出 | Matplotlib |
| 目标平台 | Windows 10 / 11 64-bit（桌面应用发布） |

> 版本选择依据：DeepLabCut 官方要求 Python 3.10–3.12，PyTorch 与 PySide6 在 3.11 上均有最成熟的轮子支持。详见 [docs/development.md](docs/development.md)。

## 当前开发阶段

```text
Current Phase:    Phase 6（6.1 / 6.2 / 6.3 已完成并集成 main）
Last Delivered:   重复间隔源联动与交点预览；独立复审 / 双平台CI / 全部HR通过，2026-10-18以2600f2a集成main
Current Subphase: Phase 6.3.1及自动时序 / 公式拟合 / 重复间隔联动维护增量已完成并集成main；6.4 / 6.5未开始
```

Phase 1 已完成：统一领域模型、Timeline、TrackStore、CalibrationTransform、schema v1 JSON 持久化、原子保存/备份、外部视频 relink 与跨平台路径防护均已落地。56 项测试在本地及 GitHub Actions 的 macOS/Windows Python 3.11 环境全部通过。

Phase 2.1–2.4 已形成桌面视频浏览、异步播放、缩放/平移、手工标注（含 Undo/Redo）、项目保存/恢复/重连与 CFR/Near-CFR 时序验证门禁，macOS 全流程 Human Review 通过；Windows 真机验收延后执行（用户决定），不影响后续阶段。

Phase 3.0–3.4 已完成全部标定、运动学引擎、交互式图表与集成验收，310 项测试 + 双平台 CI 全绿 + 整体 Human Review 通过。

Phase 4.4 已在 GUI 内接通训练、基本模型评价、推理、取消、日志历史、AI 轨迹显示和混合运动学重算；
macOS Human Review、433 项本地测试、真实 CPU GUI 组件闭环及 macOS/Windows Python 3.11 CI 均通过。
真实短训练只验证管线，不代表模型精度。经用户批准，Windows 真机/CUDA 延期到 Phase 9 打包前；详情见
[4.4 计划与验收](docs/status/phase-4.4-plan.md)。

Phase 5 已完成。5.0 收敛统一任务管道；5.1 完成 DLC uniform/K-means 代表帧选取；5.2 完成全帧原始预测、多信号困难帧筛查、时间去重/多样性与真实基准；5.3 完成 Accept/Correct/Skip 审核队列和 prediction provenance；5.4 完成候选隔离、结果激活/替换/清除与固定验证集；5.5 完成确定性 Training Advisor、显式 Restart/Resume 与 lineage；5.6 完成真实单摆 refinement 闭环及三类 delta 归档；5.7 将界面重构为“实验设置 → 获取轨迹 → 分析与图表”三个工作区、常驻状态头与状态驱动任务卡，并通过最终 Human Review。Phase 5.6 的冻结基准改善目标未达到 ≥5%（最佳 −3.3%），已按用户批准如实保留为明示缺口，不影响已完成的工作流与科研可追溯契约。详见
[Phase 5 requirements](docs/spec/phase5-requirements.md) 与 [PHASE_5_PLAN](docs/status/phase-5-plan.md)。

2026-10-11 主线先交付用户授权的三项增量（只读分析视频 / 连续修正 / 教师模型），见
[mini-plan](docs/status/main-guided-refinement-model-import-plan.md)。Phase 6 的旧需求 / 总计划 / 6.1 草案
须先按用户提供方程、通用平台分析的口径重规划，不能直接实施固定模型草案。

> **当前进度与下一步动作**：见 [docs/status/current.md](docs/status/current.md)（每个开发会话结束时更新）。开发如何组织（Phase / Subphase / Slice 循环）见 [docs/workflow.md](docs/workflow.md)。

## Roadmap

| 阶段 | 名称 | 状态 |
| --- | --- | --- |
| Phase 0 | Project Initialization | ✅ 已完成（2026-08-27） |
| Phase 1 | Project & Data Foundation | ✅ 已完成（2026-08-29） |
| Phase 2 | Video Analysis MVP | ✅ 已完成（2026-08-30，Windows 真机验收延后） |
| Phase 3 | Calibration & Physics Engine | ✅ 已完成（2026-08-31） |
| Phase 4 | Deep Learning Tracking | ✅ 已完成（2026-09-01；Windows/CUDA 延期至 Phase 9 前） |
| Phase 5 | AI-assisted Annotation & Refinement | ✅ 已完成（2026-09-18；AC-9 改善目标明示归档） |
| Phase 6 | Advanced Physics Analysis | 🔄 6.1 / 6.2 / 6.3 已完成并集成；用户公式驱动的通用分析 |
| Phase 7 | Model Library | ⬜ |
| Phase 8 | Export & Scientific Workflow | ⬜ |
| Phase 9 | Optimization & Packaging | ⬜ |
| Phase 10 | Extended Capabilities | ⬜ |

详细的目标、交付物、验收标准和技术风险见 [docs/roadmap.md](docs/roadmap.md)。

## 未来如何运行和发布

- **开发阶段**：Python 虚拟环境（conda/venv）+ 源码运行，详见 [docs/development.md](docs/development.md)。
- **最终发布**：面向普通 Windows 用户的安装程序（`AIPhysicsTracker-Setup.exe`），普通用户无需配置 Python 环境。打包方案（PyInstaller / Nuitka + Inno Setup / NSIS，CPU 版与 NVIDIA GPU 加速版）将在 Phase 9 确定并持续记录在 [packaging/](packaging/) 目录。

## 当前项目状态

- ✅ 仓库结构、基础文档、Git 初始化、GitHub 远程推送（[KYLeonis/ai-physics-tracker](https://github.com/KYLeonis/ai-physics-tracker)，Public）
- ✅ src-layout 核心/GUI 包、锁定依赖与自动化测试；GitHub Actions 覆盖 macOS/Windows Python 3.11，最新验证见 current.md
- ✅ schema v1 项目保存/恢复闭环、跨平台视频 locator 与 ADR-0003/0004
- ✅ Phase 1–4 已完成；当前训练、评价、推理与 AI 轨迹导入共享统一后台任务管线
- ✅ Phase 5 已完成：5.0–5.7 全部交付，AI-assisted tracking 到可分析轨迹的主流程通过最终 Human Review
- ✅ Phase 6.1 角运动基础 / 6.2 图表与相空间 / 6.3 显式函数拟合及重复间隔已集成 main；独立复审 / 用户 Human Review 已按各自范围完成
- ✅ R01–R03架构维护已完成：公式拟合联动、计算设置统一、重复间隔联动；当前架构与完成进度有统一接手入口
- ⬜ License 待定（`TBD`），需在引入 DeepLabCut（AGPL-3.0）等第三方依赖后进行 license review

## 文档索引

- [AGENTS.md](AGENTS.md) — 面向 Coding Agent 的项目指南
- [当前架构总览](docs/architecture.md#当前架构总览接手先读) / [重构进度与已淘汰做法](docs/status/architecture-progress.md) — Agent接手时先读；完成 / 进行中 / 后置明确区分
- [下一轮整体架构重构方案](docs/status/architecture-next-round-plan.md) — 贯通计算、结果写回与界面更新；方案待确认，未实施
- [CODE_STANDARD.md](CODE_STANDARD.md) — 代码规范（写代码前必读）
- [docs/status/current.md](docs/status/current.md) — 当前状态与下一步（不知道做什么先读）
- [docs/workflow.md](docs/workflow.md) — 开发循环说明书（Phase / Subphase / Slice）
- [docs/roadmap.md](docs/roadmap.md) — 详细路线图
- [docs/architecture.md](docs/architecture.md) — 高层架构设计
- [docs/development.md](docs/development.md) — 开发环境与工作流
- [docs/reviews/](docs/reviews/) — 独立 Review Record 存档（每 subphase 一个文件）
- [docs/decisions/](docs/decisions/) — 架构决策记录（ADR）


### 主线口径与已交付增量（2026-10-13）

后续分析采用**用户提供方程 / 公式，通用平台完成计算与分析**；论文分支固定 ODE 是复现参考，Phase 6.3已按此口径完成规划与交付（[ADR-0017](docs/decisions/0017-user-defined-equation-analysis-platform.md)）。

main 已交付 Analysis 视频只读、建议帧批量连续标注 / 修正与完成后的训练推荐、教师 DLC 模型受管导入 / 实际帧自检 / 单关键点候选轨迹。模型自检不会证明科学准确性，候选仍需显式采用。自动化 / Independent Review 已通过，用户于 2026-10-13 确认 [Human Review A/B/C](docs/notes/main-guided-refinement-model-import-human-review.md) 全部通过；已按序集成。其余回移候选在 [后续档案](docs/status/main-backport-backlog.md) 按相关阶段触发核对。

2026-10-13 首次学习引导增量已通过 Human Review 并集成 main：当前轨迹需 20 个不同人工帧才可首次学习；默认请求 20 帧 / K-means，顶部推荐的 `Custom frame selection…` 直接切换 K-means / Uniform。已有成功训练的轨迹保持原再训练门槛，教师模型推理仍可直接使用。见[计划](docs/status/initial-annotation-guidance-plan.md)与[真人验收记录](docs/notes/initial-annotation-guidance-human-review.md)。
用户实测反馈的“选了 K-means 却标前 20 帧”已修复：选帧完成后推荐 `Label suggested frames`，沿实际建议帧连续标注；没有建议结果时先选帧，原有人工标签保留。

### Phase 6.1 / 6.2 当前进度（2026-10-15）

6.1 已交付 θ/ω/α 的纯计算、双输入依赖与保存 / 后台事务，完成完整审查和修复并集成 main，
P6.2 已按 [角量图表与相空间计划](docs/status/phase-6.2-plan.md)完成S1–S5并集成main；新增两种参考、θ/ω/α时间图、θ–ω / x–vx、degree显示和只读源帧导航；
科学 / 时序 / 结果版本约束见 ADR-0019/0020，最新验证和下一步见 current。

P6.2科学 / 事务修复全量 **1007 passed（88.42s）**、独立复审 **Approve**；轨迹多选修复含名称 / 框 / 键盘真实输入，相关GUI **51项通过**，最终双平台 **1008 passed / 2 skipped**。用户确认全部Human Review通过，已以 `12b0911` 集成main；[CI证据](https://github.com/KYLeonis/ai-physics-tracker/actions/runs/38582553294)、[Review记录](docs/reviews/phase-6.2-review.md)及[真人验收记录](docs/notes/phase-6.2-human-review.md)。6.3计划已于2026-10-15获用户认可，S0真实基准和数据契约已冻结，S1–S4已实现；S5独立复审 / 全量 / 双平台CI及2026-10-16整体Human Review通过，已以92d00a2集成main。

P6.3范围为用户显式函数编辑 / 数学预览、单标量拟合、参数与残差、可选结果公式，以及独立的信号重复间隔 / 周期工具。单摆仅作示例；非周期信号不强求周期，多峰信号不把交叉间隔自动称为基本周期。详见[6.3计划](docs/status/phase-6.3-plan.md)。ODE、单位管理与参数置信区间留后续。


2026-10-16：[P6.3.1英文分析体验](docs/status/phase-6.3.1-plan.md)已在[PR #32](https://github.com/KYLeonis/ai-physics-tracker/pull/32)实现；第三轮HR反馈后，保存结果与底部尝试整页同步只读配方，Return恢复原草稿，Use显式复用；原源严格匹配时重建尝试曲线，失败 / 缺源清旧图并就地反馈。2026-10-17用户HR通过，以c0d1461集成main；本机1232项 / 双平台CI / R6独立复审通过，不设固定响应或新手完成时限，翻译后续。

2026-10-18：[公式拟合联动增量](docs/status/fit-linked-source-plan.md)全量1271 / 独立复审 / 双平台CI及本轮HR通过，已以aa86d79集成main：拟合页自动补齐当前轨迹缺失 / 过期的源曲线，再同步预览、单位和说明；沿用所选轨迹自身设置，冲突定义保留并提示。正式Fit仍显式，原始观测保持不变。契约见[ADR-0025](docs/decisions/0025-automatic-fit-source-preparation.md)。

2026-10-18：[计算配方统一解释](docs/status/source-recipe-plan.md)内部整理已以26af812集成main，全量1276 / 独立复审 / 双平台CI通过。图表、拟合准备、后台校验和同步生成共用实际计算设置定义；图例不再从摘要文字判断来源。原操作 / 数值算法 / 工程格式保持。

2026-10-18：[重复间隔联动](docs/status/recurrence-linked-plan.md)已以2600f2a集成main，独立复审 / 双平台CI / 全部HR通过。工具自动准备当前源，改参考线 / 方向 / 区间刷新候选交点、单位和说明；Measure才保存正式结果。拖线后的页面跳顶已修复并通过用户复测，曲线缩放与页面位置保持。架构及完成标记见[进度表](docs/status/architecture-progress.md)。
