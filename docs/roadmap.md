> main由用户提供方程 / 公式，通用平台承担后续分析；Phase 6已按[ADR-0017](decisions/0017-user-defined-equation-analysis-platform.md)完成重规划并交付6.1–6.4，论文固定模型仅作复现参考。

# Roadmap — AI Physics Tracker

本文档细化各开发阶段的目标、交付物、验收标准与主要技术风险。
状态标记：✅ 完成 / 🔄 进行中 / ⬜ 未开始

- 最近交付：**P6.4条件性参数SE / 95%局部t区间（2026-10-26；独立R3 / 双平台全量 / 全部HR通过，e31a4ac集成main，F1–F8 Closed）**
- 最近规划：**首个可交付版本的目标 / 范围 / 顺序于2026-10-26冻结**，文档 / MIT收口已完成；6.5完整单摆验收未开始。下一开发轮先准备6.5 mini-plan，R07仍搁置。
- 当前阶段：**Phase 6 进行中（2026-10-26，6.1 / 6.2 完成并集成 main；6.3计划已冻结、S0–S4已实现，S5自动Gate及整体HR已通过（2026-10-16），已以92d00a2集成main；6.3.1 S0–S4已实现，已完成并于2026-10-17通过用户HR，以c0d1461集成main；本机1232项 / 双平台CI / R6独立复审通过；P6.4参数误差解释已于2026-10-26以e31a4ac集成main；6.5完整单摆验收未开始；2026-10-24用户取消新增两轨迹比较 / 同帧差值）**
- 已交付 GUI 增量：首次学习 20 个人工帧、默认 K-means、推荐框自定义算法及沿真实建议帧连续标注；[计划](status/initial-annotation-guidance-plan.md)，Human Review 已通过。
- 各阶段完成后暂停，等待下一条开发指令再进入下一阶段；收尾要求见 `AGENTS.md` 第 11 节。

---

## 首个可交付版本：Mac教学试用（目标已冻结，交付未完成）

[正式目标与完成证据](spec/first-deliverable-target.md)是这次跨阶段交付的范围入口，[许可与分发边界](licensing.md)记录原创代码MIT及第三方 / 权重边界。

面向大学物理实验学生 / 教师，完成单视频 / 单目标二维运动的标注、训练 / 跟踪、修正、标定 / 分析、CSV＋PNG＋方法说明及同机保存重开。提供有分发授权的真实单摆，以及匀速直线 / 匀加速直线 / 二维抛体 / 简谐振动四类合成真值与对照报告；一名独立目标用户完成真实单摆任务。

顺序：**原定6.5验收→最小科学导出与合成核查→Mac试用包 / 教程 / 离线验证→独立用户试用与修复**，完整模型库随后推进。首次准备可联网，准备后支持流程离线；试用者无需配置Python，包不附第三方权重，接受未公证应用的单应用手动放行。

这是Phase 8 / 9部分交付的前置，不表示完整Phase 7 / 8 / 9已开始或完成；原6.5 AC、Phase 5已归档缺口及Windows正式交付边界保持。具体实施仍按独立mini-plan和对应Gate推进。

---

## Phase 0 — Project Initialization ✅

**目标**：建立可长期维护的项目仓库与文档基础。

**Deliverables**
- 仓库基础结构（docs/、src/、tests/、scripts/、resources/、examples/、packaging/）
- README.md（项目介绍）、AGENTS.md（Agent 开发指南）、.gitignore、LICENSE（初始化时TBD，现为MIT）
- docs/：roadmap.md、architecture.md、development.md、decisions/（ADR）
- Git 仓库初始化、GitHub 远程仓库（初始化时Private，当前Public）、首次提交与推送

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

## Phase 3 — Calibration & Physics Engine ✅

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
- [x] 图表与视频帧同步联动

> 全部验收标准在 3.4 整体 Human Review 中确认通过（2026-08-31）。310 tests + 双平台 CI 全绿。

