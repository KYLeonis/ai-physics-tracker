# Tracker（Open Source Physics）

## Repository

- Official repository: <https://github.com/OpenSourcePhysics/tracker>
- Current upstream branch at research time: `SwingJS`
- Checked on: `2026-08-27`
- Snapshot commit: `7674d2cd68835049ac58dbb0e827f7526800afe0`
- User-supplied `OpenSourcePhysics/tracker` is still the official source repository. It is a Java application built on the separate `OpenSourcePhysics/osp` core library.

## Purpose

Tracker is a physics-education video analysis and modeling application. It treats a video as a sequence of frames, lets the user place tracks and measuring tools, computes kinematic/dynamic quantities, and combines the result with model building and plotting.

## Relevance to AI Physics Tracker

This is the strongest prior art for the physics-facing product surface: frame/step semantics, coordinate axes, calibration objects, point-mass data variables, manual/autotracking, table/plot views, and an experiment file format. Its main limitation as an implementation source is the very large Swing/OSP object graph and the fact that video decoding is delegated to OSP/video-engine repositories.

## Technology Stack

| Area | Implementation observed |
| --- | --- |
| Language | Java |
| GUI | Swing/OSP display widgets; SwingJS build for browser output |
| Video | OSP media core (`VideoIO`, `VideoPanel`, `VideoPlayer`, `VideoClip`); optional Xuggle/video engines |
| AI/tracking | No learned model; template matching through OSP `TemplateMatcher` for `AutoTracker` |
| Plotting/data | OSP `Dataset`, `DatasetManager`, `DataTable`, `DataTool`, Tracker plot/table views |
| Persistence | OSP XML control system; `.trk` data files, `.trz`/zip resources, tabsets |
| Packaging | Ant build files, jars, distribution artifacts; the repository depends on external OSP build products |

## Repository Structure

```text
src/org/opensourcephysics/cabrillo/tracker/
  Tracker.java                 application bootstrap
  TFrame.java                  main window and tab/view organization
  TrackerPanel.java            central video + track view/model
  TTrack.java, Step.java       track and per-frame step abstractions
  PointMass.java               point position and derived kinematics
  AutoTracker.java             template-based automatic tracking UI/logic
  Calibration*.java            length/scale calibration track
  CoordAxes*.java              coordinate-system origin/angle track
  Plot*.java, Table*.java      plots and tabular data views
  TrackerIO.java               experiment/project I/O
  ExportDataDialog.java        text/CSV-like data export
src/test/                      executable Java smoke/regression tests
src/org/.../resources/help/    user-facing help that documents the interaction model
build-*.xml, jarscripts/       Ant/SwingJS and jar build scripts
distribution/                  checked-in distribution artifacts
```

`TrackerPanel` extends OSP `VideoPanel`, so the video and coordinate transform are owned by the OSP media layer while Tracker adds `TTrack` instances and view coordination on top.

## Key Files

### Application and GUI organization

`src/org/opensourcephysics/cabrillo/tracker/Tracker.java`

- `Tracker.main(String[])` is the desktop entry point.
- `Tracker.getTracker(...)` and the startup code create the application frame and dispatch file/video loading.
- The app supports multiple experiment tabs and performs preference loading before/around UI initialization.
- Worth reading to understand bootstrap, async loading hooks, resource registration, and the Java/SwingJS dual target.

`src/org/opensourcephysics/cabrillo/tracker/TFrame.java`

- `TFrame` is the main window; it creates `TrackerPanel` tabs, split views, toolbars, plots and tables.
- `addTab(...)`, `addTrackerPanel(...)`, `saveAllTabs(...)`, `setSelectedTab(...)`, and `propertyChange(...)` are the important coordination points.
- It stores selected view types, split-pane locations, and tab-level state so the project file can restore the UI arrangement.

`src/org/opensourcephysics/cabrillo/tracker/TrackerPanel.java`

- The central video/track host. It extends `VideoPanel` and imports `ClipControl`, `VideoClip`, `VideoPlayer`, `ImageCoordSystem`, and OSP filter classes.
- It exposes property names such as `PROPERTY_TRACKERPANEL_VIDEO`, `PROPERTY_TRACKERPANEL_STEPNUMBER`, `PROPERTY_TRACKERPANEL_SELECTEDPOINT`, and `PROPERTY_TRACKERPANEL_SELECTEDTRACK`.
- `calibrationTools` and `measuringTools` are explicit collections; this is useful evidence that calibration/measuring tools should be first-class domain objects rather than ad hoc overlays.
- `TrackerPanel.Loader` is involved in serializing the panel state and associated tracks.

### Video and frame navigation

