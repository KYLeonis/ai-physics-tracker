# Roadmap — AI Physics Tracker

本文档细化各开发阶段的目标、交付物、验收标准与主要技术风险。
状态标记：✅ 完成 / 🔄 进行中 / ⬜ 未开始

- 最近完成：**Subphase 3.2 — Kinematics Engine（✅ 2026-08-30）**
- 当前阶段：**Phase 3 — Calibration & Physics Engine（🔄 Subphase 3.3 Interactive Charts，计划待确认）**
- 各阶段完成后暂停，等待下一条开发指令再进入下一阶段；收尾要求见 `AGENTS.md` 第 11 节。

---

## Phase 0 — Project Initialization ✅

**目标**：建立可长期维护的项目仓库与文档基础。

**Deliverables**
- 仓库基础结构（docs/、src/、tests/、scripts/、resources/、examples/、packaging/）
- README.md（项目介绍）、AGENTS.md（Agent 开发指南）、.gitignore、LICENSE（TBD）
- docs/：roadmap.md、architecture.md、development.md、decisions/（ADR）
- Git 仓库初始化、GitHub 远程仓库（Private）、首次提交与推送

**验收标准**
- [x] 目录结构合理，无大量预生成的空 Python 文件
- [x] README 完整描述项目目标、阶段、技术方向
- [x] AGENTS.md 能指导未来 Agent 完成后续开发
- [x] Roadmap 覆盖 Phase 0–10 并含验收标准
- [x] .gitignore 覆盖视频/模型/训练数据/构建产物
- [x] Git 仓库正常、GitHub origin 正确、首次 commit 与 push 成功（首推于 2026-08-27，凭据存于 macOS 钥匙串）

**主要技术风险**
- ~~GitHub 凭据不可用时需人工完成远程仓库创建与首次 push。~~ 已解决：通过 GitHub OAuth 设备授权获取 token 并存入钥匙串。

---

## Phase 1 — Project & Data Foundation ✅

**目标**：建立统一的数据体系，使手工跟踪与 AI 跟踪共享同一套数据结构。

**Deliverables**
- `src/` 包结构与核心数据模型：Project、Video metadata、Timeline/frame info、Track、TrackPoint、Annotation、Calibration、CoordinateSystem
- 项目持久化（JSON 清单优先混合方案，见 ADR-0003）
- 原始跟踪数据与处理后数据的分层管理设计
- 核心数据结构单元测试（pytest）

**验收标准**
- [x] 能以编程方式创建项目、添加视频元数据与轨迹数据并持久化/恢复
- [x] 手工标注数据结构可无损转换为 DeepLabCut 标注格式的设计文档
- [x] 核心数据模型有单元测试且通过（56 tests；macOS/Windows Python 3.11 CI）

**主要技术风险**
- 数据模型设计不当会同时阻塞手工跟踪与 AI 跟踪 → 需在设计时对照 DLC 数据格式（CollectedData）与未来扩展（多目标、多关键点）。

---

## Phase 2 — Video Analysis MVP ✅

**目标**：第一版可使用的桌面应用，完成基本人工视频测量。

**Deliverables**
- PySide6 GUI 框架：主窗口、视频视图、时间轴
- 打开视频、播放/暂停、逐帧前后移动、跳转任意帧、帧号与时间显示
- 视频画面交互（缩放、平移）
- 手工目标标记（点选添加轨迹点）
- 保存和恢复实验项目

**验收标准**
- [x] 打开一段常见格式视频（MP4/H.264）流畅播放并可逐帧步进
- [x] 可在任意帧手工标记目标位置，形成轨迹
- [x] 关闭重开后项目状态完整恢复

> 均已在 macOS 全流程 Human Review 验证（2026-08-30）。Windows 真机验收（原 P24-10）经用户决定延后执行，完成后在本节补记；不阻塞 Phase 3。

**主要技术风险**
- OpenCV 读取与 Qt 显示的帧率/颜色空间转换性能；视频解码兼容性（依赖系统编解码器）。

---

## Phase 3 — Calibration & Physics Engine 🔄

**目标**：具备物理实验分析能力：标定、坐标系、运动学计算与基础图表。

**Deliverables**
- 长度标定（比例尺）、像素→物理坐标转换
- 坐标原点设置、坐标轴方向与旋转
- 运动学计算：x/y、vx/vy、ax/ay（含数值微分方法选择）
- 数据处理：平滑（Savitzky-Golay/Butterworth 等）、插值、异常值处理
- 基础图表：x-t、y-t、v-t、a-t、x-y 轨迹（PyQtGraph），当前帧与图表时间同步

**验收标准**
- [x] 标定后坐标转换误差满足设计精度（合成数据测试）
- [x] 用匀速/匀加速合成数据验证 v/a 计算正确
- [ ] 图表与视频帧同步联动

**主要技术风险**
- ~~数值微分的噪声放大：平滑与微分的顺序、参数选择需提供可调方案并记录 ADR。~~ 已解决：[ADR-0008](decisions/0008-numerical-differentiation-and-smoothing.md)——Savitzky-Golay 先平滑后微分，默认 window=7 / polyorder=2。
- 需求规范：[phase3-requirements.md](spec/phase3-requirements.md)（10 条验收标准，含 Subphase 划分建议）

---

## Phase 4 — Deep Learning Tracking ⬜

**目标**：接入 DeepLabCut/PyTorch，实现软件内"标注 → 训练 → 跟踪"完整流程。

