# Independent Review — Publication P3.2 bounded multistart fit

- Subphase / Issue：P3.2 — Bounded multistart fit
- Review 范围（commits / 分支 / 文件）：提交 `fef9c4c..23950c8`、分支 `codex/ejp-p3-2-multistart-fit`；`domain/pendulum_fit.py`、`domain/pendulum_fit_seed.py`、`tests/test_pendulum_fit.py`、`scripts/publication_fit_regression.py`。同时复核当前工作树中针对逐 start Jacobian 失败和 regression identity/protection 的未提交补丁及其报告。
- Context（spec / ADR / plan 路径）：[P3.2 mini-plan](../../publication/plans/p3.2-bounded-multistart-fit.md)；[P3.1 review](publication-p3.1-review.md)；[scientific-profiles §3–6/8–9](../../publication/spec/scientific-profiles.md)；[platform-requirements §7–8](../../publication/spec/platform-requirements.md)；[evidence README E2/E3](../../publication/evidence/README.md)；`publication/evidence/source-map.json`；`CODE_STANDARD.md` §8–9。
- 轮次：R1 2026-10-01（首轮）
- Reviewer：fresh-context 独立只读科学审查；未修改 `src/`、`tests/`、冻结 evidence 或外部科研资产。

## Checklist

**正确性**

- [ ] 实现与 P3.2 AC / 相关科学契约完全一致：AC7 的 E3 门禁未通过，AC1 的冻结默认 M1 合成恢复也未通过（见 F1/F2）。
- [x] 源公式、单位、IC、源时间、QC mask、500 点选样、权重、bounds、DOP853 和 least-squares 配置与封存 source 逐项核对；M0 24/24 E3 通过，说明共同输入与 M0 路径一致。
- [x] 失败/nonconverged、最终 forward 失败、逐 start diagnostics、comparison digest、边界与 Jacobian diagnostics 有实现和回归覆盖；当前补丁还增加了非有限 Jacobian 失败归档。
- [x] source map 指定的 fitting ZIP 和 M0/M1 源已按 SHA 核验；没有 import/execute 外部旧科研脚本。

**质量**

- [x] diff 的产品改动限定在 P3.2 core/tests/regression runner；本 Review 未修改上述文件。
- [x] 公开接口、参数单位、失败状态和 provenance 有说明；路径使用 `Path`，报告使用 UTF-8 与原子替换。
- [x] `tests/test_pendulum_fit.py` 定向测试通过；测试覆盖 synthetic、seed/gap、warm start、failure、cancellation、comparison、边界和回归输入 hash。
- [ ] 冻结 regression gate 全部通过：E2 为 47/48，E3 M0 为 24/24，E3 M1 为 6/24。

**流程**

- [x] 提交信息符合 Conventional Commits：`feat: add bounded multistart pendulum fitting and regression runner`。
- [x] 本轮未发现需要新增 ADR 的代码选型；数值策略/验收标准若要改变，必须先取得用户裁定并记录。

## Findings

### F1 — AC7 E3 历史重拟合门禁未通过，不能以“完成覆盖”关闭 P3.2

- **Severity**：Blocker
- **Evidence**：`publication/evidence/regression/p3.2-legacy-refit-2026-10-01.json`：`completed_fit_count=48`、`errors={}`、`identity_checks` 全部通过，但 `e3_pass_count=30`；其中 M0 为 24/24，M1 仅 6/24。18 个 M1 组合的参数、cost 或 RMSE 超出 `publication/evidence/README.md` E3 冻结容差。E2 为 47/48，P026 M1 的最大 prediction 差为 `1.5211911513e-5 rad`，超过 `1e-5`；RMSE 差在限内不能替代完整 E2 通过。
- **Impact**：P3.2 mini-plan AC7 明确要求 24×2 E3 报告、E2 通过；当前报告证明了 48 行覆盖和诊断完整性，但没有证明历史 fit 数值回归通过。根据 Review Gate，不能批准进入 P3.3，也不能把 `complete=true`（覆盖完成）解释为科学验收通过。
- **Recommendation**：保留 golden/profile/容差不变。优先在历史 run 报告的 Windows 11 + Python 3.13.0 + NumPy 2.4.3 + SciPy 1.17.1 环境复跑，以区分环境重现性与实现差异；若仍失败，再由用户裁定是否保留该历史差异并版本化数值策略/验收标准。不要用当前结果覆盖 expected，也不要以放宽容差代替诊断。
- **Decision**：Fix Before Close —— AC7 是 P3.2 硬门禁，必须有用户裁定和可审查的后续证据后才能收口。
- **Fix commit**：N/A（当前审查不修改实现）
- **Verification**：`PYTHONPATH=src /Users/leonis/Documents/ai-physics-tracker/.venv/bin/python -m pytest -q tests/test_pendulum_ode.py tests/test_pendulum_fit.py` → 52 passed；全量验证记录为 1304 passed / 9 subtests；48 行报告覆盖完整但 E3 gate 退出码为 1。
- **Re-review**：N/A；待 exact-environment refit 或用户裁定后复审。
- **Status**：Open

