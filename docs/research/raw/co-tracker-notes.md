# CoTracker

## Repository

- Official repository: <https://github.com/facebookresearch/co-tracker>
- Checked on: `2026-08-27`
- Snapshot commit: `82e02e8029753ad4ef13cf06be7f4fc5facdda4d`
- Default branch: `main`

## Purpose

CoTracker is a transformer-based point tracker that jointly tracks arbitrary points in a video. CoTracker3 provides offline and online/sliding-window models, dense/grid or sparse query points, optional segmentation-mask filtering, visibility/confidence outputs, and PyTorch inference/training code.

## Relevance to AI Physics Tracker

CoTracker is a strong benchmark candidate for point tracking when a user can specify a query point or a grid, especially for multi-point rigid/object motion. Its online API fits long videos better than an offline whole-video model. It is not a physics analysis/UI/persistence project and its license is a release blocker for a commercial desktop distribution.

## Technology Stack

| Area | Implementation observed |
| --- | --- |
| Language | Python |
| Framework | PyTorch/TorchVision; PyTorch Hub checkpoints |
| Video | imageio/FFmpeg in demos; tensors shaped `B,T,C,H,W` |
| Prompt | sparse query points `(t, x, y)`, regular grid, dense grid, optional segmentation mask |
| Outputs | tracks `B,T,N,2`; public visibility mask; internal CoTracker3 confidence and visibility logits |
| Modes | offline sliding windows and online half-window chunks |
| Plotting | `cotracker/utils/visualizer.py`, annotated MP4/TensorBoard output |
| Training | Kubric and real-video pseudo-labeling scripts; large multi-GPU training examples |
| GUI | Gradio demo; no desktop Qt GUI |
| Packaging | `setup.py`, checkpoints/Hugging Face, minimal tests; no Windows installer |

## Repository Structure

```text
cotracker/predictor.py                         public offline/online predictor façade
cotracker/models/build_cotracker.py            model/checkpoint construction
cotracker/models/core/cotracker/               CoTracker2/3 model internals
cotracker/models/core/model_utils.py           grid/query/feature helpers
cotracker/datasets/                             Kubric/real/TAP-Vid loaders
cotracker/evaluation/                           benchmark evaluation
cotracker/utils/visualizer.py                   rendering/export
demo.py, online_demo.py, gradio_demo/           interaction demos
train_on_kubric.py, train_on_real_data.py       training/pseudo-labeling
tests/test_bilinear_sample.py                   limited unit test
```

## Key Files

`cotracker/predictor.py:CoTrackerPredictor`

- Constructor calls `build_cotracker(checkpoint, offline, window_len, v2)` and sets the interpolation shape.
- `forward(...)` accepts either explicit `queries`, `grid_size`, or dense tracking; `grid_query_frame`, `segm_mask` and `backward_tracking` are exposed at the product-facing boundary.
- `_compute_sparse_tracks(...)` resizes video and queries, optionally adds a support grid, invokes the model, thresholds visibility, overwrites query-frame positions with exact prompts, and scales tracks back to original pixels.
- `_compute_backward_tracks(...)` flips video/query time and fills earlier frames from a reverse pass.

`cotracker/predictor.py:CoTrackerOnlinePredictor`

- First call with `is_first_step=True` initializes model state and stores user queries/grid.
- Later calls accept `video_chunk`; `step = window_len // 2` controls overlap and online progress.
- It returns scaled tracks plus thresholded visibility; CoTracker3 multiplies visibility by confidence before the public threshold.
- The caller must reset/recreate the predictor for a new video; this stateful contract must be explicit in our adapter.

`cotracker/models/build_cotracker.py`

- Builds `CoTrackerThreeOffline` or `CoTrackerThreeOnline` with fixed stride/correlation radius/window defaults and loads a Torch state dict from the checkpoint.
- The checkpoint file itself is not a generic “model ID”; the adapter should store checkpoint path/UID/model mode/window in metadata.

`cotracker/models/core/cotracker/cotracker3_offline.py`, `cotracker3_online.py`

