# Phase 3 需求与验收标准（Calibration & Physics Engine）

- 日期：2026-08-30 · 状态：**Draft**
- 来源：`docs/roadmap.md` Phase 3；上游依据 `docs/spec/data-model.md`（§3.7/§3.8/§6）、`docs/architecture.md` §4
- 输入：`docs/research/open-source-project-map.md` §3/§4/§6/§7（TrackLab/Tracker/Kinovea/DLC2Kinematics/Sports2D/Pose2Sim 调研）、Phase 1/2 已有实现
- 与 roadmap 的关系：本文档是 roadmap Phase 3 验收标准的**细化**，逐条可勾选判定；两者如有矛盾以本文档为准并回改 roadmap

---

## 0. 背景与约束

### 0.1 项目当前能力边界

Phase 3 启动时，项目已具备：

- **手工标注**：用户在视频帧上逐帧手动点击标记目标位置，形成 `source=manual` 的 TrackPoint（像素坐标）
- **标定域模型**：`Calibration` 数据结构与 `CalibrationTransform` 纯函数（像素↔世界坐标互转，6 条规格全测通过）
- **DerivedData 数据结构壳**：schema 定义完成（kind/pipeline/frames/values/status），但**无计算引擎**
- **GUI 框架**：视频播放/缩放/平移、时间轴 scrub、Track 面板（创建/删除/选择）、标注 overlay、项目保存/加载

项目**尚不具备**的能力（明确不在 Phase 3 范围）：

- **AI/引擎跟踪**：DeepLabCut 等自动跟踪引擎（Phase 4）
- **代表帧选取/困难帧检测**（Phase 5）
- **高级物理分析**：θ/ω/α、相图、周期分析、拟合、误差分析（Phase 6）
- **数据导出**：CSV/Excel/高质量图表导出（Phase 8）

因此 Phase 3 的运动学计算与图表**仅消费手工标注数据**。轨迹点数量有限（用户逐帧标注，典型数十~数百帧），这既是约束也是简化——无需处理 AI 批量跟踪的 confidence 过滤（该路径在 Phase 4+ 接入引擎后自然激活）。

### 0.2 基准实验场景

**单摆**是 Phase 3 的首要测试案例（roadmap §总原则）：

- 用户在单摆视频上手工标注摆锤位置（数十帧）
- 设置比例尺标定（已知摆长或参照物）
- 运动学引擎计算物理坐标、速度、加速度
- 图表显示 x(t)、y(t) 等运动轨迹，验证物理量合理性

合成数据（匀速/匀加速/单摆小角度解析解）用于自动化测试。

---

## 1. 范围

Phase 3 为项目增加**物理实验分析能力**：用户可在视频上设置标定、查看手工标注轨迹的运动学计算结果（位置/速度/加速度），并以交互图表可视化。

- 领域层运动学计算无 Qt 依赖，可 pytest 覆盖
- GUI 标定工具与图表面板使用 PySide6 + PyQtGraph
- 新增依赖：`pyqtgraph>=0.13,<0.14`、`scipy>=1.14,<2.0`
- 数据模型无 breaking change（利用已有 Calibration/DerivedData 结构）

---

## 2. 功能点清单（R1–R9）

### R1 标定 GUI — 比例尺工具

在视频画面上交互式创建/编辑比例尺标定：

1. **标定模式入口**：工具栏按钮或菜单项进入标定模式（与标注模式互斥）
2. **线段绘制**：在视频帧上拖拽/两次点击画出比例尺线段（两端点 = `scale_end_1_px` / `scale_end_2_px`）
3. **长度输入**：弹出对话框输入已知长度与单位（m / cm / mm）
4. **创建标定**：确认后创建 `Calibration` 对象，自动设为当前视频的 active calibration
5. **线段可视化**：标定线段在 VideoView 上以 overlay 显示（带端点标记与长度标注），缩放不变
6. **编辑标定**：重新拖拽端点或修改长度/单位；编辑后下游 DerivedData 自动置 stale（利用已有传播逻辑）

