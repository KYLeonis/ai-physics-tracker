# DeepLabCut

## Repository

- Official repository: <https://github.com/DeepLabCut/DeepLabCut>
- Checked on: `2026-08-27`
- Snapshot commit: `7833886b9be41f1d2313fad50bf4cedee6f0d301`
- Default branch: `main`
- Snapshot package version: `3.0.1`
- Phase 5 capability re-check: `2026-09-01`（本地已安装 wheel `3.0.1` + 官方 release/docs/main source）

## Purpose

DeepLabCut (DLC) is a trainable markerless pose-estimation system for user-defined bodyparts/features, with single- and multi-animal projects, training/evaluation/inference, tracklet stitching, refinement and model-zoo workflows. Current main code supports a PyTorch engine and retains a TensorFlow compatibility path.

## Relevance to AI Physics Tracker

DLC is the most directly aligned trainable engine for the current roadmap: sparse user labels → training dataset → checkpoint → video inference with per-keypoint likelihood → low-confidence/outlier refinement → retraining/model reuse. Its project directory and scorer/HDF5 conventions should be treated as an external adapter contract, not as our canonical domain model.

## Technology Stack

| Area | Implementation observed |
| --- | --- |
| Language | Python `>=3.10`; current metadata supports 3.10–3.12 |
| GUI | PySide6 main GUI; labeling/refinement delegated to `napari-deeplabcut` |
| Video | OpenCV/utility `VideoReader`, imageio-ffmpeg, project video folders |
| AI | PyTorch 2.x engine; legacy TensorFlow engine; torchvision/timm/Albumentations |
| Data | YAML project/config files, labeled images, JSON/COCO-style training data, HDF5/CSV/Pickle inference outputs |
| Plotting/export | Matplotlib/trajectory plotting, labeled videos, CSV/HDF5/NWB export |
| Long tasks | PyTorch runners, tqdm/logging; GUI workers/subprocesses depending on tab/backend |
| Packaging/CI | setuptools/pyproject, optional extras, GitHub Actions multi-OS/Python tests; no standalone installer in repo |

## Repository Structure

```text
deeplabcut/core/                       config, engine enum, inference/metrics/tracking utilities
deeplabcut/create_project/              project initialization and video registration
deeplabcut/generate_training_dataset/  frame extraction, label checks, train-set generation
deeplabcut/gui/                        PySide6 window/components/tabs and worker helpers
deeplabcut/pose_estimation_pytorch/    current PyTorch data/model/API/runner/config stack
deeplabcut/pose_estimation_tensorflow/ legacy TensorFlow stack
deeplabcut/refine_training_dataset/    outlier extraction and dataset merge
deeplabcut/modelzoo/                   SuperAnimal/generalized model inference
deeplabcut/utils/                      video I/O, HDF5/CSV helpers, visualization and project utilities
tests/                                 config, data, API, GUI, runner, inference and workflow tests
.github/workflows/                     CI, docs, intelligent test selection, Windows FFmpeg setup
pyproject.toml                         package metadata/dependencies/entry point
```

## Key Files

### Public API and engine selection

`deeplabcut/__init__.py`

- Re-exports project creation, dataset generation, train/evaluate/analyze/export, refinement and 3D APIs.
- GUI-heavy functions such as `label_frames`, `refine_labels`, `refine_tracklets` are lazy-loaded to avoid requiring GUI dependencies for headless use.

`deeplabcut/compat.py`

- Compatibility façade for TensorFlow/PyTorch API names.
- `train_network(...)`, `evaluate_network(...)`, `analyze_videos(...)`, `analyze_images(...)`, `create_tracking_dataset(...)` inspect `Engine` and dispatch to backend-specific implementations.
- This is the correct integration point for our `DLCAdapter`: call the stable façade, record the selected engine/version/config, and convert output into our `TrackPoint` schema.

`deeplabcut/core/engine.py`, `deeplabcut/core/config/project_config.py`, `base_config.py`, `validation.py`, `versioning.py`

- `Engine.PYTORCH`/`Engine.TF` select the backend.
- `ProjectConfig` is a typed/Pydantic-style representation of `config.yaml`, with validation/version migration and aliases for legacy fields.
- `PoseMetadata` in `pose_estimation_pytorch/config/metadata.py` builds normalized bodypart/individual/identity metadata from the project config.

### Project and annotation data

`deeplabcut/create_project/new.py`, `add.py`, `new_3d.py`

- Create a project root with `config.yaml`, video-set registrations and bodypart/individual metadata.
- The project is organized around named videos and `labeled-data/<video-stem>/` folders.

`deeplabcut/generate_training_dataset/trainingsetmanipulation.py`

