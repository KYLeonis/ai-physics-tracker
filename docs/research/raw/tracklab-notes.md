# TrackLab（TrackingLaboratory）

## Repository

- Current official repository: <https://github.com/TrackingLaboratory/tracklab>
- The requested `OpenPhysics/TrackLab` is a different repository; see [openphysics-tracklab-notes.md](openphysics-tracklab-notes.md).
- Checked on: `2026-08-27`
- Snapshot commit: `5767e86c32a6d6c68e2fc8ae7311f558fff6c7b2`
- Default branch: `main`

## Purpose

TrackingLaboratory TrackLab is a modular research framework for multi-object bounding-box and pose tracking. It is designed around configurable datasets, detectors, pose estimators, re-identification modules, trackers, evaluation and visualization rather than a desktop physics UI.

## Relevance to AI Physics Tracker

It is valuable as an adapter/inference architecture: modules declare input/output columns, engines decide online versus offline execution, and all intermediate detections are represented in Pandas tables. It is not a direct UI or kinematics reference, and its default `ExternalVideo` path currently expands video into JPEG frames, which is a useful warning for our long-video design.

## Technology Stack

| Area | Implementation observed |
| --- | --- |
| Language | Python |
| Configuration | Hydra/OmegaConf YAML groups and command-line overrides |
| AI | PyTorch, Lightning Fabric, Ultralytics/OpenMMLab/Transformers wrappers |
| Video/data | OpenCV, image files, Pandas DataFrames; external video helper materializes JPEG frames |
| Tracking | OCSort, ByteTrack, StrongSORT, DeepSORT, CAMELTrack and plugin wrappers |
| Evaluation | TrackEval/MOT metrics; callbacks and Rich/TQDM progress |
| Persistence | `.pklz` ZIP containing per-video pickled DataFrames plus `summary.json` |
| GUI | No desktop GUI; visualization is a callback/output video layer |

## Repository Structure

```text
tracklab/main.py                    Hydra entry point and pipeline assembly
tracklab/engine/                    dataset/video/offline engine execution
tracklab/pipeline/                  Module, Pipeline, level-specific abstract classes
tracklab/datastruct/                TrackingSet, TrackingDataset, TrackerState, datapipe
tracklab/wrappers/                  detector/pose/reid/tracker/dataset adapters
tracklab/callbacks/                 progress, timer, visualization and lifecycle hooks
tracklab/configs/                   engine/module/dataset/model YAML groups
plugins/track/                      vendored or plugin trackers
docs/                               architecture, installation and tutorials
tests/                              limited bundled tests plus package validation
pyproject.toml, uv.lock             package/dependency/build metadata
```

## Key Files

`main.py`, `tracklab/main.py`

- `tracklab.main.main(cfg)` initializes hardware/logging, instantiates the configured dataset/evaluator/modules, trains enabled modules, creates `TrackerState`, runs the selected engine, evaluates and saves.
- `compat`-style API is not the design center; Hydra config is. This is useful if our future engine registry needs CLI/config support, but the desktop application should expose a typed service API above it.

`tracklab/pipeline/module.py`

- `Module` declares `input_columns`, `output_columns`, `training_enabled`, `forget_columns`, and derives a module `name`/`level`.
- `Pipeline.validate(...)` walks modules in order and checks that every module’s inputs are provided by the dataset or previous modules, while accumulating outputs.
- This column-contract pattern is a strong reference for composing `manual`, `DLC`, `TAPIR`, `SAM2` and physics-processing adapters without hard-coding every engine.

`tracklab/pipeline/imagelevel_module.py`, `detectionlevel_module.py`, `videolevel_module.py`

- Define three module granularities: whole video, image, and detection.
- Each module separates `preprocess(...)` from `process(...)` and can expose a custom `datapipe`, `dataloader`, and `collate_fn`.
- `process` returns DataFrames/lists whose indexes must match the input rows; the engine merges outputs by index.

### Dataset and state model

`tracklab/datastruct/tracking_dataset.py`

- `TrackingSet` groups `video_metadatas`, `image_metadatas`, `detections_gt`, and `image_gt` DataFrames.
- `TrackingDataset` owns named sets/splits, filtering and subsampling by videos/frames, and MOT evaluation export.
- Video metadata rows carry fields such as name, fps/size in dataset implementations; image metadata rows carry `frame`, `video_id`, `file_path` and image identifiers.

`tracklab/datastruct/tracker_state.py`

- `TrackerState` keeps `detections_gt`, `detections_pred`, `image_pred`, video/image metadata and pipeline column requirements.
- It acts as a context manager per `video_id`, opening load/save ZIP files and limiting live memory to the current video.
- `save()` writes `summary.json`, `<video_id>.pkl`, and `<video_id>_image.pkl` into a `.pklz` ZIP with `pickle`/`pandas`.
- `load()` restores only the columns not replaced by the current pipeline, allowing a later run to skip already-computed stages.
- `__exit__()` closes files and drops `forget_columns`, which is a useful long-task memory policy.

### Execution engines and data flow

`tracklab/engine/engine.py`