### R2 标定 GUI — 坐标原点与轴旋转

1. **原点设置**：在视频帧上点击设置世界坐标原点（`origin_px`）；默认左下角（已有数据模型默认值 `(0, height_px)`）
2. **原点可视化**：十字+坐标轴图示（x 向右、y 向上的世界坐标系），overlay 显示
3. **旋转设置**：输入框设置 `rotation_deg`（世界 x 轴相对图像 x 轴的旋转角）
4. **坐标轴可视化**：旋转后的坐标轴方向在 overlay 上实时更新

### R3 标定状态显示与管理

1. **状态指示**：当前视频的标定状态在 UI 中可见（"未标定" / "已标定: [名称]"）
2. **标定管理面板**：列出当前视频的所有标定方案，可切换 active、删除非 active 标定
3. **退化输入拒绝**：两端点重合或已知长度 ≤ 0 时 UI 提示拒绝（利用已有 `CalibrationError`）

### R4 运动学计算引擎 — 坐标变换

1. **批量像素→物理坐标转换**：取当前视频 active calibration + 某 Track 的全部 active 手工标注点，批量调用 `CalibrationTransform.pixel_to_world`，生成 `kind=world_position` 的 DerivedData
2. **无标定时的行为**：不产生物理意义的世界坐标；兼容 3.2 已有 `world_position(unit=px, calibration_ref=None)` 记录，图表明确标注像素位置（ADR-0009），不迁移旧数据。
3. **DerivedData 填充**：完整记录 pipeline（`[{step: "calibration_transform", params: {calibration_id: ...}}]`）、`calibration_ref`、`frames`、`values`、`unit`

### R5 运动学计算引擎 — 平滑与微分

1. **Savitzky-Golay 平滑**：对物理坐标序列（或像素坐标序列，无标定时）施加 SG 滤波，生成 `kind=smoothed_position` 的 DerivedData
   - 默认参数：`window_length=7`、`polyorder=2`（ADR-0008）
   - 参数完整记录在 pipeline 中：`{step: "savitzky_golay", params: {window_length: 7, polyorder: 2}}`
2. **一阶数值微分（速度）**：对平滑后的位置序列计算 vx(t)、vy(t)，生成 `kind=velocity` 的 DerivedData
   - 方法：利用 SG 滤波器的 `deriv=1` 参数一步完成（平滑+微分），或先 SG 平滑再中心有限差分
   - **关键**：必须传入物理时间步长 `delta = 1/fps_nominal`（避免 DLC2Kinematics 的已知 bug）
   - pipeline：`{step: "savitzky_golay", params: {window_length: 7, polyorder: 2, deriv: 1, delta: ...}}` 或 `{step: "finite_difference", params: {method: "central"}}`
3. **二阶数值微分（加速度）**：同理，生成 `kind=acceleration` 的 DerivedData
4. **NaN 处理**（ADR-0008）：
   - 稀疏 TrackPoint 展开为密集时间网格时，缺测帧填 NaN
   - SG 滤波在连续有效段上独立运算（Pose2Sim/Sports2D 的 contiguous segment slicing 模式）
   - NaN 边界处微分结果保持 NaN，不跨越缺测段插值
5. **单位自动推导**：位置单位 → 速度单位 `{unit}/s` → 加速度单位 `{unit}/s²`；无标定时为 `px`、`px/s`、`px/s²`

### R6 运动学计算引擎 — 数据管理

1. **自动计算触发**：当用户添加/修改/删除标注点、切换标定时，受影响的 DerivedData 标记为 stale（利用已有传播逻辑）
2. **按需重算**：提供"重新计算"操作（按钮/菜单项），对 stale 的 DerivedData 重新运行 pipeline
3. **参数可调**：用户可修改 SG 窗口长度与多项式阶数（Phase 3 提供简单 UI，如对话框或面板上的参数输入）