### F2 — 冻结默认积分配置下，无噪声 M1 synthetic recovery 仍会“成功”但恢复错误参数

- **Severity**：Major
- **Evidence**：按 `tests/test_pendulum_fit.py::_request` 构造 M1 无噪声数据，真值为 `(alpha1, alpha2, omega2)=(0.03, 0.02, 40.0)`，使用冻结默认 `IntegrationSettings(2e-7, 2e-9)` 和默认三起点，结果为 `status=success`，但选择参数约 `(0.0608008951, 0.0103457541, 40.0785737184)`、cost `0.0129626458`、full RMSE `0.0136212671 rad`。同一请求在真值处评价 cost 为 0。提交中的 synthetic recovery 测试改用显式 `IntegrationSettings(2e-10, 2e-12)`，因此该测试不能证明冻结默认 profile 的 AC1。
- **Impact**：结果的 optimizer success 状态可能掩盖可识别的无噪声真值没有恢复；这削弱 AC1 的科学保证，也与 P3.2 计划要求的“无噪声 M0/M1 参数恢复”不完全相符。高精度设置能恢复真值，但它不是当前 legacy 默认配置，不能悄悄替换 profile。
- **Recommendation**：保留冻结默认值并把默认 profile synthetic case 纳入明确门禁；由用户决定是否接受“默认容差下的数值敏感性”作为限制，或另立 ADR/版本化稳定 Jacobian/求解策略。任何高精度诊断结果只能作为数值敏感性证据，不可冒充默认 fit 或历史回归结果。
- **Decision**：Fix Before Close —— 需在 P3.2 收尾前记录 AC1 的正式裁定和可复查证据；不要求本轮 reviewer 修改 frozen profile。
- **Fix commit**：N/A
- **Verification**：显式高精度 synthetic test 通过；默认配置 probe 复现上述偏差。当前高精度 P011 控制亦显示 cost `0.055797715923`，而默认 current-M0 warm 为 `0.392648897993`，支持 solver tolerance 与 finite-difference coupling 的解释。
- **Re-review**：N/A；待 AC1 裁定/策略证据后复审。
- **Status**：Open

## Numerical source-parity conclusion

本轮没有发现把 M1 参数顺序、sinθ 方程、时间压缩、mask、weight、bounds 或 warm-start 公式写错的实现证据：

- `/tmp/p3-source-source-fitting.py`、`/tmp/p3-source-source-m0_linear.py`、`/tmp/p3-source-source-m1_linear_quadratic.py` 的 SHA 分别匹配 `source-map.json` 的 fitting ZIP、M0、M1 封存值。
- 当前实现的 DOP853 `rtol=2e-7/atol=2e-9`、500 valid samples、sqrt(weight) soft-L1、`trf`/`2-point`/`x_scale=jac`/`max_nfev=180`、M0 三起点及 M1 warm start 与 source/profile 一致。P011 的源时间与历史 `arange/fps` 逐位一致；24 个 M0 E3 全通过。
- M1 偏差是数值敏感性而非已证实的公式或输入 bug：P011 同一当前输入下，当前 M0 warm 的 M1 cost 为 `0.392648897993`，仅替换归档 M0 warm 为 `0.404818549161`，两者都不复现归档 `0.348499402872`；显式高精度积分得到 `0.055797715923`。当前局部点的 2-point Jacobian 在步长 `h` 与 `h/2` 间对 α₁/α₂/q 的相对差约 `19.6%/53.2%/30.5%`，高精度积分时降至 `3.2%/1.7%/2.4%`。
- 历史 run 报告为 Windows 11/Python 3.13.0/NumPy 2.4.3/SciPy 1.17.1，本机为 macOS/Python 3.12.13/NumPy 1.26.4/SciPy 1.17.1；source-map 明确没有完整 lock。因此，当前证据支持“默认 adaptive integration tolerance 与 finite-difference Jacobian 噪声耦合，并叠加运行时差异”的解释，但不足以声称跨环境 bitwise 等价，也不足以让 E3 失败自动合格。

## Review Log

### R1 — 2026-10-01 · 首轮

- 范围 / 基线：`fef9c4c..23950c8` 与当前未提交的 per-start diagnostic/report hardening；P3.2 core、seed、regression runner、17 项定向测试及 48 行报告。
- 结论：**Request changes**；发现 F1 Blocker（AC7 未通过）和 F2 Major（默认 profile AC1 未被满足）。源 parity 基本成立；剩余问题是硬门禁与数值稳定性/环境可复现性，不能以 M0 通过或高精度控制替代。
- Findings 变化：新增 F1、F2；关闭 —

## Final Verdict

