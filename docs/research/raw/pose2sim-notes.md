# Pose2Sim

## Repository

- Official repository: <https://github.com/perfanalytics/pose2sim>
- Checked on: `2026-08-27`
- Snapshot commit: `65bbb056fecb3e6a7dd6064dc561bc065bc74bb6`
- Default branch: `main`

## Purpose

Pose2Sim turns multi-camera 2D pose detections into 3D marker trajectories and OpenSim kinematics. It performs camera calibration loading, pose/person association, weighted triangulation, gap handling, filtering, scaling and inverse kinematics.

## Relevance to AI Physics Tracker

Pose2Sim is the strongest reference for a scientific tracking-data pipeline after inference. It shows explicit stage directories, confidence-weighted geometry, reprojection-error quality control, TRC/MOT/C3D interchange and configurable filters. It is designed for multi-camera human biomechanics and depends on OpenSim; it is overkill for our initial single-camera pendulum but useful for future extensibility.

## Technology Stack

| Area | Implementation observed |
| --- | --- |
| Language | Python 3.11+ |
| Pose/inference | RTMLib/OpenMMPose/ONNX/OpenVINO, OpenPose JSON compatibility |
| Video | OpenCV; image/video folders and generated pose videos |
| Geometry | OpenCV camera calibration, projection matrices, weighted triangulation, reprojection |
| Association | keypoint/epipolar affinity and optional DeepSort/Sports2D tracking |
| Scientific processing | NumPy/Pandas/SciPy, OpenSim scaling and inverse kinematics |
| Filtering | Butterworth, Kalman, One Euro, GCV spline, acceleration-minimizing, Gaussian, LOESS, median, Hampel |
| Export | OpenPose JSON, TRC, C3D, MOT, BVH, plots, logs |
| Configuration | TOML with stage-specific sections |
| Packaging | setuptools-scm/PyPI, console scripts, included OpenSim setup assets |

## Repository Structure

```text
Pose2Sim/Pose2Sim.py          top-level staged workflow
Pose2Sim/poseEstimation.py   2D pose inference and JSON/video output
Pose2Sim/personAssociation.py multi-person/camera association
Pose2Sim/triangulation.py    weighted 3D reconstruction and TRC output
Pose2Sim/filtering.py        1D coordinate/IK filters and plots
Pose2Sim/kinematics.py       OpenSim scaling and inverse kinematics
Pose2Sim/calibration.py      camera calibration file creation/reading
Pose2Sim/common.py           I/O, geometry, coordinate helpers, tracking helpers
Pose2Sim/skeletons.py        skeleton/keypoint definitions
Pose2Sim/Utilities/           TRC/MOT/C3D/calibration conversion tools
Pose2Sim/OpenSim_Setup/       marker/scaling/IK/model assets
Pose2Sim/Demo_*/              single, multi-person and batch examples
.github/workflows/            CI/JOSS/PyPI release workflows
```

## Key Files

### Pipeline entry and stage layout

`Pose2Sim/Pose2Sim.py`

- The top-level workflow reads `Config.toml`, detects/loads configuration, then dispatches stages such as `poseEstimation.estimate_pose_all`, `personAssociation.associate_all`, `triangulation.triangulate_all`, `filtering.filter_all`, and `kinematics.kinematics_all`.
- The project convention is a directory per trial with `videos/`, `pose/`, `pose-sync/`, `pose-associated/`, `pose-3d/`, `kinematics/`, `calibration/`, and log files.
- The staged filesystem is useful for resumability and manual inspection; our project should use a similar raw/processed separation without copying its exact directory names.

`pose2sim.yaml`, `Demo_*/Config.toml`

- Configuration includes project directory/frame range/multi-person, pose model/backend/device/detection frequency, person association, triangulation thresholds/interpolation, filtering parameters, and OpenSim kinematics options.
- Many stages can be run independently against their persisted outputs.

### 2D pose inference and confidence

`Pose2Sim/poseEstimation.py`

- `setup_model_class_mode(...)` resolves built-in skeletons or custom model/skeleton definitions.
- `setup_backend_device(...)` selects CUDA+ONNX Runtime, ROCm, MPS/CoreML or CPU+OpenVINO depending on available providers.
- `setup_pose_tracker(...)` creates RTMLib `PoseTracker` with detection frequency and optional tracking.
- `process_video(...)` loops over frames, calls the pose tracker, filters detections, assigns stable people and writes OpenPose/MMPose/DLC-compatible JSON plus optional preview videos/images.
- `process_video_worker(...)` creates an independent pose tracker/DeepSort instance per worker, making parallel video processing possible without sharing model state.
- `estimate_pose_all(...)` resolves project videos, uses `get_max_workers(...)` for parallelism, and runs workers over input files.

### Person association

`Pose2Sim/personAssociation.py`

- `persons_combinations(...)` enumerates possible person IDs across camera views.
- `triangulate_comb(...)` performs confidence-filtered weighted triangulation and computes reprojection error.
- `best_persons_and_cameras_combination(...)` tries person combinations and progressively drops cameras when reprojection error is too high, subject to a minimum camera count.
- `compute_affinity(...)`, `matchSVT(...)`, and `associate_all(...)` address multi-person cross-view association.
- These quality-control ideas generalize to our future multi-object tracks: preserve per-observation confidence and an error/quality metric rather than only a final coordinate.

