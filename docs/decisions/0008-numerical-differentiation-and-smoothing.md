# ADR-0008 — 数值微分与平滑方法

- 状态：**Accepted**
- 日期：2026-08-30
- 决策者：开发团队
- 关联：`docs/roadmap.md` Phase 3 技术风险项；`docs/spec/data-model.md` §3.8（DerivedData pipeline 参数）；`docs/spec/phase3-requirements.md` R5

---

## Context（背景）

Phase 3 需要从原始像素轨迹数据计算运动学量（速度、加速度）。数值微分天然放大输入噪声：对长度 N 的离散位置序列做一阶差分，高频噪声幅值被放大为原始值的 `fps_nominal` 倍；二阶差分进一步放大为 `fps_nominal²` 倍。

物理实验视频的典型噪声来源：
- 手工标注精度 ~1 px（用户点击定位误差）
- 未来 AI 跟踪的帧间抖动
- 视频压缩伪影导致的亚像素偏移

因此**直接对原始数据做有限差分是不可用的**——必须先平滑再微分，或使用兼具平滑与微分能力的方法。

项目的 `DerivedData.pipeline` 字段（data-model.md §3.8）要求计算步骤的参数**完整可复现**，因此平滑和微分的方法、顺序、参数必须在此 ADR 中统一确定。

### 调研结论

开源生态中 6 个相关项目的做法（详见 `docs/research/open-source-project-map.md` §3–§4）：

| 项目 | 平滑方法 | 微分方法 | 顺序 |
|------|---------|---------|------|
| OpenPhysics TrackLab | 无平滑 | 中心有限差分 | 仅微分 |
| Tracker (OSP) | Savitzky-Golay / Moving Average / Butterworth | 中心有限差分 | 先平滑后微分 |
| DLC2Kinematics | Savitzky-Golay | SG `deriv` 参数 | 一步完成 |
| Sports2D | Butterworth 低通 | 中心差分 | 先平滑后微分 |
| Pose2Sim | Butterworth / Kalman / Gaussian / LOESS / Median | 差分 | 先平滑后微分 |
| Motion Tracker Beta | PyNumDiff（多种） | PyNumDiff | 可配置 |

**共识**：先平滑后微分（Smooth-then-Differentiate）是主流做法。Savitzky-Golay 是物理/生物力学领域最常用的选择（保相特性好、可同时提供导数、参数直观）。

### 已知陷阱

1. **DLC2Kinematics 的 `delta` bug**：`scipy.signal.savgol_filter` 有 `delta` 参数，控制采样间隔。DLC2Kinematics 未传入 `delta`（默认 1.0），导致 `deriv=1` 返回的是"每帧变化量"而非"每秒变化量"。**本项目必须显式传入 `delta = 1/fps_nominal`**。

2. **NaN 跨段桥接**：SciPy 的 `savgol_filter` 不处理 NaN——输入含 NaN 时整个输出变为 NaN。必须先将数据按 NaN 边界分割为连续有效段，逐段独立滤波（Pose2Sim/Sports2D 的做法）。

3. **边界帧伪影**：SG 滤波器在序列首尾帧附近可能出现 Runge 效应。SciPy 提供 `mode='interp'`（外插多项式平滑过渡），在典型物理实验数据长度（>20 帧）下表现可接受。

---

## Decision（决策）

### D1 顺序：先平滑后微分

采用 **Smooth-then-Differentiate** 固定顺序：

```text
Raw 观测 → (标定变换) → 物理坐标序列 → 平滑 → 微分(一阶) → 微分(二阶)
```

或利用 SG 的 `deriv` 参数一步完成（见 D2）：

```text
Raw 观测 → (标定变换) → 物理坐标序列 → SG(deriv=0) → SG(deriv=1) → SG(deriv=2)
```

### D2 平滑方法：Savitzky-Golay 作为 Phase 3 默认

选择理由：
1. **保相特性**：SG 是零相移滤波器（对称窗口），不引入时间延迟——对物理实验时间序列至关重要
2. **内建导数能力**：`scipy.signal.savgol_filter(x, window_length, polyorder, deriv=n, delta=dt)` 可同时完成 n 阶平滑和微分，一步到位
3. **参数直观**：`window_length`（奇数，决定平滑程度）和 `polyorder`（多项式阶数，决定保形能力）；用户可理解并调整
4. **生态成熟**：SciPy 实现经过广泛验证，DLC/Tracker/Pose2Sim 均使用