- `forward(...)` normalizes video, pads/chunks it into windows, extracts feature maps, builds multiscale feature pyramids, samples track/support features and iteratively calls `forward_window(...)`.
- Each iteration updates coordinates plus visibility and confidence logits using local correlation features and an update transformer.
- Offline mode overlaps sliding windows and carries prior predictions into the next window; online mode stores `online_*` feature/prediction state and advances by half a window.
- Outputs include coordinate predictions, `sigmoid` visibility and confidence, and optional train-time intermediate predictions/masks.

`cotracker/models/core/model_utils.py`

- `get_points_on_a_grid(...)` and feature sampling helpers implement prompt/grid conversion and local correlation sampling.
- Read for coordinate order and resolution scaling before integrating with `Timeline`/`TrackPoint`.

`cotracker/utils/visualizer.py`

- `Visualizer.visualize(...)` draws point tracks, visibility, query frames, optional segmentation and camera-motion compensation, then writes MP4 or TensorBoard video.
- Useful for benchmark videos and “confidence/visibility overlay” prototypes, not as a Qt drawing layer.

`gradio_demo/app.py`

- Provides UI-level ideas: upload video, choose query frame, click points, undo/clear, run grid or sparse tracking, and inspect/export a rendered result.
- The interaction is front-end state plus a model call; it does not persist an experiment project.

## Key call chains

Offline:

```text
user points/grid/mask
  -> CoTrackerPredictor.forward
  -> _compute_sparse_tracks / _compute_dense_tracks
  -> resize video + queries
  -> CoTrackerThreeOffline.forward
  -> feature pyramid + joint point transformer windows
  -> tracks + visibility + confidence
  -> threshold/restore query points/scale to pixels
  -> Visualizer / adapter TrackPoint records
```

Online:

```text
first video_chunk, is_first_step=True, queries
  -> CoTrackerOnlinePredictor.model.init_video_online_processing
  -> store self.queries
next video_chunk(s)
  -> CoTrackerThreeOnline.forward(..., is_online=True)
  -> reuse online feature/query state
  -> overlapping window prediction
  -> tracks + visible/confidence
```

## Occlusion, correction and multi-object behavior

- It is point-centric rather than object-mask-centric; multiple points are jointly processed and regular grids can approximate object coverage.
- CoTracker3 has distinct visibility and confidence streams internally; the public predictor returns a boolean visibility threshold, so the adapter may need to call the model directly if continuous confidence is required.
- Backward tracking is a separate reverse-video pass, not a correction API.
- User corrections/reinitialization are not implemented as a durable GUI workflow; a product would need to restart/update query state and record correction provenance.

## Hardware and Windows assessment

- README: GPU is strongly recommended; small tasks can run on CPU. Training examples use 32 GPUs and are not desktop-relevant.
- Model resolution/window/point count drive memory; online mode is intended for longer videos and offline mode for full clips.
- Code is PyTorch/OpenCV/imageio-based and may run on Windows with a compatible Python/PyTorch stack, but no Windows CI/installer workflow was found. `Windows compatibility: needs benchmark`.
- Exact checkpoint sizes are hosted externally and were not declared in the inspected source. Record downloaded file sizes in benchmark reports rather than relying on model names.

## Tests, build and release

- Only a small unit test (`tests/test_bilinear_sample.py`) was found; no broad integration/GUI suite.
- `setup.py` packages source; demos and training scripts are the operational documentation.
- Checkpoints are downloaded from Hugging Face and no GitHub release/desktop packaging workflow was found.

## License and data notes

- The repository README/license states that the majority of CoTracker is under `CC BY-NC 4.0`; it also calls out separate MIT/Apache terms for portions such as Particle Video Revisited, TAP-Vid and LocoTrack.
- Commercial use: not permitted for the CC BY-NC-covered material. This is a direct blocker for embedding the repository/checkpoints into a commercial product unless licensing is separately obtained.
- Model/checkpoint applicability and third-party data terms: `Needs license review`; do not infer Apache/MIT from individual dependency files.

## What to reuse

- Reuse: explicit sparse/grid/mask query API, offline/online split, windowed state management, joint multi-point processing, separate visibility/confidence, exact query-point restoration and benchmark rendering.
- Do not copy into release code until license clearance. First benchmark the official checkpoint as an external optional engine.
- Highest-value reading order: `predictor.py` → `build_cotracker.py` → `cotracker3_offline.py`/`cotracker3_online.py` → `model_utils.py` → `visualizer.py` → `gradio_demo/app.py`.
