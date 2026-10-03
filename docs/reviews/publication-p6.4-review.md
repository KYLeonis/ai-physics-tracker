# P6.4 Independent Review — release preparation

## Scope / status

Reviewer `p6_4_preparation_review` (gpt-6-luna/max), read-only under the mini-plan
Review Gate. Base b459e4a; initial range6d8361f/9ebc37c, repairs4037ec7/4240a19.
Root implements; reviewer does not edit/install/change user projects.

This review covers the current **preparation checkpoint**, not public release
approval. Final verdict: **Approve preparation with limitations** through34236e6;
4a46a5c material-only supplement reviewed and verdict confirmed. Fixed-source
native candidate passes; exact-source final CI双平台success. Real Apple signing/notarization remains untested (0 valid
identities); cv2 GPL decision and source-distribution material are blocking
release gates, honestly recorded rather than declared passed.

## Findings and disposition

| ID | Finding | Repair / verification | Status |
| --- | --- | --- | --- |
| F1 Major | Filesystem-rglob worker/data inputs could include ignored/untracked files not represented by committed provenance | Clean-tree check includes visible untracked files; `validate_inputs` rejects extra/changed source/runtime/licenses even if ignored; expected worker set derives from committed hash map; candidate rechecks snapshot | Closed4037ec7; final4a46a5c native manifest passes |
| F2 Major | Privacy scan missed common videos, HDF5/checkpoints and PKCS8/DER; private text ≥1MiB was skipped | Expanded suffixes, all UTF8 text sizes; regression includesMKV/H5/P8 and2MiB text key. Native TLS constants now distinguished from textual private material; actual old App2456 items scanned | Closed4037ec7; final4a46a5c native manifest passes |
| F3 Minor | SOURCE-MATERIALS introduction said FFmpeg LGPL despite actual cv2 GPL closure | Distinguishes standalone LGPL FFprobe from cv2 GPL issue; no source MIT or license decision changed | Closed4037ec7, reviewer confirmed |
| F4 acceptance gap | Candidate did not associate build command or exact-source CI/evidence | Build command/options, exact-commit checks URL, companion evidence/review references added. CI status expressly not certified by local build | Reviewer confirmed fields; companions now created |

## Additional root fix

Native signature verification found added worker-src `__pycache__` after smoke.
4240a19 adds CPython `-B` at shared worker launcher; isolated real hello-worker
source copy remains byte-identical and no cache directory. Reviewer confirmed
correct CLI placement and meaningful regression test. Root external/release/wizard
63passed20.04s. Final4a46a5c native smoke and post-start signature verify0 pass,
114worker modules match and no __pycache__. Original1148-byte NVIDIA MIT notice
previously ignored by cudnn*/ is now tracked with a narrow exception; reviewer
confirmed delta4a46a5c, no new findings.

## Final gate

Final native candidate passes, exact-source CI双平台success. Missing Developer ID,
notary receipts, download HR, complete source material and Windows hardware are
explicit limitations, not findings closed by these code changes. User decision
is required before GPL remediation; public tag/Release still requires “发”.
