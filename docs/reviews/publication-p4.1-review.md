# Independent Scientific Review — Publication P4.1 Model criticism

- Subphase：P4.1 — Model criticism evidence
- Review 范围：`877904f` + 当前工作树中的 `domain/pendulum_criticism.py`、`application/pendulum_fit.py`、`tests/test_pendulum_criticism.py`、`tests/test_pendulum_fit_job.py`；分支 `codex/ejp-p4-1-model-criticism`。
- 排除：P4.2 identifiability 文件及其他同时存在的工作树改动。
- Context：[`P4.1 plan`](../../publication/plans/p4.1-model-criticism.md)、[`platform requirements §8.1`](../../publication/spec/platform-requirements.md)、[`scientific profiles §4–5`](../../publication/spec/scientific-profiles.md)、[`evidence contract`](../../publication/evidence/README.md)、[`P3.3 review`](publication-p3.3-review.md)、[`P3.4 review`](publication-p3.4-review.md)、[`ADR-0020`](../decisions/0020-explicit-fit-precision-and-historical-regression-limit.md)。
- Reviewer：独立只读；只新增本 Review Record，未修改产品代码、测试或P4.2文件。

## Checklist

- [x] P3共同输入摘要、完整无权raw RMSE、收敛状态排名门禁有显式复核。
- [x] 相位交点按共同源段与方向分组；tail窗口从拟合区间末三分之一取样；能量耗散使用拟合状态且不重拟合。
- [x] 能量代理使用 `q=g/L`，拟合能量使用拟合 `q`；长度解释明确写出 `g/q` 不是实测质心长度。
- [x] 拟合身份能同时约束输入摘要与实际参数/预测；F1 已在 R2 关闭。
- [x] SG派生速度只在输出可验证地绑定到声明的同源输入/配置时参与分层和参考能量；F2、F3均已关闭。
- [x] 定向测试真实运行；结果见 Verification。
- [x] 审查范围内未见新增依赖、持久化schema变更或GUI交互。

## Findings

### F1 — 替换拟合输出后仍会被标为有效并参与M0/M1排名

- **Severity**：Blocker（不修复不能通过）
- **Evidence**：`src/ai_physics_tracker/domain/pendulum_criticism.py:219-232` 的 `_request_fit_problem` 仅从 request、model、config、bounds、starts 和 seed 重算 `input_digest`；该摘要不绑定 `fit.parameters`、`selected_start_index` 或 `trajectory`。后续 `_trajectory_problem` 只确认预测/残差彼此一致及RMSE算术一致，没有确认预测由该 `fit.parameters` 生成，也没有确认参数来自被选中的 optimizer start。现有 `tests/test_pendulum_criticism.py:88-96` 将 `m1.parameters` 和 `m1.trajectory` 替换为另一组参数的 forward 结果，但保留原 optimizer starts、成功状态与身份摘要；领域函数仍接受它。独立复现输出为 `fit_identity_status=valid`、`comparison.status=comparable`、RMSE改善 `-1803.0696%`。P3的无重优化读回校验已在 `domain/pendulum_fit.py:352-365` 校验参数、选中start、最终objective与trajectory；新增 `validated_fit_inputs` 通过 `_validate_payload` 复用该验证，但直接调用 `criticize_pendulum_fits` 不经过它。
- **Impact**：任何保留旧摘要/成功状态、但替换参数或预测的 typed fit，都可产出互相矛盾的参数、残差、phase、tail/energy证据，并被显示为可比较拟合。M0/M1结论可能不再代表已验证的优化结果，违反P4.1的共同输入与身份门禁。
- **Recommendation**：在领域入口加入与保存结果读回等价的无重优化输出验证：参数必须对应选中的start诊断，预测/残差/RMSE必须对应这些参数在当前request上的forward；任一输出不一致时将身份标记为无效并令依赖该fit的证据 unavailable。保留 `validated_fit_inputs` 对历史payload的现有复用路径，不运行 optimizer。
- **Decision**：Closed — 领域入口现在把 typed fit 交给 `validate_saved_fit` 做无优化读回复核；参数必须匹配所选 start，最终目标值及预测/残差/指标必须匹配当前 request 的 forward。
- **Fix commit**：当前工作树，尚未提交。
- **Verification**：替换参数、轨迹或 selected start 的负向回归通过；无优化器复核的回归通过。额外直接探针验证真实默认warm-start M1与M0均为 `valid` 且可比较；替换M0输出后M0标记invalid、依赖warm start的M1与比较均不可用；单独传入带隐藏warm来源的M1被保守拒绝。
- **Re-review**：R2 Closed。
- **Status**：Closed

### F2 — 未校验的 AngularAnalysis 导数仍可生成看似有效的科学证据

