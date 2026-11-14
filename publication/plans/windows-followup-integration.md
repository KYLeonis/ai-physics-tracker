# Windows follow-up — internal integration

- Date: 2026-11-14
- Status: preparing_review_and_candidates
- Coordination worktree / branch: `/Users/leonis/Documents/ai-physics-tracker-ejp` / `codex/ejp-p6-4-release`
- Source worktree / branch: `/Users/leonis/Documents/ai-physics-tracker-windows-followup` / `codex/windows-followup`
- PR: [#46](https://github.com/KYLeonis/ai-physics-tracker/pull/46)
- Candidate source: `2edd01b1d53eba7a877b10d14e574f30f9d7e9c0`
- Review base: `23c0a227179c96e9a8a501634850b58825d1f38a`; original contribution range: `154f262..6a7a031`.

## Confirmed user decisions

Q1–Q3 confirmed on 2026-11-14: integrate PR #46 into the publication candidate work branch only; main backports and public releases are separate. Codex prepares a full independent review, same-source native candidates and concise acceptance instructions. The second author tests Windows; the first author tests Mac interactions. Merge only after review, native tests/builds and this change's human acceptance pass. CUDA, clean-machine G5 and student pilot remain separately deferred; do not mark them PASS from this task.

## Context Pack / invariants

Read `AGENTS.md`, `CODE_STANDARD.md`, `docs/workflow.md` §5.1/6/10, `publication/README.md`, ADR-0021/0022/0023, `publication/spec/runtime-boundary.md`, `publication/plans/p6.2-managed-runtime.md`, `docs/reviews/publication-p6.2-review.md` (F2/F3/F7), `docs/reviews/windows-followup-repair-review.md`, and the complete PR source/test diff.

The previous independent review started at `6a7a031` and covered repairs only. This review must also cover all original ten commits: download retry/resume, install reuse, Windows process flags and cleanup, arrow stepping, four-point auto-advance, crosshair/AI marker/Correct focus, hints and progress. Scientific algorithms, profiles/golden, schema, external-worker protocol, raw/AI activation and Undo contracts remain unchanged.

No new dependencies, GitHub settings changes, force pushes, project/data writes or public tag/Release. Existing published v0.1.0 is unchanged. Reviewers are read-only for product code; implementation fixes use append-only commits on the PR branch and receive proportional regression/re-review.

## Slices / acceptance

- [ ] S1 Full independent review of `23c0a22..candidate`: all blockers resolved; findings/dispositions recorded in `docs/reviews/windows-followup-integration-review.md`.
- [ ] S2 Same exact source passes both native tests and packaging. The current `packaging.yml` push filter already accepts `codex/ejp-p6-*`; create temporary candidate ref `codex/ejp-p6-windows-followup-candidate` at the pinned PR head to trigger existing workflows without merging first or editing main.
- [ ] S3 Download candidates, check archive integrity, exact artifact IDs/size/SHA256, embedded source/provenance and available native smoke/signature evidence. Record failures honestly. Changes to product code require a new candidate generation and relevant revalidation.
- [ ] S4 Provide each human reviewer no more than five operations with expected outcomes and closed questions. Windows covers ready-runtime reuse/Repair/cancel/retry, hidden-console behavior, keyboard/review/marking interactions, and a small CPU flow using test copies. Mac confirms the affected interactions and ready-runtime behavior. User/second-author feedback must identify tested source/package.
- [ ] S5 Both human acceptances recorded; no automated UI action substitutes for HR. If either reports a problem, fix and rebuild/retest the affected scope before merging.
- [ ] S6 Merge PR #46 into `codex/ejp-p6-4-release` only after S1–S5; preserve original authorship, resolve documentation conflicts and verify the integrated code/tests against the accepted candidate. Confirm integration tests/packaging, synchronize docs and stop. Do not merge into main or `publication/ejp-damped-pendulum` in this task.

## Review Gate / responsibilities

- Independent review required: the full PR includes download/install/activation and worker lifecycle changes. Fresh reviewer session; product tree stays read-only. Reviewer owns the integration Review Record in the coordination worktree.
- Human Review required by workflow §5.1: original PR adds user-visible interactions. Both-platform CI/packaging are evidence, not human feedback.
- Codex owns preparation, implementation repairs, CI/artifact verification, instructions and PR handoff. Second author owns Windows native feedback; first author owns Mac human feedback. Missing feedback remains pending, never inferred.

## Evidence / handoff

- Prior source verification: [tests43212468799](https://github.com/KYLeonis/ai-physics-tracker/actions/runs/43212468799), `2edd01b`, Mac1505 passed/7 skipped/1 existing xfailed; Windows1506 passed/6 skipped/1 existing xfailed.
- Prior repair review: R2 modified then approved, limited to the repair range. This does not close S1.
- Current native candidates: pending. No new Windows package was found when this plan was opened.
- Candidate provenance and human feedback will be recorded in a companion acceptance document before HR.
- Next action: full PR independent review and immutable candidate builds in parallel; then verify artifacts and issue HR requests. Keep PR #46 updated with owner, source SHA, workflow/artifact links and outstanding gates. Wait for both human results before merge.