### Triangulation and missing data

`Pose2Sim/triangulation.py`

- `extract_files_frame_f(...)` reads OpenPose JSON files for one frame into x/y/likelihood arrays organized as cameras × persons × keypoints.
- `triangulate_all(...)` loads TOML camera parameters, projection matrices and skeleton/keypoint definitions, then loops over frames/keypoints, triangulates and reprojection-checks points, fills/interpolates short gaps and writes TRC.
- `indices_of_first_last_non_nan_chunks(...)` selects valid contiguous chunks using `largest/all/first/last` policies and minimum chunk size.
- `make_trc(...)` writes OpenSim-compatible TRC, converts Z-up to Y-up, stores frame/time and returns the output path.

`Pose2Sim/common.py`

- `weighted_triangulation(...)`, `reprojection(...)`, `euclidean_distance(...)`, `interpolate_zeros_nans(...)`, `zup2yup(...)`, `read_trc(...)`, `write_trc(...)`, `read_mot(...)`, and `write_mot(...)` are the reusable data/geometry primitives.
- `sort_people_sports2d(...)` and `sort_people_deepsort(...)` provide 2D identity association helpers used by Sports2D and pose estimation.

### Filtering

`Pose2Sim/filtering.py`

- `filter1d(...)` selects the configured filter function.
- `hampel_filter(...)` rejects outliers before smoothing.
- Filters split each signal into contiguous non-NaN/non-zero sequences; this avoids running zero-phase filters across missing-data gaps.
- `butterworth_filter_1d(...)` uses `scipy.signal.filtfilt`; `one_euro_filter_1d(...)` performs forward/backward adaptive smoothing; `gcv_spline_filter_1d(...)` estimates/limits smoothing strength; `acc_minimizing_filter_1d(...)` solves a sparse second-difference regularization problem; `kalman_filter(...)` models position/velocity/acceleration with optional RTS smoothing.
- `filter_all(...)` reads TRC or MOT, derives frame rate from timestamps, applies outlier rejection/filtering, optionally plots raw vs filtered values, and writes filtered TRC/MOT/C3D.

The split-by-valid-segment policy and explicit cutoff/config recap are directly useful for Phase 3. The current project should additionally record filter parameters and algorithm version as provenance in the processed-data layer.

### OpenSim kinematics

`Pose2Sim/kinematics.py`

- `perform_scaling(...)` derives segment ratios from filtered/valid 3D marker trajectories, updates OpenSim scale setup XML, and runs `opensim.ScaleTool`.
- `perform_IK(...)` updates an OpenSim IK setup and runs `opensim.InverseKinematicsTool`, producing `.mot` joint angle files.
- `kinematics_all(...)` resolves model/marker/scaling/IK setup files, supports per-person processing and optional parallel workers, logs OpenSim output, and can post-filter IK `.mot` files.
- This is a model-constrained route to angles rather than simple point-vector angle calculation; it is suitable for future advanced biomechanics but not the first pendulum MVP.

## Key call chain

```text
Config.toml
  -> poseEstimation.estimate_pose_all
  -> poseEstimation.process_video / OpenPose JSON + likelihood
  -> personAssociation.associate_all (optional multi-person/multi-camera)
  -> triangulation.triangulate_all
  -> weighted_triangulation + reprojection QC + gap interpolation
  -> pose-3d/*.trc
  -> filtering.filter_all
  -> filtered TRC/C3D
  -> kinematics.kinematics_all
  -> OpenSim scaling + IK
  -> kinematics/*.mot + logs
```

## Tests, build and release

- `Pose2Sim/Utilities/tests.py` is the main workflow/regression entry point; utility tests and demo data exercise calibration, synchronization, pose estimation, triangulation, filtering and kinematics.
- `.github/workflows/continuous-integration.yml` runs package checks; `publish-on-release.yml` handles PyPI publication; JOSS/Pages workflows build documentation/paper assets.
- `pyproject.toml` exposes many utility console scripts and packages OpenSim setup/demo assets.
- The repository has strong stage-level reproducibility but requires heavyweight OpenSim/pose dependencies and is not a turnkey Windows desktop application.

## License and data notes

- Code license: `BSD-3-Clause`.
- Model/setup files: OpenSim model, marker and setup assets are included, but OpenSim and any embedded model/geometry terms must be reviewed separately. `Needs license review`.
- Pose models: RTMLib/MMPose/OpenPose/ONNX model files are external and have separate terms. `Needs license review`.
- Demo videos/calibration data: review before redistribution.

## What to reuse

- Reuse: staged raw/processed directory layout, confidence-weighted data, reprojection/error QC, contiguous-valid-segment filtering, explicit TRC/MOT schemas, config-driven stages and recap logs.
- Avoid: pulling OpenSim into the Phase 1/2 single-camera core; make it an optional adapter later.
- Highest-value reading order: `Pose2Sim.py` → `poseEstimation.py` → `personAssociation.py` → `triangulation.py` → `common.py` → `filtering.py` → `kinematics.py`.
