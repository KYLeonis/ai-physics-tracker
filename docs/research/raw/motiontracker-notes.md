# Motion Tracker Beta

## Repository

- Repository: <https://github.com/flochkristof/motiontracker>
- Checked on: `2026-08-27`
- Snapshot commit: `d8a6b60f32f84c39d616c6e03753ddf5bd546a5f`
- Default branch: `main`
- Snapshot package version in `pyproject.toml`: `0.1.7`

## Purpose

Motion Tracker Beta is a standalone PyQt5/OpenCV application for multi-object video tracking, calibration, numerical differentiation, plotting and export. It is one of the closest surveyed projects to our initial single-camera physics workflow.

## Relevance to AI Physics Tracker

It provides a compact end-to-end implementation of video controls, user point/rectangle selection, OpenCV trackers, a ruler, ROI, rotation tracking, background threads, PyNumDiff derivatives and PyInstaller packaging. Its main weaknesses are in-memory state/no project persistence, old GUI structure, broad exception handling and no confidence-aware learned tracker.

## Technology Stack

| Area | Implementation observed |
| --- | --- |
| Language | Python 3.12 |
| GUI | PyQt5 |
| Video/tracking | OpenCV `VideoCapture`, OpenCV legacy trackers (CSRT/KCF/MOSSE/etc.) |
| Physics | `PyNumDiff` finite-difference/smoothing/optimization algorithms |
| Plotting/export | Matplotlib, CSV/Excel-oriented export, annotated video |
| Persistence | Qt `QSettings` for last directory; tracking data remains in memory |
| Packaging | Poetry + PyInstaller `MotionTracker.spec`; Windows binary/installer documented |

## Repository Structure

```text
src/MotionTrackerBeta/main.py              QApplication entry point
src/MotionTrackerBeta/widgets/gui.py       main video UI and controls
src/MotionTrackerBeta/widgets/video.py     QLabel coordinate interaction
src/MotionTrackerBeta/widgets/trackers.py  QThread/OpenCV tracking loops
src/MotionTrackerBeta/widgets/process.py   derivative/post-processing thread
src/MotionTrackerBeta/widgets/export.py    annotated video export thread
src/MotionTrackerBeta/widgets/dialogs.py   tracking/processing/export/plot dialogs
src/MotionTrackerBeta/classes/classes.py   Motion/Rotation/Ruler data objects
src/MotionTrackerBeta/functions/differentiate.py PyNumDiff dispatch
src/MotionTrackerBeta/functions/transforms.py ROI/crop/coordinate helpers
MotionTracker.spec                          PyInstaller build specification
tests/                                      no substantive tests in snapshot
```

## Key Files

`src/MotionTrackerBeta/widgets/gui.py`

- `VideoWidget.openVideo()` creates `cv2.VideoCapture` and reads FPS/frame count/width/height.
- `nextFrame()` calls `camera.read()`, draws grid/ruler/tracks, crops/zooms, converts BGR→RGB and updates `QLabel`/`QSlider`.
- `JumpForward`, `JumpBackward`, `JumpStart`, `JumpEnd`, `positionVideo` use `CAP_PROP_POS_FRAMES` and a slider range of 0–10000.
- `StartPauseVideo()` drives playback with a Qt timer at approximately `1000/fps` ms.
- `savePoint`/`saveRectangle` create object observations; `setRuler`/`saveRuler` define pixel-to-mm scale; `setRoi` restricts tracking.
- The UI contains explicit controls for displayed region/point, tracking section, objects, ruler, ROI, rotation, post-processing and plotting/export.

`src/MotionTrackerBeta/widgets/video.py:VideoLabel`

- Emits `press`, `moving`, `release`, and `wheel` signals with normalized display coordinates.
- Handles image centering and coordinate conversion from QLabel/pixmap space back to video-relative space.
- The coordinate math is a useful warning: display zoom/pan must be represented separately from video-local pixel coordinates.

`src/MotionTrackerBeta/classes/classes.py`

- `Motion` stores raw `rectangle_path`, `point_path`, `size_change` and derived `position`, `velocity`, `acceleration` arrays.
- `Rotation.calculate()` computes a relative angle from two point paths using `atan2` and unwrap-like initial offset logic.
- `Ruler` stores two pixel endpoints, real distance `mm`, and `mm_per_pix`; `calculate()` computes the scale.
- This is a useful minimal data-object inventory but needs typed/versioned persistence and explicit units in our model.