### D3 默认参数

| 参数 | 默认值 | 依据 |
|------|--------|------|
| `window_length` | 7 | 7 帧 ≈ 30fps 下 ~0.23s；足以平滑 1–2 px 测量噪声；不过度平滑 ~1 Hz 单摆信号（单摆典型周期 ~1–2s） |
| `polyorder` | 2 | 二次多项式可拟合抛物线运动（匀加速）；对单摆局部行为足够；阶数过高会拟合噪声 |
| `delta` | `1/fps_nominal` | **必传**，确保导数单位为 SI（m/s、m/s²） |
| `mode` | `'interp'` | SciPy 默认的边界外插模式，对典型物理数据长度（>20 帧）表现可接受 |

默认参数在 DerivedData 的 pipeline 中完整记录，用户可按需调整。验证计划：用单摆小角度解析解（`x(t) = A·sin(ωt + φ)`）测试不同参数组合下的速度/加速度恢复精度。

### D4 NaN 处理策略

1. 将稀疏 TrackPoint 展开为密集时间网格（帧 0 到最后一帧），缺测帧填 NaN
2. 按 NaN 边界将序列分割为**连续有效段**（contiguous valid segments）
3. 每段独立施加 SG 滤波：
   - 段长度 ≥ `window_length` → 正常滤波
   - 段长度 < `window_length` 且 ≥ `polyorder + 1` → 缩短窗口至段长度（取最近奇数）
   - 段长度 < `polyorder + 1` → 跳过（保持 NaN）
4. 重新组装为完整序列，NaN 位置保留

### D5 Pipeline 注册表预留

Phase 3 实现的步骤名：

| 注册名 | 实现 | 参数 |
|--------|------|------|
| `calibration_transform` | CalibrationTransform | `{calibration_id}` |
| `savitzky_golay` | `scipy.signal.savgol_filter` | `{window_length, polyorder, deriv, delta, mode}` |
| `finite_difference` | 中心有限差分纯函数 | `{method: "central"}` |

预留（Phase 6+ 按需实现，不影响 Phase 3 schema）：

| 注册名 | 说明 |
|--------|------|
| `butterworth` | Butterworth 低通滤波 |
| `gaussian` | 高斯核平滑 |
| `kalman` | Kalman 滤波器 |
| `loess` | 局部回归平滑 |
| `median` | 中位数滤波 |
| `hampel` | Hampel 异常值过滤 |
| `confidence_filter` | 按 confidence 阈值过滤（Phase 4+ 引擎接入后） |

新增步骤类型是 DerivedData pipeline 的 additive 扩展，不需要 schema 迁移。

---

## Consequences（影响）

### 正面

- 固定"先平滑后微分"顺序，消除歧义，pipeline 参数可精确复现
- SG 的 `deriv` 参数允许一步完成平滑+微分，减少中间步骤
- 默认参数对单摆基准场景已有理论支撑，可开箱即用
- NaN 段分割策略避免跨越缺测段产生虚假数据
- pipeline 注册表为未来扩展（Butterworth/Kalman 等）留足空间

### 负面 / 局限

- 用户需理解 `window_length` 和 `polyorder` 的含义才能做出有意义的调整
  - 缓解：Phase 3 提供合理默认值 + 简要说明；Phase 6 可增加参数自动推荐
- SG 对强非平稳信号（突变、冲击）的平滑效果有限
  - 缓解：Phase 6 可引入自适应滤波器（如 One Euro）
- 固定"先平滑后微分"限制了某些高级用法（如先微分再滤波的鲁棒微分方法）
  - 缓解：pipeline 是有序步骤列表，Phase 6 可放宽固定顺序约束
- 短段自动缩短窗口可能降低平滑质量
  - 缓解：给用户提示哪些帧段因数据不足而结果可靠性降低

---

## 参考

- `docs/research/open-source-project-map.md` §3–§4（6 个项目的平滑/微分实现细节）
- `docs/research/raw/dlc2kinematics-notes.md`（SG `delta` bug 的具体位置）
- `docs/research/raw/pose2sim-notes.md`（contiguous segment slicing 实现）
- `docs/research/raw/tracker-notes.md`（SG 边界单边多项式拟合）
- `docs/spec/data-model.md` §3.8（DerivedData pipeline 参数规范）
- SciPy `savgol_filter` 文档：https://docs.scipy.org/doc/scipy/reference/generated/scipy.signal.savgol_filter.html