3.3 批次重算通过既有扩展字段保存 `timing_context={fps_nominal, approximation}`；
`approximation` 为当前近似时序授权的来源说明（CFR 为 null），不替代已有 pipeline。
查看旧结果不需要重新授权，生成新结果必须通过当前时序关卡；不迁移 raw 或 schema。

### R7 基础图表 — PyQtGraph 集成

1. **新增依赖**：`pyqtgraph>=0.13,<0.14`（交互绘图）、`scipy>=1.14,<2.0`（SG 滤波器实现）
2. **图表面板**：作为可停靠面板（QDockWidget）集成到 MainWindow 底部或右侧
3. **五种基础图表**：
   - **x(t)**：物理 x 坐标随时间变化（或像素 x，无标定时）
   - **y(t)**：物理 y 坐标随时间变化
   - **vx(t) / vy(t) 或 |v|(t)**：速度分量或速率随时间变化
   - **ax(t) / ay(t) 或 |a|(t)**：加速度分量或加速度大小随时间变化
   - **x-y 轨迹图**：物理坐标系下的空间轨迹（y 向上）
4. **图表切换**：提供下拉框或标签页在不同图表类型间切换（不要求同时显示全部 5 种）

### R8 基础图表 — 帧同步与交互

1. **当前帧游标**：视频当前帧在图表上以竖线（InfiniteLine）标记，随播放/步进/scrub 实时移动
2. **双向同步**：
   - 视频帧变化 → 图表游标跟随
   - 用户在图表上点击/拖拽游标 → 视频跳转到对应帧（反向联动）
3. **多 Track 叠加**：同一图表上可叠加多条 Track 的数据，以 Track 颜色区分
4. **图表自适应**：数据范围变化时自动调整坐标轴范围；支持鼠标滚轮缩放与拖拽平移（PyQtGraph 内置）

### R9 数据无效态的 UI 反馈

1. **无数据提示**：选中的 Track 无标注点时，图表区域显示"无数据"提示
2. **未标定提示**：需要物理坐标但当前视频未标定时，显示"请先设置标定"或切换为像素坐标显示
3. **stale 提示**：DerivedData 为 stale 时，图表上以视觉提示（如半透明、虚线或警告图标）标识数据可能过期

---

## 3. 验收标准（细化，逐条可判定）

| # | 验收标准 | 判定方式 | 状态 |
|---|---------|---------|------|
| AC-1 | 可在视频帧上交互式创建比例尺标定（拖拽线段 + 输入已知长度） | Human Review：打开视频 → 进入标定模式 → 画线 → 输入长度 → 确认 → 标定生效 | [ ] |
| AC-2 | 可设置坐标原点与轴旋转，overlay 实时显示坐标系 | Human Review：设置原点 → 看到坐标轴十字 → 修改旋转角 → overlay 更新 | [ ] |
| AC-3 | 标定后坐标转换误差满足设计精度（合成数据测试） | pytest：已知像素坐标 + 已知标定参数 → 批量转换 → 与解析解比对，误差 < 1e-9（复用 Phase 1 的 CalibrationTransform 测试，扩展到批量 pipeline） | [ ] |
| AC-4 | 用匀速合成数据验证 v 计算正确 | pytest：匀速 (vx=2 m/s) 合成 100 帧 → SG 平滑+微分 → vx 与真值偏差 < 0.01 m/s（扣除边界 N/2 帧） | [ ] |
| AC-5 | 用匀加速合成数据验证 a 计算正确 | pytest：匀加速 (ax=1 m/s²) 合成 100 帧 → 二阶微分 → ax 与真值偏差 < 0.05 m/s²（扣除边界） | [ ] |
| AC-6 | NaN 处理正确：缺测帧不造值、不跨越缺测段平滑 | pytest：合成带间断（帧 40–60 缺测）的轨迹 → 平滑/微分结果在缺测段保持 NaN，有效段结果不受影响 | [ ] |
| AC-7 | 图表面板显示 x(t)、y(t)、v(t)、a(t)、x-y 轨迹共 5 种图表 | Human Review：标注若干帧 → 标定 → 看到图表显示运动学数据 → 切换图表类型 | [ ] |
| AC-8 | 图表与视频帧同步联动（双向） | Human Review：步进/播放视频 → 图表游标跟随 → 点击图表 → 视频跳转到对应帧 | [ ] |
| AC-9 | DerivedData pipeline 参数完整记录在 project.json 中 | pytest：生成 DerivedData → 保存 → 加载 → pipeline 参数逐字段一致 | [ ] |
| AC-10 | 标定变更后 DerivedData 自动置 stale，重算后恢复 valid | pytest：创建标定 + 计算 DerivedData → 修改标定 → DerivedData status=stale → 重算 → status=valid + 新值 | [ ] |