**主要技术风险**
- ~~数值微分的噪声放大：平滑与微分的顺序、参数选择需提供可调方案并记录 ADR。~~ 已解决：[ADR-0008](decisions/0008-numerical-differentiation-and-smoothing.md)——Savitzky-Golay 先平滑后微分，默认 window=7 / polyorder=2。
- 需求规范：[phase3-requirements.md](spec/phase3-requirements.md)（10 条验收标准，含 Subphase 划分建议）

---

## Phase 4 — Deep Learning Tracking ✅

**目标**：接入 DeepLabCut/PyTorch，实现软件内"标注 → 训练 → 跟踪"完整流程。

**Deliverables**
- AI 跟踪项目创建（生成 DLC 项目结构）
- 手工标注 → DLC 训练数据转换
- 训练任务管理（进度、日志、可取消）
- 模型评价与视频推理
- 推理结果（含 confidence）导入统一数据体系
- AI 轨迹在 GUI 中显示

**验收标准**
- [x] 在单摆基准视频上：少量标注 → 训练 → 全视频推理 → 轨迹显示，全流程在软件内完成
- [x] 置信度数据随轨迹保存（4.3 合成数据及真实 CPU 推理 save/load 验证）

4.3 Qt-free 推理/导入/运动学衔接的实现与验收见 [4.3 计划](status/phase-4.3-plan.md)。
4.4 的 Task Panel、AI 视觉样式、模型评价与 macOS Human Review 已通过，见
[4.4 计划与验收](status/phase-4.4-plan.md)。最终 `main` 集成 CI 在 macOS/Windows
Python 3.11 通过。经用户批准，Windows 真机/CUDA 验收延期到 Phase 9 打包前；该延期不等同已验证。

**主要技术风险**
- DeepLabCut 的程序化 API 稳定性与 PyTorch 版本耦合；训练耗时与 GUI 响应（需后台任务框架）；依赖体积。

---

## Phase 5 — AI-assisted Annotation & Refinement ✅

**目标**：形成“AI 推荐高价值帧、用户提供正确标签、固定验证集比较迭代结果”的
Human-in-the-loop refinement 闭环；预测永不自动成为 ground truth。

**Deliverables**
- 基于 DLC uniform/K-means 的初始代表帧选择
- 困难帧 candidate pool：confidence/缺测、trajectory jump、局部平滑残差、既有修正邻域
- 可解释 ranking → temporal de-duplication → visual/temporal diversity → Top N
- Suggested Frames：查看 AI prediction → Accept / Correct / Skip → 下一帧
- completed infer result 与 active AI result 分离；run 级 clear/activate/replace（Phase 4 Review F2）
- 固定 validation series、refinement iteration history 与跨轮结果比较
- 规则型 Training Advisor：补标数、先修/先训、resume/restart、additional epochs、batch size、snapshot
- 统一任务生命周期，收敛旧 coordinator 双轨（Phase 4 Review F3）
- 三工作区、常驻状态头与状态驱动任务卡；普通用户无需选择 run/snapshot/mode/series
- 未采用候选预览、困难帧审核、显式采用与 Ready for Analysis / Charts 交接

**Subphases**

| Subphase | 名称 | 核心交付 |
| --- | --- | --- |
| 5.0 ✅ | Tracking Pipeline Consolidation | F3：统一 runner/actions/task handle 生命周期，旧 coordinator 已移除 |
| 5.1 ✅ | Representative Frame Selection | DLC uniform/K-means 初始建议帧，自适应抽帧优化与 Human Review 通过 |
| 5.2 ✅ | Difficult Frame Mining | 全帧原始预测读取、四信号可解释评分、时间去重/多样性、后台任务与真实基准；饱和时明确返回无候选（AC-10 达成） |
| 5.3 ✅ | Suggested Frame Review & Correction | Accept/Correct/Skip、prediction provenance、恢复（Human Review 通过） |
| 5.4 ✅ | Iteration History & Result Activation | Candidate 模式、Activate/Replace/Clear 原子事务、fixed validation series（复核缺口已随 5.5 Entry Gate 关闭） |
| 5.5 ✅ | Training Advisor & Retraining | 确定性规则 Advisor、显式 restart/resume（DLC snapshot 贯通）、跨轮比较与 lineage 追溯（真实 DLC smoke + HR 通过） |
| 5.6 ✅ | Refinement Loop Integration & Acceptance | 真实闭环完成并归档三类 delta；AC-9 改善证据未达成（明示缺口，成因已分析） |
| 5.7 ✅ | Interaction Flow Redesign | 三工作区 + 状态驱动任务卡 + C1/C2（ADR-0016）；R1/R2 CLOSED，HR1 findings 闭环，最终 Human Review 通过 |