- **Severity**：Blocker（不修复不能通过）
- **Evidence**：`src/ai_physics_tracker/domain/pendulum_criticism.py:525-540` 的 `_angular_problem` 只校验 `source_series_digest`、数组长度及有限值/类型，没有验证 `input_digest` 是否对应当前 source/config，也没有验证 `omega_rad_s` 等输出是否由该输入计算得到。`_speed_evidence` 和 `_reference_energy_evidence` 随后直接消费这些值。独立探针用 `dataclasses.replace(angular, omega_rad_s=(0.0,) * n)` 保留原 `source_series_digest` 与 `input_digest`，`_angular_problem` 仍返回 `None`；同一序列的参考能量峰值因此从 `3.5473697045950763 s^-2` 变为 `3.096470580220532 s^-2`，并会被标成available。
- **Impact**：保留源摘要/输入摘要但替换SG速度的 typed analysis，可改变速度分层及 kinetic/reference total energy，而证据仍显示来自同一输入且可用。Fit输出已做同类读回验证；AngularAnalysis目前只有对象类型与摘要字段检查，未达到同等来源边界。
- **Recommendation**：只有当 AngularAnalysis 的 resolved derivative settings 与输出可被独立核对时，才消费其SG速度。可从当前 `request.series` 和明确配置重建/复核 AngularAnalysis，或由adapter提供并验证覆盖完整派生数组与配置的输出身份；摘要字符串本身不能证明数组值。
- **Decision**：Closed — `_angular_problem` 现在依据 `request.profile_id`、`request.end_frame_index` 和显式 SG 参数重新分析源序列，并比对完整 `AngularAnalysis` dataclass 与 `input_digest`；不再把摘要当作输出证明。
- **Fix commit**：当前工作树，尚未提交。
- **Verification**：R3定向测试中 forged-zero-omega 被标记 `angular_analysis_output_mismatch`；真实SG=1001短窗保留 raw residual 且将无可导数的辅助量标 unavailable；显式5/2分析仅在critic同样显式收到5/2时通过配置门禁。`None`仍只令辅助证据 unavailable，不阻断raw residual。
- **Re-review**：R3 Closed；同一输入配置/派生输出已独立复核。
- **Status**：Closed

### F3 — legacy 截断fit区间使辅助验证抛异常并中断全部批判结果

- **Severity**：Blocker（不修复不能通过）
- **Evidence**：`ObjectiveRequest`允许`profile_id=LEGACY`且`end_frame_index`早于完整`series`末帧。构造20帧完整LEGACY序列、合法archived-TOML初态与`end_frame_index=10`，再用完整序列生成有效LEGACY `AngularAnalysis`；调用`_angular_problem(request, angular, 9, 3)`复现`ValueError: legacy reproduction requires the complete post-release series`。原因是F2复核无条件调用`analyze_angular_series(... end_frame_index=request.end_frame_index)`，而LEGACY analyzer明确拒绝不完整post-release区间。`criticize_pendulum_fits`在生成残差前调用此检查，因此异常会连同独立可计算的raw residual一起中断。
- **Impact**：合法的LEGACY请求配有全序列派生分析时，批判入口可能抛出而非将不适用于该request范围的辅助证据标成unavailable；这违反辅助证据不足时不阻断其它诊断的边界。
- **Recommendation**：将LEGACY不支持该request end的情况映射为明确的angular unavailable原因，保证raw residual与其它fit证据继续生成；不要把异常当作有效派生数据。
- **Decision**：Closed — LEGACY不支持的重分析映射为 `angular_analysis_configuration_mismatch`，不再抛异常，raw fit诊断继续生成。
- **Fix commit**：当前工作树，尚未提交。
- **Verification**：独立公开路径探针构造合法archived-TOML初态、截断LEGACY request、成功M0 fit与完整LEGACY analysis，得到 `angular_analysis_configuration_mismatch`、`raw_rmse_status=available`、`fit_identity_status=valid`。修正后的 `test_unsupported_auxiliary_interval_keeps_raw_diagnostics` → **1 passed** in 8.63s。
- **Re-review**：R5 Closed。
- **Status**：Closed

## Checked paths with no finding

- `compare_fits` 仍是公开M0/M1比较语义来源；不同 objective/comparability digest 与非成功拟合不能排名。raw residual 和完整RMSE从全量有效拟合帧计算，未使用SG预测或仅用optimizer样本点替代。
- phase计算保留源frame/time及同方向；`valid_segments` 断开非连续源帧与QC缺口，匹配只在相同源段内进行。SG缺失或来源摘要不匹配时，raw residual仍可用。
- tail诊断限定到 `ObjectiveRequest.start_frame_index…end_frame_index`，采用该区间最后三分之一与至少10个完整周期；周期算法保留每周期 `q_i` 后取算术均值。
- 参考能量proxy以物理 `g/L` 构造，单位 `s^-2`；模型能量耗散检查以拟合参数及ODE预测状态构造并明确不是观测能量吻合度。`g/q` 已限定为表观动力学长度。
- `validated_fit_inputs` 复用 `_validate_payload` / `validate_saved_fit` 的身份与forward校验，没有调用optimizer；P4.1领域入口也复用 `validate_saved_fit` 守住 typed-fit 一致性。`_angular_problem` 已按同源输入与声明配置重算并验证AngularAnalysis全量输出，见已关闭的F2；LEGACY截断区间异常单列F3。
- `_angular_problem` 核对AngularAnalysis来源序列摘要与数组形状，并在可重分析范围内逐字段核对profile、配置及所有派生输出；能量proxy保留其profile ID和input digest。LEGACY完整序列可复核，截断request目前会抛异常，见F3。

