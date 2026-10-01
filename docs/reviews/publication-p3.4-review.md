# Independent Review — Publication P3.4 ODE fit UI

- Subphase：P3.4 — Fit UI
- Review 范围：`38f6de5..4e4fe2d`，branch `codex/ejp-p3-4-fit-ui`；`pendulum_fit.py`、`pendulum_fit_panel.py`、MainWindow/Kinematics/Save As 接入及 GUI 定向测试。
- Context：[P3.4 mini-plan](../../publication/plans/p3.4-fit-ui.md)、[P3.3 R2 review](publication-p3.3-review.md)、[ADR-0020](../decisions/0020-explicit-fit-precision-and-historical-regression-limit.md)。数值核心沿用已复审的 P3.3 接口；未运行 48-case refit 或数值全量回归。
- Reviewer：独立只读代码审查；只新增本记录，未修改产品代码、测试、用户项目或冻结证据。

## Review

- MainWindow 将 Kinematics 与 ODE fitting 接入独立 tab；Kinematics 的 SG 控件留在原页。Normal 与 Advanced 最终构造同一 `FitOptions`，preset/custom integration 值、模型选项、显式 IC 和源帧区间均进入请求。
- IC 在 release `t=0` 固定；rest 需要用户确认并由应用层核验连续支持帧，显式 θ₀/ω₀可直接输入。填入 θ₀ 的操作只使用当前输入和视频代际仍有效、且 release 帧 QC 有效的 Kinematics 结果。
- 图表消费已验证的拟合 payload，展示原始角度、预测、原始残差、参数单位、完整 RMSE 及 start 诊断；点击曲线/观测点按源帧导航。历史结果配置可恢复，失效输入明确标 stale。
- Worker 不操作 widgets；QTimer 在 GUI 线程交付结果。cancel、代际、输入状态及选项相等性守卫阻止迟到结果提交；未接受 payload 由持有原 job session/root 的回调清理，accepted 标志保护已登记结果。Save As 菜单和入口均在 fit pending 时阻断，避免复制尚未登记的 payload。
- 失败/取消保留旧成功图；项目/视频重置会退役旧任务并在新实验上下文恢复控件状态。未发现跨项目提交、旧结果误删或其他可执行 finding。

## Findings

None.

## Verification

- 独立 GUI/生命周期定向集：
  `PYTHONPATH=src /Users/leonis/Documents/ai-physics-tracker/.venv/bin/python -m pytest -q tests/gui/test_pendulum_fit_ui.py tests/gui/test_pendulum_analysis_ui.py tests/gui/test_project_actions.py tests/gui/test_main_window.py` → **33 passed** in 24.09s。
- Offline frozen-evidence verifier：`scripts/verify_publication_evidence.py` → **15 local files, 48 formal fit rows, 2 offline trajectory cases** validated。未执行历史 refit。
- `git diff --check 38f6de5..4e4fe2d` → passed；review 时 worktree clean。
- 实现方报告全量 **1324 passed / 1 strict xfailed / 9 subtests**；此项未由本 reviewer 重跑。strict xfail 是 ADR-0020 明示保留的默认 M1 历史敏感性限制。

## Final Verdict

- [x] Approve — 独立代码与自动化验收通过，无开放 finding。
- [ ] Request changes。

最终结论：P3.4 Independent Review **Approve**。真人 Human Review 仍待用户按 mini-plan 实际验收；本结论不代替该体验门禁，也不代表 P3 收尾/集成已完成。

日期 / 基线：2026-10-01 / `4e4fe2d`

## Human Review closeout — 2026-10-01

用户亲自运行P011 M0/M1并提出四项UI反馈，修复后明确“通过，收尾”。记录为整体交付与四项修复验收通过；不把此前自动化检查改称逐项真人实测。独立审查结论及ADR-0020数值限制不变。
