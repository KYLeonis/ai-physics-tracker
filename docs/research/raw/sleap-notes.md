# SLEAP

## Repository

- Official repository: <https://github.com/talmolab/sleap>
- Checked on: `2026-08-27`
- Snapshot commit: `6967e049debfe9a14818c5708c6c0dca1743e698`
- Default branch in snapshot: `develop`
- Snapshot package version: `1.6.5`

## Purpose

SLEAP is a desktop GUI/CLI workflow for labeling, training, inference, multi-instance tracking, proofreading and exporting pose data. The current architecture separates the GUI/glue package (`sleap`) from `sleap-io` (data/video/format model) and `sleap-nn` (PyTorch training/inference backend).

## Relevance to AI Physics Tracker

SLEAP is the strongest reference for annotation/correction UX and long-running task isolation. Its `Labels`/`LabeledFrame`/`Instance`/`PredictedInstance`/`Track` model, prediction-assisted labeling, frame seekbar, overlays and proofreading flow are directly applicable. The important architectural fact is that the current repository does not contain the complete neural backend: it delegates to versioned sibling packages.

## Technology Stack

| Area | Implementation observed |
| --- | --- |
| Language | Python 3.11–3.13 according to current `pyproject.toml` |
| GUI | PySide6 through `qtpy`, custom graphics view/overlays/docks |
| Video | `sleap-io` `Video` and media backends; OpenCV/imageio-ffmpeg compatibility helpers |
| AI | `sleap-nn[torch]` optional dependency; PyTorch models/training/inference in sibling repo/package |
| Data model | `sleap-io` `Labels`, `Video`, `LabeledFrame`, `Instance`, `PredictedInstance`, `Track`, `Skeleton` |
| Persistence | Native `.slp`; analysis HDF5/CSV/NWB/COCO/DLC import/export |
| Long tasks | QThread + subprocess CLI, structured JSON progress, cancellation/child-process kill |
| Packaging/CI | setuptools/uv metadata, platform/CUDA extras, GitHub Actions |

## Repository Structure

```text
sleap/gui/                  main window, state, commands, video widget, overlays, learning dialogs
sleap/sleap_io_adaptors/    compatibility and format/video helpers around sleap-io
sleap/io/                   format conversion/adaptor layer and analysis HDF5/CSV commands
sleap/info/                 inspection, analysis export and summaries
sleap/cli.py                unified CLI glue
tests/gui/                  GUI/widget/command/video tests
tests/io/                   format and conversion tests
pyproject.toml              BSD package + sleap-io/sleap-nn dependency boundaries
docs/learnings/             architecture, GUI and prediction-assisted labeling notes
```

## Key Files

### GUI state and commands

`sleap/gui/app.py`

- `MainWindow` creates `GuiState`, `CommandContext`, `ColorManager`, `QtVideoPlayer`, docks and overlay objects.
- The docstring describes the intended organization: `GuiState` owns transient/global UI state, `CommandContext` owns actions and update notifications, and `MainWindow.on_data_update()` refreshes affected views.
- Unsaved changes are tracked by the command context; view nodes listen to specific update topics rather than rebuilding everything.

`sleap/gui/state.py`, `sleap/gui/commands.py`

- `GuiState` provides observable state such as current video/frame/instance, visibility, trail length and selection.
- `CommandContext` exposes `loadProjectFile`, `saveProject`, `saveProjectAs`, `addVideo`, `importDLC`, `importAnalysisFile`, `exportAnalysisFile`, `exportCSVFile`, `exportNWB`, `exportLabeledClip` and package export methods.
- Each `AppCommand` declares `topics` and `does_edits`; `do_with_signal(...)` performs the action and notifies the GUI/change stack.
- This command/update-topic pattern is a useful alternative to putting business logic in widgets.

### Video player, frame navigation and correction UX

`sleap/gui/widgets/video.py`

