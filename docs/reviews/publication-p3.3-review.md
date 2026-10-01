# Independent Review — Publication P3.3 Fit execution and persistence

- Subphase / Issue：P3.3 — Fit execution and persistence
- Review 范围（commits / 分支 / 文件）：`cdeb65d..d686ae8`，分支 `codex/ejp-p3-3-fit-execution`；`application/pendulum_fit.py`、`application/project_session.py`、`domain/pendulum_fit.py`、`domain/pendulum_ode.py`、`tests/test_pendulum_fit_job.py`、`tests/test_pendulum_fit.py`，以及 P3.3 mini-plan。当前工作树中仅审查实现提交；未审查或修改 GUI/P3.4。
- Context（spec / ADR / plan 路径）：[P3.3 mini-plan](../../publication/plans/p3.3-fit-execution-persistence.md)；[experiment-run-derived-contracts](../../publication/spec/experiment-run-derived-contracts.md)；[scientific-profiles](../../publication/spec/scientific-profiles.md)；[platform-requirements](../../publication/spec/platform-requirements.md)；[ADR-0020](../../docs/decisions/0020-explicit-fit-precision-and-historical-regression-limit.md)；P3.1/P3.2 review records。
- 轮次：R1 2026-10-01（首轮）
- Reviewer：fresh-context 独立只读审查；未修改 `src/`、`tests/`、publication evidence 或外部科研资产。

## Checklist

**正确性**

- [ ] 实现与 P3.3 AC / 相关科学契约完全一致（F1 payload 完整性、F2 区间输入边界、F3 破损 payload 解析边界待处置）。
- [ ] 边界情况处理正确：取消、迟到结果、输入/视频代际、Save As、Undo、磁盘写失败和重开路径有回归；新显式 fit start 的 release 前输入仍缺少应用层 fail-closed 回归。
- [x] 数值逻辑有合成数据验证：固定 release IC、later interval source time、默认 `soft_l1` 保持不变、显式 `linear` loss、M0 路径及 M0/M1 domain warm-start/comparability 测试。

**质量**

- [x] diff 无范围外产品改动；实现限定在 P3.3 application/domain/tests 与 mini-plan。
- [x] 遵守 `Path`、UTF-8、原子 JSON payload 与项目根目录 containment 约定。
- [x] `FitOptions`、job/result、配置签名、共享 session commit guard 与失败状态有说明，命名延续 P2/P3 既有模式。
- [ ] 测试真实覆盖新逻辑；当前 model-specific settings 回归在 `insufficient_data` 分支结束，未实际执行 M0/M1 的“不兼容设置跳过 warm-start”路径。

**流程**

- [x] 提交信息符合 Conventional Commits：`feat: add detached pendulum fit execution and immutable result persistence`、`feat: support explicit fit intervals and versioned solver options`。
- [x] 本轮未发现需要新增 ADR 的选型；loss/precision/历史数值边界沿用 ADR-0020。

## Findings

### F1 — paired payload/manifest 可伪造结果正文而仍被判定为 valid

- **Severity**：P2（Major）
- **Evidence**：`src/ai_physics_tracker/application/pendulum_fit.py:223-240` 的 `load_fit_result` 只检查 payload envelope 的 `contract`/`input_digest`、重新计算的当前 snapshot、以及 `config` 与当前 resolved config。`run_fit_job` 写入的 `measurement_digest`、`measurement`、`rows`、`fits` 和 `comparison`（同文件 `184-188`）没有在读侧做互相摘要/typed schema 校验；`read_scientific_payload` 仅验证 manifest 声明的文件 size/SHA（`infrastructure/scientific_payload.py:42-54`）。

  复现方式：从一个正常 `PendulumFitResult` 深拷贝 payload，只把 `rows` 清空或改写 `measurement`，保留原 `input_digest`、`config` 和 `record.extra_fields["config"]`，用 `write_scientific_payload` 生成一个同步更新的 manifest，再调用 `load_fit_result`。当前 loader 仍返回 `valid=True`；`measurement_digest` 也未要求等于 `canonical_json_digest(measurement)` 或当前 snapshot digest。
- **Impact**：项目文件同时被篡改时，结果可以保持“当前输入/配置有效”的状态，却不再是该输入的完整 typed 预测结果；P3.3 AC1/AC2 的完整记录约束和 P3.4 消费边界会被绕过。单独改 JSON 会被 manifest hash 拒绝，但 paired manifest/payload 是本项目已有 provenance 负向测试模型，不能作为可信边界。
- **Recommendation**：增加 fit-specific read validator：校验 `measurement_digest` 与 measurement 内容及当前 snapshot 一致，并与 record extra field 一致；校验 rows 的固定列、源帧顺序/时间/QC/weight；校验 fits 的模型集合、每个 fit 的 input/config/diagnostic/trajectory 结构及 comparison。缺键、错误类型、digest 不一致一律返回 invalid 或结构化 `ProjectSessionError`。补充 paired payload/manifest 改写 rows、measurement、fits 的负向回归。
- **Decision**：Fix Before Close — P3.3 的持久化结果会被 P3.4 UI 消费，必须在进入 GUI 前建立读侧完整性边界。
- **Fix commit**：N/A
- **Verification**：当前复现基于代码路径；现有 `test_matching_payload_and_manifest_cannot_forge_fit_provenance` 只改写 `config.models[M0].sources`，不能覆盖本 finding。
- **Re-review**：待修复后复审。
- **Status**：Open

