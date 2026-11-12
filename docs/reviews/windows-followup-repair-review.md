# Review Record — Windows Follow-up F1–F4 Repair

- Subphase / Issue：Windows follow-up F1–F4 repair / PR #46
- Review 范围：`6a7a0318b4895fb7a664c26d6647894b21d97625..079baf6`；首轮产品/测试提交 `4bd0d41`、`dfe301b`；取消/超时清理修复 `079baf6`。文档同步提交 `9876f58` 不改本次审查的 `src/`、`tests/`。
- Context：`publication/plans/windows-followup-repair.md`、`docs/decisions/0022-managed-ai-runtime-bootstrap.md`、`publication/plans/p6.2-managed-runtime.md`、`docs/reviews/publication-p6.2-review.md`（F2/F3/F7）、`publication/spec/runtime-boundary.md`。
- 轮次：R1 2026-11-12（首轮）· R2 2026-11-12（复审）

## Checklist

**正确性**

- [ ] 全部 subphase AC 已核验（代码审查项通过；Windows 原生测试 CI 仍需实现方按 S5 核验）
- [x] 已检查边界与失败状态，包括取消、超时、复验目录与 active pointer 保留
- [x] 数值逻辑不适用

**质量**

- [x] 审查范围限于维修计划/状态及 4 个指定产品与测试文件
- [x] 已检查可移植路径与 Windows / macOS 测试分支
- [x] 本次改动无新增公开接口或数据结构
- [x] F1 的取消/超时清理失败由无 Torch 的 fake-handle 回归覆盖

**流程**

- [x] 修复提交使用 Conventional Commits
- [x] 不涉及新的 ADR 级决策

## Findings

### F1 — Worker 树清理失败会被当作坏 runtime 并触发新安装

- **Severity**：Blocker
- **Evidence**：`src/ai_physics_tracker/infrastructure/runtime_install.py:355-359` 将 `ExternalWorkerError` 和 `OSError` 当作可恢复候选验证失败并继续；但 `verify_runtime` 在取消或超时路径调用 `handle.cancel()`（同文件 287-292），而 `ExternalJobHandle.cancel()` 在强制终止后仍无法回收进程时抛出 `ExternalWorkerError`（`src/ai_physics_tracker/infrastructure/external_worker.py:464-469`）。`runtime-boundary.md` 的取消合同要求整棵进程树退出，child 留存即失败。
- **Impact**：当复验超时或用户取消且 worker 进程树未能回收时，异常会被误认为候选 runtime 损坏，控制流随后尝试 fresh install。旧 worker 仍可能运行，同时安装器可能开始下载或准备新环境，违反取消/超时清理语义并可能并发消耗资源。
- **Recommendation**：只把已退出 worker 的结果校验错误或可恢复启动错误归一化为候选不可用；让 `handle.cancel()` 的清理失败直接传播，阻止 fallback。增加无 Torch 的取消和超时清理失败回归，断言不启动 fresh install、active pointer 不变。
- **Decision**：Fix Before Close — 区分可恢复的启动/结果校验错误与未能回收 worker tree 的清理失败。
- **Fix commit**：`079baf6`
- **Verification**：R1 定向测试 `PYTHONDONTWRITEBYTECODE=1 QT_QPA_PLATFORM=offscreen PYTHONPATH=src /Users/leonis/Documents/ai-physics-tracker/.venv/bin/python -m pytest -p no:cacheprovider tests/test_runtime_install.py tests/gui/test_task_panel.py`：42 passed、1 skipped（Windows-only console suppression）。R2 在 `verify_runtime` 的 start / `read_result` 边界把可恢复的 `ExternalWorkerError` / `OSError` 转成 `RuntimeInstallError`；`handle.cancel()` 的错误不被转换，`_reusable_install` 仅对 `RuntimeInstallError` fallback。新增 start/result 归一化测试及取消/超时清理失败两路回归。R2 定向测试见 Review Log：45 passed、1 skipped。
- **Re-review**：R2 确认清理失败向上传播，不再触发 fallback；新测试分别覆盖取消请求与复验超时。
- **Status**：Closed

## Review Log

### R1 — 2026-11-12 · 首轮

- 范围 / 基线：检查 `6a7a0318..dfe301b` 的维修计划、状态和 4 个产品/测试文件；另核对文档同步 `9876f58` 未改本次审查的产品与测试文件。调用链包括复用筛选、复验 worker、取消/超时清理、fallback、ready 证据写入及 active pointer 提交。
- 结论：需要修改；F1 Blocker 未关闭，不能批准收尾。
- Findings 变化：新增 F1；关闭 —
- 验证边界：本机 macOS 定向测试通过；Windows 原生测试/CI 尚未由本轮 Reviewer 核验。

### R2 — 2026-11-12 · 复审

- 范围 / 基线：复审 `dfe301b..079baf6` 的 runtime 安装器与回归测试；确认 `9876f58` 仅同步 PR 目标分支已有文档。重新核对 `verify_runtime` start / result 两个归一化边界、取消和超时的 `handle.cancel()` 传播，以及 `_reusable_install` fallback 条件。
- 结论：F1 已关闭；代码审查修改后通过。
- Findings 变化：关闭 F1（`079baf6`；R2 定向测试通过）。
- 验证：`PYTHONDONTWRITEBYTECODE=1 QT_QPA_PLATFORM=offscreen PYTHONPATH=src /Users/leonis/Documents/ai-physics-tracker/.venv/bin/python -m pytest -p no:cacheprovider tests/test_runtime_install.py tests/gui/test_runtime_setup_ui.py`：45 passed、1 skipped（Windows-only console suppression）。Windows 原生测试/CI 与 Windows 实机门禁未由本 Reviewer 核验。

## Final Verdict（收口时填写）

- [ ] 通过（无未处置 Blocker）
- [x] 修改后通过（findings 按 Decision 处置完毕，复审确认）
- [ ] 需要重做（说明理由）

- 最终结论：F1 已在 `079baf6` 修复并经 R2 独立复核关闭；代码审查修改后通过。Windows 原生测试 CI 与 Windows 实机门禁仍属独立验收证据，本记录不声明其通过。
- 日期 / 依据轮次：2026-11-12 / R2
