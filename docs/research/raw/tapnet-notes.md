# TAPNet / TAPIR / TAPNext

## Repository

- Official repository: <https://github.com/google-deepmind/tapnet>
- Checked on: `2026-08-27`
- Snapshot commit: `c2cbab81cc06092b5f05bfe2da7bfec54e2079c9`
- Default branch: `main`

## Purpose

TAPNet is Google DeepMind’s repository for Tracking Any Point research, including TAPIR, online/causal TAPIR, BootsTAPIR, TAPNext, RoboTAP and TAP-Vid/TAPVid-3D tooling. The core task is class-agnostic point tracking: given query point(s) and a video, return a point trajectory plus visibility/occlusion information for every frame.

## Relevance to AI Physics Tracker

TAPIR is a strong candidate for a “click one or more points and get dense trajectories” benchmark, especially when the target is not a human skeleton or when we have only a few point prompts and no training set. It is not a desktop GUI or persistence layer. Its output is point-level trajectory/visibility, so it fits our `TrackPoint` concept better than a bbox-only MOT framework, but it still needs a wrapper for frame/time/coordinate conventions and correction/re-initialization.

## Technology Stack

| Area | Implementation observed |
| --- | --- |
| Language | Python |
| Model frameworks | JAX/Haiku original models; PyTorch reimplementations for TAPIR/TAPNext demos |
| Input/video | NumPy/Torch/JAX tensors; OpenCV capture in live demos |
| Prompt | Query point in a frame; batch of points; live demo mouse clicks; no box/mask as primary API |
| Outputs | `tracks`, occlusion logits, `expected_dist` uncertainty; visibility derived by post-processing |
| Inference modes | Offline whole-video TAPIR and causal/online TAPIR with persistent causal context |
| Training | JAX training framework under `tapnet/training`; no GUI training workflow |
| Plotting | `tapnet/utils/viz_utils.py`, demo visualizers and trajectory plots |
| Packaging | `pyproject.toml`, requirements, downloaded checkpoint files; no desktop installer |

## Repository Structure

```text
tapnet/models/                 JAX/Haiku TAPIR/TAPNet model definitions
tapnet/torch/                  PyTorch TAPIR/TAPNext implementation
tapnet/training/               supervised point-prediction training/evaluation
tapnet/tapvid/, tapvid3d/      benchmark datasets/metrics/tools
tapnet/utils/                  coordinate transforms, model utilities, visualization
tapnet/live_demo.py            JAX online webcam demo
tapnet/pytorch_live_demo.py    PyTorch online webcam demo
configs/                       model configs
colabs/                        offline/online demos and experiments
```

## Key Files

`tapnet/pytorch_live_demo.py`

- `preprocess_frames(...)` converts uint8 frames to `[-1, 1]`.
- `online_model_init(frames, points)` computes feature grids and query features.
- `online_model_predict(frames, features, causal_context)` computes tracks, occlusion/uncertainty and updates causal context.
- `postprocess_occlusions(...)` combines occlusion and expected-distance logits into a visibility mask.
- The OpenCV mouse demo loads a PyTorch checkpoint, creates an online causal state, allows up to `NUM_POINTS = 8` query points and overlays visible tracks.

`tapnet/torch/tapir_model.py`

- `TAPIR.get_feature_grids(...)` extracts normalized low/high-resolution features, supports multiple refinement resolutions and chunked feature extraction.
- `get_query_features(...)` samples feature grids at query points.
- `estimate_trajectories(...)` runs initial cost-volume matching and iterative PIPs refinement, accepts `query_points_in_video`, `query_chunk_size`, and optional causal context, and returns per-iteration tracks/occlusion/expected distance.
- `refine_pips(...)` samples local correlation neighborhoods and updates positions/logits.
- `tracks_from_cost_volume(...)` is the initial point-location stage.
- `ParameterizedTAPIR` wraps loaded JAX params/state; model code stores raster coordinates carefully.

The two-stage structure is important: initial matching can propose a location independently per frame, then temporal/local refinement improves the trajectory. It gives us a basis for a tracking adapter that exposes continuous score/visibility plus a point series, rather than only one final coordinate.