- `QtVideoPlayer` wraps `sleap_io.Video`, a `GraphicsView`, `VideoSlider`, `GuiState`, overlay nodes and a background `FrameLoaderThread`.
- It registers frame next/previous/medium/large shortcuts and links `frame_idx` state to the slider and plot.
- It builds context-menu actions for “Add Instance” with several initialization methods (`best`, `template`, `force_directed`, `copy prior frame`, `random`), marking negative frames, merging instances and other correction actions.
- `ndarray_to_qimage(...)` carefully handles RGB/RGBA/uint8/uint16/float buffers and can detach the Qt image from NumPy memory.

`sleap/gui/widgets/slider.py`

- `VideoSlider` is the seekbar/frame-range control; it exposes frame selection and marks for labeled/suggested/proximity frames.
- Read with `MainWindow`/`QtVideoPlayer` to understand how frame selection and range review are surfaced.

`sleap/gui/widgets/video_worker.py`

- `FrameLoaderThread(QThread)` reads frames from a thread-local/deep-copied `sleap_io.Video` through a queue.
- It coalesces pending requests and processes only the latest frame, counting dropped requests; this avoids decoding every intermediate frame while the user drags a seekbar.
- It emits `frameReady(frame_idx, QImage)` and has explicit `stop()`/timeout/terminate cleanup.
- This is directly useful for our frame navigation performance and cross-thread ownership design.

`sleap/gui/overlays/instance.py`, `tracks.py`, `confmaps.py`, `negative_frame.py`

- Overlay objects render user/predicted instances, track trails, confidence maps and negative-frame status separately from the player.

### Data model, annotation and persistence

The canonical data classes live in `sleap-io`, imported here as `from sleap_io import Labels, Video, LabeledFrame, ...`.

- A `Labels` project contains videos, skeletons, labeled frames, user/predicted instances, tracks and provenance.
- `Instance` stores node coordinates; `PredictedInstance` adds point/instance/tracking scores; `LabeledFrame` associates instances with a video frame.
- This naturally separates annotation identity, predicted identity and tracking metadata better than a single `(x, y, confidence)` array.

`sleap/gui/commands.py`

- `LoadProjectFile`/`LoadLabelsObject` resolve video paths and load `.slp`/supported formats.
- `SaveProjectAs` calls `sleap_io.save_file(labels=labels, filename=filename, format=extension)`.
- `ImportDeepLabCut`, `ImportDeepLabCutFolder`, `ImportAnalysisFile`, `ExportAnalysisFile` and `export_dataset_gui(...)` bridge DLC, SLEAP analysis HDF5/CSV and project files.
- Native `.slp` retains the full project graph; analysis HDF5 is a flattened per-video result intended for downstream tools.

`sleap/io/convert.py`, `sleap/io/format/sleap_analysis.py`, `sleap/info/write_tracking_h5.py`

- `sleap-convert` reads/writes SLEAP `.slp`, analysis HDF5/CSV, LEAP `.mat`, DLC CSV/YAML and COCO JSON.
- Analysis HDF5 contains `track_occupancy`, `tracks`, `track_names`, `node_names`, `edge_names`, `edge_inds`, `point_scores`, `instance_scores`, and `tracking_scores`.
- `write_tracking_h5.py` builds occupancy/locations/scores matrices and removes empty tracks; this is a strong reference for dense scientific export with explicit confidence/visibility matrices.

### Training/inference and long-running tasks

`sleap/gui/learning/runners.py`

- `InferenceWorker(QThread)` launches `sleap predict` subprocesses, reads merged stdout/stderr, parses structured JSON progress (`n_processed`, `n_total`, status/error), emits progress/status/log/finished signals, and kills the process on cancel.
- `InferenceProgressDialog` shows a progress bar, scrollable log, cancel button and final success/failure state.
- `InferenceTask.make_predict_cli_call(...)` builds output paths and trained-job arguments.
- `train_subprocess(...)` launches `sleap train` in a subprocess, uses a waiting callback for cancellation, and writes/uses a per-run checkpoint/config directory.
- `run_gui_training(...)`, `run_gui_inference(...)` and `run_learning_pipeline(...)` coordinate training-mode choices (scratch/resume/use trained model), checkpoint paths and inference merging.
- The process boundary avoids importing heavy training code into the GUI event loop and makes cancellation of child processes explicit. This is the best long-task reference among the surveyed projects.

