# pyxy3d（补充项目）

## Repository

- Repository: <https://github.com/ubermensch19/pyxy3d> (README links/repository metadata point to the `mprib/pyxy3d` project)
- Checked on: `2026-08-27`
- Snapshot commit: `e8608bca3fed9de39147af8149d70f900aecf905`
- Default branch: `main`

## Purpose and relevance

pyxy3d is a PySide6/MediaPipe multi-camera calibration and 3D landmark-triangulation application. It is outside our initial single-camera scope but is a useful reference for a tracker plugin interface, per-camera worker ownership, synchronized frame packets, TOML configuration, gap filling, Butterworth smoothing and tidy CSV/TRC output.

## Technology Stack

| Area | Implementation observed |
| --- | --- |
| Language/GUI | Python, PySide6, Qt widgets |
| Tracking | MediaPipe Pose/Hands/Holistic implementations behind a `Tracker` ABC |
| Video/sync | OpenCV camera/video streams, per-port queues/threads, synchronized packets |
| Calibration | OpenCV intrinsics/ChArUco/extrinsics, bundle adjustment, world-origin setup |
| Data | dataclasses + Pandas tidy tables; TOML config/point-estimate files |
| Processing | stereo triangulation, linear gap fill, zero-phase Butterworth smoothing |
| Export | tidy CSV, TRC/OpenSim data and 3D playback |
| License | LGPL-3.0; adapted triangulation code from Anipose under BSD-2-Clause |

## Key Files

`pyxy3d/interface.py`

- `PointPacket` carries `point_id`, image locations, optional object locations and confidence.
- `FramePacket` carries camera port, frame index/time, image and `PointPacket`; `to_tidy_table(...)` makes CSV rows.
- `SyncPacket` groups per-camera frames and exposes `triangulation_inputs`/dropped-frame counts.
- `Tracker` ABC requires `get_points`, `get_point_name`, `draw_instructions`, with optional connected-point/metarig metadata.
- This is a compact example of a protocol shared by multiple tracking algorithms; add source/visibility/quality to our equivalent.

`pyxy3d/trackers/pose_tracker.py`, `hand_tracker.py`, `holistic_tracker.py`, `holistic_opensim_tracker.py`

- Implement MediaPipe tracking. `PoseTracker` creates one processing thread/queue per camera port, converts BGR→RGB, maps normalized landmarks to pixels and returns a `PointPacket`.
- Per-port ownership avoids sharing a MediaPipe context across camera streams.

`pyxy3d/configurator.py`

- `Configurator` creates/loads `config.toml` and `point_estimates.toml`, persists camera count/size/rotation/intrinsics/extrinsics, ChArUco settings and capture-volume stage.
- TOML is human-readable and supports incremental calibration stages, but the project does not provide schema migrations comparable to DLC/SLEAP.

`pyxy3d/calibration/intrinsic_calibrator.py`, `monocalibrator.py`, `stereocalibrator.py`, `calibration/capture_volume/*`

- Implement checkerboard/ChArUco detection, intrinsic/extrinsic calibration, capture-volume optimization and world-origin setting.

`pyxy3d/triangulate/sync_packet_triangulator.py`, `triangulation.py`

- Convert synchronized frame packets to 3D point rows; preserve point IDs, camera/frame time and calibration context.

`pyxy3d/post_processing/gap_filling.py`, `smoothing.py`

- `gap_fill_xy`/`gap_fill_xyz` group by port/point ID, reindex missing frame ranges, limit fill to `max_gap_size`, and interpolate linearly.
- `_smooth_xy`/`smooth_xyz` split data into contiguous frame groups and use zero-phase Butterworth filters with FPS/cutoff/order.

## Key data flow

```text
camera stream
  -> per-port tracker queue
  -> PointPacket
  -> FramePacket
  -> synchronized SyncPacket
  -> triangulation
  -> tidy xy/xyz CSV/TRC
  -> short-gap interpolation
  -> Butterworth smoothing
  -> 3D playback/export
```

## Tests/build/release

- `tests/test_calibration.py`, `test_intrinsic_calibrator.py`, `test_real_time_triangulator.py`, `test_xy_to_xyz.py`, `test_gap_fill.py`, `test_smoothing.py`, `test_export.py`, `test_synchronizer.py` cover major geometry/data stages with reference CSV/session data.
- `pyproject.toml` uses Poetry and Python 3.10–3.11, packages PySide6/MediaPipe/OpenCV and exposes `pyxy3d` CLI.
- No current Windows installer/release pipeline was found in the inspected files.

## License and data notes

- Code: LGPL-3.0; adapted Anipose triangulation: BSD-2-Clause.
- MediaPipe/OpenSim/model assets/reference sessions are separate review items. `Needs license review`.

## What to reuse

- Reuse: `PointPacket`/`FramePacket`/`SyncPacket` protocol, per-stream worker isolation, staged TOML config and gap/filter test patterns.
- Avoid: importing multi-camera/OpenSim complexity into the current phase; keep it as a future engine interface reference.
