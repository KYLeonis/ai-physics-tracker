# AI runtime components and sources

AI Physics Tracker uses an independent, editable Python environment. The host is
MIT-licensed; each downloaded component keeps its upstream license. The installer
verifies fixed versions and SHA256 before installation. It does not modify the
upstream Python/Torch/DLC source.

## Components

- DeepLabCut 3.0.1: **LGPL-3.0-or-later**. Original LICENSE, NOTICE.yml and AUTHORS
  are under `licenses/macos/packages/deeplabcut-3.0.1.dist-info/licenses/`.
  GPL-3.0 and LGPL-3.0 reference texts accompany the host under `resources/licenses/`.
  Source: <https://github.com/DeepLabCut/DeepLabCut/tree/v3.0.1>.
- Torch 2.13.0 / torchvision 0.28.0: BSD-3-Clause, with separately licensed bundled
  components. Original texts are under `licenses/macos/packages/torch-2.13.0.dist-info/`
  and `torchvision-0.28.0.dist-info/`, and remain in each installed wheel's dist-info.
  Sources: <https://github.com/pytorch/pytorch/tree/v2.13.0>,
  <https://github.com/pytorch/vision/tree/v0.28.0>.
- CPython 3.12.15 / python-build-standalone 20261001: original Python license plus
  third-party notices are under `licenses/macos/bootstrap/` and `licenses/windows/bootstrap/`.
  Their PYTHON.json records the distribution's component/build metadata.
  Sources: <https://github.com/python/cpython/tree/v3.12.15>,
  <https://github.com/astral-sh/python-build-standalone/tree/20261001>.

`manifest.json` records every dependency's fixed artifact URL, size, SHA256,
upstream license metadata and source URL; sdist hashes are included where PyPI
provides them. Wheel licenses/notices are retained during pip installation,
including Windows CPU/CUDA-specific bundled components. The macOS material
collection is a copy of the verified installed environment, not a declaration
that every Windows binary has identical bundled components.

Bootstrap notices were extracted from checksum-verified upstream full archives:

- macOS pgo+lto: `55745a8e72464507c44db62d1a3b7fac2214601cb0c09b6f85364fab49977bc8`
- Windows pgo: `aaf7786ecc3fa0bf13259359de6545148e37038a378232609ca14fb9c875170d`

Reproduction scripts in the source repository: `scripts/prepare_runtime_manifest.py`
and `scripts/prepare_runtime_licenses.py`. The advanced `AI_PHYSICS_RUNTIME_PYTHON`
override selects a user-provided compatible Python environment, including one
containing modified upstream libraries. No upstream license is replaced by the
application's MIT license.