- `comparevideolistsanddatafolders`, `dropduplicatesinannotatinfiles`, `dropannotationfileentriesduetodeletedimages`, `dropimagesduetolackofannotation`, `dropunlabeledframes`, and `check_labels` maintain consistency between config/video folders and `CollectedData_<scorer>.h5/.csv` labels.
- `create_training_dataset(...)` and related functions split/materialize annotations into the engine-specific training representation.
- Labels use a Pandas MultiIndex with scorer/bodypart/coords and are exported to HDF5/CSV. This is important for lossless conversion design in Phase 1.

`deeplabcut/pose_estimation_pytorch/data/dataset.py`

- `PoseDatasetParameters` captures bodyparts, unique bodyparts, individuals, center-keypoint and crop settings.
- `PoseDataset` loads image/annotation dictionaries, applies augmentation/cropping, handles bottom-up/top-down/conditional top-down tasks, produces tensors and annotation dictionaries, and carries offsets/scales needed to map predictions back to original image coordinates.

`deeplabcut/pose_estimation_pytorch/data/dlcloader.py`

- `DLCLoader` resolves project/config/model folders and builds the training/inference dataset and model configuration.
- It is a central reference for project→dataset→model path resolution.

### GUI and annotation/refinement UX

`deeplabcut/gui/window.py`

- `MainWindow` owns project config state, recent files, engine/shuffle signals, tabs, toolbar/status-bar progress and config monitoring.
- It creates the GUI shell but delegates label editing to napari.

`deeplabcut/gui/components.py`

- Shared `VideoSelectionWidget`, shuffle/snapshot selectors, layouts, project controls and safe signal-update helpers.

`deeplabcut/gui/tabs/label_frames.py`

- `label_frames(...)` resolves `labeled-data` folders and calls `launch_napari(...)` from the external `napari-deeplabcut` package.
- `check_labels(...)` renders/opens labeled images for QA.

`deeplabcut/gui/tabs/extract_outlier_frames.py`, `refine_tracklets.py`

- Expose outlier algorithms, track method selection, max-gap/trail settings and the loop `extract_outlier_frames → napari refinement → merge_datasets → recreate training dataset`.
- This is the closest existing active-learning/refinement UX to our Phase 5 flow.

`deeplabcut/gui/utils.py`

- `Worker`/`CaptureWorker` wrap callable work in `QThread`, marshal exceptions through `error`, and always emit `finished`.
- `move_to_separate_thread(...)` moves the worker to a thread and quits/waits when finished.
- This helper is used by `gui/tabs/analyze_videos.py`, which disables buttons, shows the progress bar, runs inference/post-processing and restores UI state on completion/error.
- Important asymmetry found in this snapshot: `gui/tabs/train_network.py:TrainNetwork.train_network()` calls `compat.train_network(...)` directly rather than using `move_to_separate_thread`. Do not assume the DLC GUI always keeps the UI responsive; wrap our own training call in a dedicated task/subprocess boundary.

### Training, checkpoints and model reuse

`deeplabcut/pose_estimation_pytorch/apis/training.py`

- `train_network(...)` constructs `DLCLoader`, applies CLI/API config overrides, optionally creates memory-replay data, handles top-down detector training, logs config changes, selects a `Task` and calls `train(...)`.
- `train(...)` builds the PyTorch model, logger, transforms, train/test `DataLoader`s and `build_training_runner(...)`; it reports dataset sizes and supports snapshot resume.

`deeplabcut/pose_estimation_pytorch/runners/train.py`, `runners/base.py`, `runners/logger.py`

- Runner classes own the epoch/batch loop, validation, metrics and logging. `BaseLogger`, `WandbLogger` and file logging separate metrics/visualization from the GUI.
- GUI-independent logging is a good model for a task event stream: progress, metrics, log lines, checkpoint path and error should be emitted by the backend.

`deeplabcut/pose_estimation_pytorch/runners/snapshots.py`, `data/snapshots.py`

- `TorchSnapshotManager.update(...)` saves periodic and best snapshots, optionally optimizer state, enforces a maximum number of regular snapshots, and names files such as `snapshot-050.pt`/best snapshot.
- `Snapshot`/`list_snapshots(...)` provide model discovery and scorer UID generation.
- The model folder and snapshot path are part of the project metadata; model reuse must include model config, task, bodyparts, engine and checkpoint identity.

### Inference and result formats

`deeplabcut/pose_estimation_pytorch/apis/videos.py`

- `VideoIterator` reads video frames and can carry per-frame context (e.g. top-down boxes/conditional pose data).
- `video_inference(...)` builds/uses an `InferenceRunner`, optionally detector runner and `ShelfWriter`, reports video metadata, runs batched predictions and returns predictions or writes them on the fly.
- `analyze_videos(...)` resolves project/model/snapshot/config, chooses bottom-up/top-down/CTD behavior, loops videos, writes metadata/full pickle/HDF5/CSV, creates multi-animal assemblies, optionally converts detections to tracklets and stitches tracks.

