# Review Record — Phase 4.5 Engineering Stabilization

- Subphase / Issue：4.5 · [#16](https://github.com/KYLeonis/ai-physics-tracker/issues/16)
- Review 范围：分支 `feat/p4.5-stabilization` 相对 `main`（基线 `6b2a939`）的全部 diff：`1641536` / `0d604ad` / `473ee65` / `e53ab7e` / `1ca4a91`
- Context：`docs/reviews/phase4-architecture-reliability-review.md`（F1/F4/F5/F6）、`docs/spec/data-model.md` §4.2/§4.4、ADR-0012、`CODE_STANDARD.md` §4/§8/§12/§15
- 轮次：R1 2026-09-01（首轮）

> **流程偏差声明**：本环境的 subagent 模型提供方未配置（Explore / code-reviewer 两种 reviewer 均无法启动，错误 "Model provider is not configured"），Independent Review 无法由第二会话执行。R1 改为实现方对抗性自查（针对预设疑点清单逐项取证）+ 全量回归。如需补做真正独立 review，可在配置可用的环境对同一 diff 范围重跑并追加 R2。

## Checklist

**正确性**

- [x] 实现与 subphase plan 的 AC / 相关 spec 一致（AC-1…AC-4 见 `docs/status/phase-4.5-plan.md`）
- [x] 边界情况处理正确（undo 后 run 不复活的语义有测试；外来目录拒绝发生在任何写入之前；共享引用的隔离性有双向测试）
- [x] 数值逻辑不涉及本 subphase（N/A）

**质量**

- [x] diff 无范围外改动（13 个文件均对应 F1/F4/F5/F6 或其测试）
- [x] 遵守可移植性规则（pathlib、UTF-8 显式编码、无盘符/符号链接）
- [x] 公开接口有说明（`tracking_run_to_payload/from_payload`、`QueueLogStream`、`OpenCVVideoReader.path`），命名延续既有模式
- [x] 测试真实覆盖新逻辑（domain/session/GUI 三级 F1 回归；F6 拒绝 + 零写入断言；F5 隔离 + O(1) 契约；分层检测器自检）

**流程**

- [x] 提交信息符合 Conventional Commits
- [x] 无 ADR 级决策（F5 的共享契约是对既有 frozen 设计的执行，不改变架构结论；F4 的双向公共 import 现状已在测试 docstring 中声明为已接受现状）

## Findings

### F1 — 转正的公共序列化函数缺 docstring

- **Severity**：Suggestion
- **Evidence**：`project_serializer.py` 的 `tracking_run_to_payload` / `tracking_run_from_payload` 由私有转公共后无 docstring，违反 CODE_STANDARD §12（public API 必须有 docstring）。
- **Impact**：跨包公共 API 无说明，后续使用者需读实现。
- **Recommendation**：各补一行 docstring。
- **Decision**：Fix Now——收尾前廉价修复
- **Fix commit**：`1ca4a91`
- **Verification**：`python -m pytest tests/test_project_repository.py tests/test_tracking_job.py -q` 通过
- **Re-review**：R1 自查确认已补
- **Status**：Closed

### F2 — 分层测试局部 import 与缺失类型标注

- **Severity**：Suggestion
- **Evidence**：`tests/test_layer_boundaries.py::test_detector_flags_planted_violations` 函数内 `import sys`、`monkeypatch` 参数未标注 `pytest.MonkeyPatch`，与仓库测试风格不一致。
- **Impact**：风格漂移，无功能影响。
- **Recommendation**：`sys` 提至模块顶部、补标注。
- **Decision**：Fix Now——同 F1 一并处理
- **Fix commit**：`1ca4a91`
- **Verification**：`python -m pytest tests/test_layer_boundaries.py -q` 通过
- **Re-review**：R1 自查确认已改
- **Status**：Closed

### F3 — F5 共享引用后存在 dict 别名污染的理论风险

- **Severity**：Suggestion（经取证判定为受控）
- **Evidence**：对 `src/` 全量 grep `ui_state[`/`ui_state.update`/`extra_fields[`/`extra_fields.update`：仅剩读取（`task_panel.py:361-364`、`project_session.py:359`）与对**本地副本**的写入（`project_session.py:515→521`、`kinematics_job.py:94→96`、`_with_import_summary` 的 deepcopy 链）。所有变更路径均为 copy-first。
- **Impact**：若未来代码原地修改 `ui_state`/`extra_fields`，detached 快照会被污染——已由 `test_detached_snapshot_is_isolated_from_subsequent_writes` 固定为契约测试，且 `detached()` docstring 写明了前提契约。
- **Recommendation**：接受现状；依赖契约测试与 docstring 守护。
- **Decision**：Accept——理论性风险已有测试与文档双重防护
- **Fix commit**：N/A
- **Verification**：grep 取证 + `tests/test_project_session.py` 隔离测试通过
- **Re-review**：N/A
- **Status**：Closed

## Review Log

### R1 — 2026-09-01 · 首轮（实现方对抗性自查，见偏差声明）

- 范围 / 基线：`feat/p4.5-stabilization` vs `main`（`6b2a939`），全 diff 审查 + 疑点取证
- 结论：四个 review finding 的实现与测试闭环成立；自查发现 2 个 Suggestion 已当场修复，1 个理论风险取证后 Accept
- 疑点取证记录：
  - **F1 undo 语义**：undo 恢复 track/观测/派生但 runs 保持删除；`validate_project` 不做 observation↔run 交叉校验，恢复的引擎点不构成悬垂引用（引擎点仅按 `source_detail` 分组展示）。有 domain/session 测试锁定。
  - **F5 dict 别名**：见 Finding F3 取证。
  - **F6 误杀**：正常重训流程 labeled-data 仅含本视频 stem 目录（`create_project` 与导出同约定），不会触发拒绝；触发即对应"换视频复用 DLC 项目目录"的真实风险场景，错误信息给出恢复指引（删除旧目录或换新项目目录）。
  - **rename 遗漏**：全仓库 grep 旧符号名（`_tracking_run_to_payload`/`_tracking_run_from_payload`/`_QueueLogStream`）仅剩 Phase 4 review 报告中的历史引用（point-in-time 文档，不改）。
- Findings 变化：新增 F1、F2、F3；关闭 F1、F2（修复）、F3（Accept）

## Final Verdict

- [ ] 通过（无未处置 Blocker）
- [x] 修改后通过（findings 按 Decision 处置完毕，自查确认）
- [ ] 需要重做（说明理由）

- 最终结论：实现满足 Issue #16 全部 AC；全量回归 **441 passed**；无 Blocker。独立 review 因环境限制以对抗性自查替代（偏差已在顶部声明），建议用户按 `docs/status/phase-4.5-plan.md` 的手动验证步骤抽查 F1/F6 的实际行为。
- 日期 / 依据轮次：2026-09-01 · R1