### F2 — explicit fit start 在 release 之前时延迟到 worker 裸抛 `ValueError`

- **Severity**：P2（Major）
- **Evidence**：`FitOptions.__post_init__`（`application/pendulum_fit.py:56-61`）只检查 `0 <= start_frame_index <= end_frame_index`；`prepare_fit_job`（`144-148`）只把 end 交给共享 `prepare_analysis_job`。真正的 release 约束在 `_objective` 传入 `ObjectiveRequest` 后才触发（`application/pendulum_fit.py:109-112`、`domain/pendulum_ode.py:224-227`）。当 release 为 5、options 为 `start_frame_index=0` 时，prepare 成功，`run_fit_job` 抛 `ValueError("fit start must be a source frame between release and end")`。
- **Impact**：Advanced interval 的非法用户输入没有在 application prepare 边界 fail-closed；后台任务会以未分类的 `ValueError` 结束，P3.4 需要自行捕获才能显示可诊断的项目错误。该路径虽然不会写入科学记录，但不满足 AC2 的 invalid input fail-closed 语义，也没有覆盖 start-before-release 的负向测试。
- **Recommendation**：在 `prepare_fit_job` 读取 experiment release 后，将显式 start 限制在 `[release_frame_index, end_frame_index]`，并用 `ProjectSessionError` 报告；或把带 release context 的 validated interval value object 传入 options。补充 start=release、start=end、start<release 三个边界回归，保留 IC 仍从 release t=0 积分。
- **Decision**：Fix Before Close — 这是新增的用户可编辑高风险科学区间，不能把正常错误输入留给 worker 的裸异常。
- **Fix commit**：N/A
- **Verification**：已静态复核上述路径；现有 later interval 测试只覆盖合法 `start_frame_index=25`（release=5）。
- **Re-review**：待修复后复审。
- **Status**：Open

### F3 — 破损/丢失 payload 在 `load_fit_result` 读边界裸抛解析/IO 异常

- **Severity**：P2（Robustness）
- **Evidence**：`load_fit_result` 在 `pendulum_fit.py:226` 直接调用 `read_scientific_payload`，该调用位于 `try` 之前；missing file、size/hash mismatch、invalid UTF-8/JSON 和 non-object payload 会直接抛 `OSError`/`ValueError`，而不是返回该 API 声明形状的 `(payload, valid, reason)` 或统一的 `ProjectSessionError`。同一模式存在于早期 analysis loader，但 P3.3 新增了独立 fit loader，且 P3.4 尚未接入 UI。
- **Impact**：项目重开或历史结果浏览遇到破损派生文件时，调用方只能依赖 broad exception handling；未处理的 loader 调用会把数据损坏表现为后台异常，不能明确标记该结果不可读并保留旧成功结果。
- **Recommendation**：把 payload read 纳入结构化错误边界，区分“不可读 artifact”与“可读但 stale/invalid”；至少将 `OSError`/`ValueError` 包装成 `ProjectSessionError("fit payload is unreadable")`，并增加 hash、JSON、缺键三类回归。P3.4 调用方应把该状态显示为历史结果不可读，而不是让异常穿出 worker。
- **Decision**：Fix Before Close — untrusted parse 是 P3.3 读回契约的一部分；可与 F1 validator 共用边界。
- **Fix commit**：N/A
- **Verification**：代码走读；当前测试只覆盖正常 reopen、Save As、stale 和 config provenance，未覆盖破损 fit payload。
- **Re-review**：待修复后复审。
- **Status**：Open

## Checked paths with no finding

- **Snapshot / IC / source interval**：worker 使用 detached session；`build_adopted_measurement` 冻结 adopted tip、source frame/time、QC、weights、L/g、active run 和 video SHA。later interval 只改变 fit mask；IC 仍按 release 前 5 帧解析并以 release 为 t=0，原始 release-relative times 保留。
- **Loss / solver provenance**：`ObjectiveRequest.loss`、objective cost、SciPy optimizer config 和 signature/payload 均携带 `linear`/`soft_l1`；默认 `soft_l1` 行为未改。domain core versions 1.1.0 使 loss/interval 语义进入历史身份。
- **Warm start**：application 只在 M0/M1 public optimizer settings（忽略 model-specific `starts`）一致时传入 M0 warm result；不一致时让 M1 保持独立 starts，domain comparison 返回 `not_comparable` 而不抛 comparability error。当前实现方向正确，但见 Checklist 的实际求解测试缺口。
- **Late/cancel/failure/disk/Save As/reopen**：取消点覆盖每次 optimizer start/evaluation、发布前和发布后；worker 只写 immutable payload，session commit guard 同时复核 captured input state、video stat、payload identity、kind/core/freshness，并保留旧成功记录。Save As、Undo、stale、video change、write failure 和 reopen 有定向回归。P3.4 已计划由 done callback 以 job detached root 与 accepted/cancel marker 负责最终 orphan cleanup；本轮将该已声明后续作为 deferred lifecycle work，不重复升级为 P3.3 blocker。
- **Shared guard**：`ProjectSession._apply_pendulum_result` 对 analysis/fit 共用 project root、input state、video stamp、duplicate ID、immutable payload identity 检查；未发现跨项目/跨根提交旁路。

