# ADR-0019 — 角运动计算与多输入派生数据的 additive 契约

## Status

Accepted，2026-10-11。用户确认启动 Phase 6.1（角运动基础）；本 ADR 落实
[phase-6.1-plan.md](../status/phase-6.1-plan.md) Slice 1 要求的"scalar kinds / 多输入参数
additive 落点"决策。口径服从 [ADR-0017](0017-user-defined-equation-analysis-platform.md)：
角运动/求导是通用方程平台的输入能力，本 ADR 不引入任何固定拟合模型。

## Context

Phase 3 的派生数据体系围绕四项 `KINEMATICS_KINDS`（world_position / smoothed_position /
velocity / acceleration）建立，三处隐含"恰好四项 / values 恰好两列 / 单轨迹输入"的具体契约：

1. `application/chart_data.py` 只消费两列 values（单列行被丢弃）；
2. `application/kinematics_job.py` 的批次校验期望集固定为 KINEMATICS_KINDS × tracks；
3. `domain/project.py` 首次标定失效规则按 KINEMATICS_KINDS 过滤。

[phase6-requirements.md R1/R5](../spec/phase6-requirements.md) 要求单摆（固定支点）与
两点方向（双轨迹 A→B）两种角度定义，其中双轨迹的方向参考是一条完整计算依赖——
参考轨迹的编辑/删除必须使结果失效。`DerivedInput` 目前只有单个 `track_id`，
没有任何机制表达第二轨迹依赖（pre-phase6 review §10 明示不得把现有四项当成通用结果集）。

## Decision

### 1. 新增四个 additive 标量 kind（不泛化既有四项）

```text
ANGULAR_KINDS = ("angular_position", "smoothed_angular_position",
                 "angular_velocity", "angular_acceleration")
单位：rad / rad / rad/s / rad/s²（计算一律 rad，显示转换留给 GUI）
```

- `angular_position`：原始角度，atan2 输出，wrapped 到 [-π, π]。
- `smoothed_angular_position`：段内 unwrap 后的 SG(deriv=0) 平滑角度。
- `angular_velocity` / `angular_acceleration`：对 unwrap 后角度的 SG deriv=1/2。
- values 为**单列**行 `[[θ0], [θ1], ...]`；DerivedData 模型与序列化器本不限列宽，
  仅 chart_data 两列假设需 Phase 6.2 适配（6.1 不改 GUI，单列行按既有畸形数据路径丢弃）。
- 每条轨迹每种 kind 至多一条（同现有语义）：换参考或换参数重算 = 整组替换。

### 2. 双轨迹依赖：DerivedInput 增加可选 `reference_track_id`

- `DerivedInput.reference_track_id: UUID | None = None`（additive，旧文件缺省 None）。
- 语义：两点方向参考轨迹（B）的完整计算依赖；`reference_track_id == track_id` 在构造时拒绝。
- 失效传播：
  - `mark_tracks_stale` 同时匹配主 `track_id` 与 `input.reference_track_id`
    （参考轨迹的观测编辑使结果 stale）；
  - `delete_track(B)` 级联删除**其他轨迹**中 `input.reference_track_id == B` 的派生记录
    （与既有"Track 删除级联其派生"一致，Undo 快照一并恢复）；
  - `validate_project` 校验 reference_track_id 必须指向已注册轨迹。
- 序列化：仅当非 None 时写入 input 对象；旧版本代码读取新文件时该键落入
  extra_fields（tolerant read），不破坏兼容。

### 3. 单摆支点：像素参数记入 pipeline，不进 DerivedInput

- 支点不是观测，是计算参数：只记录在 pipeline 的 `angular_reference` 步骤
  （`{"mode": "pendulum", "pivot_px": [x, y]}`），并用与摆球**相同的 active 标定**变换。
- 两点方向的 pipeline 步骤记录 `{"mode": "two_point", "reference_track_id": "..."}`；
  实体引用在 `DerivedInput.reference_track_id`，pipeline 记录仅为可复现配方。
- R1 首版要求有效标定：无 active 标定时拒绝计算，不提供像素角度模式
  （角度虽对比例尺不敏感，但受标定旋转影响，且口径统一为"标定后的世界系角度"）。

### 4. 角度定义与数值规则（phase6-requirements R1）

- 单摆：`theta = atan2(world_x - pivot_x, -(world_y - pivot_y))`，竖直向下为零，
  向右摆动为正（y 向上世界系）。
- 两点方向：`theta = atan2(world_y_B - world_y_A, world_x_B - world_x_A)`，
  +x 为零，逆时针为正；仅使用两轨迹同帧有效点交集，两点重合帧无定义（NaN，不造 0）。
- unwrap 仅在各连续段内进行（np.unwrap 默认 discont=π，pipeline 记录该值）；
  不声称恢复跨段整周偏移。
- 平滑/微分沿用 [ADR-0008](0008-numerical-differentiation-and-smoothing.md)：
  默认 window=7 / polyorder=2，`delta = 1/fps_nominal`，段长不足时按短段规则，
  可定义原始角度保留、不造 ω/α。
- 管线顺序：θ(raw, wrapped) → 段内 unwrap → SG(deriv=0/1/2)，与既有线性管线
  "对原始信号一次 SG 取各阶导"一致（不对平滑结果再级联微分）。

### 5. 后台事务复用既有骨架

`angular_job` 复用 AnalysisInputs / detached 快照 / 主线程输入复核 / `_commit_store`
原子提交：批次期望集 = ANGULAR_KINDS × 目标轨迹（参考轨迹的自身派生不动）；
`analysis_inputs` 的 track 集合同时包含目标与参考轨迹，任一输入变化即拒绝迟到结果；
取消在规格间检查，整个批次一个 Undo 步。非目标 kind 与未知 extra_fields 保留。

## Consequences

- schema v1 无迁移：新 kind、单列 values、reference_track_id 全部 additive；
  旧项目读取行为不变（无回归）；旧代码读新文件 tolerant 不报错。
- 既有四项运动学与图表行为不变；chart_data 对单列行的丢弃是有意留待 6.2 的适配点。
- `KINEMATICS_KINDS` 首次标定失效规则无需修改：角度结果恒带 calibration_ref，
  标定切换/编辑/删除路径天然覆盖；首版无像素角度结果。
- 后续 6.2（角运动图表）需显式适配 chart_data 的两列假设与 kind 映射；
  6.3（周期/拟合）按 ADR-0017 另行重规划，不引用本 ADR 的任何拟合语义。
