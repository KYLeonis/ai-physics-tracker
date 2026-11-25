# Windows follow-up — internal integration

- Date: 2026-11-25（自 2026-11-14 基线滚动更新）
- Status: awaiting_human_review
- Coordination worktree / branch: `/Users/leonis/Documents/ai-physics-tracker-ejp` / `codex/ejp-p6-4-release`
- Source worktree / branch: `/Users/leonis/Documents/ai-physics-tracker-windows-followup` / `codex/windows-followup`
- PR: [#46](https://github.com/KYLeonis/ai-physics-tracker/pull/46)
- Candidate source: `d293dd1f4904f6be5608ba6269a1363262c5f9f5`（替代原候选 `38628ba`）
- Review base: `23c0a227179c96e9a8a501634850b58825d1f38a`; original contribution range: `154f262..6a7a031`, plus `35bb617` and repairs `5739bf5`, `781f001`, `d293dd1`.

## Confirmed user decisions

Q1–Q3 confirmed on 2026-11-14: integrate PR #46 into the publication candidate work branch only; main backports and public releases are separate. Codex prepares a full independent review, same-source native candidates and concise acceptance instructions. The second author tests Windows; the first author tests Mac interactions. Merge only after review, native tests/builds and this change's human acceptance pass. CUDA, clean-machine G5 and student pilot remain separately deferred; do not mark them PASS from this task.

## Context Pack / invariants

Read `AGENTS.md`, `CODE_STANDARD.md`, `docs/workflow.md` §5.1/6/10, `publication/README.md`, ADR-0021/0022/0023, `publication/spec/runtime-boundary.md`, `publication/plans/p6.2-managed-runtime.md`, `docs/reviews/publication-p6.2-review.md` (F2/F3/F7), `docs/reviews/windows-followup-repair-review.md`, and the complete PR source/test diff.

The previous independent review started at `6a7a031` and covered repairs only. This review must also cover all original ten commits: download retry/resume, install reuse, Windows process flags and cleanup, arrow stepping, four-point auto-advance, crosshair/AI marker/Correct focus, hints and progress. Scientific algorithms, profiles/golden, schema, external-worker protocol, raw/AI activation and Undo contracts remain unchanged.

No new dependencies, GitHub settings changes, force pushes, project/data writes or public tag/Release. Existing published v0.1.0 is unchanged. Reviewers are read-only for product code; implementation fixes use append-only commits on the PR branch and receive proportional regression/re-review.

## Slices / acceptance

- [x] S1 Full independent review of `23c0a22..d293dd1`: all blockers resolved; findings/dispositions recorded in `docs/reviews/windows-followup-integration-review.md` (R1–R5 approve after fixes; F1–F7 and R4/R5 findings Closed).
- [x] S2 Same exact source (`d293dd1`) passes both native tests (`45577876431` / `45577863310`) and packaging (`45577876955`) without merging or editing main.
- [~] S3 `38628ba` artifacts were downloaded & locally verified; for `d293dd1`, CI packaging (`45577876955`) artifact IDs (`15005611459` Mac / `15005281891` Windows), exact byte sizes, outer ZIP SHA256 digests and native frozen smoke (`smoke: ok`) are verified from CI logs (local download of `d293dd1` artifacts aborted due to Azure Blob throttling).
- [x] S4 Acceptance instructions updated for `d293dd1` (including W1 remaining subitems + UX-16/18/19/13b/W2 slider/device list and M1–M5).
- [ ] S5 Both human acceptances recorded; `38628ba` Windows W1–W5 feedback recorded (with `UX-18` FAIL and W1 reuse/Repair/diagnostics `NOT_RUN`), awaiting `d293dd1` Windows supplementary HR and first-author Mac M1–M5.
- [ ] S6 Merge PR #46 into `codex/ejp-p6-4-release` only after S1–S5; preserve original authorship, resolve documentation conflicts and verify the integrated code/tests against the accepted candidate. Confirm integration tests/packaging, synchronize docs and stop. Do not merge into main or `publication/ejp-damped-pendulum` in this task.

## Review Gate / responsibilities

- Independent review required: the full PR includes download/install/activation and worker lifecycle changes. Fresh reviewer session; product tree stays read-only. Reviewer owns the integration Review Record in the coordination worktree.
- Human Review required by workflow §5.1: original PR adds user-visible interactions. Both-platform CI/packaging are evidence, not human feedback.
- Codex owns preparation, implementation repairs, CI/artifact verification, instructions and PR handoff. Second author owns Windows native feedback; first author owns Mac human feedback. Missing feedback remains pending, never inferred.

## Evidence / handoff

- Prior source verification: [tests43212468799](https://github.com/KYLeonis/ai-physics-tracker/actions/runs/43212468799), `2edd01b`, Mac1505 passed/7 skipped/1 existing xfailed; Windows1506 passed/6 skipped/1 existing xfailed.
- Prior repair review: R2 modified then approved, limited to the repair range. This does not close S1.
- Complete PR review R1 found F1–F6; `109ef88` fixes all six. Independent R2 closed them (72 passed / 1 Windows-only skip). Implementation-agent targeted suite: 116 passed / 1 Windows-only skip. See [Review Record](../../docs/reviews/windows-followup-integration-review.md).
- Candidate generations (history retained): `2edd01b` tests43600270555 success, packaging43600270512 cancelled after review findings; `109ef88` tests43601805962 both-platform success, packaging43601805936 Windows failed because the old FFprobe URL returned404, Mac cancelled. Neither generation is issued for HR.
- `38628ba` fixes packaging F7 by pinning the retained October31 monthly LGPL FFprobe build and synchronizing NOTICE. The downloaded input is167778744 bytes, SHA256 `d4c2a42673917b4a97104a3e9f082729a9730796b98664e37c0b7eba6c6c613d`; ZIP CRC passed. Related ffprobe/launch/provenance tests61 passed / 1 Windows-only skip. Existing dependencies, architecture and MIT license remain unchanged.
- Same-source [tests45577876431](https://github.com/KYLeonis/ai-physics-tracker/actions/runs/45577876431) (plus PR-branch [45577863310](https://github.com/KYLeonis/ai-physics-tracker/actions/runs/45577863310)) and [packaging45577876955](https://github.com/KYLeonis/ai-physics-tracker/actions/runs/45577876955) both success at `d293dd1`. Mac `1532 passed / 7 skipped / 1 existing xfailed`; Windows `1532 passed / 6 skipped / 1 existing xfailed`. Local full pytest at `d293dd1`: `1536 passed, 3 skipped, 1 xfailed` (210.74s).
- Earlier `38628ba` candidate (`43602320267` / `43602320306`) received Windows HR feedback on 2026-11-24 (`W1–W5` PASS with `UX-18` FAIL and W1 reuse/Repair/diagnostics `NOT_RUN`), plus `35bb617` (`UX-16` cursor hiding). Fixes `5739bf5`, `781f001`, `d293dd1` resolved all findings and produced the new `d293dd1` candidate.
- Next action: wait for Mac M1–M5 and Windows `d293dd1` supplementary HR (`W1` remaining subitems + `UX-16`/`UX-18`/`UX-19`/`UX-13b`/slider/device list). After both pass, resolve doc conflicts and merge PR #46 into `codex/ejp-p6-4-release`.
