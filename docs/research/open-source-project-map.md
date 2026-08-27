# Open-source Project Map — AI Physics Tracker

面向未来 Coding Agent 的开源生态与代码参考地图。本文件整合 `docs/research/raw/` 下 16 份源码级调研笔记，回答：哪些项目与 AI Physics Tracker 最接近、每个项目最值得读的代码在哪里、各能力维度分别采用什么实现思路、哪些设计应借鉴/回避、哪些 tracking 技术值得 benchmark、许可证如何影响发布，以及当前推荐的架构方向。

**使用方式**：本文件是索引与结论层；任何要真正动手实现的模块，先读本文件对应小节，再进入 raw notes 找到具体源码路径与调用链。

---

## 1. Executive Summary

- **调研范围**：16 个开源项目，分四类——物理/视频分析产品（Tracker、Kinovea、OpenPhysics TrackLab、Motion Tracker Beta、GoTracker）、可训练姿态跟踪（DeepLabCut、SLEAP、TrackingLaboratory TrackLab）、markerless 运动学/标定（Sports2D、Pose2Sim、DLC2Kinematics、pyxy3d）、即用型基础点/掩码跟踪（TAPNet/TAPIR、CoTracker、SAM2）。全部笔记基于 2026-08-27 的源码快照，每份记录了 commit SHA。
- **最值得深入参考的 5 个项目**：**OpenPhysics TrackLab**（Phase 1–3 领域模型/标定/运动学的最佳小型范本）、**Kinovea**（Windows 桌面播放器/缓存/时间轴/跟踪生命周期/持久化 sidecar 的最成熟参考）、**DeepLabCut**（Phase 4–7 可训练引擎适配的首选）、**SLEAP**（标注校正 UX 与后台任务隔离的最佳参考）、**Tracker (OSP)**（物理量体系与 keyframe 式自动跟踪交互的 prior art）。SAM2/TAPIR/CoTracker 作为引擎 benchmark 对象，不作架构范本。
- **最重要的架构结论**：
  1. **规范数据单元是"带上下文的观测"，不是裸坐标**——所有强实现（Tracker 的 Step、Kinovea 的 TimedPoint、SLEAP 的 PredictedInstance、DLC 的 likelihood、TAPIR 的 visibility+uncertainty）都在坐标之外携带 frame/time、source、confidence/visibility。Phase 1 的 `TrackPoint` 必须一步到位。
  2. **原始观测不可变，派生数据分层**——标定坐标、平滑值、微分、拟合全部是带 provenance 的派生层；任何 AI 引擎的 HDF5/Pickle 都不能成为唯一事实源。
  3. **一个产品级后台任务抽象 + 引擎适配器**——训练/推理/导出走统一的可取消任务（SLEAP 的 subprocess + 结构化 JSON 进度是最佳范本），OpenCV/DLC/TAPIR/SAM2 全部藏在适配器后面（Kinovea 的 `AbstractTracker` 是接口范本）。
- **最重要的许可证结论**：CoTracker 主体为 **CC BY-NC 4.0**，是商业分发的直接阻断项；Tracker/Kinovea/Motion Tracker Beta（GPL）与 OpenPhysics TrackLab（AGPL）只能作参考不能抄代码；DLC（LGPL-3.0）+ SAM2（Apache-2.0）是当前最可行的引擎路线，但每个 checkpoint/权重需单独审计。
- **最重要的 benchmark 结论**：没有任何项目同时提供"Windows 桌面 UX + 物理标定 + 少量标注训练 + 任意点即时跟踪 + 可修正置信度闭环 + 模型库"。这个组合是本项目的差异化空间。默认引擎决策推迟到统一 pendulum benchmark 之后（见第 11 节）。

---

## 2. Project Landscape

### 2.1 分类与角色

| 类别 | 项目 | 一句话定位 | 对我们的角色 |
| --- | --- | --- | --- |
| 物理/视频分析产品 | OpenPhysics TrackLab | 浏览器版物理视频标注 MVP（TS/SceneryStack） | **直接架构参考**（Phase 1–3） |
| | Kinovea | Windows C#/WinForms 视频分析产品 | **直接桌面参考**（视频/时间轴/持久化/发布） |
| | Tracker (OSP) | Java/Swing 物理教育视频分析标准件 | 物理量体系与交互 prior art |
| | Motion Tracker Beta | PyQt5/OpenCV/PyNumDiff 小型端到端 | Python 端到端对照与反面教材 |
| | GoTracker | Go 单点 template-matching 最小实现 | 最小跟踪引擎/基线范本 |
| 可训练跟踪/姿态 | DeepLabCut | 少量标注→训练→推理（PyTorch 引擎） | **Phase 4–7 首选引擎适配对象** |
| | SLEAP | 标注/训练/校对桌面工作流（PySide6） | **标注校正 UX + 任务隔离参考** |
| | TrackingLaboratory TrackLab | Hydra 模块化 MOT 研究框架 | 模块列契约/引擎组织参考 |
| Markerless 运动学 | Sports2D | 2D 人体姿态→角度→米制导出 | 置信度→NaN 策略、导出参考 |
| | Pose2Sim | 多相机 2D→3D→OpenSim | 后处理流水线/滤波参考（未来 3D） |
| | DLC2Kinematics | DLC 输出后处理库 | 下游 API 形态参考（含数值陷阱） |
| | pyxy3d | PySide6 多相机标定/三角化 | 跟踪器协议/包结构参考（未来） |
| 即用型基础跟踪 | TAPNet (TAPIR/TAPNext) | 任意点跟踪 + visibility/uncertainty | 引擎 benchmark 候选 |
| | CoTracker3 | 联合多点跟踪（offline/online） | 引擎 benchmark 候选（许可证受限） |
| | SAM2 | 可提示掩码传播 + 交互修正 | 可选 mask 引擎 + 修正 UX 参考 |

**命名提醒**：`OpenPhysics/TrackLab`（浏览器物理工具）与 `TrackingLaboratory/tracklab`（MOT 研究框架）是两个不相关的项目，raw notes 分别记录，阅读时不要混淆。

### 2.2 Activity Map（2026-08-27，GitHub REST API）

Stars/forks 只表示生态规模；Open items 可能包含 PR。活跃度判断：DLC、SLEAP、Sports2D、Pose2Sim、TAPNet、SAM2 活跃度足以支撑直接集成实验；DLC2Kinematics（2023-12 后停滞）只取 API 形态、不取其数值行为；pyxy3d 同样停滞，仅作未来参考。

| Project | Stars | Last pushed | Latest release | Snapshot commit |
| --- | ---: | --- | --- | --- |
| OpenSourcePhysics/tracker | 306 | 2026-08-23 | v6.1.6 (2024-02) | 7674d2c (2026-08-10) |
| Kinovea/Kinovea | 490 | 2026-08-23 | 无公开 release | b9bf901 (2026-08-15) |
| OpenPhysics/TrackLab | 0 | 2026-08-24 | v0.9.0 (2026-06) | 05c7079 (2026-08-19) |
| TrackingLaboratory/tracklab | 247 | 2026-05-01 | v1.3.24 (2026-05) | 5767e86 (2026-05-01) |
| davidpagnon/Sports2D | 288 | 2026-08-25 | v0.8.34 (2026-07) | 4392177 (2026-08-25) |
| perfanalytics/pose2sim | 784 | 2026-08-24 | v0.10.49 (2026-07) | 65bbb05 (2026-08-24) |
| AdaptiveMotorControlLab/DLC2Kinematics | 154 | 2023-12-13 | v0.0.7 (2023-06) | dd2b036 (2023-12-13) |
| DeepLabCut/DeepLabCut | 5,745 | 2026-08-26 | v3.0.1 (2026-07) | 7833886 (2026-08-26) |
| talmolab/sleap | 610 | 2026-08-12 | v1.6.5 (2026-08) | 6967e04 (2026-08-13) |
| google-deepmind/tapnet | 1,968 | 2026-07-22 | 无公开 release | c2cbab8 (2026-07-22) |
| facebookresearch/co-tracker | 5,079 | 2026-03-03 | 无公开 release | 82e02e8 (2025-01-21) |
| facebookresearch/sam2 | 19,770 | 2026-05-30 | 无公开 release | 2b90b9f (2024-12-15) |
| flochkristof/motiontracker | 33 | 2026-03-02 | v0.1.6 (2023-05) | d8a6b60 (2026-03-02) |
| ubermensch19/pyxy3d | 0 | 2023-12-27 | 无 | e8608bc (2023-12-27) |
| thalestmm/go-tracker | 0 | 2026-04-21 | v0.2.0 (2026-04) | d880de8 (2026-04-21) |

