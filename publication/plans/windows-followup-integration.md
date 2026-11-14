# Windows follow-up — internal integration

- Date: 2026-11-14
- Status: awaiting_human_review
- Coordination worktree / branch: `/Users/leonis/Documents/ai-physics-tracker-ejp` / `codex/ejp-p6-4-release`
- Source worktree / branch: `/Users/leonis/Documents/ai-physics-tracker-windows-followup` / `codex/windows-followup`
- PR: [#46](https://github.com/KYLeonis/ai-physics-tracker/pull/46)
- Candidate source: `38628baf3a4b25543a49aef5bfa9b703bfa762b2`
- Review base: `23c0a227179c96e9a8a501634850b58825d1f38a`; original contribution range: `154f262..6a7a031`.

## Confirmed user decisions

Q1–Q3 confirmed on 2026-11-14: integrate PR #46 into the publication candidate work branch only; main backports and public releases are separate. Codex prepares a full independent review, same-source native candidates and concise acceptance instructions. The second author tests Windows; the first author tests Mac interactions. Merge only after review, native tests/builds and this change's human acceptance pass. CUDA, clean-machine G5 and student pilot remain separately deferred; do not mark them PASS from this task.

## Context Pack / invariants

Read `AGENTS.md`, `CODE_STANDARD.md`, `docs/workflow.md` §5.1/6/10, `publication/README.md`, ADR-0021/0022/0023, `publication/spec/runtime-boundary.md`, `publication/plans/p6.2-managed-runtime.md`, `docs/reviews/publication-p6.2-review.md` (F2/F3/F7), `docs/reviews/windows-followup-repair-review.md`, and the complete PR source/test diff.

The previous independent review started at `6a7a031` and covered repairs only. This review must also cover all original ten commits: download retry/resume, install reuse, Windows process flags and cleanup, arrow stepping, four-point auto-advance, crosshair/AI marker/Correct focus, hints and progress. Scientific algorithms, profiles/golden, schema, external-worker protocol, raw/AI activation and Undo contracts remain unchanged.

No new dependencies, GitHub settings changes, force pushes, project/data writes or public tag/Release. Existing published v0.1.0 is unchanged. Reviewers are read-only for product code; implementation fixes use append-only commits on the PR branch and receive proportional regression/re-review.

## Slices / acceptance

- [x] S1 Full independent review of `23c0a22..candidate`: all blockers resolved; findings/dispositions recorded in `docs/reviews/windows-followup-integration-review.md` (R2/R3 approve after fixes; F1–F7 Closed).
- [x] S2 Same exact source passes both native tests and packaging. Existing push filter accepts temporary candidate ref `codex/ejp-p6-windows-followup-candidate`; both workflows below are success at38628ba without merging or editing main.
- [x] S3 Downloaded both candidates; exact artifact IDs/size/SHA256, archive CRC, source identity and native smoke/signature evidence verified and recorded in the acceptance document. Windows text source uses CRLF, verified after LF normalization; no undocumented byte-exact claim. Product code changes require a new candidate generation.
- [x] S4 Each human has five operations, expected outcomes and closed questions in the acceptance document. Windows covers runtime reuse/Repair/cancel/retry, hidden-console behavior, keyboard/review/marking and a small CPU flow; Mac confirms affected interactions and runtime behavior. Feedback must identify tested source/package.
- [ ] S5 Both human acceptances recorded; no automated UI action substitutes for HR. If either reports a problem, fix and rebuild/retest the affected scope before merging.
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
- Same-source [tests43602320267](https://github.com/KYLeonis/ai-physics-tracker/actions/runs/43602320267) and [packaging43602320306](https://github.com/KYLeonis/ai-physics-tracker/actions/runs/43602320306) both success at38628ba. Mac1523 passed/7 skipped/1 existing xfailed; Windows1524 passed/6 skipped/1 existing xfailed. Both native packages passed frozen smoke; downloaded artifacts and local Mac packaged smoke verified.
- Candidate provenance and human feedback: [acceptance document](windows-followup-human-review.md). Mac fixture was copied from the existing synthetic T001 project, all132 files verified before preparation; only the review copy has12 manual points at frames0–2 removed, allowing the four-point behavior to be tested. Original project/video/model data remain untouched.
- Next action: stop and wait for Mac M1–M5 and Windows W1–W5 actual feedback on38628ba. F7 R3 approved, native validation/artifact verification passed. Keep PR #46 as handoff; on failure fix/rebuild/retest the affected scope. After both HR gates pass, resolve documentation-only integration conflicts and merge only into codex/ejp-p6-4-release, then verify the integrated tree. No source merging has occurred.
