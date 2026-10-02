# ADR-0022 — Pinned managed AI runtime bootstrap

- Status: Accepted (2026-10-02; user selected complete P6.2 and authorized implementation).
- Scope: publication worktree; supplements ADR-0021. Public tag/Release still requires explicit user authorization.

## Context

The lightweight native host must run annotation→training→inference without asking
ordinary users to configure Python. P6.1 already isolates external workers and
provides an atomic interpreter pointer. Shared development venv and user projects
must remain untouched. Windows real-machine gates remain deferred by user ruling.

## Decision

Use CPython 3.12.15 from python-build-standalone 20261001, fixed upstream asset
URLs/sizes/SHA256. Pin DLC 3.0.1, Torch 2.13.0, torchvision 0.28.0 and the complete
native dependency closures: Apple Silicon CPU/MPS (macOS 14+), Windows x64 CPU,
Windows x64 CUDA 13.0. Windows locks are generated on native CI runners; this is
dependency evidence, not a claim that CUDA hardware has passed acceptance.

Download verified artifacts into a private cache. Install each attempt into its
final UUID directory; never rename a venv whose launchers may hold absolute paths.
Use an OS file lock and an explicit cancellation/commit lock. Verify pip, Python
identity, exact core versions, Torch forward/backward and DLC import before the
last atomic replacement of `runtimes/active.txt`. Failures preserve the old pointer
and logs. A commit that wins the cancellation race reports success; a cancellation
that wins prevents activation. Keep old runtimes for repair/rollback diagnostics.

GUI polls a background installer using the existing timer pattern. Training/model
checks/inference are blocked during installation and receive the new interpreter
after success. Source mode defaults to its existing interpreter; only a verified
managed installation overrides it. Frozen mode retains the explicit environment
override for compatible user-modified libraries.

License correction: the verified DLC 3.0.1 artifact and upstream v3.0.1 LICENSE
are LGPL-3.0-or-later; older project records saying AGPL do not describe this locked
artifact. Source MIT is unchanged. Keep original notices, source links/digests and
bootstrap component metadata; host and downloaded runtime retain separate licenses.

## Consequences

First setup needs network and space, and first training may separately download
pretrained weights. Verified cached packages are reusable after retry; an incomplete
artifact is never installed. Already installed model inference runs offline.
Runtime changes require new model/device self-tests. Automatic updating, deleting
old environments, signing and Windows real-machine acceptance remain separate work.

Evidence and limitations: `publication/evidence/runtime/p6.2-validation.md`;
mini-plan: `publication/plans/p6.2-managed-runtime.md`.
