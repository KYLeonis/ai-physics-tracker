# Windows follow-up F1–F4 repair

- Date: 2026-11-12
- Status: in_progress
- Owner: first-author Codex implementation agent
- Worktree: `/Users/leonis/Documents/ai-physics-tracker-windows-followup`
- Branch: `codex/windows-followup`
- Start SHA: `6a7a0318b4895fb7a664c26d6647894b21d97625`
- Coordination: [PR #46](https://github.com/KYLeonis/ai-physics-tracker/pull/46); append commits, no force push. Other agents must read this entry and the latest PR comments before writing this branch.

## Goal / Context Pack

Repair F1–F4 from the 2026-11-11 coauthor review and make the same source pass macOS / Windows tests CI. Read `AGENTS.md`, `CODE_STANDARD.md`, `publication/STATUS.md`, ADR-0022, `p6.2-managed-runtime.md`, `runtime_install.py` / `external_worker.py` and their tests. Baseline CI43046359695 failed: Windows1495pass/2fail; Mac1492pass/4fail.

## Scope / invariants

- F1: reuse a ready environment with a fresh, exclusive verification job directory; handle expected worker failures so a broken candidate can be replaced, preserving cancellation and the old active pointer until verification and publication succeed.
- F2: keep one A-key Accept shortcut; preserve arrow-key and input-focus behavior.
- F3: align the existing progress assertion with the intended counter/percent display; retain metrics and bounded-log checks.
- F4: run platform-independent reuse tests on each native platform; retain true Windows-only skips.
- No changes to dependencies, scientific algorithms/profiles/golden, schema, worker protocol, application activation, public releases or branch integration. No real AI training or user-environment modifications.

## Slices / acceptance

- [ ] S1: regression covers an existing selftest directory, repeated reuse, expected worker failure, cancellation and failed fallback preserving the pointer; regression fails on the original implementation.
- [ ] S2: F2/F3 existing GUI regressions pass; F4 tests run natively on both systems.
- [ ] S3: relevant runtime/worker/GUI tests and local full suite pass, allowing documented existing skips/xfail.
- [ ] S4: independent read-only review approves the repair diff; any findings resolved and recorded.
- [ ] S5: tests CI passes both native platforms for the final source SHA; PR and status list source, verification and handoff.

## Review Gate

Independent Review required: runtime re-verification crosses worker lifecycle and atomic-publication boundaries. Reviewer owns `docs/reviews/windows-followup-repair-review.md`; implementation agent owns product/test changes. This repair restores intended behavior and does not introduce new GUI interactions; the coauthor's broader GUI HR and Windows/CUDA/clean-machine gates remain separate pending evidence.

## Verification / handoff

Use the existing venv with `QT_QPA_PLATFORM=offscreen PYTHONPATH=src /Users/leonis/Documents/ai-physics-tracker/.venv/bin/python -m pytest ...`; no dependency upgrades. Preserve every original coauthor commit. Record repair commits, exact test counts, independent-review verdict and CI links here and in PR #46. Do not merge when finished; hand off the verified branch for Windows native retesting and a later integration decision.