`deeplabcut/pose_estimation_pytorch/runners/inference.py`

- `InferenceRunner.inference(...)` supports sequential or asynchronous preprocessing. `_prepare_inputs`, `_process_batch`, `_extract_results`, `_async_inference` and `_preprocessing_worker` decouple image loading/preprocessing from model batches.
- Postprocessors return structured arrays including bodypart coordinates and scores; context carries offsets/scales for inverse transforms.

`deeplabcut/pose_estimation_pytorch/data/postprocessor.py`

- `build_bottom_up_postprocessor`, `build_top_down_postprocessor`, `ConcatenateOutputs`, `RescaleAndOffset`, `PadOutputs`, identity assignment and confidence filtering normalize model outputs.
- This is the right place to understand how prediction arrays become stable `(x, y, likelihood)` records.

`deeplabcut/pose_estimation_pytorch/runners/shelving.py`

- `ShelfWriter` stores per-frame predictions in Python `shelve` files, writes metadata (`nframes`, joints, PAF graph, thresholds), and keeps memory roughly constant for long videos.
- It stores coordinates and confidence separately and can also store identity scores/features.

`deeplabcut/pose_estimation_pytorch/apis/videos.py:create_df_from_prediction(...)`

- Converts predictions to a Pandas MultiIndex `(scorer, bodyparts, coords)` or `(scorer, individuals, bodyparts, coords)` DataFrame with `coords = x/y/likelihood`.
- Saves HDF5 under `df_with_missing`, optionally CSV, while `*_full.pickle` retains richer prediction data.

### Long-running task boundary and progress

The current code has three patterns:

1. backend progress/logging through `tqdm`/logging;
2. GUI-side `Worker`/`QThread` for analysis tabs;
3. the current SLEAP-inspired subprocess/structured-progress approach is not consistently used for DLC training.

For AI Physics Tracker, define one task abstraction for training/inference/export with cancellation, progress events, metrics/log stream, checkpoint/result paths and failure state, then adapt DLC behind it.

## Key call chains

Training:

```text
GUI TrainNetwork.train_network
  -> deeplabcut.compat.train_network
  -> get_shuffle_engine + ProjectConfig
  -> pose_estimation_pytorch.apis.training.train_network
  -> DLCLoader
  -> PoseDataset/DataLoader
  -> build model + training runner
  -> TorchSnapshotManager / logger
  -> snapshot-*.pt + metrics/logs
```

Video inference:

```text
GUI AnalyzeVideos._run_pipeline
  -> deeplabcut.analyze_videos
  -> compat.analyze_videos
  -> DLCLoader + snapshot selection
  -> get_pose_inference_runner / optional detector runner
  -> VideoIterator
  -> InferenceRunner.inference
  -> preprocessing -> model.predict -> postprocessor
  -> likelihood/confidence arrays
  -> *_full.pickle / *_meta.pickle / *_h5 / *_csv
  -> optional convert_detections2tracklets -> stitch_tracklets
```

Refinement:

```text
low-confidence/outlier video result
  -> extract_outlier_frames
  -> napari-deeplabcut label/correction GUI
  -> merge_datasets
  -> create_training_dataset again
  -> train_network resume/fine-tune
```

## Tests, build and release

- The repository has a substantial test tree: `tests/core/config/*`, `tests/generate_training_dataset/*`, `tests/pose_estimation_pytorch/apis/*`, `tests/pose_estimation_pytorch/data/*`, `tests/pose_estimation_pytorch/runners/*`, `tests/gui/*`, `tests/test_video.py`, `test_trackingutils.py`, `test_triangulation.py` and more.
- `tests/gui/test_worker.py` specifically verifies that worker exceptions emit an error and that the thread quits; this is a good regression-test pattern for our task manager.
- `.github/workflows/python-package.yml` installs on Ubuntu/macOS/Windows across Python 3.10–3.12, runs targeted/full pytest and installs FFmpeg on each platform. The Windows lane downloads a pinned BtbN shared FFmpeg build and verifies `ffmpeg`/`ffprobe`.
- `.github/workflows/intelligent-testing.yml` selects affected tests/workflows based on changed files and can run docs, fast targeted tests or the full matrix.
- `pyproject.toml` packages Python/config/assets and exposes `dlc = deeplabcut.__main__:main`; no Inno Setup/MSIX/PyInstaller desktop installer is included.

## License and data notes

- Code license: `LGPL-3.0-or-later` (`pyproject.toml`, source headers, GitHub metadata). The legacy TensorFlow subdirectory also carries license text.
- Model weights: the repository contains model-zoo/configuration code, but downloaded SuperAnimal/pretrained checkpoints and third-party backbone weights do not automatically inherit the code license. `Needs license review` per model/checkpoint.
- Dataset/data format: user labels are user data; sample/benchmark data and external model training data require separate review.
- External GUI `napari-deeplabcut`, PyTorch/TorchVision/timm, FFmpeg and other dependencies have their own license obligations.

