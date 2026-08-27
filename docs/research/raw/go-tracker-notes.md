# GoTracker（补充项目）

## Repository

- Repository: <https://github.com/thalestmm/go-tracker>
- Checked on: `2026-08-27`
- Snapshot commit: `d880de81afac04a19f2cd17219f1e47de6b05280`
- Default branch: `main`

## Purpose and relevance

GoTracker is a small physics-oriented single-point tracker inspired by OSP Tracker. It opens a video, asks the user to click a point, tracks it with template matching, pauses on a low-confidence match for manual realignment, calibrates pixel scale, computes derivatives and exports CSV/annotated video.

It is a valuable “minimum viable tracking engine” reference and benchmark baseline, not a general multi-object/trainable system.

## Technology Stack

| Area | Implementation observed |
| --- | --- |
| Language/GUI | Go; GoCV window/event API |
| Video | GoCV/OpenCV `VideoCapture` wrapper |
| Tracking | grayscale template matching; CPU matcher and optional CUDA matcher file |
| Calibration | two clicked reference points → pixels per unit |
| Kinematics | central finite differences with endpoint forward/backward differences |
| Export | CSV with optional confidence, calibrated x/y and vx/vy/ax/ay; annotated MP4 |
| Config/build | TOML config, Go modules, Docker/justfile, Go tests |
| License | MIT for project; GoCV/OpenCV separate licenses |

## Key Files

`main.go`

- `runSingle(...)` opens the reader, reads metadata, seeks to a start frame/time, optionally calibrates, requests a point click/zoom confirmation, initializes the tracker, runs frame processing, handles pause/realignment/step controls, and writes outputs.
- `buildJobs(...)` gives a simple per-video batch naming convention.

`video/reader.go`

- `Reader.Open`, `Read`, `Seek`, `Info`, `Close` wrap OpenCV and normalize FPS/dimensions/frame count into `VideoInfo`.

`tracker/tracker.go`

- State machine: `StateIdle`, `StateTracking`, `StatePausedForRealignment`, `StateDone`.
- `Initialize(...)` captures a grayscale template at a clicked point.
- `ProcessFrame(...)` computes adaptive search margin from recent motion, runs `Matcher.Match`, returns a `TrackPoint` with time and confidence, and transitions to realignment pause below threshold.
- `Realign(...)` replaces the template and resets recent position state; `Resume`, `State`, `LastPos`, `Points` and `Close` define the small engine API.

`tracker/matcher.go`, `matcher_cuda.go`, `roi.go`

- `Matcher` is an interface; the CPU implementation uses `TM_CCOEFF_NORMED` and `MinMaxLoc`.
- ROI helpers define template/search regions; adaptive search is controlled by `Config`.

`export/csv.go`

- `TrackPoint` has `Time`, integer `X/Y`, and `Confidence`.
- `CSVOptions` controls confidence, scale/unit, derivatives.
- `ComputeScale(...)` returns pixels per real-world unit.
- `computeVelocity(...)` uses actual point timestamps and forward/backward/central differences; `computeAcceleration(...)` differentiates velocity similarly.
- Output columns are explicit (`time,x,y,confidence,x_m,y_m,vx_m/s,...`).

`gui/window.go`, `gui/graph.go`

- `Window.WaitClick`, `WaitClickZoom`, `WaitTwoClicks`, `WaitPause`, `ShowFrame`, `drawOverlay` implement click-to-select, zoom confirmation, calibration, pause/re-align, axes/trail/ROI/confidence rendering.
- `GraphWindow` displays real-time x(t)/y(t) and optional derivative data.

## Key call chain

```text
main.runSingle
  -> video.Open / Reader.Seek / Reader.Read
  -> gui.WaitTwoClicks (optional scale)
  -> gui.WaitClickZoom
  -> tracker.New + Tracker.Initialize
  -> Tracker.ProcessFrame
  -> Matcher.Match / adaptive ROI
  -> StatePausedForRealignment on low confidence
  -> gui.WaitPause -> Tracker.Realign or Resume
  -> export.WriteCSV / export.WriteVideo / graph
```

## Tests/build/release

- `tracker/tracker_test.go`, `matcher_test.go`, `roi_test.go`, `config_test.go`, and `export/csv_test.go` use synthetic frames and check initialization, motion tracking, loss/realignment, accumulation, scale and export behavior.
- `go.mod` requires Go 1.25 and GoCV 0.43; `Dockerfile`, `justfile`, and CI/release files should be checked before relying on Windows builds.
- No project persistence/model library or multi-object track UI was found.

## License and data notes

- Code: `MIT`.
- GoCV/OpenCV and optional CUDA runtime: separate license/runtime review.
- No learned model weights or external dataset bundled.

## What to reuse

- Reuse: small tracker lifecycle, explicit `StatePausedForRealignment`, confidence threshold, click/zoom confirmation, adaptive search, timestamp-based derivatives and synthetic test fixtures.
- Avoid: integer-only positions, single global template, no durable project file and no visibility/uncertainty beyond match confidence.