上游代码会变化。未来 Agent 使用本文件时，先核对各 raw note 记录的 SHA 与上游默认分支；`.upstream/` 本地快照（gitignored）可用于离线复核。

---

## 3. Per-project Code Map

以下为每个项目的**工程级摘要**：为什么相关、关键源码路径、关键类/函数、调用链。完整细节见对应 raw note。

### 3.1 OpenPhysics TrackLab — Phase 1–3 首选架构范本

- **Repository**: <https://github.com/OpenPhysics/TrackLab> · commit `05c7079` · AGPL-3.0-or-later · TypeScript / SceneryStack / OpenCV.js WASM
- **为什么相关**：与我们 roadmap 最接近的小型实现——物理优先、模型/视图分离干净、原始点与派生运动学分立、显式像素→模型变换、frame/time 语义有测试、手工/自动插点策略分离、跟踪在 worker 中跑。缺项目持久化与可训练模型。
- **关键源码**：

| 路径 | 内容 |
| --- | --- |
| `src/track-lab/model/Track.ts` | `TrackPoint {frame, time, x, y}`（模型坐标）、`KinematicPoint`（v/a 含 null 空缺）——我们 TrackPoint 的目标形状雏形，需加 source/confidence |
| `src/track-lab/model/TrackingModel.ts` | 轨迹集合状态机：`addPointToTrack`（自动 first-wins）、`addOrReplacePointOnTrack`（手工 last-wins）、`insertPointSorted`、`retransformTrackPoints`（标定变更后点钉回原像素）、`initTracker` 用递增 version 丢弃过期异步初始化 |
| `src/track-lab/model/KinematicsComputer.ts` | 纯函数 `computeTrackKinematics`：按各点时间戳做前向/后向/中心差分，稀疏点不假设恒定帧距；无平滑 |
| `src/track-lab/model/ModelViewTransformFactory.ts` | `buildModelViewTransform`：`s = 像素距离/真实距离`，复合 `T(origin)·R(angle)·S(s, -s)`（Y 翻转）；退化输入返回 identity |
| `src/track-lab/model/VideoPlaybackModel.ts` | time 为权威、`frame = round(time × fps)`；`seekByFrames` 步进 `1/fps`；测试覆盖 29.97 fps |
| `src/tracking/OpenCVTracker.ts` + `public/opencv-worker.js` | worker 协议：`init`/`track` 消息，高斯模糊 + `TM_CCOEFF_NORMED`，返回 `(x, y, confidence)`；facade 拒绝过期 promise、阈值 0.25、reset 时释放模板 |
| `src/track-lab/model/TrackExporter.ts` | 稀疏多轨迹 CSV 合并、空单元格、稳定表头 |
| `tests/track-lab/model/*` | Kinematics/TrackingModel/Exporter/Playback 纯模型测试——Phase 1 测试形态范本 |

- **核心调用链**（自动跟踪）：

```text
AutoTrackerNode 拖框
  -> TrackingModel.resetTracker / initTracker(video, region)
  -> OpenCVTracker.initFromVideo -> worker "init"
video timeupdate/seeked
  -> requestAnimationFrame 合并 + in-flight 防并发
  -> TrackingModel.trackFrame -> OpenCVTracker.track -> worker "track"
  -> 置信度过滤 -> 逆变换到模型坐标 -> addPointToTrack（first-wins）
  -> kinematics/table/graph 响应式更新
```

- **局限**：无项目持久化；阈值 0.25 宽松、窗口搜索面向固定相机；无 source/confidence 字段；AGPL 只能借鉴不能抄。
- **详读**：[raw/openphysics-tracklab-notes.md](raw/openphysics-tracklab-notes.md)

### 3.2 Kinovea — Windows 桌面层最强参考

- **Repository**: <https://github.com/Kinovea/Kinovea> · commit `b9bf901` · GPL-2.0 · C#/WinForms + 原生 FFmpeg/OpenCvSharp
- **为什么相关**：Windows 原生视频 UX 最成熟实现：解码/缓存/预缓冲、时间戳时间轴、可跟踪 drawing、标定 sidecar、NSIS 发布链。是架构参考而非 Python 依赖。
- **关键源码**：

| 路径 | 内容 |
| --- | --- |
| `Kinovea.Video/VideoReader.cs` | 解码器抽象契约：`Open/MoveNext/MoveTo/UpdateWorkingZone/EnumerateFrames`；`MoveBy` 经 `Info.AverageTimeStampsPerFrame` 把帧位移换算成时间戳位移；显式支持 on-demand/预缓冲/缓存三种读取器——比单个 `cv2.VideoCapture` 强得多的模型 |
| `Kinovea.Video/FrameContainers/Cache.cs`, `PreBuffer.cs` | 帧缓存/预缓冲策略，设计帧缓存前必读 |
| `Kinovea.ScreenManager/PlayerScreen/Controls/FrameTracker.cs` | 时间轴控件：`Scrub()` 拖动中只发 `PositionChanging`、`Commit()` 松手才发 `PositionChanged`——拖动反馈与昂贵解码解耦；渲染缓存段/关键帧/轨迹标记 |
| `Kinovea.ScreenManager/Metadata/Timeline.cs` | `Timeline<T>`：`SortedList<long,T>` 稀疏时间戳键值，`ClosestFrom` 二分查找、`Trim` 释放 IDisposable |
| `Kinovea.ScreenManager/Tracking/Tracking/AbstractTracker.cs` | 通用跟踪器契约：`IsReady/TrackStep/CreateTrackPoint/CreateReferenceTrackPoint/Trim/Clear/Dispose`——算法结果、存储点创建、手工参考点创建三者分离，直接映射我们的引擎适配器接口 |
| `.../TemplateMatching/TrackerTemplateMatching.cs` + `TrackingTemplate.cs` | `Cv2.MatchTemplate` 实现；`TrackingSource`（Manual/Auto/ForcedClosest）+ score；模板为**ephemeral 状态**不持久化，重开 `.kva` 后由当前帧重建；模板更新策略避免漂移 |
| `.../DrawingTrack.cs` | 可跟踪 drawing：`PerformTracking` 拒绝重复时间戳、追踪结束才更新运动学；手工修正后 `CreateReferenceTrackPoint` 重建模板 |
| `Kinovea.ScreenManager/Measurement/Calibration/CalibrationHelper.cs`, `CalibratorPlane.cs` | 标定服务：线/平面标定、`GetPoint/GetPointAtTime`（标定本身可被跟踪→时变标定）；`CalibratorPlane` 是 quad→quad 单应，变换栈 viewport→image→rectified→grid/world（Y-up） |
| `.../LinearKinematics.cs` | 基于时间戳+标定坐标的位移/速度/加速度序列，可叠加 `MotionFilter` |
| `Kinovea.ScreenManager/Metadata/Serialization/MetadataSerializer.cs` | `.kva` XML sidecar：版本号、视频路径、图像尺寸/时序先读再读坐标（换视频可重映射） |
| `Installer/makeinstaller.py` + `kinovea.nsi` | MSBuild Release x64 → NSIS 安装包；`Kinovea.targets` 复制 FFmpeg/OpenCvSharp 原生 DLL |

