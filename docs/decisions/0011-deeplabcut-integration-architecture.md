# ADR-0011 — DeepLabCut 集成架构

- 状态：**Accepted**
- 日期：2026-08-31
- 决策者：开发团队
- 关联：\`docs/roadmap.md\` Phase 4；\`docs/spec/data-model.md\` §4/§7；\`docs/research/open-source-project-map.md\` §3.4/§9

---

## Context（背景）

Phase 4 的核心目标是在 AI Physics Tracker 中接入 DeepLabCut 3.x（PyTorch 引擎），
让用户能够在软件内完成"手工标注少量帧 → 训练 → 全视频推理 → 轨迹导入"的完整流程。

### 调研结论

DeepLabCut 3.0.1（PyPI 最新稳定版，2026-08）提供了引擎无关的程序化 API 门面
\`deeplabcut/compat.py\`，核心调用链：

- **训练**：\`deeplabcut.train_network(config_path, shuffle=1)\`
  → 内部组装 DLCLoader / PoseDataset / Runner / TorchSnapshotManager
  → 产出 \`snapshot-NNN.pt\`

- **推理**：\`deeplabcut.analyze_videos(config_path, video_paths)\`
  → VideoIterator 逐帧解码 → 模型批推理 → ShelfWriter 逐帧落盘
  → \`create_df_from_prediction\` 产出 MultiIndex DataFrame \`(scorer, bodyparts, x/y/likelihood)\`

- **标注格式**：Pandas MultiIndex HDF5/CSV，\`labeled-data/<video>/CollectedData_<scorer>.csv\`

关键避坑点（见 \`docs/research/raw/deeplabcut-notes.md\`）：

1. DLC GUI 中 train_network 直接阻塞 UI——本项目必须走后台子进程
2. DLC 的 HDF5/config.yaml/scorer 命名约定是外部适配契约，不可作为内部领域模型
3. PyTorch CUDA context 不可跨进程共享——训练/推理必须 spawn 独立进程

### Phase 1 已预埋的接口

| 接口 | 预留用途 |
|------|---------|
| \`TrackPoint.source = "dlc"\` | AI 引擎来源标识（§4.5.1 注册表） |
| \`TrackPoint.confidence\` | 逐帧置信度 \`[0, 1]\`（§4.5.2） |
| \`TrackPoint.source_detail\` | 引擎 run id，如 \`"dlc:shuffle=1:snapshot=50"\` |
| \`TrackStore.add_engine_points()\` | first-wins 引擎批次写入 |
| \`TrackStore.clear_engine_run()\` | 按 source_detail 清除引擎运行 |
| \`DerivedData.mark_tracks_stale()\` | 新引擎数据导入后置 stale |

---

## Decision（决策）

### D1 适配器隔离（Adapter Isolation）

\`DLCAdapter\` 位于 \`infrastructure/\` 层，是项目中唯一允许 \`import deeplabcut\` 的位置。
Application 层通过抽象协议 \`EngineAdapter\`（Protocol）与之交互，不直接依赖 DLC。
未来可新增 TAPIR / CoTracker / SAM2 等适配器，实现同一协议。
\`DLCAdapter\` 的所有公共方法设计为可在子进程中独立运行（不依赖 Qt）。

### D2 后台任务框架（Background Task Runner）

训练和推理必须在独立子进程中执行，原因：
- PyTorch CUDA context 不可跨进程共享
- Python GIL 限制 CPU 密集型计算在线程中的并行性
- DLC 的 train_network / analyze_videos 是阻塞调用

方案：
- 使用 \`multiprocessing.Process\`（start_method="spawn"，兼容 Windows + CUDA）
- 进度通信：子进程通过 \`multiprocessing.Queue\` 发送 JSON 结构化进度消息
- GUI 主线程通过 QTimer（100ms 间隔）轮询队列，将进度更新到 Task Panel
- 取消：调用 Process.terminate() 发送 SIGTERM；子进程中注册 cleanup handler

### D3 标注数据转换（Annotation Export）

- scorer 使用固定名称 \`"AIPhysicsTracker"\`
- Phase 4 先支持**单 bodypart**（\`bodyparts: ["target"]\`），与现有 point Track 一一对应
- 标注帧的图像由 OpenCVVideoReader 按 frame_index 解码并保存为 PNG
- 后续扩展多 bodypart 时只需修改 bodyparts 列表和映射逻辑

### D4 推理结果导入（Result Import）

- likelihood 直接映射为 \`TrackPoint.confidence\`
- 已有 manual 点的帧自动跳过（first-wins），不覆盖人工标注
- 导入完成后调用 mark_tracks_stale() 使旧的 DerivedData 失效

### D5 设备选择策略

代码中的设备选择使用三态自动检测，不硬编码：cuda → mps → cpu。
DLC 的 pytorch_config.yaml 中的 device 字段由适配器根据检测结果自动设置。

### D6 依赖管理

- \`deeplabcut>=3.0,<4.0\` 作为**必需依赖**写入 \`pyproject.toml\`
  - DLC 是本项目的核心差异化能力，不作为可选依赖
  - Phase 9 Windows 打包时，安装程序可提供"完整安装"和"轻量安装（无 AI）"两个选项
- DLC 自身传递依赖 PyTorch；无需在 pyproject.toml 中单独声明 torch
- CI 测试中 DLC 相关用例使用 mock adapter，不在 Actions 中安装完整 DLC+PyTorch

### D7 License 合规

| 依赖 | 许可证 | 与 MIT 的兼容性 |
|------|--------|---------------|
| DeepLabCut | LGPL-3.0-or-later | 兼容（动态链接/pip import） |
| PyTorch | BSD-3-Clause | 兼容 |
| PySide6 | LGPLv3 | 兼容（动态链接） |
| NumPy / SciPy | BSD-3-Clause | 兼容 |
| OpenCV | Apache-2.0 | 兼容 |

**结论**：本项目可以使用 **MIT License**。

LGPL 义务（Phase 9 打包时履行）：
1. 在安装包中包含 DLC 和 PySide6 的 LGPL 许可证文本
2. 提供获取 LGPL 依赖源码的途径（指向 GitHub 仓库 URL 即可）
3. 确保用户可以用自行编译的版本替换打包中的 LGPL 库

**中国软件著作权**：软著登记保护的是申请人原创编写的源代码著作权，与依赖库的许可证类型无关。
使用 LGPL/BSD 等开源依赖不影响软著申请，只要提交登记的是自己的原创代码。

### D8 领域模型扩展

新增 \`TrackingRun\` 值对象（位于 domain/ 层），记录每次引擎运行的溯源信息：

| 字段 | 类型 | 说明 |
|------|------|------|
| run_id | UUID | 运行唯一标识 |
| video_id | UUID | 关联视频 |
| track_id | UUID | 关联 Track |
| engine | str | 引擎标识，如 "dlc" |
| engine_version | str | 引擎版本，如 "3.0.1" |
| task_type | str | "train" 或 "infer" |
| config | JsonObject | 训练/推理参数快照（可复现） |
| source_detail | str | 对应 TrackPoint.source_detail |
| model_snapshot | str \| None | checkpoint 路径 |
| status | str | "running" / "completed" / "failed" / "cancelled" |
| created_at | datetime | 创建时间 |
| completed_at | datetime \| None | 完成时间 |

TrackingRun 随 Project 持久化到 project.json，不存储训练数据或权重文件本身。

---

## Consequences（影响）

### 正面

- 适配器隔离确保 DLC 可被替换而不影响上层，符合架构设计原则
- 后台子进程框架保证 GUI 在训练/推理期间始终响应
- Phase 1 预埋的 source / confidence / first-wins 接口无需修改即可接入
- License 分析确认 MIT + LGPL 动态链接组合合规
- 单 bodypart 先行，多关键点扩展路径清晰

### 负面 / 局限

- multiprocessing.Process 的 spawn 模式启动开销较大（约 1-2s），但训练/推理本身耗时远超此开销
- CI 中使用 mock adapter 意味着真实 DLC 集成只能在本地验证，存在集成风险
  - 缓解：在 macOS（CPU）和 Windows（CUDA）上分别进行本地端到端测试
- Phase 4 先支持单 bodypart，多关键点需要后续扩展
  - 缓解：bodyparts 参数设计为列表，扩展时只需添加映射逻辑

---

## 参考

- \`docs/research/open-source-project-map.md\` §3.4（DLC 源码级集成点分析）
- \`docs/research/raw/deeplabcut-notes.md\`（DLC 3.0.1 代码结构详解）
- \`docs/spec/data-model.md\` §4（观测数据四层架构与 Provenance）
- \`docs/architecture.md\` §3（AI 跟踪子系统架构图）
- DeepLabCut GitHub: https://github.com/DeepLabCut/DeepLabCut
- LGPL-3.0 FAQ: https://www.gnu.org/licenses/gpl-faq.html
