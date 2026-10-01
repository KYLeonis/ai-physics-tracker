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

## R3 — 2026-10-01 · Windows CI 等价族 objective 回归复审

- 审查范围：`99d6d7a..2e8b5a9` 的 `tests/test_pendulum_identifiability.py` 单文件差异；按要求只读检查 `src/`、tests 其余部分与 golden。R1/R2 记录及其结论保留。

### Findings

#### F3 — 等价性断言改用更紧积分设置，未验证原 request 下的 objective

- **Severity**：P2（AC3 科学回归门槛）
- **Evidence**：`tests/test_pendulum_identifiability.py:162-164` 将两次 `evaluate_objective()` 从原 `request` 改为 `proof_request`，把积分容差从 `_request()` 的 `rtol=2e-10, atol=2e-12` 收紧到 `rtol=1e-12, atol=1e-14`。Windows 提供的原配置 costs 相差 `2.7512896285e-11`，超过该断言 `abs=1e-11, rel=1e-8` 的实际门槛 `1e-11`（pytest 采用 `max(abs, rel*abs(expected))`；此处相对门槛约 `7.07e-13`）；修改后的测试只证明更高精度配置下的相等性。局部复算显示 `lump_parameters(raw)` 与 `lump_parameters(transformed)` 的 `alpha2` 分别为 `0.03` 和 `0.030000000000000002`（一 ULP）；原配置下 DOP853 的自适应求解调用数也不同。提高积分精度令两次 cost 更接近，但没有验证实际 request 配置下这点差异是否在已接受的数值误差预算内。
- **Impact**：测试名仍称 actual objective invariant，但其等价性断言不再使用实际 fit request 的积分设置。后续 `build_identifiability_curve(request, ...)` 仍覆盖原配置的曲线流程，却没有替代两组等价 starred 参数在原配置下的 objective 比较。因此该改动保留了断言数值，却改变了它所约束的科学条件；这属于绕过 Windows 失败条件，未覆盖 ULP 舍入触发自适应步长差异这一根因。
- **Recommendation**：保留原 request 配置下的等价性检查。若评估后认定 Windows 差值属于可接受的求解误差，应在该回归中用明确的数值误差依据裁定门槛；更高精度的证明可以另加，不能替代原配置检查。
- **Decision**：Fix Before Close；保留原request检查，采用既有E4声明的轨迹≤1e−7rad、mean objective atol1e−9/rtol1e−4；原1e−11cost断言继续用于高精度数学证明，不修改产品profile或E4门槛。
- **Status**：Closed (R4)。
- **Fix commit**：`188bd47`；新增原request两组参数的轨迹/mean objective比较及curve fitted denominator与原请求计算一致性检查。
- **Verification**：5项identifiability tests通过（20.97s）；R4前未宣称该finding关闭。

### Verification

- `git diff --name-only 99d6d7a..2e8b5a9` 仅含 `tests/test_pendulum_identifiability.py`；`src/`、历史 profile 与 `publication/evidence/golden/` 均未变化。没有产品实现、profile 或 frozen golden 的隐式变更。
- `PYTHONPATH=src /Users/leonis/Documents/ai-physics-tracker/.venv/bin/python -m pytest -q tests/test_pendulum_identifiability.py::test_actual_objective_is_invariant_on_equivalent_starred_parameters_and_curve_surface_are_typed` → **1 passed**（5.30s）。
- 同一解释器下独立复算：原配置 cost 为 `7.066670112960101e-05` 与 `7.066670519170282e-05`，差 `4.0621018105e-12`；更紧配置差 `9.4059959474e-16`。本机运行未复现 Windows 的具体 cost，但任务提供的 Windows 数值按原 pytest 容差确实失败。
- 未运行全量测试；未修改 `src/`、golden 或测试实现。

### Final Verdict

- [ ] 通过
- [ ] 修改后通过
- [x] 需要修改后复审（F3 Open；R2 的 F1、F2 仍 Closed）

- **R3 Verdict：本次 Windows CI 测试配置改动不通过。** 历史 R2 对 P4.2 核心的 Approve 与 F1/F2 Closed 结论保持原样；本轮仅判定 `2e8b5a9` 的等价性测试替换不保留原 request 下的科学门槛。

## R4 — 2026-10-01 · F3 remediation review

- 审查范围：`99d6d7a..188bd47` 的 `tests/test_pendulum_identifiability.py` 差异；只读核对 domain 实现、AC2/AC3、platform-requirements §8.2 与 E4 合同。R1–R3 的发现和结论保留；R3 Evidence 中 pytest 容差数值按实际 `pytest.approx` 规则更正。
- **F3 复审结论**：关闭。`actual` 与 `equivalent` 两次 objective 仍传入原 `request`，其中积分配置为 `_request()` 的 `rtol=2e-10, atol=2e-12`。原配置下新增的轨迹断言使用 `abs=1e-7, rel=0`，mean objective 按 `2*cost/N` 计算并使用 E4 已声明的 `atol=1e-9, rtol=1e-4`；curve 的 fitted mean objective 还与 `actual_mean_cost` 直接核对。该修复没有提高 E4 容差，也未修改 `src/`、profile 或 frozen golden。高精度 `proof_request` 仍作为补充，原 `abs=1e-11, rel=1e-8` cost 数学断言保留。
- **判别力核对**：AC2 非等价对照未被改动；`omega0_sq` 从 `48` 改为 `49` 后，在同 IC/timeline 的独立 raw forward 上要求最大轨迹差 `>1e-3 rad`。它仍能区分非等价参数，不会被 E4 的等价误差预算吞掉。相同的等价变换 forward 与 objective 对照继续保留。

### Verification

- `git diff --name-only 99d6d7a..188bd47` → 仅 `tests/test_pendulum_identifiability.py`；本次修复未改领域实现、profile 或 golden。
- `PYTHONPATH=src /Users/leonis/Documents/ai-physics-tracker/.venv/bin/python -m pytest -q tests/test_pendulum_identifiability.py::test_actual_objective_is_invariant_on_equivalent_starred_parameters_and_curve_surface_are_typed` → **1 passed** in 5.44s。
- 非等价轨迹对照所在测试未被本次差异修改；按其断言静态核对，未重复运行该测试。

### R4 Final Verdict

- [x] 通过
- [ ] 修改后通过
- [ ] 需要修改后复审

- **R4 Verdict：Approve；F3 Closed。** 原 request 与积分配置下的实际 objective 已按既有 E4 预算核对；严格高精度数学断言及 AC2 非等价对照仍保留。R2 的 F1/F2 Closed 结论不变。
