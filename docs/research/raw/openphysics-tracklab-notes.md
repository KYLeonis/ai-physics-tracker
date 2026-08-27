# TrackLab（OpenPhysics）

## Repository

- Official repository: <https://github.com/OpenPhysics/TrackLab>
- Do not confuse with the research framework `TrackingLaboratory/tracklab`; these are unrelated projects with different languages, licenses and goals.
- Checked on: `2026-08-27`
- Snapshot commit: `05c707992ed42cff8f6ecb328d81f480b34f6307`
- Default branch: `main`

## Purpose

OpenPhysics TrackLab is a browser-based physics video-analysis tool built for classroom-style digitizing. It loads sample/uploaded/webcam video, provides coordinate axes and a scale ruler, manually records object positions, runs OpenCV template matching, calculates kinematics, and exports CSV.

## Relevance to AI Physics Tracker

This is the closest small reference implementation for a physics-first MVP with a clean model/view split. It makes several design choices that match our roadmap: raw points are distinct from derived kinematics, the pixel→model transform is explicit, frame/time semantics are tested, manual and automatic point insertion have different overwrite policies, and tracking runs outside the UI thread. It does not yet provide durable project persistence, trainable models or high-end video decoding.

## Technology Stack

| Area | Implementation observed |
| --- | --- |
| Language | TypeScript |
| GUI | SceneryStack scene graph plus DOM table components |
| Video | HTML `<video>` element; Vite middleware adds byte-range support for local sample videos |
| Tracking | OpenCV.js WASM `matchTemplate` in `public/opencv-worker.js` |
| Kinematics | Pure TypeScript finite differences |
| Plotting | Self-contained canvas graph subsystem |
| Persistence/export | In-memory reactive state; CSV and browser download, no experiment project format |
| Packaging | Vite + PWA/Workbox; GitHub Pages deployment via reusable OpenPhysics/Baton workflows |

## Repository Structure

```text
src/track-lab/model/
  Track.ts                         TrackPoint/kinematic types
  TrackLabModel.ts                 cross-model coordinator
  TrackingModel.ts                 track state, cache, tracker facade
  KinematicsComputer.ts            pure v/a derivation
  ModelViewTransformFactory.ts     calibration + axes transform
  OverlayToolsModel.ts             axes, calibration, tape, angle state
  VideoPlaybackModel.ts            time, frame, playback rate and dimensions
  VideoSourceModel.ts              upload/webcam/bundled video state
  TrackExporter.ts                 CSV builder
src/track-lab/view/                video, panels, overlays, table, graph
src/track-lab/graph/               configurable graph and gestures
src/tracking/OpenCVTracker.ts      main-thread async worker facade
public/opencv-worker.js            OpenCV WASM protocol and matching
tests/track-lab/model/             pure model/kinematics/export tests
vite.config.ts                     video range server, OpenCV serving, CSP/PWA
```

## Key Files

`src/track-lab/model/Track.ts`

- Defines `TrackPoint { frame, time, x, y }`, `Track`, `KinematicPoint`, and `TrackKinematics`.
- `x/y` are model coordinates, not pixels; `time` is seconds; `frame` is a discrete index.
- `KinematicPoint` includes `vx`, `vy`, `speed`, `ax`, `ay`, and acceleration magnitude, with `null` for unavailable values.
- This is a compact target shape for the first version of our `TrackPoint`/`ProcessedData` model, but our version should add source/confidence/validity and preserve raw pixel observations.

`src/track-lab/model/TrackingModel.ts`

- Reactive track collection in `tracksProperty`; active track in `activeTrackIdProperty`.
- `addPointToTrack(...)` is the auto-tracking path and uses first-wins deduplication.
- `addOrReplacePointOnTrack(...)` is the manual correction path and lets the last click replace a point at the same frame.
- `insertPointSorted(...)` keeps points ordered even if the user scrubs backward.
- `trackKinematicsProperty` caches by `points` array identity; all mutations create new immutable arrays.
- `retransformTrackPoints(prevMvt, newMvt)` maps old model coordinates through pixel space and back through the new transform so existing marks stay pinned to the same video pixels.
- `initTracker(...)` uses a monotonically increasing `initVersion` to discard stale async initialization after reset/reselection.

