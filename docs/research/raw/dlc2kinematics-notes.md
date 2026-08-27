# DLC2Kinematics

## Repository

- Repository: <https://github.com/AdaptiveMotorControlLab/DLC2Kinematics>
- Checked on: `2026-08-27`
- Snapshot commit: `dd2b036a43843b1798af4604a49c3b38fd3104b6`
- Default branch in snapshot: `master`

## Purpose

DLC2Kinematics is a post-processing library for DeepLabCut output. It loads DLC HDF5 multi-index data, smooths trajectories, computes velocity/speed/acceleration, computes joint angles and angular derivatives, and supports plotting/PCA/UMAP/quaternion analysis.

## Relevance to AI Physics Tracker

It is a compact reference for the downstream API we will need after importing AI predictions, especially bodypart/name selection, confidence cutoff handling, joint definitions and HDF5 result persistence. It is not a project manager or GUI, is old relative to DLC 3.x, and should not be treated as the numerical gold standard without validation.

## Technology Stack

| Area | Implementation observed |
| --- | --- |
| Language | Python 3.8+ in metadata (legacy constraints) |
| Input/data | Pandas MultiIndex DataFrame from DLC HDF5; optional C3D |
| Math | NumPy, SciPy `savgol_filter`, scikit-kinematics/quaternions |
| Analysis | velocity, speed, acceleration, joint angles, angular velocity/acceleration, PCA, UMAP |
| Plotting | Matplotlib, optional 2D/3D visualization |
| Persistence | HDF5 with `df_with_missing` key; C3D reader/writer helpers |
| GUI/packaging | No GUI; setuptools/pytest/tox |

## Repository Structure

```text
src/dlc2kinematics/preprocess.py       DLC HDF5 loading and trajectory smoothing
src/dlc2kinematics/mainfxns.py         linear kinematics and dimensionality reduction
src/dlc2kinematics/joint_analysis.py   joint angles and angular derivatives
src/dlc2kinematics/utils/auxiliaryfunctions.py  geometry/confidence helpers
src/dlc2kinematics/plotting.py         Matplotlib plots/PCA visualization
src/dlc2kinematics/preprocess_c3d.py   C3D input
src/dlc2kinematics/quaternions.py      3D joint orientation derivatives
src/dlc2kinematics/_tests/             minimal test placeholder
setup.py, setup.cfg, tox.ini            legacy package/test configuration
```

## Key Files

`src/dlc2kinematics/preprocess.py`

- `load_data(filename, smooth=False, ...)` reads `df_with_missing` (or the default HDF5 key), returns the DataFrame, unique `bodyparts`, and `scorer`.
- `smooth_trajectory(...)` selects x/y(/z) columns from the DLC MultiIndex and applies `scipy.signal.savgol_filter` with `deriv=0/1/2`; likelihood columns are excluded and returned unchanged.
- Optional output is another HDF5 file under `df_with_missing`.

Important caveat: `smooth_trajectory` does not pass a physical `delta`/time step to SciPy’s Savitzky–Golay filter. Its derivative output is therefore per sample index unless the caller scales it externally. This must not be copied into our physics engine without an explicit `fps`/timestamp contract.

`src/dlc2kinematics/mainfxns.py`

- `compute_velocity(...)` and `compute_acceleration(...)` are thin wrappers over `smooth_trajectory(..., deriv=1/2)`.
- `compute_speed(...)` computes the norm of vector velocity while joining the original likelihood/probability columns.
- The code supports both single-animal and MultiIndex `individuals` layouts.
- `extract_kinematic_synergies(...)` and `compute_umap(...)` are exploratory analysis utilities, not core kinematics.

`src/dlc2kinematics/joint_analysis.py`

- `compute_joint_angles(df, joints_dict, pcutoff=0.4, smooth=False, save=True, ...)` filters low-probability 2D keypoints to `NaN`, applies a user-defined joint→bodypart dictionary, and computes row-wise angles using `auxiliaryfunctions.jointangle_calc`.
- Multi-animal columns are grouped by `individuals`; output names include the individual.
- Results are cached/saved in HDF5 under `df_with_missing`.
- `compute_joint_velocity(...)` and `compute_joint_acceleration(...)` apply Savitzky–Golay derivatives to the angle table and persist HDF5 outputs.
- `dropnan` is available for downstream PCA-like operations, but dropping rows changes temporal continuity and must be explicit in our API.

`src/dlc2kinematics/utils/auxiliaryfunctions.py`

- `check_2d_or_3d(...)` detects whether the coordinate level contains `z` or `likelihood`.
- `points_above_pcutoff(...)` changes x/y values to `NaN` when likelihood is below threshold.
- `jointangle_calc(...)` forms two vectors around the middle bodypart and uses quaternion shortest rotation; `jointquat_calc`, `calc_q_angle`, `calc_q_axis` provide 3D orientation helpers.
- `create_empty_df(...)` preserves the DLC scorer/bodypart/coord schema for transformed results.

`src/dlc2kinematics/plotting.py`

- `plot_velocity(...)` compares velocity with loaded position data.
- `plot_joint_angles(...)` plots selected angle columns; `plot_3d_pca_reconstruction(...)` reconstructs bodypart positions from principal components.
- Useful as post-processing visualization examples, but not suitable as a Qt-integrated plotting layer.

## Data flow

```text
DLC analyzed .h5 / MultiIndex DataFrame
  -> load_data
  -> confidence cutoff -> NaN for low-likelihood x/y
  -> smooth_trajectory(Savitzky-Golay)
  -> compute_velocity / compute_speed / compute_acceleration
  -> compute_joint_angles(joints_dict)
  -> compute_joint_velocity / compute_joint_acceleration
  -> HDF5 df_with_missing + Matplotlib plots
```

## Tests, build and release

- `src/dlc2kinematics/_tests/test_reader.py` currently contains `test_something(): pass`; it is not evidence of numerical correctness.
- `setup.py`/`setup.cfg` define legacy dependencies with restrictive NumPy/scikit-learn pins; `tox.ini` targets Python 3.8/3.9 on Linux/macOS/Windows.
- No current GUI or release/installer workflow was found.

## License and data notes

- Code license: the repository contains an Apache-2.0 `LICENSE` and source comments state that some functions were adopted from DeepLabCut under LGPL-3.0. `Needs license review` for file-level provenance before copying code.
- Model weights: none included; DLC model/checkpoint terms are external.
- Example HDF5/C3D files: data provenance/redistribution rights should be reviewed.

## What to reuse

- Reuse: a clear DataFrame column contract, named `joints_dict`, confidence→missing-value policy, and separate angle/linear kinematics functions.
- Fix before reuse: pass timestamps or `delta=dt`, preserve raw values and validity masks, handle gaps without row-dropping by default, and add analytical synthetic tests.
- Highest-value reading order: `preprocess.py` → `mainfxns.py` → `joint_analysis.py` → `utils/auxiliaryfunctions.py` → `plotting.py`.
