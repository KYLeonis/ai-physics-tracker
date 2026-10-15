# ADR-0021 — 显式函数拟合与信号重复间隔的输入 / 结果契约

## Status

Accepted，2026-10-15。P6.3 S0；用户已批准产品范围（Issue #29）。冻结 `9bf9acd` 的全新Luna-max定向独立检查Approve、无finding；真实人工参考 / 用户提供的P011标定与旧DLC / 本次时序授权已冻结。见[review](../reviews/phase-6.3-review.md)及[基准记录](../notes/phase-6.3-reference-preparation.md)。

## Context

[ADR-0017](0017-user-defined-equation-analysis-platform.md)确定用户提供公式；[6.3计划](../status/phase-6.3-plan.md)要求单轨迹 / 单物理量显式函数拟合、独立重复间隔测量、最新结果与保存重开。已有DerivedData / Session快照 / Undo可以复用，但存在三个具体缺口：

1. 当前结果版本栅栏只检查被覆盖的目标结果，不检查作为输入的上游派生结果。相同raw上换支点 / SG会产生新的source ID，旧拟合必须失效，后台迟到结果也必须拒绝。
2. 图表既有一列 / 两列数据不承载拟合参数、源样本、预测 / 残差与交叉事件的不同语义。
3. 删除参考轨迹会删除角量记录；仍可查看的历史拟合不能依靠已删除实体才能解释，也不能带悬空的活引用。

选择在既有schema v1中追加受限结果kind与一个有版本的analysis扩展。拒绝另建结果库 / 通用依赖图 / 全部历史引擎；保持一个最新结果槽和现有事务边界。

## Decision

### 1. 目标量与最新结果槽

- 允许quantity为`x/y/vx/vy/ax/ay/theta/omega/alpha`，一次一个轨迹 / 量，时间为唯一自变量。
- `function_fit_<quantity>`与`signal_recurrence_<quantity>`为两族明确kind。同一轨迹 / quantity每族至多一条，换公式或测量 / 平滑来源仍替换同一槽；两族独立。
- 仅允许既有KINEMATICS_KINDS / ANGULAR_KINDS提供来源；不允许本期结果再作拟合输入，也不建立任意结果依赖图。
- 测量 / 平滑选择落实为具体`source_kind + component`；例如x可选world_position[0]或smoothed_position[0]，theta可选angular_position[0]或smoothed_angular_position[0]。速度 / 加速度披露既有SG配方。
- 对同一key出现重复旧记录或不可读的新版本，不静默任选一个参与新计算，先明确拒绝并指明恢复方式。

### 2. 源信号、时间与快照

- prepare先复用AnalysisInputs / 当前时序授权，再核对source状态valid、轨迹 / 视频、配方 / 标定 / 参考、SG、记录的时间区间与当前会话一致。不能以“能读取values”替代科学有效性检查。
- 快照保存source ID、kind、component、完整input / pipeline、时序 / 标定 / 角参考定义、实际源样本和帧区间；不凭新参数反推缓存来源。
- 分析区间为当前working zone内的闭区间`[start_frame,end_frame]`；默认working zone。`video_time_s`由Timeline换算；`relative_time_s = video_time_s - frame_to_time(start_frame)`，界面称`t`，不修改raw时间。
- `samples`保存实际使用的有序帧、视频时间、相对时间、量值和连续段身份；缺测不造值，下一段不重新计时。它是本次计算的可重现数值输入，不声称保留全部旧项目或优化器每一次试算。
- source若为wrapped角，来源需明确；跳变用于周期分段，不静默unwrap或改写样本。拟合来源与误差说明也必须披露wrapped / smoothed-unwrapped选择。

### 3. schema v1 additive落点

- 复用Project.derived / DerivedData，序列化器继续保留未知字段。新kind不改变既有四项 / 角量kind、旧结果宽度或源数据。
- P6.3拥有`DerivedData.extra_fields["analysis"]`对象，`version=1`；记录quantity、source快照 / ID、interval、samples、方法规格与摘要。缺失 / 未知版本允许只读保存，不能拿来新计算或冒充已验证结果。
- `frames`始终为原视频源帧号；拟合`values`列明确为`[prediction,residual]`，残差定义为`measured-prediction`，单位沿用source。实际测量值 / 两种时间保存在analysis.samples中，对齐frames且均为有限实数。
- 重复间隔结果的`values`仅一列源信号量值，单位仍是source单位；事件 / 间隔 / 均值 / 样本标准差以显式`*_s`字段保存于摘要，不能把秒伪装成逐帧位置列。
- 交叉事件保存实际相邻源帧夹点、夹点时间与插值事件时间；事件不是人工TrackPoint，不编造整数事件帧或写回raw。
- 拟合摘要保存表达式 / 语法版本、参数初值 / 边界 / 固定状态、解、求解选项 / 版本 / 终止状态、样本数、RMSE / 可辨识性状态、可选结果公式与代入值。仅保存有限JSON值；不可估计用null加原因，不用0或NaN。
- 本期结果的DerivedInput仅持有所属轨迹的活引用；原角量reference_track_id等是source快照里的历史事实。calibration_ref沿用既有派生语义，不要求已删除标定必须能重新求值。
- 更新已拥有的analysis字段时保留同版本未知扩展；未来版本不能被当前实现降级重算。保存 / Save as原样保留；不从旧结果继承上次拥有但本次不适用的参数 / 事件 / 摘要。