The decoder and core play loop are not implemented in this repository. The real path is:

```text
Tracker.main
  -> TFrame
  -> TrackerIO.openURL(...) / video loading
  -> TrackerPanel (OSP VideoPanel)
  -> VideoClip + ClipControl + VideoPlayer
  -> frame/step properties consumed by tracks and views
```

`VideoClip.frameToStep(...)` and `VideoClip.stepToFrame(...)` are used by `AutoTracker` and track code. The distinction between video frame number and Tracker “step” is important: a clip can have a start frame, step size, and frame range, so downstream data must not assume that “row index == source frame number”.

Relevant paths to inspect together:

- `src/org/opensourcephysics/cabrillo/tracker/TrackerPanel.java`
- `src/org/opensourcephysics/cabrillo/tracker/TFrame.java`
- external dependency `OpenSourcePhysics/osp` (`org.opensourcephysics.media.core.VideoClip`, `ClipControl`, `VideoPlayer`, `ImageCoordSystem`)
- `src/test/PlayVideoTest.java`

### Manual tracking and track data

`src/org/opensourcephysics/cabrillo/tracker/TTrack.java`

- Base class for named tracks, selection/visibility, per-panel state, step arrays, properties and XML loading.
- `Step` and `StepSet` provide the per-frame editing abstraction.

`src/org/opensourcephysics/cabrillo/tracker/PointMass.java`

- `PointMass extends TTrack` and represents a tracked point.
- `PositionStep` stores the image-space `Position` at a frame/step.
- `createStep(...)`, `getStep(...)`, `getVelocity(...)`, `getAcceleration(...)`, and the data-building methods connect raw positions to displayed vectors and data tables.
- The `dataVariables` array includes `t`, `x`, `y`, `r`, `vx`, `vy`, `v`, `ax`, `ay`, `a`, `theta`, `omega`, `alpha`, step/frame, momentum, pixel coordinates, path length, kinetic energy, and mass. This is a useful checklist for the future `TrackPoint`/`ProcessedData` model.

`src/org/opensourcephysics/cabrillo/tracker/PositionStep.java`

- Owns one editable position point and its screen rendering/hit testing.
- `getPosition()` returns the actual interactive `TPoint`; drawing converts world/image state through the current `TrackerPanel` coordinate system.
- Labels and rollover state are part of the step/view object, not raw data.

Manual mark flow is effectively:

```text
mouse event on TrackerPanel
  -> selected TTrack / PointMass
  -> PointMass.createStep(frame, x, y)
  -> PositionStep(Position)
  -> TTrack step array + key-frame/autofill state
  -> PointMass.getData(...)
  -> PlotTrackView / TableTrackView / ExportDataDialog
```

### Automatic tracking

`src/org/opensourcephysics/cabrillo/tracker/AutoTracker.java`

- `AutoTracker` implements `Interactive`, `Trackable`, and `PropertyChangeListener` and is tied to a `TrackerPanel` and active `TTrack`.
- It uses OSP `TemplateMatcher`, a mask/template region, a search region, key-frame data and match thresholds.
- `findMatchTarget(boolean predict)` performs the template search; prediction uses a short history of prior points and finite-difference-like velocity/acceleration/jerk estimates to place the search area.
- The tracking action calls `track.autoMarkAt(...)` and stores per-frame `FrameData`/match state. `STOP_NO_MATCH`, `NEVER_STOP`, and search-area policies are explicit state-machine choices.
- The algorithm is not a learned detector and does not expose a modern probabilistic confidence object, but its “keyframe + autofill + stop policy + user realignment” interaction is directly relevant to an AI-assisted correction workflow.

The relevant path is:

```text
PointMass menu -> TrackerPanel.getAutoTracker(true)
  -> AutoTracker.Wizard
  -> AutoTracker.findMatchTarget(predict)
  -> TemplateMatcher
  -> TPoint match
  -> PointMass.autoMarkAt(frame, x, y)
  -> PositionStep / FrameData
```

### Calibration and coordinate system

`src/org/opensourcephysics/cabrillo/tracker/Calibration.java` and `CalibrationStep.java`

- Calibration is a track/tool with editable per-frame steps, rather than a single global scalar.
- It uses OSP `ImageCoordSystem`, allowing the image-to-world transform to be part of the video/clip state.

`src/org/opensourcephysics/cabrillo/tracker/CoordAxes.java` and `CoordAxesStep.java`

- `CoordAxes` exposes editable origin `x/y` and angle fields, can draw a world grid, and updates `ImageCoordSystem.setOriginXY(...)`/angle state for the current frame.
- The constructor and action handlers show how GUI edits are converted into coordinate-system mutations while preserving the selected frame.