**验收标准**
- [x] F3 关闭：旧 coordinator lifecycle 已移除，训练/推理只维护统一 runner/actions/task handle 路径
- [x] DLC uniform/K-means 可在 working zone 推荐去重代表帧，不自动创建标签（✅ 5.1 完成）
- [x] 困难帧扫描消费指定 infer run 的全帧原始预测；连续低 confidence 片段不会垄断 Top N（✅ 5.2 完成）
- [x] Accept 不产生 ground truth，Correct 保留 prediction provenance，Skip 不造坐标；保存重开一致（✅ 5.3 完成）
- [x] 新 completed infer result 可显式激活/替换，且不丢 manual、旧 run 产物与历史；事务可撤销并使派生 stale（✅ 5.4 完成）
- [x] 至少两轮使用相同 fixed validation membership，RMSE 与 coverage/confidence 分开报告（✅ 5.6：iter1–iter4 同一 series，报告分栏）
- [x] Training Advisor 覆盖补标、resume/restart、epochs、batch size 与 snapshot，且不会自动启动无限训练（✅ 5.5）
- [x] 单摆基准完成一次完整 refinement 闭环，并记录 fixed-validation、coverage、remaining difficult frames 的变化（✅ 5.6；改善幅度缺口见下）
- [x] 冻结人工审计集上的 Precision@N/review yield 优于 lowest-confidence-only Top N 基线（✅ 5.2：0.800/0.300 vs 0.600/0.000）

> **已批准的未达成目标（2026-09-16）**：Phase 5 requirements AC-9 还要求至少一次
> 冻结基准上可复现的 refinement 改善；真实四轮实验最佳为 −3.3%，未达到 ≥5% 目标。
> 用户批准按真实结果归档并停止扩大实验，不修改验收口径。闭环、三类 delta 与可追溯性
> 已完成；改善证据留作以后使用独立保留帧或第二视频重新评估。详见
> [Phase 5.6 review](reviews/phase-5.6-review.md) 与
> [loop report](benchmarks/phase-5-loop-report.md)。

**主要技术风险**
- confidence 不等于定位误差，连续遮挡会淹没候选 → 多信号候选 + 去重/多样性 + 固定人工审计集。
- 每轮随机重分训练/验证会制造不可比结果 → 显式冻结 validation membership。
- DLC 高层 outlier API 有文件副作用且不返回综合排名 → 只在 adapter 复用适合的算法/primitive，本项目维护策略层。
- 需求规范：[phase5-requirements.md](spec/phase5-requirements.md)；总计划：[PHASE_5_PLAN](status/phase-5-plan.md)。

---

## Phase 6 — Advanced Physics Analysis 🔄

**目标**：更丰富的物理分析能力。