**Deliverables**
- AI 跟踪项目创建（生成 DLC 项目结构）
- 手工标注 → DLC 训练数据转换
- 训练任务管理（进度、日志、可取消）
- 模型评价与视频推理
- 推理结果（含 confidence）导入统一数据体系
- AI 轨迹在 GUI 中显示

**验收标准**
- [ ] 在单摆基准视频上：少量标注 → 训练 → 全视频推理 → 轨迹显示，全流程在软件内完成
- [ ] 置信度数据随轨迹保存

**主要技术风险**
- DeepLabCut 的程序化 API 稳定性与 PyTorch 版本耦合；训练耗时与 GUI 响应（需后台任务框架）；依赖体积。

---

## Phase 5 — AI-assisted Annotation & Refinement ⬜

**目标**：提升少量标注条件下的使用体验，形成主动学习式迭代。

**Deliverables**
- 代表帧自动选取
- 低置信度检测、异常轨迹检测、困难帧发现（高速/遮挡/运动模糊区域）
- 用户快速修正工具与再训练/微调
- 训练结果比较与精度评价

**验收标准**
- [ ] 修正少量困难帧并再训练后，单摆基准实验的跟踪精度有可量化提升
- [ ] 困难帧定位准确率满足设计指标

**主要技术风险**
- 困难样本检测的启发式/统计方法有效性需实验验证。

---

## Phase 6 — Advanced Physics Analysis ⬜

**目标**：更丰富的物理分析能力。

**Deliverables**
- θ/ω/α 计算（含刚体角度定义）、phase space 与单摆相图、θ-ω 相图
- 周期分析、数据拟合、运动模型拟合（如单摆阻尼模型）
- 多目标数据分析、数据误差分析
- 后续研究：FFT、参数识别、阻尼分析、能量变化、理论模型对比

**验收标准**
- [ ] 单摆实验可得到 θ(t)、ω(t)、α(t) 与相图，拟合周期与实测一致（误差指标待定）
- [ ] 误差分析输出可解释

**主要技术风险**
- 角度定义（atan2 分支）、拟合初值与收敛稳定性。

---

## Phase 7 — Model Library ⬜

**目标**：完整的模型管理能力。

**Deliverables**
- 模型保存、命名、版本管理、评价、继续训练、复制、应用到新视频
- 模型元数据记录：名称、版本、跟踪目标、创建时间、训练数据量、验证结果、来源实验、训练配置

**验收标准**
- [ ] 已训练模型可保存并在新视频上直接推理；可记录并追溯全部元数据
- [ ] 模型库目录结构稳定且有迁移方案

**主要技术风险**
- 模型与 DLC 版本/目录结构的耦合，需在模型元数据中记录引擎版本以便迁移。

---

## Phase 8 — Export & Scientific Workflow ⬜

**目标**：完善科学实验工作流与数据导出。

**Deliverables**
- CSV / Excel 导出（frame、time、object、x、y、confidence 及运动学结果）
- 图表导出（Matplotlib 高质量图）、轨迹图片
- 跟踪后视频导出、项目归档
- 原始跟踪数据保留机制（可重新处理验证）

**验收标准**
- [ ] 导出的 CSV 可被 Excel/pandas 正常读取且列结构稳定
- [ ] 项目归档可完整恢复（含原始数据）

**主要技术风险**
- 大视频导出的编码性能与临时空间管理。

---

## Phase 9 — Optimization & Packaging ⬜

**目标**：性能优化与 Windows 桌面发布。

**Deliverables**
- 性能优化：内存、视频处理、AI 推理速度、GPU 支持、模型加载速度
- Windows 打包：PyInstaller / Nuitka 评估与选择，Inno Setup / NSIS 安装程序
- CPU 版与 NVIDIA GPU 加速版的发布策略、PyTorch/CUDA Runtime 与模型文件管理

**验收标准**
- [ ] `AIPhysicsTracker-Setup.exe` 在干净 Windows 10/11 上安装即用，无需 Python 环境
- [ ] 启动时间、安装体积、推理速度达到届时设定的指标

**主要技术风险**
- DeepLabCut+PyTorch 打包体积（数 GB 级）；CUDA 运行时分发；杀毒软件误报；打包工具与 PyTorch 的兼容性。

---

## Phase 10 — Extended Capabilities ⬜

**目标**：根据前面阶段的实验结果决定范围。

**候选方向**：多目标、多关键点、多摄像机、3D Tracking、实时摄像头、新的视觉模型、ONNX/OpenVINO 推理、更轻量部署、自动实验分析、插件系统。

**验收标准**：届时根据具体方向定义。

**主要技术风险**：范围蔓延；需以前面阶段实验数据为依据立项。

---

## 版本选择记录（摘要）

- Python 3.11（2026-08 确定）：DeepLabCut 3.x 官方支持 Python 3.10–3.12，PyTorch/PySide6 在 3.11 上轮子最成熟。详见 [development.md](development.md) 与 [decisions/0002](decisions/0002-choose-python-3.11.md)。
- GUI 框架（PySide6）与交互绘图（PyQtGraph）为"优先评估"项，最终确认分别在 Phase 2 / Phase 3 前完成并记录 ADR。
- License：TBD，须在发布前完成第三方依赖（DeepLabCut AGPL-3.0、Qt LGPL、FFmpeg 等）license review。
