# v0.1.0 Mac source and build materials

Public unsigned Mac prerelease supplement, 2026-10-09. MIT applies to this
repository's application code; third-party libraries retain their own licenses
and copyright notices. Modification of libraries and reverse engineering for
debugging such modifications are permitted. Shared-library/process boundaries
are not asserted as automatic license exemptions.

## v0.1.0 Mac release supplement — 2026-10-09

All companion assets are served beside the binary at
https://github.com/KYLeonis/ai-physics-tracker/releases/tag/v0.1.0.
`SHA256SUMS` covers every upload except itself. `release-manifest.json` is the
unaltered CI snapshot; `release-decision.json` records subsequent user permission
for unsigned public prerelease. Binary build source is
`54638e484ca3160d2d335e8f78c0580bef21949a`, not a later documentation commit.
The DMG is ad-hoc signed, not Developer ID signed or Apple notarized.

### Downloadable corresponding source

- `AIPhysicsTracker-0.1.0-source.tar.gz`: exact application Git snapshot54638e4,
  including worker, PyInstaller spec, all build/replacement scripts, requirements,
  runtime artifact/source manifest, original license texts and MIT license.
- `AIPhysicsTracker-0.1.0-ffmpeg-sources.zip`: official unmodified FFmpeg7.1.1
  tarball (SHA733984395e0dbbe5c046abda2dc49a5544e7e0e1e2366bba849222ae9e3a03b1),
  actual OpenCV configure output, LGPL build commands and OpenCV replacement script/inputs.
  Standalone ffprobe buildconf is retained in the third-party source companion.
  The mounted final host libavcodec itself reports LGPL2.1+ and disable-gpl,
  disable-nonfree, disable-version3. It is not the old Homebrew GPL binary.
- `AIPhysicsTracker-0.1.0-third-party-sources.zip`: official unmodified Qt6.11.2
  qtbase/qtsvg/qtimageformats source archives and PySide/shiboken6.11.2 pyside-setup
  source archive, verified against Qt MirrorBrain published SHA256. Qt source
  includes its vendored components, LICENSES and CMake build scripts. These modules
  cover the actual delivered frameworks and image-format/platform/style/TLS plugins;
  no QtQuick/QML/WebEngine framework is distributed. No application changes to Qt.
  The archive also contains GNU GCC13.4.0 source plus its Homebrew Darwin patch, upstream SciPy release workflow
  and toolchain build materials for bundled libquadmath/libgfortran, and version
  corrections for timezone-package notices. `source-index.json` records exact
  URLs, commit/version, sizes, archive hashes and build-origin evidence.

The final mounted App's frozen scipy.__config__ identifies SciPy1.17.1,
Accelerate BLAS and **GCC13.4.0** Fortran. It contains libquadmath (LGPL2.1+)
and libgfortran (GPL3+ with GCC Runtime Library Exception3.1). The older macOS12
OpenBLAS wheel build instructions select GCC12.1; they do not describe this
macOS14 Accelerate build and are not used as source proof for this binary.
The versioned scipy-release workflow selects preinstalled gfortran-13 for
Accelerate. Included GNU GCC13.4.0 tarball SHA256 is
`9c4ce6dbb040568fdc545588ac03c5cbc95a8dbf0c7aa490170843afb59ca8f5`;
Homebrew's GCC13.4 Darwin patch SHA256 is
`60b22ae7f5f78b41e12c51d8c6e99ba933a7e124454fe8cdbff7200505167949`.
Source tarball, exact patch, historical compiler formula/build instructions,
release wheel workflow (SOURCE_REF_TO_BUILD=v1.17.1) and measured App compiler/BLAS metadata are included.
The compiler recipe is Homebrew/homebrew-core commit
`36f6d3a30a5f2d3c653bf90ca77425cfbbbfaadd`; the scipy-release workflow is commit
`a09f7a0f9639782b7d05243873b17c430da2fcc2`. Original LGPL text for libquadmath
is retained in NumPy's notice and the GCC source COPYING.LIB.

