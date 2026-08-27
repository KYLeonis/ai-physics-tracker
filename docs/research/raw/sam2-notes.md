# SAM 2 / SAM 2.1

## Repository

- Official repository: <https://github.com/facebookresearch/sam2>
- Checked on: `2026-08-27`
- Snapshot commit: `2b90b9f5ceec907a1c18123530e92e794ad901a4`
- Default branch: `main`

## Purpose

SAM 2 is a promptable image/video segmentation model with streaming memory. Its video predictor accepts positive/negative points, boxes and masks, returns object masks per frame, supports multiple objects, and allows corrections during propagation.

## Relevance to AI Physics Tracker

SAM2 is highly relevant as an interactive “select object → propagate mask → correct difficult frames” engine, especially when a user wants a whole object region rather than a single keypoint. It is not a point-trajectory/kinematics engine: the adapter must extract a centroid/landmark from masks, define confidence/visibility, and decide how segmentation corrections become physics track points.

## Technology Stack

| Area | Implementation observed |
| --- | --- |
| Language | Python; web demo also TypeScript/React |
| Framework | PyTorch `>=2.5.1`, TorchVision, Hydra/OmegaConf |
| Video | `decord`/JPEG frame loaders and cached tensors; optional async loading/offload |
| Prompt | positive/negative point, box, mask; object IDs can be added after tracking starts |
| State | per-video `inference_state` with cached image features, per-object prompt/output dictionaries and memory frames |
| Outputs | mask logits/masks at model/original video resolution; web API encodes RLE |
| Long tasks | generator propagation, session state, lock, cancellation flag in web demo |
| GUI | official browser demo: React frontend + Python GraphQL/backend; no desktop Qt GUI |
| Packaging | `setup.py`/`pyproject.toml`, optional CUDA connected-component extension; no Windows installer |

## Repository Structure

```text
sam2/sam2_video_predictor.py             current stateful video API
sam2/sam2_video_predictor_legacy.py      older batched/multi-object path
sam2/sam2_image_predictor.py             image prompt API
sam2/build_sam.py                        model/config/checkpoint construction
sam2/modeling/                           memory encoder, attention, prompt/mask decoder
sam2/utils/misc.py                       frame loading, offload and mask post-processing
sam2/configs/                            SAM2/SAM2.1 model YAML
demo/backend/server/inference/predictor.py  session/stream API adapter
demo/frontend/src/common/tracker/         browser tracker/tracklet client
demo/frontend/src/common/components/video/ video worker/filmstrip/interaction
demo/frontend/src/common/components/annotations/ tracklet UI/swimlanes
training/, notebooks/                    training/demo material
```

## Key Files

### Video predictor state machine

`sam2/sam2_video_predictor.py: SAM2VideoPredictor`

- `init_state(video_path, offload_video_to_cpu, offload_state_to_cpu, async_loading_frames)` loads/initializes frames, stores original dimensions, chooses storage device and creates maps for object IDs, prompts, cached features and per-object outputs.
- `_obj_id_to_idx(...)` maps stable client object IDs to model batch indexes and permits adding new objects after tracking begins.
- `add_new_points_or_box(...)` normalizes points, converts boxes into special labels, stores point prompts, determines conditioning versus correction frame, feeds previous mask logits when available, and returns immediate masks for the prompted frame.
- `add_new_mask(...)` stores/resizes a binary mask prompt and follows the same conditioning/correction path.
- `propagate_in_video_preflight(...)` consolidates temporary outputs and prepares memory before propagation.
- `propagate_in_video(...)` is a generator over `(frame_idx, obj_ids, video_res_masks)`, supports forward/reverse traversal and writes per-object state.
- `clear_all_prompts_in_frame(...)`, `reset_state(...)`, and `remove_object(...)` implement correction/reset/delete operations.
- `clear_non_cond_mem_around_input` and `add_all_frames_to_correct_as_cond` are explicit policies for how corrections affect neighboring memory.

This separation between immediate prompt feedback, durable per-object prompt state, temporary outputs and full-video propagation is the best source for an interactive correction state machine.

### Frame loading and memory/offload

`sam2/utils/misc.py`

- `load_video_frames(...)` dispatches to MP4/decord or JPEG directory readers.
- `load_video_frames_from_video_file(...)` reads/resizes all frames and can keep them on CPU or move them to compute device.
- `AsyncVideoFrameLoader` provides lazy/background frame loading for image sequences.
- The predictor documents that offloading video/state to CPU saves GPU memory at a measurable FPS cost; this is a useful product-level memory policy for long videos.

### Model construction and hardware

`sam2/build_sam.py`, `sam2/modeling/sam2_base.py`, `sam2/configs/sam2.1/*.yaml`

- Build functions load config/checkpoint and construct image encoder, prompt encoder, memory encoder/attention and mask decoder.
- The README publishes SAM2.1 model size/speed table: tiny 38.9M, small 46M, base-plus 80.8M, large 224.4M; listed FPS is measured on an A100 and must not be read as CPU/Windows performance.

### Web UI/backend integration

`demo/backend/server/inference/predictor.py:InferenceAPI`