- `TrackingEngine.track_dataset()` calls lifecycle callbacks around each video and delegates one-video execution to `video_loop(...)`.
- `default_step(...)` selects the module level, extracts the correct metadata/detections, invokes `model.process(...)`, then merges returned DataFrames through `merge_dataframes(...)`.
- `merge_dataframes(...)` adds new columns/rows with `NaN` and lets returned values override existing values.

`tracklab/engine/offline.py`

- `OfflineTrackingEngine.video_loop(...)` loads state, updates the module datapipe with image paths/metadata/detections, runs DataLoader batches per module, emits callbacks, and short-circuits when detections become empty.
- This is the clearest example for batch inference and GPU utilization across a pre-indexed video.

`tracklab/engine/video.py`

- `VideoOnlineTrackingEngine.video_loop()` uses `cv2.VideoCapture`, builds per-frame metadata (`id`, `frame`, `video_id`), and calls image/detection modules sequentially.
- It resets stateful modules per video, supports target FPS sampling, and emits `on_image_loop_start/end` callbacks.
- It is a prototype-style path and does not reuse the main `TrackingEngine.default_step` exactly; treat it as a pattern, not an API guarantee.

`tracklab/datastruct/datapipe.py`

- `EngineDatapipe.__getitem__` loads an image, selects matching detections/metadata, and calls the module’s preprocess method.
- This isolates file I/O and preprocessing from model execution.

### Progress and long-running work

`tracklab/callbacks/callback.py`, `progress.py`, `timer.py`

- Callback hooks cover dataset/video/image/module start/end and module step start/end.
- `TQDMProgressbar` and `RichProgressbar` subscribe to the same hooks; the engine does not know how progress is rendered.
- `Timer` reports per-video/module FPS. This callback protocol is a good basis for a GUI task event bus.

There is no GUI-thread bridge or cancellation contract comparable to SLEAP in this repository. A desktop integration would need to wrap engine calls in a worker and define cancellation/error events explicitly.

### Input/output and model reuse

`tracklab/wrappers/dataset/external_video.py`

- `ExternalVideo` creates a `TrackingSet` for arbitrary MP4/video input.
- `write_video_images_to_disk(...)` and its class docstring explicitly say the current implementation first writes frames to `tmp/<video>` JPEGs; the code marks direct MP4 support as TODO.
- This makes the metadata/dataframe schema easy to reuse but can multiply disk usage and adds a decode/write pass.

`tracklab/wrappers/track/oc_sort_api.py` (and sibling tracker wrappers)

- Each wrapper declares input/output columns and implements `reset`, `preprocess`, `process`.
- `OCSORT.process(...)` receives a batch, filters by confidence, runs the tracker, and returns rows indexed back to source detection IDs.

### Configuration and output layout

`tracklab/configs/config.yaml`

- The pipeline is a list of module names; engine, dataset, visualization, model and state are Hydra defaults/config groups.
- `state.load_file`/`save_file` support resumable `.pklz` execution.
- Hydra changes into a run directory and creates `outputs/<experiment>/<date>/<time>`; all logs/models/visualizations are grouped there.

`pyproject.toml`

- Entry point: `tracklab = tracklab.main:main`.
- Package data includes YAML configs; dependencies are extensive and GPU-centric.

## Key call chains

Offline:

```text
tracklab.main.main(cfg)
  -> instantiate dataset/evaluator/modules
  -> Pipeline(models)
  -> TrackerState(...)
  -> OfflineTrackingEngine.track_dataset()
  -> TrackerState(video_id).load()
  -> EngineDatapipe/DataLoader
  -> TrackingEngine.default_step()
  -> Module.process()
  -> merge_dataframes()
  -> TrackerState.on_video_loop_end() / save()
  -> evaluator.run()
```

Module extension:

```text
new ImageLevelModule
  -> input_columns/output_columns
  -> preprocess(image, detections, metadata)
  -> process(batch, detections, metadatas)
  -> DataFrame rows keyed by source index
  -> engine merge
```

## Tests, build and release

- `tests` are not a broad physics/GUI suite; the repository relies on module/evaluation tests and demos.
- `pyproject.toml` plus `uv.lock` define a modern Python package, but no Windows desktop installer workflow was found.
- Configuration and state snapshots make repeated experiments reproducible, but pickle-based state is Python/version-sensitive and should never be loaded from untrusted files.

## License and data notes

- Code license: `MIT` (`LICENSE` and GitHub metadata).
- Model weights: external detector/pose/ReID checkpoints have their own licenses; the repository does not make the entire model zoo one license. `Needs license review`.
- Dataset licenses: SoccerNet/MOT/PoseTrack and other datasets are external and separate. `Needs license review`.
- Output/state data: user/project data; pickle format has security implications.

## What to reuse

- Reuse: module input/output contracts, per-video state context, `merge_dataframes` semantics, lifecycle callback hooks, explicit offline/online engines, and output directory conventions.
- Adapt: replace DataFrame-only detections with our typed `TrackPoint`/observation schema at the application boundary, while allowing DataFrame export adapters.
- Highest-value reading order: `pipeline/module.py` → `engine/engine.py` → `datastruct/tracker_state.py` → `engine/offline.py` → `engine/video.py` → `callbacks/progress.py` → `ExternalVideo`.