Actual CI host interpreter is official CPython **3.12.10**. The earlier local
3.12.13 reference is historical. Actual pytz/tzdata are **2026.5**; the original
2026.4-named bundled MIT/Apache texts are byte-identical to their 2026.5 wheel
counterparts. Correctly named copies and wheel URLs/hashes accompany this release;
we did not patch the signed bundle or misstate its inventory. Other actual host
packages/versions are recorded in release-manifest build.build_packages.
OpenCV's preserved libaom3.12.1 and libavif1.3.0 (Mach-O library ABI16.3.0) use
permissive BSD-style licenses retained in the original wheel THIRD-PARTY text;
source: https://aomedia.googlesource.com/aom/+/refs/tags/v3.12.1 and
https://github.com/AOMediaCodec/libavif/tree/v1.3.0. libaom also links libvmaf3.0.0
(BSD-2-Clause-Patent, copyright2020 Netflix, Inc.), source
https://github.com/Netflix/vmaf/tree/v3.0.0. Its missing original-wheel notice is
supplied in full in THIRD-PARTY-NOTICES.md, the source companion and Release body,
which are documentation provided with this binary distribution. Future builds
also collect packaging/licenses/libvmaf-3.0.0.LICENSE. CPython source:
https://github.com/python/cpython/tree/v3.12.10; PyInstaller6.22.3 source and
bootloader exception are identified above. This supplement is delivered separately
because the already verified DMG remains byte-identical to CI.

### Build and library replacement

Extract the exact application snapshot on Apple Silicon with Xcode command-line
tools and Python3.12. Initialize a local Git checkout/commit for the candidate
provenance script (the exported tarball has no .git); to retain original commit
identity instead clone the repository and checkout54638e4. Run:

```sh
git clone https://github.com/KYLeonis/ai-physics-tracker.git
cd ai-physics-tracker
git checkout 54638e484ca3160d2d335e8f78c0580bef21949a
bash packaging/build_macos.sh
```

The script creates its own build venv, records actual dependencies, builds the
FFmpeg libraries, repairs fixed OpenCV wheels and invokes PyInstaller. Leave
APT_CODESIGN_IDENTITY/APT_NOTARY_PROFILE unset for local ad-hoc builds. Historical
transitive versions are in the manifest: pin those versions explicitly when
reconstructing that dependency set; the current script's transitive resolution
is not a promise of identical binaries. A build from the source tarball has the
same code but a different local provenance commit. Apple credentials are unnecessary.

For a compatible modified Qt build, extract qtbase and build shared arm64 Qt with
`configure -opensource -confirm-license -prefix <your-qt-prefix>` and CMake;
then configure/build/install qtsvg and qtimageformats against that prefix. Follow
pyside-setup's included README/setup.py/build_scripts using that Qt prefix and
Python3.12 to build modified PySide6-Essentials/shiboken wheels. Install them in a
separate application build venv in place of the locked upstream wheel versions
and invoke the supplied PyInstaller spec (maintain FFprobe/OpenCV/build-info
resource environment variables from build_macos.sh). No code modification or
reverse engineering for debugging such library changes is prohibited.
Alternatively compatible framework/plugin replacement in a copied onedir app
must retain original install names/architecture and be locally re-signed ad-hoc;
the original signature will no longer verify after modification. These are
recombination instructions, not a tested bit-for-bit Qt/compiler rebuild.

GCC source contains top-level configure/build and libquadmath/Makefile/configure.
Apply the supplied gcc-13.4.0.diff with `patch -p1` from the extracted source
directory and follow the included Homebrew formula configure/make options.
Build in a separate prefix with GCC13.4 Darwin arm64,
then use compatible shared libquadmath/libgfortran in a rebuilt/copied app and
re-sign locally. No compiler is installed by this release preparation.

The AI runtime is separately downloaded and editable. Exact sources/sdist URLs,
original license texts and bootstrap compiler-source provenance are in the
application snapshot resources/runtime. imageio-ffmpeg remains a separate GPL
program; the Mac cv2 repair does not declare the complete runtime GPL-free.
Windows binaries are not assets of this release and receive no Mac-based closure
or hardware certification. Original project/videos/weights/private keys are absent.

Original independent runtime sources/license metadata and all artifact hashes are
in resources/runtime/manifest.json of the exact application snapshot. Managed
runtime uses PBS20261001/CPython3.12.15, DLC3.0.1, Torch2.13.0 and torchvision0.28.0;
the manifest specifies exact package sources and immutable artifact URLs. To use
modified compatible AI components, AI_PHYSICS_RUNTIME_PYTHON selects your separate
interpreter. Repair installs a new environment, leaving an existing one intact.

References: https://doc.qt.io/qt-6/lgpl.html and https://ffmpeg.org/legal.html.
