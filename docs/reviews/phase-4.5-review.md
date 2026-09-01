# Review Record — Phase 4.5 Engineering Stabilization

- Subphase / Issue：4.5 · [#16](https://github.com/KYLeonis/ai-physics-tracker/issues/16)
- Review 范围：分支 `feat/p4.5-stabilization` 相对 `main`（基线 `6b2a939`）的全部 diff：`1641536` / `0d604ad` / `473ee65` / `e53ab7e` / `1ca4a91`
- Context：`docs/reviews/phase4-architecture-reliability-review.md`（F1/F4/F5/F6）、`docs/spec/data-model.md` §4.2/§4.4、ADR-0012、`CODE_STANDARD.md` §4/§8/§12/§15
- 轮次：R1 2026-09-01（首轮）· R2 2026-09-01（复审，独立 code-reviewer 子智能体）

> **流程偏差声明（已被 R2 修复）**：R1 时本环境 subagent 模型提供方未配置（`builtin:bigmodel-start-plan` 不存在，Explore / code-reviewer 均无法启动），首轮以实现方对抗性自查 + 取证替代。随后修复了工作区子智能体配置（`agents-state.json` 与自定义 agent 的模型指向改为已配置的 `builtin:bigmodel-coding-plan`），**R2 已由独立 code-reviewer 子智能体（只读、新会话）完成**，覆盖同一 diff 范围并复核 R1 四个疑点。

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
- **Re-review**：R2 独立复核确认（"src 内无污染共享快照的原地修改路径"）
- **Status**：Closed

### R2-F1 — `VideoReader` 端口缺 `path` 成员，导出契约漂移

- **Severity**：Suggestion
- **Evidence**：R2 reviewer：F6 让 `export_annotations` 依赖 `video_reader.path`，但 `application/video.py` 的 `VideoReader` Protocol 未增加该成员；媒体身份本是端口概念，替代实现（FFmpeg、测试 fake）无法从类型系统得知此要求。
- **Impact**：未来替代读取器实现 Protocol 后无法驱动导出，且无静态提示。
- **Recommendation**：把 `path` 补进 Protocol。
- **Decision**：Fix Before Close——端口契约应与实现同步
- **Fix commit**：`b46c041`（Protocol 补 `path` property 及语义说明）
- **Verification**：`python -m pytest -q` → 441 passed
- **Re-review**：N/A（修复即 reviewer 建议原文）
- **Status**：Closed

### R2-F2 — application↔infrastructure 公共 import 规则缺少权威文档表述

- **Severity**：Suggestion
- **Evidence**：R2 reviewer：该依赖方向决策只存在于 `tests/test_layer_boundaries.py` docstring；`docs/architecture.md` 四层图与 `CODE_STANDARD.md` §4 无此规则，架构读者无从判断测试与架构图谁说了算。
- **Impact**：规则可被发现性差，易被当作测试私有假设清理掉。
- **Recommendation**：在 architecture.md §1 落一句权威表述。
- **Decision**：Fix Before Close——纯文档
- **Fix commit**：`b46c041`（architecture.md §1 新增"分层务实边界"原则，含 AST 强制说明）
- **Verification**：文档审阅
- **Re-review**：N/A
- **Status**：Closed

### R2-F3 — 分层检测器两处绕过：相对导入与 `import X._module`

- **Severity**：Suggestion
- **Evidence**：R2 reviewer：`level > 0` 的相对导入被静默跳过，"src 一律绝对导入"只是假设；`import a.b._c as m` 形式下 private 规则拿到空 names 列表，可跨层穿透私有模块而检测器不可见。
- **Impact**：未来代码可用相对导入或整模块导入绕过层规则。
- **Recommendation**：相对导入判违规；Import 语句检查模块末段下划线。
- **Decision**：Fix Before Close——检测器漏洞
- **Fix commit**：`b46c041`（相对导入违规 + `parts[-1].startswith("_")` 检查；自检测试植入 `from . import sibling` 与 `import …infrastructure._hidden` 两个绕过样本）
- **Verification**：`python -m pytest tests/test_layer_boundaries.py -q` 通过（自检断言新样本被抓）
- **Re-review**：N/A
- **Status**：Closed

### R2-F4 — labeled-data 目录比较大小写敏感

- **Severity**：Suggestion（低）
- **Evidence**：R2 reviewer：`entry.name != video_stem` 在 Windows（NTFS 大小写不敏感）上会把仅大小写改名的 relink 误判为"another video"，指向该视频自己的旧目录；方向保守、恢复无损。
- **Recommendation**：两侧 `.casefold()`。
- **Decision**：Fix Before Close——一行修复贴合目标平台语义
- **Fix commit**：`b46c041`（casefold 比较 + 平台语义注释）
- **Verification**：`python -m pytest tests/test_dlc_adapter.py -q` 通过
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

### R2 — 2026-09-01 · 复审（独立 code-reviewer 子智能体，只读新会话）

- 范围 / 基线：同 R1（`6b2a939..2d0c858`）；输入按 workflow §6 最小化（diff 范围 + 文档路径，不给实现叙述）
- 结论：**approve-with-comments**，无 Blocker；4 个 Suggestion（R2-F1 端口契约 / R2-F2 规则文档化 / R2-F3 检测器绕过 / R2-F4 大小写）全部由实现方按 Fix Before Close 处置（`b46c041`），全量回归 441 passed
- R1 四个疑点独立复核：F1 undo 语义无悬垂引用路径（validate 无 observation↔run 交叉校验、src 无按 source_detail 反查 run 的消费点）；F5 全部写点 copy-first；F6 正常单视频流程不会误杀（应用链不调 DLC 建目录 API、项目目录按 track 隔离）；F4 rename 无遗漏、AST 规则严格强于旧字符串检查
- Findings 变化：新增 R2-F1…R2-F4；全部关闭

## Final Verdict

- [x] 通过（无未处置 Blocker；R2 独立复审 approve-with-comments，其 4 项 Suggestion 已全部修复并经全量回归验证）
- [ ] 修改后通过（findings 按 Decision 处置完毕，自查确认）
- [ ] 需要重做（说明理由）

- 最终结论：实现满足 Issue #16 全部 AC；全量回归 **441 passed**；R1 对抗性自查 + R2 独立复审双层确认，7 项 finding（3+4）全部 Closed。
- 日期 / 依据轮次：2026-09-01 · R1 + R2