- **调用链**（时间轴→解码）：

```text
FrameTracker 鼠标/键盘 -> PositionChanging|PositionChanged
  -> PlayerScreenUserInterface2 -> FrameServerPlayer
  -> VideoReader.MoveTo / MoveBy -> VideoFrame -> 刷新 + 标记更新
```

- **局限**：C#/WinForms、数据与 GUI 对象耦合较重（domain 不独立）；无学习模型；GPL。
- **详读**：[raw/kinovea-notes.md](raw/kinovea-notes.md)

### 3.3 Tracker (OSP) — 物理量体系 prior art

- **Repository**: <https://github.com/OpenSourcePhysics/tracker> · commit `7674d2c`（branch `SwingJS`）· GPL-3.0 · Java/Swing，依赖独立的 `OpenSourcePhysics/osp` 核心库
- **为什么相关**：我们产品对标物。frame/step 语义、坐标轴/标定作为一等 track 对象、丰富运动学变量表、keyframe+autofill 自动跟踪修正是最完整的 prior art。实现层面是庞大 Swing/OSP 对象图，解码器在 osp 仓库，不可作代码依赖。
- **关键源码**：`PointMass.java`（`createStep/getStep/getVelocity/getAcceleration`；`dataVariables` 覆盖 t/x/y/r/vx/vy/v/ax/ay/a/theta/omega/alpha/step/frame/px/py/momentum/KE——我们 ProcessedData 变量清单的检查表）；`PositionStep.java`（单帧可编辑位置）；`AutoTracker.java`（`findMatchTarget(predict)` 用短历史做速度/加速度预测放搜索窗；`STOP_NO_MATCH/NEVER_STOP` 停止策略、keyframe 重对齐交互）；`Calibration.java`/`CoordAxes.java`（标定与坐标系是可编辑的 per-frame track，写入 OSP `ImageCoordSystem`）；`Derivative.java`/`SavitzkyGolayFilter.java`/`ButterworthFilter.java`（滤波器独立对象、NaN 分段边界一侧多项式拟合）；`TrackerIO.java`/`ExportDataDialog.java`（.trk/.trz、按 frame 合并多 track 稀疏导出）。
- **调用链**：

```text
鼠标事件 -> PointMass.createStep(frame, x, y) -> PositionStep
  -> step 数组 -> PointMass.getData -> Plot/Table/Export
AutoTracker: 菜单 -> findMatchTarget(predict) -> OSP TemplateMatcher
  -> autoMarkAt(frame,x,y) -> FrameData + 停止策略/重对齐
```

- **关键教训**：区分 image/world/screen 三种坐标；**不要**把 GUI 子类当作持久化数据模型（其 XML loader 模式是反面教材的根源）。
- **详读**：[raw/tracker-notes.md](raw/tracker-notes.md)

### 3.4 DeepLabCut — Phase 4–7 首选可训练引擎

- **Repository**: <https://github.com/DeepLabCut/DeepLabCut> · commit `7833886` · v3.0.1 · LGPL-3.0-or-later · Python 3.10–3.12 · PyTorch 2.x（保留 TF 兼容路径）· PySide6 GUI，标注委托 napari-deeplabcut
- **为什么相关**：与 roadmap Phase 4–7 一一对应的引擎：稀疏标注→训练集→checkpoint→视频推理（per-keypoint likelihood）→outlier 修正→再训练→模型复用。项目目录与 scorer/HDF5 约定应视为**外部适配契约**，不是我们的领域模型。
- **关键源码**：

| 路径 | 内容 |
| --- | --- |
| `deeplabcut/compat.py` | 引擎无关 API 门面：`train_network/evaluate_network/analyze_videos` 按 `Engine` 分发——**DLCAdapter 的正确集成点** |
| `deeplabcut/core/config/project_config.py` | `ProjectConfig`：typed config.yaml 表示、校验/版本迁移/legacy 别名 |
| `deeplabcut/generate_training_dataset/trainingsetmanipulation.py` | 标注↔训练集一致性维护；标签为 Pandas MultiIndex (scorer/bodyparts/coords)，HDF5/CSV 双写——Phase 1 无损转换设计的对照物 |
| `deeplabcut/pose_estimation_pytorch/apis/training.py` | `train_network`→`DLCLoader`→`train`：模型/日志/DataLoader/runner 组装，支持 snapshot resume |
| `.../runners/train.py`, `snapshots.py` | Runner 拥有 epoch 循环与指标；`TorchSnapshotManager.update` 管周期/最佳 snapshot、上限清理、`snapshot-050.pt` 命名——Phase 7 模型库的 checkpoint 管理范本 |
| `.../apis/videos.py` | `VideoIterator`（可携带逐帧上下文）、`video_inference`、`analyze_videos`（多任务模式/全 pickle/HDF5/CSV/tracklet 拼接）；`create_df_from_prediction` 产出 (scorer, [individuals,] bodyparts, x/y/likelihood) MultiIndex |
| `.../runners/inference.py`, `data/postprocessor.py` | 预处理与模型批解耦（同步/异步）；后处理器归一化为稳定 (x, y, likelihood) 记录、坐标逆变换 offsets/scales |
| `.../runners/shelving.py` | `ShelfWriter`：逐帧 shelve 落盘，长视频内存近恒定——长视频策略参考 |
| `deeplabcut/gui/utils.py`, `gui/tabs/analyze_videos.py` | `Worker(QThread)` + `move_to_separate_thread`：异常经 error 信号、必发 finished；analyze tab 的禁用→进度→恢复模式 |
| `deeplabcut/refine_training_dataset/` + `gui/tabs/extract_outlier_frames.py` | `extract_outlier_frames → napari 修正 → merge_datasets → 重建训练集` 循环——最接近 Phase 5 的现成主动学习 UX |

- **重要陷阱**：本快照中 `gui/tabs/train_network.py:TrainNetwork.train_network()` **直接调用** `compat.train_network`，未走 worker 线程——不要假设 DLC GUI 训练不卡 UI；我们自己的训练调用必须放在独立任务/子进程边界内。
- **CI 参考**：`.github/workflows/python-package.yml` 三平台 × Py3.10–3.12 + Windows 固定 BtbN FFmpeg 并验证 ffmpeg/ffprobe——Windows FFmpeg 处理方式可借鉴。
- **详读**：[raw/deeplabcut-notes.md](raw/deeplabcut-notes.md)

### 3.5 SLEAP — 标注校正与任务隔离最佳参考

- **Repository**: <https://github.com/talmolab/sleap> · commit `6967e04`（develop）· v1.6.5 · Clear BSD · Python 3.11–3.13 · PySide6/qtpy；**数据模型在 `sleap-io`、训练/推理在 `sleap-nn` 两个独立姊妹包**
- **为什么相关**：标注/校对 UX 与长任务隔离的最强参考。`Labels/LabeledFrame/Instance/PredictedInstance/Track` 数据模型天然区分用户标注与预测；prediction-assisted labeling、frame suggestion、track trails 直接适用 Phase 5。
- **关键源码**：