`tapnet/models/tapir_model.py`

- JAX/Haiku reference implementation of `TAPIR`, `get_feature_grids`, `get_query_features`, `estimate_trajectories` and causal state handling.
- Read when comparing PyTorch parity or understanding the original checkpoint structure.

`tapnet/utils/transforms.py`, `tapnet/utils/model_utils.py`

- Coordinate conversion and image/feature-grid resize utilities.
- The repository README explicitly distinguishes stored normalized raster coordinates, regular pixel coordinates and 3D query order; our adapter must normalize this into one `(frame, time, x, y)` convention.

`tapnet/utils/viz_utils.py`

- `Visualizer` draws tracks, visibility and optional camera-motion compensation and writes annotated videos.
- Useful for benchmark rendering, not as a Qt view layer.

## Data flow and prompt semantics

```text
user click at frame t, pixel (x, y)
  -> query point [t, y, x] in TAPIR internal convention
  -> get_feature_grids(video)
  -> get_query_features(video, query_points)
  -> estimate_trajectories(...)
  -> tracks [B, N, T, 2] + occlusion + expected_dist
  -> postprocess visibility
  -> adapter emits TrackPoint(frame, time, x, y, confidence/visibility)
```

The PyTorch public demo uses query arrays shaped `(B, N, 3)` with time and raster coordinates; the exact order is documented in model docstrings as `[t, y, x]`, while some demos manipulate OpenCV `(x, y)` values. Treat coordinate order as an integration hazard and add explicit tests.

## Occlusion, correction and multi-point behavior

- Visibility is not simply a confidence score; it is derived from occlusion and expected-distance logits.
- The online API keeps `causal_context` across frames, which reduces recomputation but makes correction/restart a state-management problem.
- New query points are inserted with `model.update_query_features(...)` in the demo; this suggests a correction design based on updating query features and causal state, but the repository does not provide a GUI correction workflow.
- Query chunks (`query_chunk_size`) limit memory for many points.
- No native mask/box prompt API is exposed by the TAPIR demo path; masks/segmentation are not the primary output.

## Hardware and Windows assessment

- The README reports live causal TAPIR around 17 FPS on 480×480 with a Quadro RTX 4000; this is a GPU-oriented measurement, not a Windows packaging guarantee.
- Model code has CPU-capable Torch operations, but CPU speed/memory and JAX CUDA setup must be benchmarked. No CPU performance claim was found in the inspected source.
- The live demos use OpenCV and should be portable in principle, but JAX/Torch/CUDA dependencies and checkpoint downloads require platform-specific verification. `Windows compatibility: needs benchmark/release test`.
- The model family is ResNet18-based in the published checkpoint table; exact checkpoint disk size was not declared in the inspected repository. Do not hard-code a size.

## Tests, build and release

- The repository contains benchmark/evaluation code and notebooks, but no broad desktop/GUI test suite or release installer workflow was found.
- `pyproject.toml`, `requirements.txt`, `requirements_inference.txt` and `CONTRIBUTING.md` define package/dev setup.
- Pretrained checkpoints are downloaded separately from Google storage/Hugging Face.

## License and data notes

- Code license: `Apache-2.0` (`LICENSE`).
- Model checkpoints: checkpoint hosting and model-specific terms are not fully restated in the source tree; treat as `Needs license review` before redistribution in a desktop installer.
- TAP-Vid/TAPVid-3D/RoboTAP data have separate dataset terms; the README explicitly calls out a separate license for TAPVid-3D and third-party source-video rights.
- Any pretrained model/backbone dependency must be audited independently of this repository license.

## What to reuse

- Reuse: point-prompt API shape, offline/causal split, query feature initialization/update, uncertainty+visibility outputs, query chunking, coordinate conversion tests and benchmark metrics.
- Avoid: embedding the OpenCV mouse demo as the product UI; wrap the model in a background inference service with explicit reset/reseed/correction events.
- Highest-value reading order: `pytorch_live_demo.py` → `torch/tapir_model.py` → `utils/transforms.py`/`model_utils.py` → `utils/viz_utils.py` → `training/supervised_point_prediction.py`.
