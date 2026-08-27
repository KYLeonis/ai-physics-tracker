# Sports2D

## Repository

- Official repository: <https://github.com/davidpagnon/Sports2D>
- Checked on: `2026-08-27`
- Snapshot commit: `4392177d75dff43b4da60514d3766029201a5c5e`
- Default branch: `main`

## Purpose

Sports2D estimates 2D human keypoints from a video/webcam, maintains person identities, computes joint and segment angles, optionally converts coordinates to meters with perspective/floor correction, and exports OpenSim-compatible pose/angle files and plots.

## Relevance to AI Physics Tracker

This is a useful markerless kinematics reference for the “tracking result → calibrated coordinates → angles → scientific export” half of our roadmap. It is not a general object tracker or desktop project manager: the pipeline is a large procedural function driven by TOML/CLI configuration, and its velocity/acceleration are not computed as a general physics engine.

## Technology Stack

| Area | Implementation observed |
| --- | --- |
| Language | Python 3.11+ |
| Video | OpenCV `VideoCapture`/`VideoWriter`; optional webcam/realtime display |
| Pose | RTMLib/MMPose/RTMPose/RTMO backends; ONNX Runtime/OpenVINO/OpenCV device backends |
| Person tracking | custom `sports2d` association or DeepSort |
| Coordinates | pixel coordinates, floor-angle/origin/perspective conversion, TOML calibration |
| Kinematics | joint/segment angle computation; optional OpenSim marker augmentation and IK through Pose2Sim |
| Plotting | Matplotlib/Qt tabbed windows; raw vs filtered comparison plots |
| Export | TRC, C3D, MOT, MP4/images, TOML calibration, logs |
| Packaging/config | `pyproject.toml`, setuptools-scm, TOML config, console entry points |

## Repository Structure

```text
Sports2D/Sports2D.py       CLI/config merge and per-video orchestration
Sports2D/process.py        video loop, pose association, angles, coordinate conversion, export/plots
Sports2D/Utilities/common.py  helper functions and plotting window
Sports2D/Demo/             demo video/config/calibration
Sports2D/Utilities/tests.py end-to-end demo workflow test
pyproject.toml              package metadata and Pose2Sim dependency pin
.github/workflows/          CI/build configuration inherited from package setup
```

## Key Files

`Sports2D/Sports2D.py`

- `read_config_file(...)` loads TOML.
- `base_params(...)` opens each input with OpenCV to read FPS and resolves video/time-range lists.
- `merge_dicts(...)` recursively merges partial Python/CLI overrides into `DEFAULT_CONFIG`.
- `process(...)` creates one output directory per video, configures logging, and calls `Sports2D.process.process_fun(...)`.
- `main(...)` exposes the CLI and converts flat CLI parameters into nested configuration values.

`Sports2D/process.py`

- `setup_video(...)`/`setup_webcam(...)` create OpenCV capture/writer objects.
- `process_fun(...)` is the main pipeline. It resolves model/skeleton, backend/device, time range, output paths, pose tracker, person-association options, calibration options and post-processing options.
- The main loop reads frames with `cap.read()`, runs RTMLib pose inference, filters detections using average likelihood/NMS, associates people, computes per-person angles, draws overlays and accumulates arrays.
- `load_pose_file(...)` bypasses inference and reuses a pixel TRC, which is useful for separating inference benchmarks from downstream kinematics benchmarks.

### Person tracking and confidence

`Sports2D/process.py` and imported `Pose2Sim.common`

- `tracking_mode` is `sports2d` or `deepsort`.
- `sort_people_sports2d(...)` accepts `match_by` (`keypoints`, `centroid`, `bbox`), optional displacement prediction, `max_distance`, `min_iou` and `max_unseen_frames`.
- Detection frequency can be >1: pose estimation still runs every frame while person detection can be less frequent.
- Low-likelihood keypoints become `NaN`; person filtering uses average likelihood and the number of valid keypoints.
- The resulting arrays preserve per-keypoint confidence separately from x/y coordinates, which should map to our `TrackPoint.confidence`/visibility fields.

### Angles

`Sports2D/process.py:compute_angle`, `compute_angles_for_person`

