# Phase 4 — Deep Learning Tracking 需求规范

> 本文档定义 Phase 4（Deep Learning Tracking）的功能需求、验收标准与 Subphase 划分建议。
> 架构决策见 [ADR-0011](../decisions/0011-deeplabcut-integration-architecture.md)。

---

## 1. 功能需求

### R1 引擎适配器与后台任务框架

1. **EngineAdapter 协议**：定义 infrastructure 层的引擎适配器抽象接口（Protocol），
   包含 create_project / export_annotations / train / infer / import_results 等方法
2. **DLCAdapter 实现**：唯一允许 import deeplabcut 的位置，实现 EngineAdapter 协议
3. **TaskRunner 后台任务框架**：基于 multiprocessing.Process（spawn 模式）的后台任务执行器，
   支持启动/进度通信/取消/错误处理
4. **TrackingRun 领域模型**：记录每次引擎运行的溯源信息（引擎版本、参数快照、状态）

### R2 标注导出（Annotation Export）

1. 将当前 Track 的 active manual TrackPoint 导出为 DLC labeled-data 格式
2. 按 frame_index 从视频中解码标注帧图像并保存为 PNG
3. 生成 DLC config.yaml 与项目目录结构
4. 调用 deeplabcut.create_training_dataset 生成训练集
5. scorer 固定为 "AIPhysicsTracker"，bodyparts 为 ["target"]（单 bodypart）

### R3 训练管线（Training Pipeline）

1. 启动后台训练任务，传入 DLC 项目路径和训练参数
2. 实时传递训练进度（epoch / loss / 学习率）到 GUI
3. 支持取消正在进行的训练任务
4. 训练完成后记录 TrackingRun（含 best snapshot 路径）
5. 设备自动检测：cuda → mps → cpu

### R4 推理管线（Inference Pipeline）

1. 使用训练产出的 snapshot 对目标视频执行全帧推理
2. 实时传递推理进度（已处理帧数 / 总帧数）到 GUI
3. 支持取消正在进行的推理任务
4. 推理完成后将结果 DataFrame 转换为 TrackPoint 并导入 TrackStore
5. TrackPoint 字段映射：source="dlc", confidence=likelihood, source_detail 包含 run 信息

### R5 AI 轨迹显示与交互

1. 推理导入后的 AI 轨迹在 VideoView 上显示，与手工标注使用不同视觉样式（如空心圆）
2. AI 轨迹点可通过手工标注覆盖（已有的 manual last-wins 机制）
3. 图表面板自动识别新导入的 AI 数据（需重算运动学量）

### R6 训练/推理 GUI 面板

1. Task Panel：显示当前/历史任务（训练/推理）的状态、进度、日志
2. Start Training / Start Inference 按钮（根据条件启用/禁用）
3. Cancel 按钮终止正在运行的任务
4. 任务完成/失败后的状态提示

---

## 2. Subphase 划分建议

| Subphase | 名称 | 核心交付 |
|----------|------|---------|
| 4.0 | Research & ADR | ADR-0011 + 本需求规范 + Issue |
| 4.1 | Engine Adapter & Task Framework | DLCAdapter + TaskRunner + TrackingRun 领域模型 + 单元测试 |
| 4.2 | Training Pipeline | 标注导出 + DLC 项目创建 + 训练启动/监控/取消 + 集成测试 |
| 4.3 | Inference & Import Pipeline | 模型推理 + 结果导入 TrackStore + AI 轨迹点生成 + 集成测试 |
| 4.4 | GUI & Integration | Task Panel + AI 轨迹视觉样式 + 端到端验收（单摆基准） |

---

## 3. 验收标准

| # | 验收标准 | 判定方式 | 状态 |
|---|---------|---------|------|
| AC-1 | DLCAdapter 可创建 DLC 项目并导出标注数据 | pytest（mock DLC API，验证目录结构和文件内容） | [ ] |
| AC-2 | TaskRunner 支持启动/进度/完成/取消生命周期 | pytest（后台进程单元测试） | [ ] |
| AC-3 | 推理结果导入后 TrackPoint 字段正确（source/confidence/first-wins） | pytest（合成 DataFrame → import → 校验） | [x] |
| AC-4 | confidence 随项目 JSON 持久化（save → load 一致） | pytest | [x] |
| AC-5 | 在单摆基准视频上：标注 → 训练 → 推理 → 轨迹显示，全流程在软件内完成 | Human Review | [ ] |
| AC-6 | 任务面板显示进度、支持取消 | Human Review | [ ] |

---

## 4. CI 与测试策略

4.3 实现证据：`tests/test_dlc_predictions.py`、`test_dlc_inference.py`、
`test_inference_session.py`、`test_inference_job.py`；真实 CPU 闭环脚本
`scripts/smoke_test_dlc_infer.py` 验证 10 帧预测、5 点导入/5 个人工点保护及保存重开。
GUI 验收 AC-5/6 保持未完成；帧进度数据已通过应用接口提供，显示接线留给 4.4。

- **GitHub Actions CI 不安装 DLC/PyTorch**（依赖链过大），DLC 相关测试全部使用 mock adapter
- 真实 DLC 端到端测试在本地进行：
  - macOS (Apple Silicon)：CPU / MPS 模式
  - Windows (NVIDIA GPU)：CUDA 模式
- mock adapter 需模拟真实的 DLC 输出格式（MultiIndex DataFrame），确保导入逻辑的正确性

---

## 5. 技术风险

| 风险 | 缓解措施 |
|------|---------|
| DLC 程序化 API 不稳定 | 通过 compat.py 门面接入，API 表面最小化；适配器隔离降低耦合 |
| PyTorch 版本与 DLC 版本耦合 | pyproject.toml 约束 deeplabcut>=3.0,<4.0，由 DLC 管理 PyTorch 兼容性 |
| 训练耗时导致用户体验差 | 后台子进程 + 实时进度 + 可取消；Phase 7 可引入预训练模型加速 |
| CUDA 内存不足 | 检测并报告友好错误，建议降低 batch_size；CPU fallback 始终可用 |
| Windows spawn 子进程的 pickling 限制 | 子进程入口函数定义在模块顶层，不使用 lambda 或局部函数 |
