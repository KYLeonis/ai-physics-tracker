# ADR-0028 — 拟合参数的条件性标准误差

## Status

Accepted for implementation，2026-10-24。用户授权执行已冻结P6.4计划；Issue [#42](https://github.com/KYLeonis/ai-physics-tracker/issues/42)。实现及Gate见[计划](../status/phase-6.4-plan.md)。

## Context

现有拟合在无量纲参数与残差坐标求解。统计必须还原参数尺度，且不能改变求解成功语义。旧结果及尝试日志没有统计，不能重拟合历史补造记录。

## Decision

- 仅world_position / angular_position源支持SE；平滑及导数源自由参数记unsupported_source，固定参数仍记fixed。沿用相同实际样本、固定值及等权最小二乘。
- 用最终解处SciPy Jacobian（残差除以residual_scale，参数除以parameter_scales）及同尺度残差计算。n为实际样本数，p为自由参数数；SE来自SSE/(n-p)与局部Jacobian协方差。逐列先除最大绝对值及二范数，再SVD；恢复列尺度和原参数尺度。以范数 / 对数乘除避免极大 / 极小单位平方溢出或下溢，不直接求逆。
- 独立统计判据：n<=p为insufficient_dof；非有限输入 / 无法表示的SE为nonfinite；零列或最小/最大奇异值比<=eps*max(n,p)为rank_deficient；该比<=1e-5为ill_conditioned。列归一化使判据不因单位改变。既有求解器1e-7可辨识门不变，已拒绝拟合不发布统计。
- 自由参数任一active_mask非零，或距有限边界<=1e-7*max(1,abs(无量纲解))，则全部自由参数boundary_limited；局部无约束协方差不适用。全固定只记Fixed；n-p不用于固定参数。统计失败只影响统计，保留合法参数 / 预测 / RMSE。
- additive字段analysis.summary.parameter_uncertainty：version=1，method=local_jacobian_svd，sample_count / free_parameter_count / degrees_of_freedom为严格整数；parameters按spec顺序逐项保存name / status / standard_error / reason。estimated的SE必须有限且非负；其余为null和明确原因，固定不能记0。状态集合见实现；读取边界严格拒绝bool伪整数、非有限值、未知状态、固定状态矛盾及参数错配。
- 缺少字段显示Not recorded；未来版本 / 损坏统计只读披露，不展示数值且不能自动覆盖该槽。新结果发布核对摘要与outcome、样本 / 参数 / 来源。保存原样保留；重算保留v1未知扩展（含按名字匹配的参数扩展），不继承旧拥有的统计值。尝试日志沿原摘要通路记录；历史只读重建仅展示当时记录，不计算SE。
- GUI在记录视图显示Parameter / Estimate / Conditional standard error三列及可展开方法；stale明确为历史输入结果。草稿 / 预览 / 失败 / 切上下文清除统计。R09草稿事实、源版本及两个执行器不变。
- 说明独立同方差、零均值残差及局部线性假设；原始源不保证独立性。RMSE是残差尺度，重复间隔样本标准差是间隔离散，SE是条件性参数稳定性；比例尺、支点和时序系统误差未量化。换算结果只给数值，不传播SE。

## Verification contract

线性解析fixture：t=linspace(0,4,41)，y=2.5*t-0.7+固定seed噪声。独立闭式直线斜率 / 截距SE与实现相对误差<=2e-5；信号尺度1e-150 / 1 / 1e150及参数坐标缩放保持该相对容差，无噪声预测 / RMSE沿既有回归。另测固定 / 全固定、自由度、零列 / 共线、条件比1e-6、边界 / 内点、非有限 / 极端表示、不支持源、旧 / 未来 / 未知扩展、JSON往返 / Undo / 历史及GUI清除。

方法核对：[SciPy curve_fit](https://docs.scipy.org/doc/scipy/reference/generated/scipy.optimize.curve_fit.html)的残差方差与局部近似；[least_squares](https://docs.scipy.org/doc/scipy/reference/generated/scipy.optimize.least_squares.html)的Jacobian及active_mask。在线文档当前为1.18，项目仍使用锁定1.17.1，不升级依赖；实际API以本机版本为准。

## Consequences

无schema迁移或新依赖；可用SE不等于置信区间、完整测量不确定度或模型成立。保留旧求解拒绝语义，统计门更保守。6.5真实流程验收仍独立保留。