- [ ] 通过（无未处置 Blocker）
- [ ] 修改后通过（findings 按 Decision 处置完毕，复审确认）
- [x] 需要重做（F1/F2 Open；E3/AC7 未通过）

- 最终结论（一句话）：实现的 source parity、失败诊断和 48 行覆盖基本成立，但冻结 E3 仅 30/48 通过、E2 47/48，且默认容差下 M1 synthetic recovery 仍错误；按“不能批准未满足 AC7”规则，P3.2 **Request Changes**，不得进入 P3.3。
- 日期 / 依据轮次：2026-10-01 / R1


## Implementer checkpoint after R1

- 未关闭F1/F2，也未改R1结论。已请求用户科学门禁裁定；回复前不集成/进入P3.3。
- 默认M1恢复现在有明确strict xfail门禁test（F2 Open）；不把高精度测试冒称默认通过。定向ODE+fit最终54 passed / 1 xfailed，24.63s。
- 逐start非有限Jacobian失败和report source-map保护两项新增回归通过；报告补齐48项identity和归档nfev/rank/condition，无需重复optimizer。
- 全量1304 tests/9subtests在上述小型补丁前通过；后续只扩大到改动对应定向集。最终frozen verifier/diff check通过。P3.2仍为Request Changes checkpoint。


## Re-review R2 — 2026-10-01 · Accepted Limitation

- **Reviewer / mode**：fresh-context 独立只读复审；仅追加本 Review Record，未修改产品代码、测试、回归报告、冻结 evidence 或外部科研资产。
- **范围 / 基线**：分支 `codex/ejp-p3-2-multistart-fit`；P3.2 base `fef9c4c`；实现及证据硬化 `23950c8..16af211`；用户裁定与修订 AC 记录 `e6266b3`；复核 `ADR-0020`、P3.2 mini-plan 的 revised AC1/AC7、R1 F1/F2。

### R2 verification

- 冻结回归报告仍诚实保留失败：48 行、`errors={}`、identity checks 全通过，E2 `47/48`，E3 `30/48`（M0 `24/24`、M1 `6/24`）；P026 M1 的 E2 最大 prediction 差仍为 `1.5211911513e-5 rad`，超过 `1e-5`。报告中的 `complete=true` 仅表示请求覆盖完整且无运行错误，不表示 E2/E3 科学门禁通过；脚本仍在任一 E2/E3 失败时返回退出码 1。
- 冻结默认 M1 synthetic recovery 的严格门禁仍是有意的 xfail：`PYTHONPATH=src /Users/leonis/Documents/ai-physics-tracker/.venv/bin/python -m pytest -q tests/test_pendulum_ode.py tests/test_pendulum_fit.py` → **54 passed, 1 xfailed**；未把 xfail 计为通过。
- `16af211` 的硬化保持边界清晰：非有限 Jacobian 归档为 failed start；regression runner 增加 identity/source-map 输出保护并保留逐 start/归档诊断；未覆盖或重写失败数值。`source-map`、`golden` 和 `publication/profiles` 相对 P3.2 base 均未改变。
- 本轮未发现新的 actionable bug、证据伪造或 frozen mutation。

### Finding dispositions

#### F1 — AC7 历史 E2/E3 数值门禁未通过

- **Decision**：按 `ADR-0020` 记为 **Accepted Limitation**；用户在查看上述失败证据后明确授权：“没有问题，继续P3.3/P3.4”。
- **Re-review**：用户授权关闭处置门，而非把失败改成通过。E2 仍 `47/48`、E3 仍 `30/48`；golden、profile 与容差保持冻结，Windows 精确历史环境复跑仍是后续平台门禁任务。
- **Status**：**Closed by user-authorized disposition; numerical gate remains failed**。

#### F2 — 冻结默认积分配置下 M1 synthetic recovery 缺口

- **Decision**：按 `ADR-0020` 记为 **Accepted Limitation**；显式高精度 `rtol=2e-10/atol=2e-12` 的 synthetic recovery 作为修订 AC1 证据，冻结默认配置的严格 xfail 保留。
- **Re-review**：optimizer success、显式高精度结果或历史回归覆盖均未被解释为默认 profile 数值正确；产品设置须继续明示 precision 与实际 resolved values。
- **Status**：**Closed by user-authorized disposition; default-profile recovery remains unproven**。

## R2 verdict

- 原始 P3.2 数值 AC1/AC7 **未通过**：本复审不声称默认 M1 recovery 或 48/48 E2/E3 通过。
- 按用户批准、并已记录于 `ADR-0020` 与 revised mini-plan AC1/AC7 的处置口径，P3.2 获得 **Conditional Approve to proceed to P3.3/P3.4**：继续工作以接受限制为前提，保持失败证据、冻结资产和显式高精度选择可追溯。
- P3.2 AC8 的集成、最终文档同步与 push 仍待实现方完成；这不改变本 R2 对 P3.3/P3.4 的条件性放行结论。
- 日期 / 依据轮次：2026-10-01 / R2