| 路径 | 内容 |
| --- | --- |
| `sleap/gui/commands.py` | `CommandContext`：每个 `AppCommand` 声明 `topics`（更新通知域）与 `does_edits`（变更栈）——业务逻辑不进 widget 的命令模式 |
| `sleap/gui/widgets/video.py` | `QtVideoPlayer`：`ndarray_to_qimage` 处理 RGB/RGBA/uint8/uint16/float；"Add Instance" 多种初始化（best/template/copy prior frame）；frame 快捷键体系 |
| `sleap/gui/widgets/video_worker.py` | `FrameLoaderThread`：**只解码最新请求**、合并过期请求并计数丢弃——拖动时间轴时不解码中间帧，帧导航性能设计直接可用 |
| `sleap/gui/widgets/slider.py` | `VideoSlider`：标注/建议帧标记的 seekbar |
| `sleap/gui/learning/runners.py` | **最佳长任务范本**：`InferenceWorker(QThread)` 跑 `sleap predict` 子进程、解析结构化 JSON 进度（n_processed/n_total/status）、取消即 kill 子进程；`train_subprocess` 同理；`InferenceProgressDialog` = 进度条+日志+取消 |
| `sleap/info/write_tracking_h5.py` | 分析 HDF5：`track_occupancy/tracks/point_scores/instance_scores/tracking_scores`——带显式置信度/占用矩阵的科学导出范本 |

- **教训**：重训练后端不进 GUI 进程（子进程边界）；不要把核心数据模型耦合到 `sleap-io`，先定义自己的适配器。
- **详读**：[raw/sleap-notes.md](raw/sleap-notes.md)

### 3.6 SAM 2 — 可选 mask 引擎 + 修正状态机范本

- **Repository**: <https://github.com/facebookresearch/sam2> · commit `2b90b9f` · Apache-2.0（代码与 checkpoint）· PyTorch ≥2.5.1 · Hydra 配置
- **为什么相关**：点/框/掩码提示→逐帧 mask→交互修正的引擎；per-object `inference_state` + conditioning/correction memory 是**交互式修正状态机的最佳源码**。不是点轨迹引擎：mask→质心/标志点的转换误差必须量化。
- **关键源码**：`sam2/sam2_video_predictor.py`（`init_state`（offload 选项）/`add_new_points_or_box`（conditioning vs correction 帧）/`propagate_in_video`（generator，前向/反向）/`remove_object`/`reset_state`；`clear_non_cond_mem_around_input` 与 `add_all_frames_to_correct_as_cond` 显式修正影响记忆的策略）；`sam2/utils/misc.py`（`load_video_frames` 分发 decord/JPEG、`AsyncVideoFrameLoader`、CPU offload 换显存）；`demo/backend/server/inference/predictor.py`（`InferenceAPI`：session 锁、CUDA/MPS/CPU 选择、流式 propagate + 取消标志——状态推理服务范本）；`demo/frontend/.../TrackletSwimlane.tsx`（mask 占用段+点击跳转修正帧——我们"困难帧发现"的 UI 范本）。
- **硬件警告**：官方文档面向 GPU/WSL；CPU/Windows 原生性能未承诺，`SAM2_BUILD_CUDA=0` 可装但失去 GPU 后处理。不进入默认引擎，除非 benchmark 通过。
- **详读**：[raw/sam2-notes.md](raw/sam2-notes.md)

### 3.7 TAPNet (TAPIR / TAPNext) — 点跟踪 benchmark 首选

- **Repository**: <https://github.com/google-deepmind/tapnet> · commit `c2cbab8` · Apache-2.0（代码；checkpoint 条款未完整重述，需 review）· JAX/Haiku 原始实现 + PyTorch 复现
- **为什么相关**："点一个点→整段轨迹+逐帧 visibility/occlusion+expected_dist 不确定度"，无训练集也能跑，输出形态天然贴合 TrackPoint。causal/online 模式带持久上下文。
- **关键源码**：`tapnet/pytorch_live_demo.py`（`online_model_init`/`online_model_predict`/`postprocess_occlusions`——visibility 由 occlusion+expected_dist logits 后处理而来）；`tapnet/torch/tapir_model.py`（`get_feature_grids`→`get_query_features`→`estimate_trajectories`（初始 cost-volume 匹配 + PIPs 迭代精化），`query_chunk_size` 控多点内存）；`tapnet/utils/transforms.py`（坐标约定：内部 `[t, y, x]` 归一化光栅坐标 vs OpenCV `(x, y)`——**集成风险点，必须加显式测试**）。
- **局限**：无 GUI/持久化/修正工作流；JAX/CUDA 与 CPU 性能未承诺；仓库还含更新的 TAPNext 可一并纳入 benchmark。
- **详读**：[raw/tapnet-notes.md](raw/tapnet-notes.md)

### 3.8 CoTracker3 — 多点联合跟踪（许可证受限）

- **Repository**: <https://github.com/facebookresearch/co-tracker> · commit `82e02e8` · **主体 CC BY-NC 4.0**（部分代码 MIT/Apache）· PyTorch/TorchVision
- **为什么相关**：sparse 点/grid/mask 查询、offline 滑窗 + online 半窗推进、联合多点；online API 适合长视频。**仅可作外部 benchmark 依赖，代码/checkpoint 不得进入产品构建**，除非另行取得授权。
- **关键源码**：`cotracker/predictor.py`（`CoTrackerPredictor.forward`：queries/grid_size/segm_mask/backward_tracking；查询帧位置精确回填、分辨率缩放回原像素；`CoTrackerOnlinePredictor`：`is_first_step=True` 初始化、`step = window_len//2` 推进、换视频必须重建 predictor）；`models/core/cotracker/cotracker3_{offline,online}.py`（窗口化特征金字塔+迭代更新）；`gradio_demo/app.py`（查询帧选择/点击/撤销的交互雏形）。
- **陷阱**：公开 API 的 visibility 是布尔阈值（CoTracker3 内部 confidence×visibility 后阈值化）——要连续置信度需直接调模型；`backward_tracking` 是反向整段重跑，不是修正 API。
- **详读**：[raw/co-tracker-notes.md](raw/co-tracker-notes.md)

### 3.9 TrackingLaboratory TrackLab — 模块契约/引擎组织参考

MIT · commit `5767e86`。Hydra 配置的 MOT 研究框架。值得借鉴：`pipeline/module.py` 的 **input_columns/output_columns 声明式模块契约**（`Pipeline.validate` 校验依赖闭包——我们组织 manual/DLC/TAPIR/SAM2/物理处理适配器时可参考）；`TrackerState` 按 video 分段落盘 `.pklz`、`forget_columns` 内存策略；callback 协议（进度/计时器与引擎解耦）。警告：`ExternalVideo` 把视频先落成 JPEG 帧（TODO 直读 MP4）——长视频磁盘反例；pickle 状态不可信来源加载；无取消契约。
**详读**：[raw/tracklab-notes.md](raw/tracklab-notes.md)

### 3.10 Pose2Sim — 后处理流水线/滤波参考（未来 3D）

BSD-3-Clause · commit `65bbb05`。多相机 2D→3D→OpenSim。值得借鉴：分阶段目录（pose/pose-associated/pose-3d/kinematics 各自可独立重跑）；置信度加权三角化 + 重投影误差 QC；`filtering.py` 的**按连续有效段切分再滤波**（Butterworth/Kalman/One Euro/GCV spline/加速度最小化等）、Hampel 前置去野值、显式 cutoff 配置 recap；`common.py` 的 TRC/MOT 读写与 Z-up→Y-up。不要把 OpenSim 拉进 Phase 1/2 核心。
**详读**：[raw/pose2sim-notes.md](raw/pose2sim-notes.md)

