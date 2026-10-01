# Independent Scientific Review — Publication P4.2 Identifiability core

- Subphase：P4.2 — Identifiability pure core
- 审查范围：`HEAD 877904f` 加当前未跟踪的 `src/ai_physics_tracker/domain/pendulum_identifiability.py` 与 `tests/test_pendulum_identifiability.py`；其他并行工作文件不在范围内。
- Context：[P4.2 mini-plan](../../publication/plans/p4.2-identifiability-core.md)、[platform requirements §8.2](../../publication/spec/platform-requirements.md)、[scientific profiles §5](../../publication/spec/scientific-profiles.md)、[E4 evidence contract](../../publication/evidence/README.md)。
- 轮次：R1 2026-10-01；R2 2026-10-01
- Reviewer：fresh-context 独立只读科学审查；未修改 `src/` 或 `tests/`。

## Findings

### F1 — direct node 可把旧曲线的分母用于不同 request

- **Severity**：P2（科学比较完整性）
- **Evidence**：`evaluate_surface_node_direct()` 在 `pendulum_identifiability.py:544-547` 把调用方提供的 `request` 与 `fitted_parameters` 交给 `evaluate_objective_at_q()`，但同时无条件传入 `curve.fitted_mean_objective_rad2`。`IdentifiabilityCurve` 没有保存 request/input 身份，函数也没有核对曲线里的 fitted q、starred damping 与当前参数是否相同。于是不同视频、IC、权重、loss 或 fit 参数的曲线可以作为当前 request 的归一化分母，仍返回 `status="success"` 的 ratio。现有测试只使用同一个 request/fit 构建曲线并直接复核，未覆盖错配输入。
- **Impact**：P4.3 若将迟到的旧曲线与当前输入组合，显示的 raw valley ratio 会用错误基准；节点自身 objective 虽按当前 request 计算，ratio 却不再是该 request 下相对 fitted objective 的量。
- **Recommendation**：给 curve 保存可核对的 request/fitted-parameter identity 并在 direct evaluator 拒绝错配；或从传入的 request 和 fitted parameters 重新计算归一化基准。增加不同 IC/weight/loss 或参数曲线误配的负向回归，要求拒绝或得到当前 request 的正确 ratio。
- **Decision**：Fix Before Close；此 core 进入 GUI 前需要保证 direct node 的比值与其所接收请求属于同一科学输入。
- **Status**：Closed (R2)
- **R2 Verification**：`IdentifiabilityCurve` 保存 `objective_request_digest` 与 fitted q / 两项 starred damping；direct evaluator 在复用 fitted 分母前比对这四项身份。digest 覆盖轨迹和时间数组、QC、权重、IC、区间、L/g、loss、sampling 与积分配置。回归分别以改权重、改 IC、改 fitted damping 的曲线错配断言拒绝；代码也显式校验 fitted q。

### F2 — direct-vs-interpolation 回归落在曲线端点，没有验证插值

- **Severity**：P2（AC3 验收缺口）
- **Evidence**：`tests/test_pendulum_identifiability.py:178-183` 选择 `alpha_a=0` 且 `omega0_sq=surface.omega0_sq_s_inv2_values[-1]`。此时 `q=1.16*q_fit`，正好等于 q curve 最后一个网格点；`build_identifiability_surface()` 在 `pendulum_identifiability.py:520-521` 命中 `interpolate_objective_at_q()` 的精确网格分支，而非 `np.interp` 分支。该断言验证 endpoint direct 值，不满足 mini-plan AC3 / E4 contract 要求的 direct objective 与插值 surface 节点比较。
- **Impact**：Frozen E4 全面核对归档曲面，能证明投影与 frozen expected 一致，但没有独立确认任一非网格 raw 坐标上的插值值接近实际 ODE objective；q 映射或插值实现偏差可能仍被归档 surface 对照沿用。
- **Recommendation**：选一个 `alpha_a>0` 的内部 surface 网格点，使其对应 q 不等于 curve 任一节点；用同一 request 直接计算该点，并按声明容差比较 objective ratio。保留现有 E4 golden 对照。
- **Decision**：Fix Before Close；AC3 明确要求 direct node 与插值结果核对。
- **Status**：Closed (R2)
- **R2 Verification**：新增 surface 内部点 `(row=50, column=74)`，断言其 q 不属于 curve 网格；同一 request 对该点做直接 ODE objective，并与 q 线性插值 ratio 比较（相对误差 ≤1e−4）。端点用例仍保留，frozen E4 golden 对照未变。

## Checked paths with no finding

- raw lumping 与 λ 变换符合 `s=1+αa>0` 的代数；`feasible_lambda_range()` 对 inertia、线性阻尼、二次阻尼和频率 bounds 取交集，拒绝空域；转换不逐项 clip。raw RHS 和 lumped RHS 分别由 ODE solver 积分。
- `IdentifiabilityState` 与 raw 参数是 frozen typed values，教学参考的 `illustrative=True` 明示其非测量结果。
- q scan 通过 `evaluate_objective()` 使用实际 request 的 sample indices、weights、loss、IC 与 integration settings；`2*cost/N` 与 P011 E4 frozen mean objective 一致。raw 坐标 surface 是固定 starred damping 的 q 曲线投影，未执行全参数 profile optimization。
- 零 fitted objective 的 direct node 返回 unavailable/`zero_fitted_objective`；objective 节点失败有 unavailable 状态；curve cancellation 会传播异常且不会返回部分曲线。raw/lumped等价与非等价轨迹对照、完整 P011 E4 raw overlap 均有覆盖。

## Verification

- `PYTHONPATH=src /Users/leonis/Documents/ai-physics-tracker/.venv/bin/python -m pytest -q tests/test_pendulum_identifiability.py` → **5 passed** in 37.42s。
- 未运行 full suite；本轮仅审查指定核心和定向回归。
- R2：`PYTHONPATH=src /Users/leonis/Documents/ai-physics-tracker/.venv/bin/python -m pytest -q tests/test_pendulum_identifiability.py` → **5 passed** in 38.80s。覆盖 off-grid direct-vs-interpolation、错配输入拒绝、零 fitted objective、取消传播及 frozen P011 E4。

## Final Verdict

- [x] 通过
- [ ] 修改后通过
- [ ] 需要修改后复审（F1、F2 Open）

- **R2 Verdict：Approve；F1、F2 Closed。** direct node 现在拒绝 request 或 fitted 参数身份不匹配的旧曲线；内部非网格节点的直接 objective 与插值 surface 已有明确回归比较。定向数值验证通过，未发现新增 finding。P4.2 独立科学复审通过，可进入 mini-plan 规定的后续 gate。
