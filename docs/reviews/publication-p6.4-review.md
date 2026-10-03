# P6.4 Independent Review — release preparation

## Scope / status

Reviewer `p6_4_preparation_review` (gpt-6-luna/max), read-only under the mini-plan
Review Gate. Base b459e4a; initial range6d8361f/9ebc37c, repairs4037ec7/4240a19.
Root implements; reviewer does not edit/install/change user projects.

This review covers the current **preparation checkpoint**, not public release
approval. Native fixed-source candidate proof and final reviewer verdict are
pending at this commit. Real Apple signing/notarization remains untested (0 valid
identities); cv2 GPL decision and source-distribution material are blocking
release gates, honestly recorded rather than declared passed.

## Findings and disposition

| ID | Finding | Repair / verification | Status |
| --- | --- | --- | --- |
| F1 Major | Filesystem-rglob worker/data inputs could include ignored/untracked files not represented by committed provenance | Clean-tree check includes visible untracked files; `validate_inputs` rejects extra/changed source/runtime/licenses even if ignored; expected worker set derives from committed hash map; candidate rechecks snapshot | Reviewer confirmed code fix, final build pending |
| F2 Major | Privacy scan missed common videos, HDF5/checkpoints and PKCS8/DER; private text ≥1MiB was skipped | Expanded suffixes, all UTF8 text sizes; regression includesMKV/H5/P8 and2MiB text key. Native TLS constants now distinguished from textual private material; actual old App2456 items scanned | Reviewer confirmed code fix, final build pending |
| F3 Minor | SOURCE-MATERIALS introduction said FFmpeg LGPL despite actual cv2 GPL closure | Distinguishes standalone LGPL FFprobe from cv2 GPL issue; no source MIT or license decision changed | Closed4037ec7, reviewer confirmed |
| F4 acceptance gap | Candidate did not associate build command or exact-source CI/evidence | Build command/options, exact-commit checks URL, companion evidence/review references added. CI status expressly not certified by local build | Reviewer confirmed fields; companions now created |

## Additional root fix

Native signature verification found added worker-src `__pycache__` after smoke.
4240a19 adds CPython `-B` at shared worker launcher; isolated real hello-worker
source copy remains byte-identical and no cache directory. Reviewer confirmed
correct CLI placement and meaningful regression test. Root external/release/wizard
63passed20.04s. Final native smoke must additionally preserve signature seal.

## Final gate

Pending final native candidate and commit-specific CI. Missing Developer ID,
notary receipts, download HR, complete source material and Windows hardware are
explicit limitations, not findings closed by these code changes. User decision
is required before GPL remediation; public tag/Release still requires “发”.
