# 0.1.0 source and build materials

P6.4 review, updated 2026-10-07. This is a concrete source index, **not a declaration that
all release obligations are complete**. No public binary release has happened.
The application uses Qt and standalone FFprobe under their LGPL terms. On
2026-10-07 the user authorized replacing the actual Mac cv2 GPL FFmpeg closure
with a matching-major LGPL build; both host and newly installed runtime wheels
are repaired by the build scripts. Old installed environments are unchanged. Original license texts
and copyright notices accompany the app; MIT applies to this repository's code.
Modification of libraries and reverse engineering for debugging such modifications
are not prohibited. Process isolation is not used as an automatic licensing exemption.

## Exact source/build inputs

| Delivered component | Source and build material |
| --- | --- |
| Application + worker | Candidate manifest's exact `source_commit` in [repository](https://github.com/KYLeonis/ai-physics-tracker); `packaging/build_macos.sh`, spec and host lock at that commit. All tracked input hashes and actual build Python/package versions are embedded in `resources/build-info.json` |
| Qt 6.11.2 | [Qt 6.11.2 full source archive](https://download.qt.io/archive/qt/6.11/6.11.2/single/qt-everywhere-src-6.11.2.tar.xz), [versioned submodules](https://download.qt.io/archive/qt/6.11/6.11.2/submodules/). Actual Mac frameworks: Core/Gui/Widgets/Network/DBus/OpenGL/OpenGLWidgets/Test (qtbase), Svg (qtsvg). This inventory does not imply every Qt module is distributed |
| PySide6-Essentials/shiboken6 6.11.2 | [Exact QtForPython source](https://download.qt.io/official_releases/QtForPython/pyside6/PySide6-6.11.2-src/pyside-setup-everywhere-src-6.11.2.tar.xz). Locked unmodified PyPI wheels; PyInstaller relocates/re-signs the collected native libraries |
| Mac ffprobe 7.1.1 | [Official source](https://ffmpeg.org/releases/ffmpeg-7.1.1.tar.xz), SHA256 `733984395e0dbbe5c046abda2dc49a5544e7e0e1e2366bba849222ae9e3a03b1`; complete configure/build command in `scripts/build_ffprobe_lgpl.sh`. No upstream code patch, GPL/nonfree/version3 disabled; source source-link + original notices do not alone prove final distribution completeness |
| OpenCV 4.14.0.94 and its bundled FFmpeg/components | Raw wheel `LICENSE.txt`/`LICENSE-3RD-PARTY.txt` in `resources/licenses/`; [exact package source/build tag94](https://github.com/opencv/opencv-python/tree/94). **Actual Mac wheel/old App libavcodec61.19.101 declares FFmpeg7.1.1/Homebrew7.1.1_3, `--enable-gpl --enable-version3` with x264/x265**, unlike release notes mentioning8.1.2. Do not infer Mac binary contents from Linux/release headline or standalone ffprobe. Historical finding; repaired candidates use the LGPL replacement described below |
| CPython host | Actual patch version/build packages in `build-info.json`; [CPython source](https://github.com/python/cpython), corresponding patch tag. Native build interpreter is separate from AI runtime; current local build Python3.12.13 |
| AI Python/PBS | CPython3.12.15/PBS20261001; [CPython exact source](https://github.com/python/cpython/tree/v3.12.15), [PBS build scripts](https://github.com/astral-sh/python-build-standalone/tree/20261001); bootstrap archive URLs/SHA in runtime manifest, original per-platform PYTHON.json/third-party texts under `resources/runtime/licenses/` |
| DLC3.0.1/Torch2.13.0/torchvision0.28.0 and all runtime dependencies | Every artifact URL, size, SHA, license metadata and source/sdist URL/hash when available in `resources/runtime/manifest.json`; [DLC v3.0.1](https://github.com/DeepLabCut/DeepLabCut/tree/v3.0.1), [Torch v2.13.0](https://github.com/pytorch/pytorch/tree/v2.13.0), [vision v0.28.0](https://github.com/pytorch/vision/tree/v0.28.0). Original wheel notices retained; Torch/DLC remain separate. Repaired Mac OpenCV wheels are shipped as trusted installer resources |
| PyInstaller6.22.3 | [Exact source](https://github.com/pyinstaller/pyinstaller/tree/v6.22.3); original COPYING with bootloader exception in app's licenses. No installer framework on Mac, Apple's hdiutil creates DMG |
| Other host wheels | Fixed versions in host lock, original wheel texts under licenses; actual build closure/version list in embedded build-info. Numerical packages include their own bundled dependency notices |

## Replacement / recombination

The host uses shared Qt libraries in its onedir app; AI packages remain in a
separate editable runtime. For a modified compatible Qt/library build, check out
the candidate source, use the corresponding library/source build and build this
application with `APT_CODESIGN_IDENTITY` unset (ad-hoc), then test it locally.
Apple Developer ID private keys are not required to build an altered local copy.
Do not change an already signed app and expect its original signature to remain valid.
For modified compatible AI components, the existing `AI_PHYSICS_RUNTIME_PYTHON`
override selects the user's interpreter. These are developer instructions; ordinary
users install and manage the runtime in Settings.

## Material gate still pending before public release

Actual P6.3 final App path:
`Contents/Frameworks/cv2/__dot__dylibs/libavcodec.61.19.101.dylib`, SHA256
`77b55196650377557f90e43e18b03265919b1c20815520c3625ee5debfee5a76`.
`strings` confirms the complete Homebrew configure line (GPL/version3,
libx264/libx265/libxvid/libvidstab/librubberband). This is a measured issue, not
a hypothetical license concern. On 2026-10-07 the user authorized direct repair
with LGPL FFmpeg; source MIT stays. The old candidate is not the repaired package.

- Verify the rebuilt candidate's actual cv2 closure before making distribution claims.
  Match OpenCV wheel's actual bundled component versions/build sources, not just
  package-level metadata. Mirror/provide exact corresponding LGPL source and build
  material alongside the eventual binary download (including standalone FFprobe,
  Qt/PySide and cv2's applicable bundled libraries). Release links are not created yet.
- Lock/record native build interpreter provenance and dependent third-party source
  obligations. Original notices are available; a generic upstream link is not the
  same as proof of the exact binary's complete corresponding source.
- Windows material/CPU/CUDA inventories and hardware results are not inferred from
  Mac. The exact Windows FFprobe asset and source tag remain in its build script.

References: [Qt LGPL terms](https://doc.qt.io/qt-6/lgpl.html),
[FFmpeg official distribution guidance](https://ffmpeg.org/legal.html).
This gate remains pending until the actual downloadable materials are reviewed;
do not label S2 fully passed based on this index alone.

## Mac OpenCV replacement materials (2026-10-07)

`packaging/opencv_macos_inputs.json` pins three original wheel URLs/SHA/sizes: host
headless4.14.0.94 and runtime regular/headless4.11.0.86. `scripts/build_opencv_ffmpeg_lgpl.sh`
builds unmodified official FFmpeg7.1.1 from the same source SHA as standalone
ffprobe, with GPL/nonfree/version3/autodetect disabled. Only system libraries are
linked; major ABI is retained. `scripts/prepare_opencv_lgpl.py` changes install names,
prunes unused Homebrew libraries (including x264/x265), retains the non-FFmpeg
OpenCV closure, signs Mach-O and regenerates every wheel RECORD. This is library
replacement, not a full OpenCV source rebuild. OpenCV's compiled build-info remains
historical; actual libav* license/configuration and read/write/seek are checked.

Each candidate includes `opencv-lgpl/manifest.json` with original/new wheel hashes
and library hashes, copied into embedded build provenance. The companion
`AIPhysicsTracker-0.1.0-ffmpeg-sources.zip` contains exact FFmpeg source tarball,
actual configure output and build/replacement scripts/inputs; it is prepared for
publication beside the DMG, not uploaded yet. Source itself is unmodified.
LGPL2.1/GPL2 license texts are present in that source archive.

Repaired runtime wheels retain upstream name/version and original notices; the
installer logs replacements explicitly after validating original artifact identity
and new local SHA. Existing runtimes require Repair into a new directory. The
independent imageio-ffmpeg executable is a separate GPL component in the downloaded
AI runtime; this OpenCV fix does not claim the complete AI environment is GPL-free.
Qt/PySide and other corresponding-source materials still need final publication
review; source MIT and Windows not_run remain unchanged.