**状态**：6.1 / 6.2已完成并集成main（6.2合并 `12b0911`，Issue #27）。科学 / 事务1007全量、独立复审Approve；控件51项GUI、最终双平台1008 passed / 2 skipped及全部Human Review通过。6.3已于2026-10-15完成grilling并获用户认可，见[6.3已冻结计划](status/phase-6.3-plan.md)：显式函数编辑 / 单标量拟合、独立通用信号重复间隔与可选结果公式；S0–S4已实现，S5自动Gate及整体HR已通过（2026-10-16），已以92d00a2集成main。6.3.1英文分析体验S0–S4已实现，已完成并于2026-10-17通过用户HR，以c0d1461集成main；本机1232项 / 双平台CI / R6独立复审通过；P6.4参数误差解释已于2026-10-26以e31a4ac集成main；完整单摆整体验收仍待6.5。2026-10-24用户在[6.4 grilling](status/phase-6.4-plan.md)明确取消新增两轨迹比较 / 同帧差值，既有多轨迹叠图保留。
规划入口：[phase6-requirements.md](spec/phase6-requirements.md)、
[phase-6-plan.md](status/phase-6-plan.md)、[phase-6.1-plan.md](status/phase-6.1-plan.md)、[phase-6.2-plan.md](status/phase-6.2-plan.md)。

**Deliverables**
- θ/ω/α 计算（含刚体角度定义）、phase space 与单摆相图、θ-ω 相图
- 周期分析、数据拟合、运动模型拟合（用户提供方程，单摆阻尼模型可作示例）
- 多目标数据分析、数据误差分析
- 后续研究：FFT、参数识别、阻尼分析、能量变化、理论模型对比

**验收标准**
- [ ] 单摆实验可得到 θ(t)、ω(t)、α(t) 与相图，拟合周期与实测一致（误差指标待定）
- [x] 误差分析输出可解释（P6.4，2026-10-26独立 / 双平台 / 全部HR通过）

完整单摆全流程验收留待6.5；本次不将参数误差解释的通过扩大为整个Phase 6完成。

**主要技术风险**
- 角度定义（atan2 分支）、拟合初值与收敛稳定性。

---

## Phase 7 — Model Library ⬜

**目标**：完整的模型管理能力。

完整模型库排在首轮Mac教学试用之后，先沿用已有模型 / run基础，见[首发目标](spec/first-deliverable-target.md)。

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

选定结果CSV＋方法 / 参数说明及现有PNG的交付核对前置到[首轮教学试用](spec/first-deliverable-target.md)；原生Excel、视频导出及通用跨机器归档后续排。以下完整Phase AC保持未完成。

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