`src/track-lab/model/TrackLabModel.ts`

- `recordTrackPoint(...)` reads the current time/frame, inverse-transforms a video-pixel position through `OverlayToolsModel.modelViewTransformProperty`, and calls the tracking model.
- Wires transform changes to `retransformTrackPoints` and source changes to atomic tracking reset.
- This is the best example here of a thin coordinator that owns cross-cutting invariants without absorbing all domain logic.

### Video playback and frame navigation

`src/track-lab/model/VideoPlaybackModel.ts`

- `currentTimeProperty` is authoritative; `currentFrameProperty` derives `Math.round(time * fps)`.
- `seekByFrames(...)` advances by exactly `1 / fps` and pauses before stepping.
- `totalFrameCountProperty`, `durationProperty`, `frameRateProperty`, `playbackRateProperty`, and `videoDimensionsProperty` are explicit state.
- The tests cover non-integer 29.97 FPS frame derivation and endpoint clamping.

`src/track-lab/view/VideoPlayerNode.ts` and `PlaybackControlsNode.ts`

- `VideoPlayerNode` hosts the HTML video element and all video-local overlays; playback controls only write model time/state.
- `timeupdate`/`seeked` events drive the UI/model synchronization. The project documents a half-frame/deadband guard to avoid feedback loops.
- `src/track-lab/view/VideoSourceControlNode.ts` handles bundled, uploaded and webcam recordings; `src/webcam.ts` estimates/repairs frame-rate metadata.

`vite.config.ts`

- `serveVideos()` serves local video with `Accept-Ranges` and `Content-Range`; this is essential for browser seeking.
- The production build copies videos into `dist/videos`.

### Calibration and coordinate system

`src/track-lab/model/OverlayToolsModel.ts`

- Stores coordinate origin/angle, calibration endpoints, calibration distance/unit, measuring tape and angle-tool state as reactive properties.
- Exposes derived velocity/acceleration unit strings and a read-only `modelViewTransformProperty`.

`src/track-lab/model/ModelViewTransformFactory.ts`

- `buildModelViewTransform(origin, angle, p1, p2, dist)` computes `s = pixelDistance / realDistance` and composes `T(origin) · R(angle) · S(s, -s)`.
- The negative Y scale converts the video’s down-positive Y to a physics-style up-positive model Y.
- Returns identity for degenerate calibration values.

`src/track-lab/view/CoordinateSystemNode.ts` and `CalibrationToolNode.ts`

- Implement draggable origin/rotation and draggable calibration endpoints directly in the video-local coordinate layer.
- The node code defers some scene-graph mutations with `queueMicrotask` to avoid Scenery re-entry while property listeners are firing.

### Manual and automatic tracking

`src/track-lab/view/DigitizingOverlayNode.ts`

- Receives a click on the current frame, displays a magnifier and calls the model’s manual replace path.
- Advances one frame after a successful click; Delete removes the current point.

`src/track-lab/view/AutoTrackerNode.ts`

- User drags a `TrackerRegion` rectangle on the video; a track is auto-created if necessary.
- On each `timeupdate`/`seeked`, `requestAnimationFrame` coalesces events and an `in-flight` flag prevents concurrent tracker calls.
- Accepted pixel matches are inverse-transformed and inserted through the auto-tracking first-wins path.
- Reset/reselection cancels pending animation and invalidates stale async initialization.

`src/tracking/OpenCVTracker.ts` and `public/opencv-worker.js`

- Main thread draws the current `<video>` frame into an offscreen canvas, reads either the initial region or a small window around the last match, and sends an `init`/`track` message to the worker.
- The worker loads OpenCV.js, applies Gaussian blur, calls `cv.matchTemplate` with `TM_CCOEFF_NORMED`, and returns `(x, y, confidence)`.
- The facade rejects superseded promises, drops matches below `MATCH_CONFIDENCE_THRESHOLD = 0.25`, and disposes the worker template on reset.
- The implementation is intentionally stationary-camera oriented: windowed search and a permissive threshold trade robustness for speed. It is a good baseline, not a replacement for a learned tracker.

