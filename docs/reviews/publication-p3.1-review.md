# Independent Review — Publication P3.1 Forward and objective

- Subphase / Issue：P3.1 — Forward and objective
- Review 范围（commits / 分支 / 文件）：`970bd95..7d8ee0b`，分支 `codex/ejp-p3-1-forward-objective`；`pendulum_ode.py`、`test_pendulum_ode.py`、P3.1 mini-plan 与 publication status 同步。
- Context（spec / ADR / plan 路径）：[P3.1 mini-plan](../../publication/plans/p3.1-forward-objective.md)；[scientific-profiles §2–4/6/8–9](../../publication/spec/scientific-profiles.md)；[platform-requirements §7](../../publication/spec/platform-requirements.md)；[evidence README E2](../../publication/evidence/README.md)；`CODE_STANDARD.md` §8–9。
- 轮次：R1 2026-10-01（首轮）
- Reviewer：fresh-context 独立只读审查；未修改 `src/`、`tests/` 或产品数据。

## Checklist

**正确性**

- [ ] 实现与 subphase plan 的 AC / 相关 spec 完全一致（F1–F3）
- [ ] 边界情况处理正确（正常输入、缺测、gap、零/非均匀时刻通过；F1–F3 为请求/失败边界缺口）
- [x] 数值逻辑有合成数据验证：α₂=0 线性极限、非零 ω₀、能量恒等式、耗散、采样与 soft-L1。

**质量**

- [x] diff 无范围外产品改动；改动限定为 P3.1 core/tests 与计划/status。
- [x] 代码未引入新的路径/编码/平台依赖问题。
- [x] 公开接口和领域对象有说明，命名与附近代码一致。
- [ ] 测试覆盖全部输入/失败边界（未覆盖缺失 release、错误 IC 类型、solver `RuntimeError`）。

**流程**

- [x] 提交信息符合 Conventional Commits：`feat: add publication pendulum ODE forward and objective core`。
- [x] 本轮未发现需要新增 ADR 的技术选型。

## Findings

### F1 — 请求允许 release frame 不存在于 source series

- **Severity**：Blocker
- **Evidence**：`src/ai_physics_tracker/domain/pendulum_ode.py:207-214` 只校验 `end_frame_index` 属于 `series.frame_indices`，没有校验 `release_frame_index` 属于该序列；随后仅按 frame ID 与相对时间符号校验。可复现探针从合法 0–100 序列移除 frame 50、保留其余相对时间并构造 `release_frame_index=50`：构造成功，输出 `missing_release_in_series True`、`request_constructed 50 100`。
- **Impact**：P3 请求可以把 t=0 放在没有源观测/源时间的帧上，违反 platform-requirements §4.2 的“选择有效释放帧 r”与 scientific-profiles §2 的 release-relative 身份语义；后续选样、`N_interval` 和 fit eligibility 会基于一个未存在的 release frame 计算。
- **Recommendation**：在 `ObjectiveRequest.__post_init__` fail-closed 要求 `release_frame_index in series.frame_indices`，并保留已有的 release 行时间为 0 检查；增加缺失 release 的回归测试。
- **Decision**：Fix Now — 收敛已复现的输入/失败边界，增加对应回归。
- **Fix commit**：N/A
- **Verification**：修复后core tests 35 passed；缺失source release拒绝、缺失release观测但source存在允许。
- **Re-review**：N/A
- **Status**：Open

### F2 — 错误 IC 类型在请求构造边界泄漏 `AttributeError`

- **Severity**：Blocker
- **Evidence**：`ObjectiveRequest.__post_init__` 在访问 `self.initial_condition.source` 前没有 `isinstance(self.initial_condition, InitialCondition)` 检查（`pendulum_ode.py:220-231`）。`replace(_request(), initial_condition=None)` 实际抛出 `AttributeError: 'NoneType' object has no attribute 'source'`，不是契约要求的结构化 `ValueError`。
- **Impact**：无效请求没有在 Qt-free 输入边界被拒绝；应用/worker 可将类型错误当作未分类异常，不能按“needs explicit IC / invalid request”安全呈现或记录。该边界属于 CODE_STANDARD §8 和 scientific-profiles §6 的请求构造校验。
- **Recommendation**：构造期先验证 `InitialCondition`（同时对 `AngularSeries`、`IntegrationSettings` 等协作者保持同样的类型边界），以 `ValueError` 点名字段；补充错误类型回归。
- **Decision**：Fix Now — 收敛已复现的输入/失败边界，增加对应回归。
- **Fix commit**：N/A
- **Verification**：修复后core tests 35 passed；缺失source release拒绝、缺失release观测但source存在允许。
- **Re-review**：N/A
- **Status**：Open

### F3 — solver `RuntimeError` 未转为结构化 forward failure

- **Severity**：Blocker
- **Evidence**：`simulate_pendulum`（`pendulum_ode.py:170-183`）只捕获 `FloatingPointError`、`OverflowError`、`ValueError`。将模块的 `solve_ivp` 替换为抛出 `RuntimeError("synthetic solver crash")` 后，`evaluate_objective(...)` 直接向外抛出 `RuntimeError`，没有 `ForwardResult(status="failed", reason=...)`。
- **Impact**：积分器异常可越过 objective/后台调用边界，令一次候选评估中断整个 fit 流程；与 P3.1 AC2、platform-requirements §7.1 的“integration failure 独立状态、不能冒充成功”不一致。
- **Recommendation**：在 solver 调用边界把预期数值求解异常（至少 `RuntimeError`，并保留原始消息）转换为结构化 failed result；增加 objective 与 full-trajectory 两条回归，确认 `cost_rad2 is None` 且失败状态保留。
- **Decision**：Fix Now — 收敛已复现的输入/失败边界，增加对应回归。
- **Fix commit**：N/A
- **Verification**：首轮已复现；正常 SciPy 失败返回、非有限 prediction guard 与 1000 penalty 已由现有测试通过。
- **Re-review**：N/A
- **Status**：Open

## 实际验证

- `PYTHONPATH=src /Users/leonis/Documents/ai-physics-tracker/.venv/bin/python -m pytest tests/test_pendulum_ode.py -q` → **30 passed**。
- `python3 scripts/verify_publication_evidence.py` → `local_files=15, formal_fit_rows=48, offline_trajectory_cases=2, external_sources=0`。
- `git diff --check 970bd95..7d8ee0b` → 通过。
- 独立探针确认：M0/M1 α₂=0、非均匀真实时刻、gap 连续积分、前 5 帧 IC、50/ceil/3Tref 门槛、ties-to-even 选样、权重与全帧 RMSE 分离、E2 P011/P014 两模型均通过；F1–F3 的负例如上。

## Review Log

### R1 — 2026-10-01 · 首轮

- 范围 / 基线：`970bd95..7d8ee0b`，P3.1 forward/objective core 与相关测试。
- 结论：**Request changes**；发现 3 个 Blocker，未宣布通过。
- Findings 变化：新增 F1、F2、F3；关闭 —

## Final Verdict（收口时填写）

- [ ] 通过（无未处置 Blocker）
- [ ] 修改后通过（findings 按 Decision 处置完毕，复审确认）
- [ ] 需要重做（说明理由）

- 最终结论（一句话）：R1 发现三个请求/失败边界 blocker；修复并由新的独立会话复审通过后才能收口。
- 日期 / 依据轮次：2026-10-01 / R1