## Verification

- `PYTHONPATH=src /Users/leonis/Documents/ai-physics-tracker/.venv/bin/python -m pytest -q tests/test_pendulum_fit_job.py tests/test_pendulum_analysis.py tests/test_pendulum_fit.py` → **36 passed, 1 strict xfailed** in 62.93s；strict xfail 为 ADR-0020/P3.2 已接受的冻结默认 M1 数值限制，未计为通过。
- `git diff --check cdeb65d..d686ae8` → passed。
- 未运行 full suite 或 48-case refit；P3.3 mini-plan/status 中实现方报告的 full-suite 结果不是本审查的独立复跑。

## Review Log

### R1 — 2026-10-01 · 首轮

- 范围 / 基线：`cdeb65d..d686ae8`；P3.3 application/domain persistence 与 current working changes，未进入 GUI。
- 结论：**Request changes**；发现 F1 结果正文完整性旁路、F2 interval 输入边界延迟、F3 破损 payload 读边界异常；取消/代际/原子写/Save As/共享 guard/loss 默认路径未发现额外旁路。
- Findings 变化：新增 F1、F2、F3；关闭 —

## Final Verdict

- [ ] 通过（无未处置 Blocker）
- [ ] 修改后通过（findings 按 Decision 处置完毕，复审确认）
- [x] 需要重做（F1/F2/F3 Open；结果读回与 invalid interval 边界尚未达到 P3.3 AC2/AC5）

- 最终结论（一句话）：后台 fit 执行、snapshot/IC、取消与 shared commit guard 的主链路已有真实回归，`soft_l1` 默认和 `linear` 扩展身份清楚；但 paired payload/manifest 完整性、显式 start 的 release 前输入和破损 payload 解析仍有开放风险，P3.3 在进入 P3.4 GUI 前 **Request Changes**。
- 日期 / 依据轮次：2026-10-01 / R1

## R2 Re-review — 2026-10-01 · fresh-context

- 范围 / 基线：`cdeb65d..00854e1`（最终 P3.3 fix commit `00854e1`）；GUI/P3.4 文件仍在范围外。R1 三项 finding 与 eligibility/readback guards 均复核。
- F1：**Closed**。读侧现校验归档测量摘要、重建 source rows、列契约、models/config、typed starts、选中目标成本、最终 forward/trajectory/residual/metrics、比较结果、结果状态与区间；不重跑 optimizer。`eligibility` 也由历史输入重算并逐项校验。
- F2：**Closed**。`prepare_fit_job` 在任务准备边界拒绝 release 前的显式 start；release frame 与 end frame 边界有回归覆盖。
- F3：**Closed**。读 payload 的 IO/JSON 错误被转换为 `ProjectSessionError`；无效结构也在 fit 读边界返回结构化错误。Overflowing numeric input 已由额外探针确认被结构化拒绝。
- 新 findings：**None**。当前额外只读探针也确认 `selected_start_index` 的 bool 伪装会被拒绝，insufficient-data 结果可读回，伪造 `eligibility` 被拒绝。
- 复审结论：**修改后通过**；本段结论 supersede R1 的 Request Changes。R1 原 findings 的状态按本轮复核关闭。

### R2 Verification

- 独立定向测试：`PYTHONPATH=src /Users/leonis/Documents/ai-physics-tracker/.venv/bin/python -m pytest -q tests/test_pendulum_fit_job.py tests/test_pendulum_analysis.py tests/test_pendulum_fit.py` → **41 passed, 1 strict xfailed** in 57.41s。Xfail 是 `test_frozen_default_m1_parameter_recovery_gate`，对应 ADR-0020 / P3.2 已接受的冻结 M1 数值限制；不计作数值通过。
- 最新 eligibility/guard 工作树：保存重开与 stale/Undo 路径、insufficient-data readback、伪造 eligibility、bool selected index、超大数值输入的定向检查均通过；另一个 focused pytest run 为 **2 passed** in 3.96s。
- `git diff cdeb65d..00854e1 --check` 与当前 `git diff --check` 均通过。
- 未运行 full suite、48-case refit 或 GUI Human Review；P3.4 UI 仍在本轮范围之外。