## Verification

- `PYTHONPATH=src /Users/leonis/Documents/ai-physics-tracker/.venv/bin/python -m pytest tests/test_pendulum_criticism.py tests/test_pendulum_fit_job.py` → **16 passed** in 25.43s。
- R2独立定向测试：`PYTHONPATH=src /Users/leonis/Documents/ai-physics-tracker/.venv/bin/python -m pytest tests/test_pendulum_criticism.py tests/test_pendulum_fit_job.py` → **17 passed** in 32.58s。
- F1回归与实际warm-start探针：参数/trajectory/selected-start替换被拒；真实M0→M1默认warm path可读回并比较；invalid M0会使依赖warm的M1不可用，nonconverged不排名，单独提交隐藏warm来源的M1不可用。
- F2独立输出替换探针：保留 `AngularAnalysis.source_series_digest` 和 `input_digest`，替换全部SG速度为零，仍通过 `_angular_problem`，且参考能量结果发生变化。
- R3定向验证：`PYTHONPATH=src /Users/leonis/Documents/ai-physics-tracker/.venv/bin/python -m pytest tests/test_pendulum_criticism.py tests/test_angular_analysis.py tests/test_pendulum_fit_job.py` → **49 passed** in 38.77s。另以20帧合法LEGACY序列与截断end=10直接探测`_angular_problem`，复现上述ValueError。
- R4修复复核：直接调用 `criticize_pendulum_fits` 的合法LEGACY/M0公共路径探针确认aux unavailable且raw RMSE可用；新增回归用例当时因LEGACY IC构造错误而未运行断言。
- R5复审：修正后的 `PYTHONPATH=src /Users/leonis/Documents/ai-physics-tracker/.venv/bin/python -m pytest -q tests/test_pendulum_criticism.py::test_unsupported_auxiliary_interval_keeps_raw_diagnostics` → **1 passed** in 8.63s；关闭F3。R3的其余49项未重跑。
- 未重跑全量测试、48项历史refit、冻结资产校验；本轮没有触及其数值资产。

## Review Log

### R1 — 2026-10-01 · 首轮

- 范围 / 基线：`877904f` + 指定P4.1工作树改动；P4.2文件排除。
- 结论：**Request changes**；发现一个会让被替换的拟合输出通过身份校验并参与比较的阻断finding。
- Findings变化：新增F1；关闭 —

### R2 — 2026-10-01 · 修复后复审

- 范围 / 基线：当前工作树中的指定P4.1领域函数、fit应用输入adapter与对应测试；P4.2/P4.3文件排除。
- 结论：**Request changes**；F1已关闭，但独立检查发现同源摘要不能验证SG派生速度值，新增F2。
- Findings变化：F1 Closed；新增F2 Open；关闭 —

### R3 — 2026-10-01 · F2 修复复审

- 范围 / 基线：当前工作树中的P4.1 criticism、angular analysis与fit adapter定向行为；未检查/修改GUI；P4.2/P4.3文件排除。
- 结论：**Request changes**；F2关闭。额外检查LEGACY profile边界时发现截断fit end导致`_angular_problem`异常并中断批判结果，新增F3。
- Findings变化：F2 Closed；新增F3 Open；关闭 —

### R4 — 2026-10-01 · F3 修复复审

- 范围 / 基线：当前工作树中的 `_angular_problem` 异常映射及新增LEGACY公共路径回归用例；未修改产品代码或测试。
- 结论：**Request changes**；独立公共路径探针确认修复行为，但新增pytest在合法性检查前因测试构造遗漏archived-TOML IC而失败，无法据该回归关闭F3。
- Findings变化：F3仍 Open；关闭 —

### R5 — 2026-10-01 · F3 回归复核

- 范围 / 基线：已修正的 `test_unsupported_auxiliary_interval_keeps_raw_diagnostics` 与对应 `_angular_problem` 修复。
- 结论：**Approve**；合法LEGACY request、成功M0 fit与完整序列AngularAnalysis路径通过；不支持的辅助区间标记unavailable，raw RMSE继续可用。
- Findings变化：F3 Closed；无开放Blocker。

## Final Verdict

- [x] 通过（无未处置Blocker）
- [ ] 修改后通过（findings按Decision处置完毕，复审确认）
- [ ] 需要重做（F3仍开放）

- 最终结论（一句话）：F1、F2、F3均已关闭；合法LEGACY截断区间无法提供角速度辅助证据时，critic返回具体unavailable原因且保留有效raw residual。
- 日期 / 依据轮次：2026-10-01 / R5
