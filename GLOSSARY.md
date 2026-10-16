# AI Physics Tracker — Analysis

本表只定义高级分析的新术语。Project / Track / Observation / Timeline等既有核心术语以[数据模型术语表](docs/spec/data-model.md#1-术语表中英对照)为准。

## Language

**源信号（Source Signal）**：一次分析实际使用的物理量及其样本、时间与来源。测量角度和平滑角度是不同来源，不能静默互换。
_Avoid_: 当前显示的曲线（显示选择不一定是计算输入）

**分析区间（Analysis Interval）**：用户选定的本次计算范围。其起点是公式中相对时间的零点，视频原始时间仍保留。
_Avoid_: 重置视频时间

**拟合结果（Function Fit Result）**：用户声明的显式函数在指定样本与参数设置下得到的参数、预测、残差和求解状态。收敛不证明物理模型成立或参数唯一。
_Avoid_: 正确物理模型

**交叉事件（Crossing Event）**：所选信号按指定方向经过参考水平的一次事件。事件时刻可以由相邻有效样本估计，不是新增的观测。
_Avoid_: 人工标注点

**重复间隔（Recurrence Interval）**：同一连续有效段中，相邻两次指定方向交叉之间的时间差。
_Avoid_: 基本周期（尚未建立一一对应关系时）

**周期估计（Period Estimate）**：信号每个完整循环恰对应一次指定交叉时，对循环持续时间的估计。
_Avoid_: 已证明的恒定周期

**模型换算值（Model-derived Value）**：将本次参数代入用户声明的结果公式得到的数值。它与直接从信号测得的重复间隔具有不同来源。
_Avoid_: 独立测量值