### 4. 失效、清除与事务

- 对本期分析结果执行有限的直接依赖核对：source ID被替换 / 删除 / stale，或来源身份 / 配方发生变化，则其结果stale，保留样本快照只读；不自动接到同kind新结果或自动再拟合。
- 既有raw编辑、AI显式激活 / 清除、标定、working zone仍沿原入口置源结果stale，再传播到本期结果。同步compute_kinematics / compute_angular和后台批次替换也要在同一事务标记下游。
- 删除所属轨迹A仍删除A的全部结果；删除参考轨迹B仍删除引用B的角量源，保留A的拟合 / 间隔结果为stale且来源可读，不能留下新的活引用。
- `clear_derived(track_id)`保留现有“清该轨迹全部派生数据”契约，包含本期两族；不擅自改成只清上游。删除 / 替换特定源时则将仍保留的直接下游标为stale。
- Undo/Redo恢复完整源 / 目标结果与状态，不在历史恢复后另行把已恢复正确的结果置stale。一次发布 / 失效是一个既有Project快照事务，失败不改部分集合。

### 5. 后台提交的两类版本与配方核对

- Job分别捕获：AnalysisInputs、确切source记录及快照、用户当前规格、将被替换的目标槽旧ID。source版本与目标版本不能混成一个previous_derived_ids。
- 发布前重查：当前raw / 参考 / 标定 / 时序与prepare一致，source仍存在 / valid且记录 / 数值 / 配方一致，目标槽版本未变，结果的实际样本 / 公式 / 初值 / 边界 / 求解或周期规格与请求一致。
- GUI在用户改公式 / 参数 / 区间、切换项目 / 轨迹 / 分析来源时取消任务；显示切换与保存不单独改变科学输入。结果只在主线程原子提交。
- 配方未知、样本错位、域错误、不可辨识、达到上限或取消不发布“正常成功”的拟合，不覆盖上次成功值。全参数固定是明确的给定参数计算。
- 周期事件不足是一次完成但无可估计间隔的测量：可保存其信号 / 方法 / 失败原因，摘要不得展示有效周期。DerivedData.status仅表示输入新鲜程度，不代替测量成功状态。

### 6. 科学含义与表达式边界

- 公式输入是受限数学表达式，解析成同一语义树用于解释执行与排版；不以任意eval/exec / MathText解析器执行用户代码。固定函数 / 运算、名称、节点 / 深度 / 长度与数值范围检查在边界完成。
- 普通最小二乘、单组用户初值 / 边界、等权有效样本；不承诺全局最优。常量信号可拟合可辨识常量模型，不能因为不振荡就拒绝通用拟合。
- 结果换算仅引用本次参数与允许常数 / 函数，不引用时间或其他换算结果；除零等单独标错，保留原拟合。
- 同向参考线交叉只定义重复间隔；每个完整循环恰有一次该交叉时才可解释为周期估计。多峰 / 变周期不自动解释为唯一基本周期。非单摆 / 非周期 / 无有效穿线均有独立用例。
- 单个间隔的样本标准差不可估计；实测近似时序、平滑来源、拟合残差和周期离散分别披露。

### 7. 依赖

用户已批准Matplotlib，仅用于本期MathText公式预览；实施时声明并锁定依赖，默认不启用外部TeX，保留许可通知。当前S0未安装 / 使用，安装和双平台检查在GUI Slice完成。

## Consequences

复用现有持久化与Undo事务，无schema迁移或通用结果库；代价是本期结果有明确专用kind / 元数据解析及依赖失效适配。所有数值与生命周期实现、定向 / 全量 / CI / 独立复审 / 新HR仍未完成。S0的独立人工参考、连续轨迹与角参考已单独冻结；本ADR不代替真实算法验收，也不批准按算法效果选择片段。