### 3.11 Sports2D — 置信度策略与导出参考

BSD-3-Clause · commit `4392177`。2D 人体姿态→角度→米制。值得借鉴：低 likelihood 关键点→NaN（而非静默造值）；`load_pose_file` 允许跳过推理直接用像素 TRC（分离推理 benchmark 与下游运动学 benchmark 的做法）；角度定义是配置/数据而非硬编码；raw 与 filtered 分开导出绘图。反面教材：`process_fun` 是巨型过程函数，推理/GUI/绘图/导出全耦合。
**详读**：[raw/sports2d-notes.md](raw/sports2d-notes.md)

### 3.12 DLC2Kinematics — 下游 API 形态参考（含数值陷阱）

Apache-2.0（部分文件源自 DLC、标注 LGPL-3.0，**文件级溯源混杂，复制前需 review**）· commit `dd2b036`（2023-12 后停滞）。值得借鉴：DLC MultiIndex 列契约、`joints_dict` 命名角度定义、`pcutoff`→NaN 策略。**必须修正后再用**：`smooth_trajectory` 调 `savgol_filter` 未传物理 `delta`/dt，导数单位是"每样本"而非物理单位——我们的物理引擎绝不能照抄；测试只有一个 `pass` 占位，不构成正确性证据。
**详读**：[raw/dlc2kinematics-notes.md](raw/dlc2kinematics-notes.md)

### 3.13 pyxy3d — 跟踪器协议/包结构参考（未来）

LGPL-3.0（三角化代码源自 Anipose，BSD-2）· commit `e8608bc`（2023-12 后停滞）。值得借鉴：`interface.py` 的 `PointPacket/FramePacket/SyncPacket` + `Tracker` ABC（多算法共享协议的紧凑范本）；每相机端口独立 tracker 线程/队列（不共享模型上下文）；短间隙插值限制 `max_gap_size`、按连续帧组做零相位 Butterworth。多相机/OpenSim 复杂度不进当前阶段。
**详读**：[raw/pyxy3d-notes.md](raw/pyxy3d-notes.md)

### 3.14 Motion Tracker Beta — Python 端到端对照

GPL-3.0 · commit `d8a6b60`。PyQt5/OpenCV/PyNumDiff 端到端。值得借鉴：`Motion` 原始路径与派生 v/a 数组分离、显式 `dt` 传入 PyNumDiff、专用 QThread worker（tracking/后处理/导出各一线程）、`MotionTracker.spec` 的 PyInstaller hidden-imports 清单（PyQt5/SciPy/CVXPY 等）。反面教材：0–10000 滑块当时间模型、数据仅内存、宽泛 except、OpenCV 布尔 `ret` 当置信度、无有效测试。
**详读**：[raw/motiontracker-notes.md](raw/motiontracker-notes.md)

### 3.15 GoTracker — 最小跟踪引擎基线范本

MIT · commit `d880de8`。Go/GoCV 单点模板匹配。值得借鉴：显式状态机（`StateIdle/StateTracking/StatePausedForRealignment/StateDone`——**低置信度暂停等待人工重对齐**正是我们要的兜底语义）；自适应搜索窗来自近期运动量；`Realign` 替换模板并重置状态；导出列显式（time,x,y,confidence,x_m,...vx_m/s）；合成帧测试。局限：整数坐标、单点、无持久化。
**详读**：[raw/go-tracker-notes.md](raw/go-tracker-notes.md)

---

## 4. Cross-project Feature Map

各能力维度的实现思路对比（★ = 该维度最佳参考）：

| 能力 | OpenPhysics TrackLab | Kinovea | Tracker (OSP) | Motion Tracker Beta | GoTracker | DLC | SLEAP | Sports2D/Pose2Sim | TAPIR/CoTracker/SAM2 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| **视频播放/seek** | HTML video + time 权威 + rAF 合并 | ★ `VideoReader` 契约 + Cache/PreBuffer + scrub/commit | OSP VideoClip，frame vs step 分离 | cv2.VideoCapture + QTimer | GoCV Reader 包装 | VideoIterator 批读 | ★ FrameLoaderThread 只解码最新帧 | cv2 逐帧 | 整段张量/decord |
| **标定/坐标系** | ★ 纯 MVT：T·R·S(s,-s) | CalibrationHelper/单应平面/时变标定 | CoordAxes/Calibration 为 per-frame track | 两点 Ruler→mm/px | 两点→像素/单位 | —（无物理标定） | — | 人体身高/透视模型（非通用） | — |
| **手工跟踪** | 点击+放大镜，last-wins 替换 | drawing 编辑 + 修正后重建模板 | ★ PositionStep 可编辑、keyframe 语义 | savePoint/saveRectangle | 点击+缩放确认 | napari 委托 | ★ QtVideoPlayer+命令模式 | — | — |
| **自动/AI 跟踪** | OpenCV.js worker 模板匹配 | AbstractTracker+TemplateMatching（ephemeral 模板） | TemplateMatcher+预测搜索窗+停止策略 | OpenCV legacy（CSRT/KCF…） | 模板匹配+重对齐状态机 | ★ 可训练关键点+likelihood | 可训练+suggestion | 人体姿态模型 | ★ 点/掩码提示即用型 |
| **运动学计算** | ★ 纯函数+时间戳差分 | LinearKinematics+MotionFilter | ★ 变量体系+独立滤波器对象 | PyNumDiff 多方法+显式 dt | 时间戳差分 | — | — | 角度→OpenSim | — |
| **图表** | 自绘 canvas+可插拔量注册表 | 时间序列视图 | ★ DatasetManager 变量任意组合 | Matplotlib | 实时 GraphWindow | matplotlib 轨迹图 | 相图/轨迹 overlay | raw vs filtered 对比图 | — |
| **项目保存** | ✗（仅 CSV） | ★ .kva XML sidecar | .trk/.trz + tabset | ✗（QSettings） | ✗（CSV） | 项目目录+config.yaml | .slp 项目图 + 分析 HDF5 | 分阶段目录+TOML | ✗ |
| **模型管理** | ✗ | ✗ | ✗ | ✗ | ✗ | ★ snapshot/模型目录/engine 版本 | checkpoint 复用/resume | 外部模型 | checkpoint 文件 |
| **后台任务** | worker+过期请求丢弃 | 解码/缓存与 UI 分离 | 异步 loader | QThread×3 | CLI 同步 | Worker 分析/训练直调（不一致） | ★ subprocess+JSON 进度+取消 | 进程池 worker | SAM2 流式+取消标志 |
| **打包** | Vite/PWA | ★ MSBuild+NSIS+原生 DLL | Ant/jar（非现代 CI） | PyInstaller spec 清单 | Go 二进制 | CI 三平台+Win FFmpeg | 无安装器 | PyPI | 无安装器 |

**跨项目要点**（详释）：

- **视频层**：没有项目用裸 `cv2.VideoCapture` 满足"流畅随机 seek + 缓存 + 拖动反馈"。Kinovea 的能力契约 + SLEAP 的最新帧合并 + TrackLab 的 scrub/commit 三件套组合是我们 Phase 2 的目标形态。
- **标定层**：最干净的是 TrackLab 的纯函数 MVT（可解析测试）；Kinovea/Tracker 证明标定/坐标系应是一等可观察对象（有 CalibrationChanged 事件），坐标变换不得散落在渲染代码里。
- **任务层**：SLEAP 的"子进程 + 结构化 JSON 进度 + kill 取消"是唯一完整方案；DLC 的 GUI worker 只覆盖分析不覆盖训练；其余项目要么无取消要么无任务抽象。
- **持久化层**：Kinovea sidecar（视频不复制、元数据独立、先读尺寸/时序再读坐标）与 Pose2Sim 分阶段目录（每阶段可独立重跑）是两种互补模式。