Mac arm64小范围教学试用包、独立环境 / Repair复用与离线验证已前置到[首发目标](spec/first-deliverable-target.md)，具体实现尚未开始；本节正式Windows交付目标保持。

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
- GUI框架PySide6与交互绘图PyQtGraph已在Phase 2 / 3采用，当前分工见[架构总览](architecture.md#当前架构总览接手先读)。
- License：2026-10-26用户确认原创软件采用MIT，根LICENSE及包元数据已落实，沿用ADR-0011与历史Mac发行方向；具体第三方 / 权重及分发边界见[licensing](licensing.md)，具体安装包材料尚待准备。

2026-10-17维护补丁：[自动采用合格近似时序](status/automatic-timing-plan.md)，取消Review timing / Yes，独立review / 双平台CI / 本轮HR于2026-10-17均通过并集成main；不改变Phase 6.4 / 6.5状态。

2026-10-18维护增量：[公式拟合联动](status/fit-linked-source-plan.md)源自动补齐、相关预览 / 单位 / 来源说明同步，本机1271 / 独立复审 / 双平台CI / 本轮HR通过，以aa86d79集成main。

- [x] 当前拟合页补齐缺失 / stale源，沿用所选轨迹设置，冲突定义保留并提示；相关输入变化刷新预览 / 单位 / 说明。
- [x] 正式Fit保持显式；旧结果保留并按上游变化标stale，历史只读。

本轮不改变上方Phase 6比较 / 误差及完整单摆验收的未完成状态。

2026-10-18内部整理：[计算配方统一解释](status/source-recipe-plan.md)，26af812集成main；全量1276 / 独立复审 / 双平台CI通过。

- [x] 同步写入 / 后台校验 / 拟合与GUI恢复共用SG、参考、时序定义，重复表与线性后台时序覆写删除。
- [x] 图例读取来源字段，不从摘要文字猜计算含义；现有数值 / 操作 / 未知数据保护保持。

该内部整理未改变Phase 6未完成验收项；后续重复间隔联动见下述R03交付，6.4 / 6.5未开始。

2026-10-18维护增量：[R03重复间隔源联动 / 候选交点预览](status/recurrence-linked-plan.md)，全部AC / Independent / 双平台CI / HR通过，2600f2a集成main。F1拖线跳顶修复4bd723a经81项相关GUI / 独立17 / 最终双平台1296 passed（2个既有可选skip）及用户复测通过；正式Measure、算法、格式与事务契约保持。R01–R03已完成；R04随后获用户授权，当前实施 / Gate状态见顶部及current.md；6.4 / 6.5未开始。

2026-10-18维护收尾：[R04分析主干职责重构](status/analysis-workflow-plan.md)全部Gate与本轮HR通过，085219e集成main；计算只持有必要冻结输入，同步 / 后台共用受控核对发布，顶部 / 按钮 / 源准备共用事实，自动补源跳顶F1 Closed。本机1316 / 独立Approve / 最终双平台通过。R07仅形成方案与待办，不开始6.4 / 6.5。


2026-10-20维护收尾：[R08历史查看流程归属](status/signal-history-plan.md)全部Gate及本轮HR通过，f34d3b8集成main；全量1329 / 独立R2 Approve / 最终双平台通过，F1 Closed。

- [x] 两个历史入口共用当前草稿保护及查看生命周期，保留未完成 / 无效文本。
- [x] 返回 / 采用 / 切Charts或Explore / 换上下文 / 关闭时取消旧查看，迟到结果不覆盖当前显示。
- [x] 查看与采用不发布、不改工程事务或尝试日志；正式Fit / Measure仍显式，两个执行器及科学算法保持。

本维护周期已收尾，停止等待用户指令；Phase 6比较 / 误差和整体单摆验收仍保留未完成状态。

2026-10-24：[P6.4](status/phase-6.4-plan.md)获开工授权，Issue #42 / `feat/p6.4-parameter-error`；S0契约及S1统计 / 展示已实现，全量1387 / 独立R2 Approve / 双平台CI通过，待本轮HR，尚未集成main。6.5整体验收不在本轮。

2026-10-24 HR后扩展：用户确认95%双侧局部t置信区间，P6.4 mini-plan v1.1 / ADR-0029已更新；产品12ea18d已实现，独立R3 Approve / 定向129及关联110通过，最终全量1408 / 双平台CI40077232972通过，新HR待用户。未合并，不进入6.5。

2026-10-26 HR局部返工：用户确认其余通过，F4横滑Closed；F6区间可读性 / 列宽拖动、F7术语hover / Fixed引导已实现，统计算法及摘要契约保持。验证与三项补测见[current](status/current.md) / [Review](reviews/phase-6.4-review.md)，未整体完成HR，不合并、不进入6.5。

2026-10-26追加布局反馈：用户要求整个面板可拖动调大小，1082a09以左右 / 上下分隔条替换固定布局，移除结果高度 / 右栏最大宽度限制，取消区间强制分行并填满余宽。F6仍待当前布局HR，自动验证以current为准。

2026-10-26 Fixed缺陷HR：用户无法勾选空白Fixed列，9c1aa63复用既有清晰空框 / 整格点击交互，并支持空格切换、保持历史只读。相关56项GUI / 原体验工程打开自检通过，双平台及F8真人补测以current为准；数值不改，未合并、不进入6.5。

2026-10-26 P6.4完整收尾：用户最终“HR通过，收尾”，e31a4ac以--no-ff集成并push main；源码 / 测试与最终产品9c1aa63一致，R3 Approve / 最终双平台各1412 passed、2个既有可选skip / GUI56及本轮HR通过，F1–F8 Closed。Issue #42 Closed / PR #43 Merged。6.5未开始；上方各轮待验描述保留历史事实。