`sleap/gui/learning/main_tab.py`, `dialog.py`, `configs.py`

- Build typed/configurable training forms, select model profiles, inspect trained configurations and expose scratch/resume/reuse modes.
- Model config files are versioned and saved alongside the run; `best.ckpt`/`best_model.h5` discovery supports reuse/fine-tuning.

### Refinement and identity tracking

`sleap/gui/suggestions.py`, `sleap/gui/overlays/tracks.py`, `sleap/gui/commands.py`

- Prediction-assisted labeling and frame suggestions direct the user to likely problematic frames.
- Commands can toggle/merge/swap/remove tracks and instances; update topics keep the player/docks/overlays coherent.
- Read together with `docs/guides/tracking-and-proofreading.md` and `docs/tutorial/correcting-predictions.md` for the intended correction flow.

## Key call chains

Project/annotation:

```text
MainWindow
  -> CommandContext.loadProjectFile
  -> LoadProjectFile
  -> sleap_io.load_file / Labels
  -> GuiState + QtVideoPlayer + overlays
  -> user click/drag
  -> AppCommand.do_action
  -> Labels/LabeledFrame/Instance mutation
  -> update topics + unsaved-change state
```

Frame display:

```text
GuiState.frame_idx / VideoSlider
  -> QtVideoPlayer.plot/request frame
  -> FrameLoaderThread.request_frame
  -> thread-local Video[index]
  -> ndarray_to_qimage
  -> frameReady
  -> GraphicsView.setImage + overlays
```

Training/inference:

```text
LearningDialog / GUI config
  -> run_gui_training
  -> train_subprocess -> sleap train -> checkpoint/config/metrics
  -> InferenceTask
  -> InferenceWorker -> sleap predict
  -> structured progress/logs
  -> predicted .slp
  -> Labels.merge / proofread / export
```

## Tests, build and release

- The test tree is extensive for GUI and data integration: `tests/gui/test_video_player.py`, `test_commands.py`, `test_state.py`, `tests/gui/learning/*`, `tests/io/test_convert.py`, plus fixtures for `.slp`, HDF5, CSV, videos and model runs.
- `pyproject.toml` requires `python >=3.11,<3.14`, depends on `sleap-io[all]`, and places `sleap-nn[torch]` behind optional extras such as `nn-cpu`, `nn-cuda118`, `nn-cuda128`, `nn-cuda130`.
- `.github/workflows/ci.yml`, `build.yml`, docs and PR workflows define package checks; this repository does not provide a single Windows installer recipe in the inspected files.

## License and data notes

- Code license: The Clear BSD License (`LICENSE`).
- `sleap-io` and `sleap-nn` are separate packages and must be audited separately; do not infer their terms solely from `sleap`.
- Model checkpoints, pretrained backbones, sample videos and user datasets have separate provenance/terms. `Needs license review`.

## What to reuse

- Reuse: `Labels`-style separation of video/frame/annotation/instance/track, command/update-topic architecture, latest-frame coalescing in the decoder worker, frame-marked seekbar, subprocess training/inference with structured progress, resume/reuse checkpoint UX, and explicit analysis HDF5 score matrices.
- Avoid: coupling our core data model to `sleap-io` unless we deliberately choose it as a dependency; first define an adapter.
- Highest-value reading order: `gui/app.py` → `gui/commands.py` → `gui/widgets/video.py`/`video_worker.py` → `gui/state.py` → `gui/learning/runners.py` → `io/convert.py`/`format/sleap_analysis.py` → tests.
