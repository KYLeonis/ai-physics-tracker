# ADR 0019: 可显式调整角速度SG窗口与阶数

## Status

Accepted (2026-10-01)，用户要求对已取得的tip轨迹提供自定义SG。

## Context

角速度是角度的局部导数估计；相图是同帧(θ,ω)，reference energy也需要ω。固定SG9/3把最长8帧可信数据全部判为不可求导，不说明其他合法估计设置，误导用户继续训练。SG窗口/阶数是分析参数，不能等同跟踪质量门槛。

## Decision

保留student-default-v2的默认9/3与冻结字节，允许显式resolved overrides。窗口为奇数整数≥3，阶数为整数且1≤p<window；legacy拒绝覆盖。按每个连续、均匀、QC-valid源帧段直接调用已有SciPy savgol_filter(deriv=1, mode=interp)，不预平滑、不跨缺口。快捷7/3与5/2及自定义控件使用同一计算路径。

记录实际窗口/阶数、最短段、edge半窗、override来源与依赖版本；纳入分析digest/job/payload，并从已保存结果恢复控件。修改设置只使显示参数待应用，明确旧图仍是旧设置；必须重算。禁止隐式自动缩窗或用未采用点补缺。

## Consequences

短段可得到局部图，但更短窗口减少平均作用、导数通常对噪声更敏感；边缘估计仍单独标记。预览显示预计可求导覆盖，不宣称误差更小。SG设置不改变周期过零/tail完整周期要求、tip QC、confidence或未来拟合资格。

依据：[SciPy savgol_filter](https://docs.scipy.org/doc/scipy/reference/generated/scipy.signal.savgol_filter.html)：interp窗口不超过数据长度，polyorder小于窗口，delta为采样间隔。