---

## 5. Tracking Technology Comparison

候选跟踪技术的横向对比（面向单摆等 2D 物理实验场景）：

| 技术 | 提示/输入 | 是否需训练 | 输出与置信度 | 优势 | 劣势 | CPU/Windows 就绪度 | 代码许可 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| OpenCV 模板匹配 | 矩形 ROI 模板 | 否 | 归一化相关系数 | 确定性、CPU 快、实现小（GoTracker/TrackLab/Kinovea 三处范本） | 固定相机假设、旋转/尺度/遮挡即失效、阈值语义弱 | ★ 完全就绪 | OpenCV Apache-2.0 |
| OpenCV legacy tracker（CSRT/KCF/MOSSE） | 框 | 否 | 布尔 ret | 接口简单 | 无连续置信度（Motion Tracker 反面教材）、精度一般 | 就绪 | OpenCV Apache-2.0 |
| DLC 3.x PyTorch | 标注帧（自定义关键点） | **是**（少量标注） | per-keypoint likelihood | 少量标注后精度高、可迭代精化、任意物体/关键点、模型可复用（Phase 7） | 依赖重（数 GB）、训练耗时、打包体积、引擎版本耦合 | 部分就绪（Win CI 存在，打包需实验） | LGPL-3.0（权重单独审） |
| SLEAP (sleap-nn) | 标注帧 | 是 | point/instance/tracking scores | 标注校正 UX 最佳、任务隔离最佳 | 后端拆在姊妹包、人体姿态生态为主 | 待评估 | Clear BSD（栈需审） |
| TAPIR / causal TAPIR / TAPNext | 查询点 [t,y,x] | 否 | 轨迹 + visibility + expected_dist 不确定度 | 零训练任意点、逐帧可见性、在线模式 | 无修正 GUI/持久化、JAX/Torch 栈重、坐标约定易错 | 需 benchmark（GPU 向） | Apache-2.0（checkpoint 需审） |
| CoTracker3 | 稀疏点/grid/mask | 否 | 公开 API 仅布尔 visibility（内部有连续 confidence） | 联合多点、长视频 online 模式 | **CC BY-NC 商用阻断**、无修正 API | 需 benchmark（GPU 推荐） | **CC BY-NC 4.0 主体** |
| SAM2.1 tiny/small | 点/框/掩码 | 否 | mask logits/score（无点级 likelihood） | 交互选目标、遮挡修正记忆、修正 UX 范本 | mask→点转换误差需量化、GPU/WSL 倾向、内存 | 需 benchmark（CPU 未承诺） | Apache-2.0（代码+官方 checkpoint） |

**Benchmark 优先级**（详见第 11 节实验计划）：

1. OpenCV 模板匹配——确定性 CPU 基线，永远保留为 fallback。
2. Causal TAPIR（含 TAPNext）——点提示 + visibility/uncertainty，零训练路线的代表。
3. DLC 3.x PyTorch 小数据集——可训练精化路线的代表，做标注预算曲线。
4. CoTracker3——多点长序列对照（仅研究性依赖，不进发布）。
5. SAM2.1 tiny/small——仅作 mask 提示/修正分支，测 mask→质心转换误差而非 IoU。
6. SLEAP——仅当 sleap-io/sleap-nn 许可栈与单摆场景相对 DLC 有具体优势时纳入。

**决策规则**：少量标注后 DLC 的精度/恢复能力显著优于 foundation tracker → 默认 DLC；零训练即达目标且 CPU 成本可接受 → 默认 TAPIR 系；无论选谁，OpenCV 模板匹配保留为离线兜底。

---

## 6. Patterns Worth Adopting

1. **观测即上下文（Observation with provenance）**。Phase 1 的持久化观测至少包含：`video_id / frame_index / time_seconds / object_id|keypoint_id / pixel_x,pixel_y / (派生) world_x,world_y / source = manual|template|dlc|tapir|cotracker|sam2-derived / confidence|visibility / quality_flags`。依据：Tracker、Kinovea、SLEAP、DLC、TAPIR/CoTracker、TrackLab 六家的共同形态。
2. **显式 Timeline 契约**。源帧号、presentation timestamp、名义 FPS、起止帧、变帧率策略与显式转换方法一次定义；任何图表/表格禁止从 DataFrame 行号推断时间。依据：Kinovea 时间戳制、TrackLab time 权威制、Tracker frame/step 分离的三种教训。
3. **手工与自动的不同覆写策略**。自动插入 first-wins（同帧首个值保留）、手工修正 last-wins（最后点击替换）、修正事件被记录（TrackLab 语义；Kinovea 修正后重建模板；SAM2 修正喂回 conditioning memory 同理）。
4. **标定/坐标变换独立成纯服务**。`T·R·S(s,-s)` 式纯函数 + 变换可逆不变量 + `CalibrationChanged` 事件（TrackLab + Kinovea 综合）；UI 拖动只更新标定状态，不直接改写画布像素；变换用解析点做单元测试。
5. **一个产品级任务抽象**。`TaskManager/TaskHandle`：queued/running/canceling/succeeded/failed/canceled 状态、progress、日志流、metrics、输出路径、checkpoint 路径、错误。实现形态采纳 SLEAP：重引擎（DLC 训练/推理）走子进程 + 结构化 JSON 进度 + kill 取消；轻任务（导出、帧解码）走 QThread worker（DLC `gui/utils.Worker` 的 error/finished 语义 + `tests/gui/test_worker.py` 的回归测试模式）。
6. **原始/派生数据分层 + 处理 provenance**。Raw observation 不可变；平滑/微分/拟合结果带算法名、参数、版本号分层存放（Pose2Sim 滤波配置 recap、DLC raw/full/filtered 多层输出、Sports2D raw vs filtered 双导出的共同做法）。
7. **时间轴 scrub/commit + 解码合并**。拖动中只发轻量预览事件、松手才解码；解码 worker 只处理最新请求并丢弃过期请求（Kinovea FrameTracker + SLEAP FrameLoaderThread + TrackLab rAF 合并）。
8. **引擎适配器契约**。Kinovea `AbstractTracker`（算法结果/存储点创建/参考点创建分离）+ TrackingLaboratory `Module` 的 input/output 列声明 + pyxy3d `Tracker` ABC 三者综合：适配器声明输入输出、可 reset/trim/dispose、瞬时引擎状态（模板/记忆/因果上下文）与持久观测分离。
9. **困难帧定位/修正 UX**。SAM2 tracklet swimlane（遮挡空段可视化+点击跳转）、SLEAP suggestion/proofreading、Tracker keyframe+autofill+重对齐、GoTracker `StatePausedForRealignment`——Phase 5 的修正交互直接从这四个模式组合。
10. **逐帧置信度伴随轨迹全程**。DLC likelihood 进导出与图表着色；TAPIR visibility+expected_dist；低置信度→NaN 而非静默值（Sports2D/DLC2Kinematics pcutoff 策略）。
11. **模型库元数据**。模型身份 = checkpoint 路径/UID + 模型配置 + task + bodyparts + 引擎与版本 + 快照语义（DLC `TorchSnapshotManager`/`Snapshot` + SLEAP best.ckpt 发现/resume 模式）。
12. **长视频内存策略**。DLC `ShelfWriter` 逐帧落盘 + SAM2 offload 选项 + Kinovea Cache/PreBuffer：大视频处理永不整段驻留内存。

## 7. Patterns to Treat with Caution