- Keeps `session_states` keyed by UUID and wraps model calls in an `inference_lock`.
- `start_session(...)` selects CUDA/MPS/CPU, applies autocast on CUDA, initializes predictor state and stores cancellation state.
- `add_points(...)` calls `add_new_points_or_box(...)` and returns masks as RLE values.
- `add_mask(...)`, `clear_points_in_frame(...)`, `clear_points_in_video(...)`, and `remove_object(...)` expose corrections/tracklet management.
- `propagate_in_video(...)` yields responses while iterating the predictor generator; `cancel_propagate_in_video(...)` sets a session flag checked during streaming.
- This is a strong example of separating GUI/client interaction from a stateful inference service and streaming long-task results.

`demo/frontend/src/common/tracker/Tracker.ts`, `SAM2Model.ts`, `TrackerTypes.ts`

- Define a tracker abstraction with `startSession`, `updatePoints`, `clearPointsInFrame`, `clearPointsInVideo`, `streamMasks`, `abortStreamMasks`, tracklet creation/deletion and response types.
- `SAM2Model` sends GraphQL mutations, owns client tracklet state/colors/thumbnails, and updates masks asynchronously.
- `demo/frontend/src/common/components/annotations/TrackletSwimlane.tsx` renders mask occupancy segments and clickable frames, an excellent UI pattern for locating propagation gaps/corrections.

`demo/frontend/src/common/components/video/VideoWorker.ts`, `VideoWorkerContext.ts`

- Runs playback/filmstrip/tracker messaging in a web worker and serializes errors back to the UI.
- Useful for the principle that heavy inference and video effects should not block interactive controls.

## Key call chains

Prompt and immediate correction:

```text
user positive/negative points or box
  -> frontend SAM2Model.updatePoints
  -> backend InferenceAPI.add_points
  -> SAM2VideoPredictor.add_new_points_or_box
  -> prompt encoder + mask decoder (+ prior mask logits)
  -> immediate frame mask
  -> RLE response -> client tracklet mask/state
```

Video propagation:

```text
start session
  -> predictor.init_state(video)
  -> add prompts for object IDs
  -> InferenceAPI.propagate_in_video (generator)
  -> predictor.propagate_in_video
  -> streaming frame masks/object IDs
  -> mask logits threshold + RLE encode
  -> TrackletSwimlane/VideoWorker updates
  -> cancel flag can stop the generator
```

## Prompt, occlusion, confidence and correction assessment

- Point labels are positive/negative segmentation prompts, not direct coordinate observations.
- Box prompts are encoded as two special points with labels 2/3; mask prompts replace point prompts on a frame.
- Object IDs are explicit and independent from model batch indexes.
- SAM2 returns mask logits and masks. There is no per-point likelihood equivalent to DLC; a physics adapter would need a confidence policy based on mask score/area/stability/visibility and potentially centroid uncertainty.
- Occlusion is represented indirectly by mask absence/low score and memory behavior, not as a first-class point visibility series.
- Corrections can be applied to previously tracked frames, with configurable conditioning-memory invalidation; this is valuable for our refinement UX.

## Hardware and Windows assessment

- README/INSTALL require Python ≥3.10, PyTorch ≥2.5.1 and matching TorchVision; GPU/CUDA is strongly recommended.
- Windows is not a first-class native target in the docs; the project recommends WSL/Ubuntu. The custom CUDA extension can be skipped (`SAM2_BUILD_CUDA=0`), but GPU post-processing is then unavailable.
- CPU mode is present in the web API and model code, but performance/memory for long videos is not promised. `Windows native + CPU feasibility: needs benchmark`; do not put SAM2 in the default engine before testing.
- Model sizes are listed above; exact checkpoint files are downloaded separately.

## Tests, build and release

- `sam2` includes model/training/demo code and a lightweight formatting workflow; no Windows installer/release workflow was found.
- `setup.py` builds an optional CUDA `connected_components` extension and tolerates build errors by default.
- The official web demo is a useful integration reference but adds backend/frontend/GraphQL complexity not needed for our first desktop MVP.

## License and data notes

- Code, model checkpoints, demo code and training code: `Apache-2.0` per README/LICENSE.
- Third-party: `cc_torch` connected-components adaptation has a separate `LICENSE_cctorch`; Inter font and Noto Color Emoji use SIL OFL 1.1.
- SA-V and other datasets/media are separate assets with their own terms. `Needs license review` for dataset redistribution.
- Apache code/model licensing is compatible in principle with a permissive product, but all third-party assets/weights must still be recorded.

## What to reuse

- Reuse: prompt/state API (`init_state`, immediate feedback, per-object IDs, correction-frame memory policy), generator-based propagation, session lock/cancel, mask RLE transport and tracklet swimlane UX.
- Avoid: treating masks as point tracks without defining a deterministic centroid/landmark/uncertainty conversion.
- Highest-value reading order: `sam2_video_predictor.py` → `utils/misc.py` → `build_sam.py` → backend `predictor.py` → frontend `SAM2Model.ts`/`TrackletSwimlane.tsx`.