Call chain:

```text
AutoTrackerNode drag
  -> TrackingModel.resetTracker()
  -> TrackingModel.initTracker(video, region)
  -> OpenCVTracker.initFromVideo()
  -> postMessage({type: "init"})
  -> opencv-worker.js cv.matchTemplate setup

video timeupdate/seeked
  -> requestAnimationFrame(processFrame)
  -> TrackingModel.trackFrame(video)
  -> OpenCVTracker.track()
  -> postMessage({type: "track"})
  -> worker returns center + confidence
  -> TrackingModel.addPointToTrack()
  -> kinematics/table/graph reactive updates
```

### Kinematics and plotting

`src/track-lab/model/KinematicsComputer.ts`

- `computeTrackKinematics(track)` is a pure function with no SceneryStack dependency.
- `finiteDifference(...)` uses forward/backward differences at endpoints and central differences inside.
- It differentiates using each point’s recorded timestamps, so sparse points and deleted interior points do not assume a constant frame interval.
- Acceleration is obtained by applying the same finite-difference helper to velocity. This is simple and testable, but it is still noise-sensitive and lacks smoothing/interpolation.

`src/track-lab/graph/`

- `PlottableProperty.ts` describes graph quantities with a name, unit and accessor.
- `kinematics-plottable-properties.ts` is the single registry for `t`, `x`, `y`, `vx`, `vy`, `speed`, `ax`, `ay`, `|a|`.
- `GraphDataManager.ts` handles data selection/range, `GraphRenderer.ts` draws, and gesture handlers pan/zoom/resize.
- `KinematicsGraphNode.ts` converts `TrackKinematics` to graph records and colors each track consistently.

### Export and persistence

`src/track-lab/model/TrackExporter.ts`

- `buildDataRows(...)` merges sparse points from all tracks by frame and sorts rows.
- `generateCsv(...)` creates stable headers such as `x_A (m)`, leaves cells blank where a track has no point on a frame, and formats with shared decimal precision.

No project file/persistence layer was found in this snapshot. Uploaded videos are kept as browser blobs and track/overlay state is reset with the simulation; CSV is the durable output. This is a direct gap against our Phase 1/2 requirements.

## Tests, build and release

- `tests/track-lab/model/KinematicsComputer.test.ts` covers endpoint finite differences, null gaps and single-point tracks.
- `tests/track-lab/model/TrackingModel.test.ts` covers point ordering, first-wins auto insertion, manual replacement, deletion/restore and cache invalidation.
- `tests/track-lab/model/TrackExporter.test.ts` covers sparse multi-track CSV shape.
- `tests/track-lab/model/VideoPlaybackModel.test.ts` covers 29.97 FPS and frame-step behavior.
- `tests/memory-leak.test.ts` checks listener disposal/GC behavior; fuzz tests use Playwright.
- `package.json` scripts run TypeScript checks, Biome lint, Vite build and Vitest.
- `.github/workflows/ci.yml` and `deploy.yml` delegate CI/deployment to OpenPhysics/Baton; this is a browser deployment template rather than a Windows desktop release workflow.

## License and data notes

- Code/license declaration: `AGPL-3.0-or-later` in `package.json` and README.
- Model weights: none; OpenCV.js is a separate dependency and needs its own notice review.
- Sample videos under `videos/`: redistribution rights are not defined in this repository map; `Needs license review` before reuse.

## What to reuse

- Reuse directly as a design reference: the pure `Track`/`KinematicsComputer`/`TrackExporter` modules, explicit `ModelViewTransformFactory`, timestamp-authoritative playback, dual manual/auto insertion policies, worker protocol and `requestAnimationFrame` coalescing.
- Adopt with changes: add raw pixel coordinates, source (`manual`/`ai`), confidence, visibility and processing provenance to our durable model; add project persistence; use a real video reader service for desktop.
- Highest-value reading order: `Track.ts` → `KinematicsComputer.ts` → `TrackingModel.ts` → `TrackLabModel.ts` → `ModelViewTransformFactory.ts` → `AutoTrackerNode.ts` → `OpenCVTracker.ts` → `VideoPlaybackModel.ts` → tests.
