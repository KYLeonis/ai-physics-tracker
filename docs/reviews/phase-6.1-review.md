# Review Record — Phase 6.1 Angular Analysis Foundation

- Subphase：[phase-6.1-plan.md](../status/phase-6.1-plan.md) · Issue [#25](https://github.com/KYLeonis/ai-physics-tracker/issues/25)
- 分支：`feat/p6.1-angular-analysis`（叠加于待 HR 的 `feat/main-guided-refinement-model-import`）
- Reviewer：Independent code-reviewer（只读，全新实例，Flash 模型）
- 首轮日期：2026-10-11 · 状态：Final Verdict 已出

## Scope

实现提交 `feat: add angular analysis foundation with multi-input derived data`
（domain/angular.py 新增；DerivedInput.reference_track_id additive 扩展；
compute_angular / angular_job / serializer / validate_project / delete_track 级联；
41 项新测试）。审查维度按 mini-plan Review Gate：A 科学定义与数值、B 多输入依赖失效、
C 存储兼容、D 事务、E 代码规范。权威上下文：ADR-0019、phase6-requirements R1/R5、
ADR-0008、pre-phase6 review §10（P6R-01）。

## Findings（首轮 R1）

| # | 维度 | Severity | Observed/Inferred | 摘要 |
| --- | --- | --- | --- | --- |
| R1 | A | Low | Observed（数值复现） | `-dy + 0.0` 规整无可观测行为差异且注释论据错误（`atan2(y>0, ±0)` 恒 π/2；dx=dy=0 已被重合守卫覆盖） |
| R2 | B | Low | Observed | `update_timeline` 仅 working_zone 变化时不置 stale，角运动/运动学共用此既有缺口（非本 diff 引入） |
| R3 | D | Low | Inferred | `prepare_angular_job` 不预检 active calibration，无标定批次在 worker 内才失败 |
| R4 | B | Low | Observed | `validate_project` 对 reference_track_id 只校验存在性，不校验同视频 |
| R5 | E | Nit | Observed | `compute_angular` docstring "同一角度定义下" 与无条件整组替换的实现不符 |
| R6 | 文档 | Low | Observed | 提交时 plan/current.md 未同步（Slice 4 中间态，收尾必须完成） |
| R7 | 范围外 | Low | Observed | `tests/gui/test_suggested_frame_review_reliability.py::test_save_reopen_and_resume_review_matrix` 负载下时序 flake（父分支 1ee9323 既有） |

维度结论：A/B/C/D/E 五个维度均无 High/Medium finding；B 维度逐点核对了全部
`mark_tracks_stale` 调用点与删除/Undo 路径，未发现失效传播漏洞。

## Triage 与 Fixes

- **R1 → Fixed**：删除无效规整与错误注释（reviewer 复核 atan2 语义后确认守卫已覆盖）。
- **R3 → Fixed**：`prepare_angular_job` 对目标/参考轨迹所属视频 fail-fast 校验 active
  calibration，新增回归测试。
- **R4 → Fixed**：`validate_project` 增加 reference_track_id 同视频聚合校验，新增跨视频
  拒绝测试。
- **R5 → Fixed**：docstring 改为"重算即整组替换（含更换参考模式）"。
- **R2 → Deferred（接受）**：zone-only 变更不失效是 Phase 3 以来的既有语义，kinematics
  同样继承；当前 GUI 无 zone 编辑入口。移交 Phase 6.2（角运动图表暴露 zone 相关 UI 前）
  处理，届时统一决定 zone 变更的失效策略。
- **R6 → Fixed**：Slice 4 收尾同步（本文件 + plan AC/Slice 勾选 + current.md）。
- **R7 → Deferred（范围外）**：父分支 flake，与 6.1 diff 无关（在 a36007e 上以 1/6
  失败率复现，隔离运行 ~1/5–1/3）。已做无害加固：该文件 8 处 `waitUntil` 超时
  3000→15000 ms（独立 test 提交）。竞态疑似重开 `projectChanged` 与测试点击之间，
  需专门排查，不阻塞本子阶段；若 CI 偶发红，单独修复。

## Verification

- 首轮：Reviewer 独立运行新增 41 项 + 相邻回归 114 项 + 全量 4 次（3×906 passed）。
- 修复后（实现方）：定向 angular 43 项 passed；全量 906/907 passed（唯一失败为 R7
  flake，与本 diff 无关）。

## Re-review

修复提交 `fix: dispose independent review findings R1/R3/R4/R5` 由全新独立 code-reviewer
复审（2026-10-11）：R1 数值情形逐一验证语义不变；R3 覆盖目标+参考、同视频多 spec 无
误拒、与 worker 校验逐字一致；R4 索引安全且不破坏既有构造（定向 57 + 全量 908
passed）；R5 与实现一致；两项新回归测试在修复前必失败、真实覆盖。附 2 条风格 nit
（`_job_track_ids` 重复计算、"R1" 引用口径），实现方当场处置。**结论：确认修复完毕
（approve）。**

## Final Verdict

**修改后通过（Approve with findings disposed）**：R1/R3/R4/R5/R6 已修复并复审确认，
复审附带的 2 条 nit 已处置；R2/R7 记档延期（均非本 diff 引入）；科学定义、多输入依赖
失效、存储兼容与事务四大高风险面通过审查。集成前剩余条件：双平台 CI 绿。
