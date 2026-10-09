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

## OpenCV LGPL continuation — 2026-10-07

The user subsequently authorized the OpenCV GPL FFmpeg repair and selected an
unnotarized test package (no Apple Developer membership). Required reviewer
`p6_4_opencv_review` (gpt-6-luna/max) worked read-only; root implemented and tested.
Range: 70f774a → 5fe09ca → final source 76f42c1. This continuation supersedes the
pending OpenCV authorization above; it does not close other release gates.

| ID | Initial finding | Repair / verification | Status |
| --- | --- | --- | --- |
| O1 / P2 | Reusing the FFmpeg build prefix could associate the current source SHA with stale compiled libraries | Each invocation now extracts verified source and compiles into a fresh directory; only tarball cached. Final native build/source zip checked | Closed |
| O2 / P2 | Source-material text still treated repair authorization as pending | Actual user authorization, replacement procedure and source materials recorded; MIT unchanged | Closed |
| O3 / evidence | Preliminary runtime installation used different wheel hashes from the final clean native build | Fresh private runtime installed using actual final App resources; ready wheel and six library hashes verified, then same interpreter completed 36-frame MPS inference | Closed |

Final verdict: **Approve with limitations**. Reviewer verified commit/source
inputs, App build info and OpenCV manifest at 76f42c1, all 2204 inventory entries,
DMG and both source archive copies, fixed FFmpeg tar SHA, exact final runtime
binding, bundled worker hash, native video smoke and signature, and both jobs in
each exact-source CI run 37622723056 / 37622723409. No blocking code/install
regression found. Root ran 41 targeted tests; reviewer did not run pytest.

Minor stale README/release-note decision wording was corrected in final docs.
Non-blocking public-build hygiene: FFmpeg configuration contains the local build
prefix path, not a secret; normalize for a future public candidate. Current
candidate is ad-hoc and Gatekeeper rejection is consistent with this scope.
Installation/Repair HR, Developer ID/public notarization, other release materials
and Windows hardware are pending. Windows CI is not hardware acceptance.

Exact candidate/runtime/CI evidence and HR steps:
`publication/evidence/runtime/p6.4-opencv-lgpl-validation.md`. No integration or
public tag/Release at this checkpoint; wait for installation/Repair HR.

## Local GUI follow-up — 2026-10-08

User confirmed previous Mac candidate playback/seek and runtime Repair/inference
HR passed, then reported Windows wheel zoom and dark top recommendation bugs.
This is a Normal-risk GUI repair under the continuation mini-plan; root self-review
and regression checks, not a new independent review or scientific/build change.
Source a13b4b1 restores ordinary vertical wheel zoom at the shared VideoView
handler, retaining touchpad/pixel/phase scrolling and no-frame/horizontal behavior.
Paired foreground/background resolves fixed pale hints under dark palettes.
Four viewport-wheel regressions failed before the fix; all 75 targeted GUI tests
pass after repair. Actual dark-palette top/guide foreground/background self-check
passes. Same-source tests37734658400 and packaging37734658340 are both successful
on macOS/Windows. New candidate Human Review remains pending; no merge/public
Release. This result does not promote the other Windows hardware gates.

## Unsigned Mac publication review — 2026-10-09

Required read-only reviewer `p6_4_publication_review` (gpt-6-luna/max), root prepared
materials and performed the publication. Exact binary source: 54638e4. Verdict:
**Approve with limitations**, contingent on root final remote asset verification;
that verification was subsequently completed for all 11 files before and after
publication. This is an unsigned Mac prerelease authorized explicitly by the user,
not a claim that all P6 production, Windows, or student gates have passed.

Reviewer checked actual mounted App inventory (2198 entries, 336650126 bytes),
ad-hoc seal, LGPL FFprobe/OpenCV dependency closure, Qt/PySide source/module
coverage, actual SciPy GCC13.4/Accelerate metadata and matching compiler source /
Darwin patch / upstream release workflow, original notices, archive CRC/SHA and
local checksum list. No pytest rerun for source/documentation distribution changes.

| Finding | Disposition | Status |
| --- | --- | --- |
| Missing VMAF full license in original wheel/App | Exact v3.0.0 BSD-2-Clause-Patent license supplied in release body, notice sidecar and companion source ZIP; tracked future build license added; original bundle untouched | Closed |
| Initial GCC12.1 inference from Mac12 OpenBLAS recipe did not describe actual bundle | Actual SciPy metadata GCC13.4/Accelerate checked; matching GCC13.4 source, Homebrew Darwin patch and v1.17.1 release workflow included; no bit-for-bit rebuild claim | Closed |
| Qt imageformats/compiler archives initially absent from source index | Final module coverage, sources, hashes and build materials indexed and verified | Closed |
| Source workflow described too broadly / stale timezone package versions | Wording narrowed to actual release workflow; pytz/tzdata2026.5 notices verified byte-identical to original embedded2026.4-named files, actual version table corrected | Closed |

Root remote check: release407616340, exactly11 uploaded assets, all names/sizes
and service SHA256 equal final local files; public draft=false/prerelease=true;
fetch tag v0.1.0 resolves54638e484ca3160d2d335e8f78c0580bef21949a. Reviewer did not
independently finish remote checks (transient TLS errors); root performed this gate.
Details: `publication/evidence/runtime/p6.4-v0.1.0-release.md`.
