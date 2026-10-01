# Independent Review — P3.4 HR Follow-up UI

- Review scope: uncommitted diff from `0ef685b` in `src/ai_physics_tracker/gui/pendulum_fit.py`, `src/ai_physics_tracker/gui/pendulum_fit_panel.py`, and `tests/gui/test_pendulum_fit_ui.py`.
- Read-only review; no product, test, or user-data files changed.
- Context: [P3.4 mini-plan](../../publication/plans/p3.4-fit-ui.md) and the prior [P3.4 review](publication-p3.4-review.md). This review does not substitute for the pending Human Review.

## Findings

### F1 [P1] Read the timing action's actual busy-state property — Closed (R2)

- Location: `src/ai_physics_tracker/gui/pendulum_fit.py:132`
- R1 found that `TimingActions` exposes `pending`, not `busy` (`timing_actions.py:34-36`). R2 now reads `timing.pending`, matching the production action. The regression test constructs the actual `TimingActions`, assigns its pending `Future`, and checks the validating UI state; the prior fake-property gap is closed.

## Verification

- R2 code inspection confirms `_enableRun()` reads the real `TimingActions.pending` property, and the updated test exercises that property through an actual `TimingActions` instance.
- The implementation agent reported the focused 8-test fit UI run and 34-test adjacent GUI run were in progress; this reviewer did not rerun them.
- Initial R1 targeted suite: **8 passed** in 19.07s; this predates the R2 regression-test update.

## Final Verdict

- [x] Approve (R2) — F1 is closed; no open code-review findings remain.
- [ ] Request changes.

实现方最终验证（非reviewer重跑）：34 GUI定向passed / 25.64s；替换为真实TimingActions的最终8项passed / 18.92s。diff check通过。

## Human Review closeout — 2026-10-01

用户亲自运行P011 M0/M1并提出四项UI反馈，修复后明确“通过，收尾”。记录为整体交付与四项修复验收通过；不把此前自动化检查改称逐项真人实测。独立审查结论及ADR-0020数值限制不变。