> roadmap 原始三条验收标准的对应：
> - "标定后坐标转换误差满足设计精度" → AC-3
> - "用匀速/匀加速合成数据验证 v/a 计算正确" → AC-4/AC-5
> - "图表与视频帧同步联动" → AC-7/AC-8

---

## 4. 建议 Subphase 划分

| Subphase | 名称 | 一句话目标 | 新增依赖 |
|----------|------|-----------|---------|
| 3.0 | Spec & Requirements | 需求规范 + ADR-0008（**本 Subphase**） | 无 |
| 3.1 | Calibration UI | GUI 标定工具：比例尺线段、原点、旋转、overlay | 无 |
| 3.2 | Kinematics Engine | 运动学计算引擎：坐标转换 + SG 平滑 + 微分 + DerivedData 生产 | `scipy>=1.14,<2.0` |
| 3.3 | Interactive Charts | PyQtGraph 图表面板 + 帧同步联动 + 多 Track 叠加 | `pyqtgraph>=0.13,<0.14` |
| 3.4 | Integration & Phase Close | 端到端验收 + Human Review + 文档收尾 | 无 |

### 依赖关系

```text
3.0 (spec) → 3.1 (calibration UI)
                ↘
3.0 (spec) → 3.2 (kinematics) → 3.3 (charts) → 3.4 (close)
```

3.1 和 3.2 可并行（标定 UI 只需已有 CalibrationTransform；运动学引擎是纯领域层），但 3.3 依赖 3.2 的计算结果来渲染图表。

---

## 5. 测试要求

| 模块 | 必测内容 | 数据 |
|------|---------|------|
| 运动学计算 — 坐标转换 | 批量 pixel→world 正确性 | 合成：已知标定 + 像素网格 |
| 运动学计算 — SG 平滑 | 平滑后曲线保形、NaN 段隔离 | 合成：sin(t) + 高斯噪声 + NaN 间断 |
| 运动学计算 — 速度 | 匀速 → 常数 v；sin(t) → cos(t) | 合成：解析解比对 |
| 运动学计算 — 加速度 | 匀加速 → 常数 a；sin(t) → -sin(t) | 合成：解析解比对 |
| 运动学计算 — NaN 处理 | 缺测段不造值、不跨段平滑 | 合成：带间断的轨迹 |
| 运动学计算 — 单位推导 | m → m/s → m/s²；无标定时 px | 单元测试 |
| DerivedData pipeline | 参数往返持久化一致 | 保存/加载 round-trip |
| DerivedData stale | 标定变更 → stale → 重算 → valid | 操作序列 |
| 标定 GUI | 交互式标定流程（Human Review） | 手动验收 |
| 图表面板 | 5 种图表显示 + 帧同步 + 多 Track（Human Review） | 手动验收 |

- 数值断言带显式容差（CODE_STANDARD.md §9.4）
- 运动学测试用**解析已知解的合成数据**（CODE_STANDARD.md §9.7）
- GUI 测试以手动验收为主；标定工具和图表面板均需 Human Review

---

## 6. 明确不做（Phase 3 边界）