- `compute_angles_for_person(...)` resolves visible side (`auto`, `right`, `left`, `front`, `back`, `none`), flips x coordinates as needed, then calls `compute_angle(...)` for each configured angle.
- `compute_angle(...)` looks up keypoint names in `angle_dict` and delegates geometric angle math to `Pose2Sim.common.fixed_angles(...)`.
- Missing keypoints produce `NaN` rather than silently creating a value.
- Angle definitions are configuration/data, not hard-coded one-off GUI operations; this is a good pattern for a future pluggable physical-quantity registry.

### Pixel→meter coordinate processing

`Sports2D/process.py:get_floor_params`, `compute_floor_line`, `convert_px_to_meters`

- Calibration can come from a TOML file, explicit floor angle/origin, or an estimate from foot/ankle kinematics.
- `convert_px_to_meters(...)` corrects floor rotation, floor level and optional depth/perspective effects using camera center/focal or distance parameters and subject height.
- `Pose2Sim.calibration.toml_write` is used to save calibration metadata.
- This is a domain-specific monocular human-height/perspective model, not a general planar homography. For the single-pendulum baseline, a simpler explicit planar scale/axis transform is preferable.

### Filtering and gaps

Sports2D delegates filtering to the `Pose2Sim.filtering` module. Configuration exposes:

- Hampel outlier rejection;
- interpolation of gaps smaller than a configured frame count;
- large-gap policy (`last_value`, `nan`, `zeros`);
- section selection (`all`, `largest`, `first`, `last`);
- Butterworth, acceleration-minimizing, Kalman, One Euro, GCV spline, Gaussian, LOESS, median and Butterworth-on-speed options.

The pipeline writes raw/unfiltered and processed data separately for plotting. This is directly aligned with our “raw observations never overwritten” rule.

### Export and plots

`Sports2D/process.py:trc_data_from_XYZtime`, `make_trc_with_trc_data`, `make_mot_with_angles`, `pose_plots`, `angle_plots`

- TRC is written with OpenSim headers and X/Y/Z marker columns.
- MOT is tab-separated, declares `inDegrees=yes`, carries a `time` column and angle columns.
- Plots compare raw and filtered values per keypoint/angle and can either display Qt windows or save PNGs headlessly.
- Output paths are deterministic per video/person, e.g. `*_px.trc`, `*_m.trc`, `*_angles.mot`, graph directories and log files.

## Key call chain

```text
Sports2D.main/process(config)
  -> base_params/read_config_file
  -> process_fun(config_dict, video_file, time_range, frame_rate, output_dir)
  -> setup_video / setup_pose_tracker
  -> cap.read()
  -> pose_tracker(frame)
  -> NMS + likelihood filtering
  -> sort_people_sports2d or sort_people_deepsort
  -> compute_angles_for_person
  -> optional get_floor_params + convert_px_to_meters
  -> Pose2Sim.filtering.filter1d / gap interpolation
  -> TRC/MOT/MP4/PNG/log export
```

## Tests, build and release

- `Sports2D/Utilities/tests.py` is an end-to-end demo workflow test. It runs Python and CLI variants, a precomputed TRC path, different model/backend/tracking/filter settings, calibration, marker augmentation and IK.
- `pyproject.toml` defines the `sports2d` and `tests_sports2d` console scripts and pins a Pose2Sim Git commit for development installation.
- The project publishes to PyPI via setuptools metadata; no standalone Windows desktop installer is defined in this repository.

## License and data notes

- Code license: `BSD-3-Clause`.
- Model weights: RTMLib/MMPose/ONNX models are downloaded/used externally and are not automatically covered by the Sports2D BSD license. `Needs license review`.
- OpenSim/Pose2Sim and their model/setup assets have separate licenses/terms. `Needs license review`.
- Demo video/media: review before redistribution.

## What to reuse

- Reuse: nested TOML configuration with Python overrides, confidence→`NaN` policy, explicit raw/processed export, named physical quantity definitions, deterministic per-video output directories, and headless plotting mode.
- Avoid: coupling inference, GUI, plotting and export in one monolithic function. Extract our pipeline stages into typed services and keep the GUI as an orchestrator.
- Highest-value reading order: `Sports2D.py` → `process_fun` → `compute_angles_for_person` → `get_floor_params`/`convert_px_to_meters` → `Pose2Sim/filtering.py` → export functions.