1. **DLC GUI 训练直调 API**（`train_network.py` 不走 worker）——我们的训练必须有自己的任务/子进程边界，不能假设上游 GUI 行为。
2. **DLC2Kinematics 的 Savitzky-Golay 无 dt**——导数单位错误；任何数值代码必须带显式 fps/timestamps 契约与解析合成数据测试。
3. **CoTracker 公开 API 布尔 visibility**——需要连续置信度时绕过 predictor 直调模型（许可未解决前不集成）。
4. **SAM2 mask 当点轨迹**——质心/标志点转换误差未量化前不作为物理点来源；A100 上的 FPS 不可外推到 CPU/Windows。
5. **TAPNet 坐标顺序**——内部 `[t, y, x]` 归一化坐标 vs OpenCV `(x, y)`，集成点必须加显式转换测试。
6. **TrackingLaboratory 的 JPEG 物化与 pickle 状态**——任意视频先落 JPEG 帧是磁盘反例；pickle 状态不可从不可信来源加载。
7. **Motion Tracker Beta 的反模式**——0–10000 滑块当时间模型、OpenCV 布尔返回当置信度、内存态项目、宽泛 except、空测试。
8. **OpenPhysics TrackLab 的宽松阈值/固定相机假设**——0.25 置信度阈值与窗口搜索只适用于静止相机短程运动；作为基线可，作为产品跟踪不可。
9. **Tracker/Kinovea 的 GUI-数据耦合**——Swing/WinForms 对象兼任持久化模型导致序列化复杂；我们的领域层必须无 Qt 依赖。
10. **Sports2D 单体过程函数**——推理/关联/角度/导出在一个 500+ 行函数中；我们用 typed service 分阶段。
11. **DataFrame 行号当时间**——多个研究项目的隐式假设；违反第 6 节第 2 条。
12. **把引擎输出格式当领域模型**——DLC HDF5/Pickle、SLEAP .slp、.kva 都不能成为我们唯一事实源；一律经适配器转换。

---

## 8. License & Distribution Notes

> 这是路由图，不是法律意见。模型/数据列在仓库证据不完整时一律 `Needs license review`。

| 项目 | 代码许可 | 模型/权重 | 数据/媒体 | 商用 | 对我们的影响 |
| --- | --- | --- | --- | --- | --- |
| Tracker (OSP) | GPL-3.0 | 无 | 需审 | GPL 义务下可 | 只作参考；osp 核心另有许可 |
| Kinovea | GPL-2.0 | 无 | 需审 | GPL 义务下可 | 只作参考；FFmpeg/OpenCvSharp 运行时需另行声明 |
| OpenPhysics TrackLab | AGPL-3.0-or-later | 无 | 示例视频需审 | AGPL 义务下可 | 架构/数学作 prior art，不作库 |
| TrackingLaboratory TrackLab | MIT | 外部模型需审 | 数据集需审 | MIT 代码可 | 模块契约思想可借鉴 |
| Sports2D / Pose2Sim | BSD-3-Clause | 外部模型需审 | 需审 | BSD 代码可 | 思路可借鉴；OpenSim 资产需审 |
| DLC2Kinematics | Apache-2.0（混 LGPL-3.0 文件） | 无 | 需审 | **需 review** | 文件级溯源混杂，不复制代码 |
| **DeepLabCut** | LGPL-3.0-or-later | SuperAnimal/预训练权重需逐个审 | 用户数据自有 | LGPL+资产条款下一般可行 | **当前最可行引擎路线**；注意 LGPL 动态链接义务与依赖清单 |
| SLEAP | Clear BSD | sleap-nn/backbones 需审 | 需审 | 基础栈需审 | 姊妹包逐一审计后可用 |
| TAPNet | Apache-2.0 | checkpoint 条款未完整重述 | TAP-Vid 系列另有条款 | 代码可，权重不确定 | benchmark 可，分发前审 checkpoint |
| **CoTracker** | **CC BY-NC 4.0（主体）** | 适用性需审 | 需审 | **NC 材料商用不允许** | **商业发布阻断项**；仅研究性外部依赖 |
| SAM2 | Apache-2.0 | 官方 checkpoint 声明 Apache-2.0 | SA-V 等数据集另有条款 | Apache 下一般可行 | 基础候选中最干净；cc_torch(OFL 例外)、运行时依赖需清单 |
| Motion Tracker Beta | GPL-3.0 | 无 | 需审 | GPL 义务下可 | PyInstaller spec 清单可参考做法本身 |
| pyxy3d | LGPL-3.0（三角化 BSD-2） | MediaPipe 等需审 | 需审 | 全栈需审 | 未来参考 |
| GoTracker | MIT | 无 | 无 | MIT 可 | 基线思想可自由借鉴 |

**分发层面结论**：

- **CoTracker 的 NC 条款是唯一硬阻断**：代码与 checkpoint 都不得进入产品构建；benchmark 阶段作为可选研究依赖隔离安装。
- **GPL/AGPL 项目（Tracker、Kinovea、Motion Tracker Beta、OpenPhysics TrackLab）只读不抄**：借鉴算法行为并用自己的实现+测试重写是安全路径；逐行移植会传染 copyleft。
- **LGPL（DLC、pyxy3d）**：以正常 pip 依赖 + 动态链接方式使用一般可行，但分发 Windows 安装包时需履行 LGPL 义务（许可文本、对应源获取方式）；发布前做一次完整依赖树清单（PyTorch、Qt LGPL、FFmpeg 许可变体、OpenCV、numpy 等）。
- **权重≠代码**：DLC/SuperAnimal、TAPIR、CoTracker、SAM2 checkpoint 的条款独立于代码仓库，逐个记录来源与条款后才能打进安装包。
- **本项目 License（TBD）**：在确定是否商业分发与是否内置 DLC 之前保持 TBD；届时记 ADR。

---

## 9. Recommended Architecture Direction

综合全部调研，与 `docs/architecture.md` 四层设计一致并细化的推荐组合：

```text
GUI:          PySide6/Qt（PyQtGraph 交互图 + Matplotlib 导出图）
视频:         自有 VideoReader/Timeline 服务；初期 OpenCV/FFmpeg 后端；
              能力契约参考 Kinovea（seek/cache/枚举/时序），解码 worker 参考 SLEAP
领域层:       无 Qt 依赖的 typed 数据模型；
              TrackPoint(观测, immutable) / Annotation(训练数据来源) /
              Calibration(纯变换服务) / ProcessedData(带 provenance 的派生层)；
              数值核心以 TrackLab 的纯函数风格 + 解析合成数据测试建立
跟踪引擎:     统一 EngineAdapter 契约（Kinovea AbstractTracker + 模块列声明综合）
              ├── OpenCV 模板匹配（CPU 确定性 fallback，GoTracker 状态机语义）
              ├── DeepLabCut 3.x PyTorch（第一可训练引擎，经 compat.py 门面）
              ├── TAPIR/TAPNext（零训练点跟踪，benchmark 后决定地位）
              ├── CoTracker3（仅研究性外部依赖，许可未清前不集成）
              └── SAM2（可选 mask 修正分支）
任务系统:     TaskManager/TaskHandle（SLEAP subprocess+JSON 进度+取消 范本）；
              训练/推理/导出全部可取消后台化，GUI 永不直调引擎
持久化:       项目清单/配置 + 原始轨迹 + 派生处理记录三层；
              视频/模型不入库（引用）；.kva 式 sidecar 与分阶段目录两种模式择优
模型库:       元数据 = checkpoint 身份 + 配置 + task/bodyparts + 引擎版本 + 来源实验
              （DLC snapshot manager + SLEAP resume 模式综合）
```