`src/org/opensourcephysics/cabrillo/tracker/Ruler.java`, `TapeMeasure.java`, `Protractor.java`, `CircleFitter.java`, and `RGBRegion.java` are the measuring-tool family. Each is a `TTrack`/`Step`-style object with its own rendering and serialization.

Design lesson: distinguish at least `image/pixel coordinates`, `world coordinates`, and `screen coordinates`; make calibration and axes observable state so every track/view can recompute consistently.

### Kinematics, filtering and plots

`src/org/opensourcephysics/cabrillo/tracker/Derivative.java`, `FirstDerivative.java`, `SecondDerivative.java`, and `BounceDerivatives.java`

- `Derivative.evaluate(Object[])` receives x/y arrays, validity flags and parameters, and returns first/second derivative arrays.
- The interface explicitly permits `NaN` where a derivative cannot be determined, which is useful for gaps and boundary handling.

`src/org/opensourcephysics/cabrillo/tracker/SavitzkyGolayFilter.java`, `ButterworthFilter.java`, `MovingAverageFilter.java`, `MotionFilter.java`, `FilteredPoint.java`

- Filters are separate motion-processing objects and can be serialized through OSP XML loaders.
- The current `SavitzkyGolayFilter` operates on contiguous valid segments and uses one-sided polynomial fits at segment boundaries; it is a concrete reference for preserving output length without inventing values over invalid gaps.

`PointMass` computes and exposes linear and angular quantities, while `PlotTrackView`/`TrackPlottingPanel` obtain a `DatasetManager` from `track.getData(...)` and refresh plots on frame/property changes. `TableTrackView` and `TableTView` expose the same data in tabular form.

### Export and persistence

`src/org/opensourcephysics/cabrillo/tracker/TrackerIO.java`

- `save(File, TrackerPanel)` writes the current panel/project.
- `saveTabset(File, TFrame)` persists a group of tabs.
- `openURL(...)`, async loaders and file chooser helpers route video/data/project opening.
- The file filters explicitly distinguish `.trk`, `.trz`, text data, jar and video files.

`src/org/opensourcephysics/cabrillo/tracker/ExportDataDialog.java`

- Collects selected track datasets and selected columns, merges data by frame index, supports formatted/unformatted output and configurable delimiters, then writes a text file.
- This is a useful reference for stable column selection and sparse multi-track export, although the file format is not a modern schema-first CSV/JSON design.

`PointMass` and view classes define OSP `XML.ObjectLoader` implementations. A loader serializes track properties, footprints/colors, frame data and keyframes, then reconstructs `PositionStep`s on load. This demonstrates the value of explicit loaders per domain class but also shows why our persistence layer should avoid making GUI subclasses the canonical data model.

## Tests, build and release

- Tests are mostly executable Java smoke tests rather than a Python-style unit-test suite: `src/test/PlayVideoTest.java`, `FilterSelfTest.java`, `TrackerLauncher.java`, and `src2/test/Test_XML2.java`.
- `build-trackercore.xml`, `build-site.xml`, `build-add-tracker-resources-and-copy-lib-from-OSP.xml`, and `jarscripts/` build the Java/SwingJS artifacts.
- `distribution/tracker.jar` and `distribution/tracker-assets.zip` are checked-in release artifacts; the source build requires the separate OSP core and optional video engine repositories.
- No modern GitHub Actions/Windows installer workflow was found in this snapshot. The public project site provides installers, but packaging is not a clean Python/Windows CI template for us to copy.

## License and data notes

- Code license: `GPL-3.0` (`LICENSE` and source headers).
- Model weights: none in the learned-model sense.
- Example videos/resources: individual media/resource terms are not normalized in the repository; review before redistribution.
- External OSP core and video-engine repositories have their own licenses. `Needs license review` before copying or embedding any code/assets.

## What to reuse / what not to copy

- Reuse conceptually: `TFrame`/`TrackerPanel` view composition, frame-vs-step semantics, track/tool object taxonomy, XML loader pattern, rich kinematic variable registry, and keyframe-based auto-tracking correction.
- Do not copy the Swing/OSP inheritance graph into the Python application. Keep our `Track`, `TrackPoint`, `Calibration`, `CoordinateSystem`, and `ProcessedData` independent from PySide6.
- Read first for future Phase 2/3 work: `TrackerPanel.java`, `TTrack.java`, `PointMass.java`, `PositionStep.java`, `AutoTracker.java`, `Calibration.java`, `CoordAxes.java`, `PlotTrackView.java`, `TableTrackView.java`, and `TrackerIO.java`.
