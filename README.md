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
手工标注少量代表帧
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
Current Phase:   Phase 2 — Video Analysis MVP
Last Completed:  Phase 2.3 — Manual Annotation ✅（2026-08-30）
Current Subphase: Phase 2.4 — Project Workflow & Phase Close（Plan 待确认）
```

Phase 1 已完成：统一领域模型、Timeline、TrackStore、CalibrationTransform、schema v1 JSON 持久化、原子保存/备份、外部视频 relink 与跨平台路径防护均已落地。56 项测试在本地及 GitHub Actions 的 macOS/Windows Python 3.11 环境全部通过。

Phase 2.1–2.3 已形成桌面视频浏览、异步播放、缩放/平移、手工标记与 Undo/Redo；当前规划 2.4 的项目保存/恢复、重连及 Phase 2 验收，尚未开始实现。

> **当前进度与下一步动作**：见 [docs/status/current.md](docs/status/current.md)（每个开发会话结束时更新）。开发如何组织（Phase / Subphase / Slice 循环）见 [docs/workflow.md](docs/workflow.md)。

## Roadmap

| 阶段 | 名称 | 状态 |
| --- | --- | --- |
| Phase 0 | Project Initialization | ✅ 已完成（2026-08-27） |
| Phase 1 | Project & Data Foundation | ✅ 已完成（2026-08-29） |
| Phase 2 | Video Analysis MVP | 🔄 Subphase 2.4 Plan |
| Phase 3 | Calibration & Physics Engine | ⬜ |
| Phase 4 | Deep Learning Tracking | ⬜ |
| Phase 5 | AI-assisted Annotation & Refinement | ⬜ |
| Phase 6 | Advanced Physics Analysis | ⬜ |
| Phase 7 | Model Library | ⬜ |
| Phase 8 | Export & Scientific Workflow | ⬜ |
| Phase 9 | Optimization & Packaging | ⬜ |
| Phase 10 | Extended Capabilities | ⬜ |

详细的目标、交付物、验收标准和技术风险见 [docs/roadmap.md](docs/roadmap.md)。

## 未来如何运行和发布

- **开发阶段**：Python 虚拟环境（conda/venv）+ 源码运行，详见 [docs/development.md](docs/development.md)。
- **最终发布**：面向普通 Windows 用户的安装程序（`AIPhysicsTracker-Setup.exe`），普通用户无需配置 Python 环境。打包方案（PyInstaller / Nuitka + Inno Setup / NSIS，CPU 版与 NVIDIA GPU 加速版）将在 Phase 9 确定并持续记录在 [packaging/](packaging/) 目录。

## 当前项目状态

- ✅ 仓库结构、基础文档、Git 初始化、GitHub 远程推送（[KYLeonis/ai-physics-tracker](https://github.com/KYLeonis/ai-physics-tracker)，Private）
- ✅ src-layout 核心/GUI 包、锁定依赖与 124 项 pytest 测试（2.3 基线）；GitHub Actions 覆盖 macOS/Windows Python 3.11
- ✅ schema v1 项目保存/恢复闭环、跨平台视频 locator 与 ADR-0003/0004
- ⬜ License 待定（`TBD`），需在引入 DeepLabCut（AGPL-3.0）等第三方依赖后进行 license review

## 文档索引

- [AGENTS.md](AGENTS.md) — 面向 Coding Agent 的项目指南
- [CODE_STANDARD.md](CODE_STANDARD.md) — 代码规范（写代码前必读）
- [docs/status/current.md](docs/status/current.md) — 当前状态与下一步（不知道做什么先读）
- [docs/workflow.md](docs/workflow.md) — 开发循环说明书（Phase / Subphase / Slice）
- [docs/roadmap.md](docs/roadmap.md) — 详细路线图
- [docs/architecture.md](docs/architecture.md) — 高层架构设计
- [docs/development.md](docs/development.md) — 开发环境与工作流
- [docs/decisions/](docs/decisions/) — 架构决策记录（ADR）
