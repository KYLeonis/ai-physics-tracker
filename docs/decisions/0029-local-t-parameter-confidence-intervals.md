# ADR-0029 — 参数的95%双侧局部t置信区间

## Status

Accepted for implementation，2026-10-24。用户在P6.4 HR后明确要求新增置信区间，并选择“采用上述95%局部t区间”。仅替代ADR-0028的“不提供置信区间”、三列表格与统计对象v1写入条款；其SE算法 / 科学拒绝 / 原子生命周期条款继续有效。见[计划v1.1](../status/phase-6.4-plan.md)。

## Context

现有SE不是具体区间。用户需要在拟合参数旁直接看到上下限；不扩展到平滑 / 导数源、换算量传播或预测带，也不重拟合历史。

## Decision

- 固定95%双侧、逐参数局部区间：estimate ± t.ppf(0.975, n-p) × SE；n为实际样本数，p为自由参数数。使用已有SciPy 1.17.1，不新增依赖或可调置信水平。
- 零均值、独立同方差假设保留，新增残差近似正态假设。线性正态误差模型下为通常的t区间，非线性模型仅是最终解附近局部近似；不称联合95%覆盖、不称95%概率真值在当前区间内，不代表完整实验不确定度。
- 仅未平滑world_position / angular_position源。Fixed不估计，平滑 / 导数或SE不可估计则无区间，明确原因。区间端点非有限、非零SE的宽度小于浮点可表示范围，或对称区间触及 / 跨越参数边界时不给区间；不截断到边界，不因此删除合法SE / 参数 / 预测 / RMSE。SE为精确零时可记录退化区间，不解释为没有系统误差。
- 仍用analysis.summary.parameter_uncertainty，**新写入version=2**；method继续local_jacobian_svd，增加confidence_level=0.95与interval_method=local_student_t。每个parameters条目增加confidence_interval（两个原参数尺度的有限上下限或null）和interval_reason（有效时空串，否则具体原因）。SE status / standard_error / reason不变。
- 读取器支持v1 / v2；v1只读SE，CI显示Not recorded，绝不从旧SE补造区间。未知未来版本、损坏字段 / 端点、选择 / 快照冲突仍只读拒绝，不自动覆盖。v2须严格检查置信水平 / 方法、估计值 / SE / 自由度与已记录区间的一致性；校验可以重算预期端点，不向历史写入缺失区间。新结果保存 / Undo / 尝试摘要沿原通路，同版本及v1→v2重算保留未知扩展，旧拥有字段不泄漏。
- 参数表改为Parameter / Estimate / Conditional standard error / 95% confidence interval (local)四列，区间显示[lower, upper]；极窄区间提高显示精度避免上下限显示成同一个数。方法详情披露公式、正态 / 独立 / 局部假设，原始源支持提示明确。草稿清除同SE，不新增执行器 / 上下文键。
- 用户换算结果仍只给数值，重复间隔统计不变；Bootstrap / profile likelihood / 同时置信区间 / 系统误差与误差传播继续后置。P6.5不在本轮。

## Verification

原解析直线SE fixture基础上，用独立常数t(0.975,39)=2.022690920036761验证上下限 / 原尺度恢复（相对半宽容差2e-5，1e±150与原参数坐标缩放）；小样本自由度2用4.302652729749464验证不能硬编码1.96。另测Fixed / 全固定、已有不可估计源、边界交叠、不截断、非有限 / 极窄浮点范围、旧v1 / 缺统计 / 未来版本、未知扩展、保存 / Undo / 历史不回填及GUI四列 / 清除 / 横向可达。新增科学契约必须全新独立审查、定向 / 全量、双平台CI及新HR，旧R2结论不自动覆盖。

方法依据：[SciPy t.ppf](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.t.html)、[局部协方差局限](https://docs.scipy.org/doc/scipy/reference/generated/scipy.optimize.curve_fit.html)、[NIST非线性拟合](https://www.itl.nist.gov/div898/software/dataplot/refman1/auxillar/fit.htm)。

## Consequences

Project schema仍为v1，无迁移；已有SE-only结果可读且不会自动补算，旧应用把嵌套统计v2当未来版本保护。追加区间失败仅影响区间展示，不改变既有拟合 / SE成功语义。置信区间只表达已声明假设下的参数不确定程度。
