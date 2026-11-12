# Windows follow-up F1–F4 repair

- Date: 2026-11-12
- Status: complete — verified source; PR unmerged
- Owner: first-author Codex implementation agent (writing released after closeout)
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

- [x] S1: regression covers an existing selftest directory, repeated reuse, expected worker failure, cancellation and failed fallback preserving the pointer; regression fails on the original implementation.
- [x] S2: F2/F3 existing GUI regressions pass; F4 tests run natively on both systems.
- [x] S3: relevant runtime/worker/GUI tests and local full suite pass, allowing documented existing skips/xfail.
- [x] S4: independent read-only review approves the repair diff; any findings resolved and recorded.
- [x] S5: tests CI passes both native platforms for the final source SHA; PR and status list source, verification and handoff.

## Review Gate

Independent Review required: runtime re-verification crosses worker lifecycle and atomic-publication boundaries. Reviewer owns `docs/reviews/windows-followup-repair-review.md`; implementation agent owns product/test changes. This repair restores intended behavior and does not introduce new GUI interactions; the coauthor's broader GUI HR and Windows/CUDA/clean-machine gates remain separate pending evidence.

## Verification / handoff

Use the existing venv with `QT_QPA_PLATFORM=offscreen PYTHONPATH=src /Users/leonis/Documents/ai-physics-tracker/.venv/bin/python -m pytest ...`; no dependency upgrades. Preserve every original coauthor commit. Record repair commits, exact test counts, independent-review verdict and CI links here and in PR #46. Do not merge when finished; hand off the verified branch for Windows native retesting and a later integration decision.

## Results

| Item | Repair commit / verification |
| --- | --- |
| F2 / F3 | `4bd0d41`: one A Accept shortcut; existing progress assertion matches counter/percent; GUI43 passed |
| F1 / F4 | `dfe301b`: unique selftest-reuse job per attempt; native profile/path fixtures; new regressions before repair4 failed/31 passed/1 Windows-only skip; runtime/worker/FFprobe/GUI153 passed/3 Windows-only skips after repair |
| Independent finding R1-F1 | `079baf6`: only start/result errors are normalized; cleanup errors propagate and stop fallback. New cancel/timeout regressions fail twice against intermediate `dfe301b`; final runtime/setup45 passed/1 Windows-only skip |
| Independent review | [R2 modified then approved](../../docs/reviews/windows-followup-repair-review.md), reviewer independently45 passed/1 Windows-only skip; R1-F1 Closed |
| Target refresh | `9876f58`: merge existing target-branch documentation into the working branch, resolve STATUS only; `src/tests/packaging/resources/scripts/.github/pyproject/requirements` identical to `dfe301b`. PR remains unmerged |
| Source candidate | `079baf6b3edd42d97c59912b9f2db4c7903ebae5` |
| CI | [tests43210994098](https://github.com/KYLeonis/ai-physics-tracker/actions/runs/43210994098): both native jobs success; Mac1505 passed/7 skipped/1 existing xfailed (278.57s); Windows1506 passed/6 skipped/1 existing xfailed (375.13s) |
| Local full suite | Final source:1509 passed/3 Windows-only skipped/1 existing strict xfailed,9 subtests passed (354.18s). An earlier intermediate-source run was deliberately interrupted after review found a lifecycle issue (314 passed before interrupt), not counted as full-suite success |

PR comments record takeover and each pushed repair. No CI skip/xfail policy was weakened; true Windows-specific tests remain enabled on Windows. Runtime/GUI native HR, CUDA, clean-machine setup, scientific export/restore and broader integration are separate evidence and scope.

Next action: the second-author agent reads the latest PR comment and this record, updates from `KYLeonis:codex/windows-followup` with a clean worktree, then prepares a package from the verified code for Windows native retesting. This branch is available for an explicit handoff; do not merge or publish as part of this repair. General-main backports remain the separate next task in the coauthor sync report.