`src/MotionTrackerBeta/widgets/trackers.py`

- `TrackingThread`/`TrackingThreadV2` are `QThread` workers with `progressChanged`, `newObject`, `success`, `rotation_calculated`, and `error_occured` signals.
- Each object can use an OpenCV tracker (`BOOSTING`, `MIL`, `KCF`, `TLD`, `MEDIANFLOW`, `MOSSE`, `CSRT`), initializes from a rectangle, and appends rectangle/point paths frame by frame.
- `TrackingThreadV2` initializes all trackers once and updates several objects together; `cancel()` flips `is_running` and clears failed paths.
- There is no continuous confidence score; OpenCV’s boolean `ret` is converted into a user-facing error/stop state.

`src/MotionTrackerBeta/widgets/process.py`

- `PostProcesserThread` is a dedicated worker for derivatives.
- For each `Motion`, it extracts x/y from `point_path`, calls `differentiate(...)` or `optimize_and_differentiate(...)` with `dt`, stores smoothed position and velocity/acceleration arrays, and reports progress/errors.
- The same thread processes `Rotation` into angular velocity/acceleration.

`src/MotionTrackerBeta/functions/differentiate.py`

- `differentiate(p, dt, parameters)` dispatches to PyNumDiff finite difference, median/mean/Gaussian/Butterworth/spline/Friedrichs smoothing, total variation regularization, spectral, Savitzky–Golay, polynomial and Chebyshev methods.
- Most methods are applied once to position→velocity and again to velocity→acceleration; `dt` is explicit.
- `optimize_and_differentiate(...)` uses PyNumDiff optimization to select parameters, which is a useful experiment for Phase 3 but should be isolated behind a tested interface.

`src/MotionTrackerBeta/functions/transforms.py`

- ROI/crop/coordinate transformation helpers map between the user display, ROI and video coordinates.
- Read alongside `gui.py` before implementing zoom/pan and track overlay drawing.

`src/MotionTrackerBeta/widgets/dialogs.py`, `functions/display.py`, `widgets/export.py`

- Dialogs expose algorithm/derivative/filter settings, progress bars, plot selection and export selection.
- `ExportingThread` reads frames, calls `display_objects(...)` and writes an annotated video in a worker thread.

## Key call chain

```text
VideoWidget.openVideo
  -> cv2.VideoCapture metadata
  -> QTimer.nextFrame / QSlider positionVideo
  -> user savePoint + saveRectangle
  -> TrackingSettings
  -> TrackingThread.run
  -> cv2 tracker.update
  -> Motion.point_path / rectangle_path
  -> PostProcesserThread.run
  -> PyNumDiff differentiate(p, dt)
  -> Motion.position/velocity/acceleration
  -> plot/export dialogs
```

## Tests, build and release

- The snapshot has only `tests/__init__.py`; there is no meaningful automated test suite for the tracking/physics path.
- `pyproject.toml` uses Poetry, pins Python `~3.12`, and exposes GUI console scripts.
- `MotionTracker.spec` enumerates hidden imports for PyQt5, SciPy, OpenCV, Matplotlib, PyNumDiff, CVXPY/CVXOPT and packages images/styles.
- README documents Windows binaries, installer releases and `poetry run pyinstaller MotionTracker.spec`, but no current CI release workflow was found.

## License and data notes

- Code license: `GPL-3.0`.
- PyNumDiff and OpenCV dependencies have separate licenses; review before copying/inlining.
- No model checkpoints; no standardized sample-data license map found.

## What to reuse

- Reuse: simple multi-object raw/derived data split, explicit `dt`, dedicated QThread workers/signals, ruler/ROI interaction, and PyInstaller hidden-import packaging checklist.
- Avoid: the 0–10000 slider as a canonical time model, in-memory-only `Motion` objects, broad `except` blocks, and treating a boolean tracker return as confidence.
- Highest-value reading order: `classes/classes.py` → `widgets/gui.py` → `widgets/trackers.py` → `widgets/process.py` → `functions/differentiate.py` → `widgets/export.py` → `MotionTracker.spec`.