## What to reuse

- Reuse: `ProjectConfig`/metadata concepts, labels→training dataset conversion, `InferenceRunner` pre/postprocessor separation, `ShelfWriter` long-video streaming, snapshot manager, explicit per-keypoint likelihood, outlier/refinement loop and testable `Worker` error semantics.
- Avoid: using DLC’s HDF5/Pickle files as the only internal model; retain an adapter that maps to our own versioned `TrackPoint`/`Annotation` model.
- Highest-value reading order: `compat.py` → `core/config/project_config.py` → `generate_training_dataset/trainingsetmanipulation.py` → `pose_estimation_pytorch/apis/training.py` → `runners/train.py`/`snapshots.py` → `apis/videos.py` → `runners/inference.py`/`postprocessor.py` → `gui/utils.py` and `gui/tabs/analyze_videos.py` → tests.

## Phase 5 capability re-check（2026-09-01）

复核对象：项目 `.venv` 中的 DeepLabCut 3.0.1 wheel、官方 3.0.1 release、当前官方开发文档与
`DeepLabCut/DeepLabCut` main source。PyPI/GitHub 当前稳定版仍为 3.0.1：

- Release: <https://github.com/DeepLabCut/DeepLabCut/releases/tag/v3.0.1>
- PyPI: <https://pypi.org/project/deeplabcut/3.0.1/>
- Frame extraction API: <https://deeplabcut.github.io/DeepLabCut/dev/main/reference/deeplabcut/generate_training_dataset/frame_extraction/>
- Outlier source/API: <https://github.com/DeepLabCut/DeepLabCut/blob/main/deeplabcut/refine_training_dataset/outlier_frames.py>
- Standard refinement workflow: <https://github.com/DeepLabCut/DeepLabCut/blob/main/docs/standardDeepLabCut_UserGuide.md>
- PyTorch resume configuration: <https://deeplabcut.github.io/DeepLabCut/docs/pytorch/pytorch_config.html>

### Frame extraction

- `extract_frames(..., mode="automatic", algo="kmeans"|"uniform")` 是公开 API。
- `uniform` 在指定 start/stop 区间随机抽取时序分布帧；`kmeans` 将降采样帧展平后用
  `MiniBatchKMeans` 聚类，每簇选一帧。`cluster_step`、`cluster_resizewidth` 与 `cluster_color`
  控制长视频成本和颜色信息。
- 高层 API 写入 `labeled-data/<video>/imgNNN.png` 且返回 `None`；底层
  `UniformFramescv2`/`KmeansbasedFrameselectioncv2` 返回 frame indices。
- Phase 5 因 UI 需要 frame indices 而不是让 DLC 直接拥有标签状态，适合由 `DLCAdapter` 包装底层
  selector；算法本身不重写，随机 seed 和 DLC 版本随建议批次记录。

### Outlier frames

- 单目标 analyzed DataFrame 支持 `uncertain`（likelihood `< p_bound`）、`jump`（相邻坐标距离
  `> epsilon`）、`fitting`（SARIMAX 拟合残差），以及 manual/list 模式。
- 检出的 indices 会去重，再由 uniform 或 K-means 选 `numframes2pick`，最后写入
  `labeled-data`/`machinelabels`；函数不返回带 component score/reason 的排序对象。
- 所以 Phase 5 直接复用原始 HDF5/likelihood、DLC 的规则定义与 K-means primitive，但候选合并、
  分数归一化、时序去重、跨信号排序和解释由本项目策略层负责。高层
  `extract_outlier_frames` 保留为对照基线，不作为唯一产品实现。

### Refinement、fixed split 与 retraining

- DLC 原生闭环是 `extract_outlier_frames → refine_labels(napari) → merge_datasets →
  create_training_dataset → train_network`。`merge_datasets` 更新 DLC config iteration。
- 本项目已有 canonical manual `TrackPoint`、prediction provenance、Undo/Redo 和自己的 GUI；直接嵌入
  napari refinement 会形成第二套 ground truth，因此 Phase 5 不直接使用 `refine_labels`/
  `merge_datasets` 作为内部状态机，而是每轮重新导出 canonical manual labels。
- `create_training_dataset` 明确接受 `trainIndices`/`testIndices`；`mergeandsplit` 文档也将此称为
  freeze a split。Phase 5 可用它维持 fixed validation membership。
- PyTorch `train_network` 公开 `snapshot_path`、`epochs`、`batch_size`、`device` 等参数；
  `evaluate_network` 可指定 snapshot 或评估全部 snapshots。第一版 Advisor 可直接建议这些已支持参数，
  无需先进入 optimizer/scheduler/HPO。