**分阶段落地要点**：

- **Phase 1**：数据模型是全局地基——TrackPoint 带 source/confidence、Timeline 显式契约、raw/derived 分层一次到位；对照 DLC CollectedData 格式设计无损转换（验收标准已要求）。持久化格式（JSON vs SQLite）在 ADR 中决策，注意 Kinovea"先读尺寸/时序再读坐标"的兼容教训。
- **Phase 2**：视频层先做"契约 + OpenCV 后端 + 解码 worker + scrub/commit 时间轴"，不引入 AI。
- **Phase 3**：KinematicsComputer 纯函数 + 显式 dt + 滤波按连续有效段切分（Pose2Sim）；平滑/微分顺序与参数记 ADR。
- **Phase 4**：DLCAdapter 经 `compat.py` 集成，训练/推理在子进程任务中；推理输出（含 likelihood）转 TrackPoint。
- **Phase 5**：困难帧 = 低置信度 + 轨迹异常检测；修正 UX 组合 SAM2 swimlane + SLEAP suggestion + Tracker 重对齐。
- **Phase 9**：打包体积的主要敌人是 PyTorch+DLC；Windows FFmpeg 处理参考 DLC CI（固定 BtbN 构建 + 验证）；PyInstaller hidden-imports 清单参考 Motion Tracker spec 的方法论（不用其内容）。

这不是锁死的依赖清单；Phase 1 先用小接口验证，重要决策记 ADR，benchmark 结果（第 11 节）决定默认引擎。

---

## 10. Recommended Reading Order for Future Agents

进入各 Phase 前，按下列顺序读本文件小节 + raw notes（每份 note 末尾都有该项目的最高价值阅读顺序）：

| 任务 | 本文件 | 先读 raw notes | 再读源码（.upstream 快照） |
| --- | --- | --- | --- |
| Phase 1 数据模型 | §3.1, §6.1–6.2 | openphysics-tracklab → sleap → deeplabcut | `Track.ts`、`TrackingModel.ts`；sleap-io Labels；DLC `trainingsetmanipulation.py` |
| Phase 2 视频/时间轴 | §3.2, §6.7 | kinovea → sleap → openphysics-tracklab | `VideoReader.cs`、`FrameTracker.cs`；`video_worker.py`；`VideoPlaybackModel.ts` |
| Phase 3 标定/运动学 | §3.1–3.3, §3.10, §3.12 | openphysics-tracklab → tracker → pose2sim | `ModelViewTransformFactory.ts`、`KinematicsComputer.ts`；`PointMass.java`；`filtering.py` |
| Phase 4 DLC 集成 | §3.4, §6.5 | deeplabcut | `compat.py` → `apis/training.py` → `runners/*` → `apis/videos.py` → `gui/utils.py` |
| Phase 5 修正/主动学习 | §3.5–3.6, §6.9 | sleap → sam2 → tracker → go-tracker | `gui/learning/runners.py`；`sam2_video_predictor.py`；`AutoTracker.java`；`tracker.go` |
| 引擎 benchmark | §5, §11 | tapnet → co-tracker → sam2 | `pytorch_live_demo.py`、`tapir_model.py`；`predictor.py`；demo backend |
| Phase 7 模型库 | §3.4, §6.11 | deeplabcut → sleap | `runners/snapshots.py`；`gui/learning/runners.py` |
| Phase 8 导出 | §4 持久化行 | tracker → pose2sim → sleap | `ExportDataDialog.java`；`common.py`；`write_tracking_h5.py` |
| Phase 9 打包 | §8, §9 | kinovea → motiontracker → deeplabcut | `makeinstaller.py`/`kinovea.nsi`；`MotionTracker.spec`；DLC CI workflow |

**通用规则**：任何模块动手前，先确认 raw note 的 commit SHA 仍接近上游 HEAD；差异大时重新核对关键路径是否存在。本文件的结论基于 2026-08-27 快照。

---

## 11. Conclusions / Next Experiments

### 结论

1. **最近邻排序**（物理产品 + 可落地源码）：OpenPhysics TrackLab（Phase 1–3）> Kinovea（桌面层）> DeepLabCut（Phase 4–7 引擎）> SLEAP（标注/任务）> Tracker（物理量 prior art）。Motion Tracker Beta 是最近的 Python 端到端但质量弱；无一个项目覆盖我们的完整组合。
2. **成熟实现清单**：播放/seek/cache（Kinovea）、标定/坐标（TrackLab/Kinovea/Tracker）、手工标注（TrackLab/Tracker/SLEAP）、训练工作流（DLC/SLEAP）、困难帧修正（DLC outlier/SLEAP suggestion/SAM2 memory）、置信度体系（DLC/TAPIR）、科学导出（Tracker/Pose2Sim/SLEAP）、Windows 发布（Kinovea/DLC CI）。
3. **空缺即机会**：面向普通用户的 Windows 桌面 UX + 物理标定 + 少量标注训练 + 任意点即时跟踪 + 可修正置信度闭环 + 原始/处理数据溯源 + 模型库 + 可复现发布——没有项目同时具备，这是本项目的差异化空间。

### Next Experiments（Tracking Engine 决策实验）

建立**引擎无关的 pendulum benchmark**，全部候选经统一 EngineAdapter 接入：

1. **合成真值集**：解析单摆/匀速/匀加速生成带真值 2D 视频与轨迹；再在真实单摆视频人工逐帧标注真值子集，覆盖低/高 FPS、运动模糊、遮挡、亮度变化、压缩、轻微抖动。
2. **统一指标**：像素 MAE/RMSE、最大漂移、失败/不可见帧率、恢复时间、人工修正帧数、CPU/GPU 时间、峰值内存、启动/模型加载时间。
3. **提示与初始化矩阵**：点提示 vs 框/ROI vs mask；第 0 帧 vs 首个可见帧 vs 中间帧初始化；正向/反向/forward-backward 一致性。
4. **DLC 标注预算曲线**：5/10/20/50 帧训练后整段误差 + 困难帧再训练收益；记录 checkpoint 体积与 Windows CPU/NVIDIA 可部署性。
5. **SAM2 mask→点误差**：测质心/悬点/边界点转换误差，不看 mask IoU。
6. **平台矩阵**：先 macOS/Linux 做算法对比，再 Windows 10/11 + Python 3.11 做安装/CPU/NVIDIA/FFmpeg/长视频回归。
7. **决策**：按 §5 末尾的规则选默认引擎；OpenCV 模板匹配永久保留为 fallback。

### 待进一步验证的事项（Open Items）

- [ ] TAPNext（tapnet 仓库内更新的模型）相对 TAPIR 的精度/速度——raw note 未覆盖，benchmark 时补查。
- [ ] DLC 3.x 在 Windows + PyInstaller/Nuitka 的实际打包体积与启动时间（Phase 9 前的早期 spike）。
- [ ] SAM2/TAPIR 在纯 CPU Windows 上的吞吐是否可用于交互式预览（还是只能后台批处理）。
- [ ] TAPIR 与 CoTracker checkpoint 的具体分发条款（各自托管页/Hugging Face）。
- [ ] DLC LGPL 义务在 PyInstaller 打包形态下的具体履行方式（许可文本/源码提供方式）。
- [ ] OpenCV VideoCapture 在 Windows 上对目标用户常见视频格式（手机拍摄 H.265/HEVC 等）的解码兼容性。
- [ ] sleap-io/sleap-nn 完整许可栈审计（若考虑 SLEAP 路线）。
- [ ] 各项目上游 HEAD 漂移复核（本文件结论基于 2026-08-27 快照，重大实现前重对 SHA）。
