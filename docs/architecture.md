# Architecture — AI Physics Tracker

本文档记录**高层设计**与未来模块关系。当前刻意不提前固定所有类和接口——具体设计在进入对应 Phase 时细化，重要决策以 ADR 形式记录在 `docs/decisions/`。

---

## 1. 系统总览

AI Physics Tracker 是一个单机桌面应用，内部由四层组成：

```text
┌─────────────────────────────────────────────────────────┐
│                     GUI 层（PySide6）                     │
│  主窗口 · 视频视图 · 时间轴 · 标定工具 · 标注工具 ·        │
│  图表面板 · 训练/推理任务面板 · 模型库管理                  │
├─────────────────────────────────────────────────────────┤
│                     应用服务层                            │
│  项目生命周期 · 视频播放控制 · 标定/坐标系服务 ·            │
│  标注服务 · AI 训练/推理任务编排 · 模型库服务 · 导出服务    │
├─────────────────────────────────────────────────────────┤
│                     领域/核心层                           │
│  数据模型（Project/Video/Track/Annotation/Calibration）·  │
│  运动学计算引擎 · 数据处理（平滑/插值/异常值）·            │
│  困难帧检测 · 物理量派生                                  │
├─────────────────────────────────────────────────────────┤
│                     基础设施层                            │
│  持久化 · DeepLabCut/PyTorch 适配器 · 视频解码（OpenCV/    │
│  FFmpeg）· 后台任务执行器 · 日志 · 配置                    │
└─────────────────────────────────────────────────────────┘
```

设计原则：

- **GUI 与核心分离**：领域/核心层不依赖 Qt，可独立测试；GUI 只做展示与交互。
- **数据先行**：手工跟踪与 AI 跟踪使用统一数据体系（Phase 1 的核心目标），AI 只是轨迹数据的另一种来源。
- **适配器隔离**：DeepLabCut/PyTorch 通过适配层接入，未来可替换为其他视觉模型（ONNX/OpenVINO 等）而不影响上层。
- **长任务后台化**：训练、推理、视频导出全部为可取消的后台任务，GUI 保持响应。

## 2. 核心数据体系（Phase 1 起细化）

统一数据模型将围绕以下概念组织（示意，非最终接口）：

| 概念 | 说明 |
| --- | --- |
| Project | 一次实验分析会话：引用视频、标定、轨迹集合、模型引用 |
| Video | 文件路径、帧率、总帧数、分辨率等元数据；不包含帧像素 |
| Timeline | 帧号 ↔ 时间的映射、0-based 帧约定与 working zone |
| Track | 一个跟踪目标在全部帧上的轨迹数据序列 |
| TrackPoint | 单帧单目标观测：像素坐标 + confidence + 来源（manual/ai） |
| Annotation | 用户手工标注（是 TrackPoint 的一种来源，同时是 AI 训练数据） |
| Calibration | 比例尺（像素↔物理长度）、坐标原点、轴方向/旋转 |
| DerivedData | 由原始 Track 经标定/平滑/微分等得到的派生数据，原始数据永不覆盖 |

关键约定：**原始跟踪数据只增不改**；所有处理（平滑、微分、拟合）产生的派生数据分层存放，保证可回溯、可重新处理（对应导出需求中的"保留原始跟踪数据"）。

## 3. AI 跟踪子系统（Phase 4 起细化）

```text
手工标注（Annotation）
      ↓  转换器
DeepLabCut 项目（labeled-data / training-datasets）
      ↓  训练任务（后台）
DLC 模型（dlc-models, PyTorch engine）
      ↓  推理任务（后台, 含 confidence）
推理结果 → 转换回统一 TrackPoint（含 confidence, source=ai）
      ↓
困难帧检测（低置信度 / 轨迹异常）→ 引导用户修正 → 回到训练（主动学习闭环）
```

- 标注数据双向转换：内部模型 ↔ DLC CollectedData 格式。
- 模型库（Phase 7）记录模型元数据与来源实验，支持在新视频上复用并补充标注微调。
- 推理输出必须携带 per-point confidence，供困难帧检测与图表着色使用。

## 4. 运动学计算与可视化（Phase 3/6 起细化）

- 输入：标定后的物理坐标序列 x(t), y(t)
- 计算：一阶/二阶导数（数值微分方法与平滑策略在 Phase 3 以 ADR 确定）、θ/ω/α（Phase 6）
- 数据流：Raw Track → Calibration → (Smooth → Differentiate) → 派生量序列
- 可视化：交互图表使用 PyQtGraph（与视频帧时间同步联动），科学出图导出使用 Matplotlib。

## 5. 持久化与文件布局（Phase 1 已定，见 ADR-0003）

```text
<user_project>/
├── project.json                 # 项目清单与全部第一方数据（schema_version 守卫）
├── videos/ → 外部视频引用        # 视频文件不复制、不入库（gitignore）
├── data/engines|derived/         # 引擎原始输出 / 外置派生数组（只引用）
└── models/                       # 本项目训练/引用的模型（gitignore）
```

格式与目录细则见 [project-format.md](spec/project-format.md)。

## 6. 打包与发布（Phase 9 细化）

- 目标：Windows 10/11 安装包（Inno Setup / NSIS），CPU 版与 GPU 版（CUDA Runtime 分发策略待研究）
- 候选打包链：PyInstaller / Nuitka（对比体积、启动速度、PyTorch 兼容性后决策）
- 相关目录：`packaging/`

## 7. 决策记录

所有已接受的架构决策见 [decisions/](decisions/)。当前已记录：

- [0001 — 记录架构决策的方式](decisions/0001-record-architecture-decisions.md)
- [0002 — 选择 Python 3.11](decisions/0002-choose-python-3.11.md)
- [0003 — 项目持久化采用 JSON 清单优先的混合方案](decisions/0003-project-persistence-format.md)
- [0004 — 外部视频使用可空项目路径与绝对 locator](decisions/0004-external-video-locator.md)