| 推迟项 | 去向 | 理由 |
|--------|------|------|
| AI/引擎自动跟踪（DLC/TAPIR/SAM2） | Phase 4 | Phase 3 只消费手工标注数据 |
| confidence 阈值过滤 | Phase 4+ | 手工标注无 confidence（恒 null）；引擎接入后激活 |
| θ/ω/α 角度运动学 | Phase 6 | 需要刚体/角度定义，超出 Phase 3 "基础运动学"范围 |
| 相图（θ-ω）、周期分析、拟合 | Phase 6 | |
| 误差分析 | Phase 6 | |
| Butterworth/Kalman 等替代滤波器 | Phase 6 或按需 | Phase 3 只实现 SG；pipeline 注册表已预留扩展 |
| CSV/Excel/高质量图表导出 | Phase 8 | Phase 3 图表为交互查看，不含导出 |
| 多视频联动标定 | Phase 10 | 当前单视频分析 |
| 平面标定（单应矩阵） | Phase 10 | Phase 3 仅 `line_scale` 类型 |
| 时变标定（Kinovea `GetPointAtTime`） | Phase 10 | `applies_from/to_frame` 已预留，Phase 3 恒 null |

---

## 7. 关键设计约束（实现阶段必读）

### 7.1 SG 滤波器的 `delta` 参数

**必须**向 `scipy.signal.savgol_filter` 传入 `delta = 1/fps_nominal`，使 `deriv=1` / `deriv=2` 返回的导数值具有正确的物理单位（m/s、m/s²）。

DLC2Kinematics 未传 `delta`（默认 1.0），导致导数单位为"每帧"而非"每秒"——这是已知 bug，本项目**必须避免**。

### 7.2 连续有效段分割（contiguous segment slicing）

对含 NaN 的时间序列施加 SG 滤波时：

1. 按 NaN 边界分割为多个连续有效段
2. 每段独立施加滤波器；按 Accepted ADR-0008 D4，短段缩短至合法奇数窗口，不足 `polyorder+1` 的段保持 NaN（不跨段补值）。
3. 重新组装为完整序列（NaN 位置保留）

此模式借鉴 Pose2Sim/Sports2D 的实践，避免滤波器跨越缺测段产生虚假平滑值。

### 7.3 边界处理

SG 滤波器在有效段的边界帧可能产生边界伪影（Runge 效应）。Tracker OSP 使用单边多项式拟合处理边界——Phase 3 先用 SciPy 的默认边界模式（`mode='interp'`），在单摆基准实验中评估效果，如有必要在 Phase 6 改进。

### 7.4 图表面板呈现方式

图表面板采用 **QDockWidget** 停靠在 MainWindow 底部（默认）或右侧，可拖拽浮动/关闭/恢复。面板内使用 **标签页（QTabWidget）** 切换不同图表类型（x-t / y-t / v-t / a-t / x-y），每次只显示一种图表。

PyQtGraph 的 `PlotWidget` 提供内置的鼠标滚轮缩放与拖拽平移，无需额外实现。当前帧游标使用 `InfiniteLine`（可拖拽），提供视频↔图表的双向联动。

### 7.5 无 AI 引擎时的运动学计算输入

运动学计算引擎的输入是某 Track 的**全部 active 生效 TrackPoint**（`resolve_effective_point` 逻辑，data-model.md §4.3）。Phase 3 中这些全部是 `source=manual` 的手工标注点。

引擎不区分 source——它只接收 `(frame_index, pixel_x, pixel_y)` 序列。Phase 4+ 接入 AI 跟踪后，同一引擎自然可消费 `source=dlc` 等来源的数据，无需修改。

---

## 8. 完成定义（Definition of Done）

- [ ] AC-1…AC-10 全部勾选
- [ ] 运动学计算引擎有 pytest 覆盖，合成数据验证通过
- [ ] 标定 GUI 与图表面板 Human Review 通过
- [ ] `pyqtgraph` 与 `scipy` 依赖加入 `pyproject.toml` 与 `requirements.txt`
- [ ] DerivedData pipeline 持久化往返一致
- [ ] 按 AGENTS.md §11 完成文档同步与 push
