# Kinovea

## Repository

- Official repository: <https://github.com/Kinovea/Kinovea>
- Checked on: `2026-08-27`
- Snapshot commit: `b9bf9012f2b1c6ee9c888972c780f1c154148bb3`
- Default branch: `master`

## Purpose

Kinovea is a Windows video annotation and motion-analysis application for capture, playback, comparison, drawing, measurement and object tracking. It is not a physics-education package, but its separation of video decoding, screen/player management, drawing metadata, tracking state and calibration is highly relevant to a desktop application.

## Relevance to AI Physics Tracker

Kinovea is the strongest reference for a Windows-native video UX: cached/pre-buffered playback, a timestamp-based timeline, interactive frame navigation, trackable drawings, calibration by line/plane, and metadata sidecar persistence. It also has a small abstract tracker contract that can host multiple algorithms. The project uses WinForms/C# and a native FFmpeg/OpenCV boundary, so it is an architectural reference rather than a Python code dependency.

## Technology Stack

| Area | Implementation observed |
| --- | --- |
| Language | C#; C++/CLI/native C++ for FFmpeg player server |
| GUI | WinForms, modular assemblies |
| Video | `Kinovea.Video`, FFmpeg native reader, bitmap/synthetic/GIF readers, cache/prebuffer containers |
| Tracking | `AbstractTracker`; template matching and circle trackers using OpenCvSharp/OpenCV |
| Geometry/calibration | Custom geometry, projective homography, radial distortion, line/plane calibrators |
| Kinematics | `LinearKinematics`, `FilteredTrajectory`, `TimeSeriesCollection`, configurable derivative smoothing |
| Persistence | XML `.kva` metadata sidecars; mementos for undo/redo; workspace/window XML |
| Packaging | Visual Studio/MSBuild + native DLL copy + NSIS installer/portable zip |

## Repository Structure

```text
Kinovea/                         executable and top-level UI
Kinovea.ScreenManager/           player screens, metadata, drawings, tracking, calibration
Kinovea.Video/                   decoder abstraction, frame model, cache/prebuffer
Kinovea.Video.FFMpeg/            native FFmpeg player server
Kinovea.Pipeline/                frame producer/consumer pipeline
Kinovea.Services/                preferences, window descriptors, units and shared services
Kinovea.Tests/                   unit/integration tests for metadata and kinematics
VideoTests/                      video reader/cache/section tests
Installer/                      NSIS script and build/portable helpers
Refs/                            native/third-party runtime references
architecture.md                 assembly-level dependency map
```

## Key Files

### Main window and screens

`architecture.md`

- Declares `Kinovea` as the executable/top-level menu host, `Kinovea.ScreenManager` as the playback/capture and dual-screen coordinator, and `Kinovea.Video` as the decoder layer.
- This is a useful assembly boundary for our future GUI/application-service split.

`Kinovea/Program.cs`, `Kinovea/UserInterface/KinoveaMainWindow.cs` (top-level executable files)

- Initialize the WinForms application and host the top-level window. The exact startup path should be read with the current solution entry point when implementation begins.

`Kinovea.ScreenManager/PlayerScreen/PlayerScreen.cs`

- Owns one playback screen and exposes events such as `OpenVideoAsked`, `Loaded`, `PlayStarted`, `PauseAsked`, `ImageChanged`, and `DrawingAdded`.
- Delegates decoding to `FrameServerPlayer` and UI to `PlayerScreenUserInterface2`.

`Kinovea.ScreenManager/PlayerScreen/FrameServerPlayer.cs`

- Bridges screen metadata and the reader. It calls `VideoReader.MoveTo(...)` when the UI asks for a seek and initializes `CalibrationHelper.CaptureFramesPerSecond` from `VideoReader.Info.FramesPerSeconds`.
- This is the practical boundary between video timing and the rest of the screen.

### Video reading, seeking and caching

`Kinovea.Video/VideoReader.cs`

- Abstract decoder contract: `Open`, `Close`, `ExtractSummary`, `PostLoad`, `MoveNext`, `MoveTo`, `UpdateWorkingZone`, `BeforeFrameEnumeration`, `AfterFrameEnumeration`.
- Exposes `Current`, `Info`, `WorkingZone`, `DecodingMode`, capabilities and timestamp mapping.
- `MoveBy(int frames, bool decodeIfNecessary)` converts frame movement to timestamp movement using `Info.AverageTimeStampsPerFrame`.
- `EnumerateFrames(...)` provides lazy frame enumeration for export, while `MoveTo` handles random access.
- The contract explicitly supports on-demand, pre-buffering and caching readers; this is a stronger model than a single `cv2.VideoCapture` object.

`Kinovea.Video/VideoReaderAlwaysCaching.cs`, `Kinovea.Video/FrameContainers/Cache.cs`, `PreBuffer.cs`, `SingleFrame.cs`, `VideoFrame.cs`, `VideoInfo.cs`

- Implement storage policies and expose frames/timestamps. `Cache` and `PreBuffer` are worth reading before designing a frame cache or background decoder.

`Kinovea.Video.FFMpeg/PlayerServer/VideoReaderFFMpeg.cpp` and `.h`

- Native FFmpeg reader/player boundary. It shows why the GUI should depend on a stable reader interface and not directly on codec calls.

### Timeline and frame navigation

`Kinovea.ScreenManager/Metadata/Timeline.cs`

- `Timeline<T>` stores sparse timestamp-keyed values in a `SortedList<long,T>`.
- `Insert`, `ClosestFrom`, `Trim`, `Enumerate`, `Times`, `First`, and `Last` cover keyframe/track-marker use cases.
- `ClosestFrom` uses binary search and deterministic nearest selection; `Trim` disposes values implementing `IDisposable`.

`Kinovea.ScreenManager/PlayerScreen/Controls/FrameTracker.cs`

- Custom timeline widget with `Minimum`, `Maximum`, `Position`, `LeftHairline`, `RightHairline`, keyframe/cache/track markers and timestamp↔pixel conversion.
- `Scrub()` emits `PositionChanging` during drag; `Commit()` emits `PositionChanged` on release. This distinction prevents expensive decoding on every mouse move while still allowing interactive feedback.
- The control renders cache segments, keyframes, chronos and track markers and supports drag/drop of keyframes.

`Kinovea.ScreenManager/PlayerScreen/Controls/PlayerScreenUserInterface2.cs`

- Handles `FrameTracker.PositionChanging/PositionChanged`, synchronizes the UI playhead with `FrameServer.VideoReader.MoveBy(...)`/`MoveTo(...)`, and wires keyboard/frame-step actions.
- Read around `trkFrame_PositionChanging`, `trkFrame_PositionChanged`, `MoveTo(...)`, and `CurrentTimestamp` to reproduce the actual navigation chain.

Effective chain:

```text
FrameTracker mouse/keyboard event
  -> PositionChanging or PositionChanged
  -> PlayerScreenUserInterface2
  -> FrameServerPlayer / VideoReader.MoveTo or MoveBy
  -> current VideoFrame
  -> screen refresh + drawing/keyframe marker update
```

### Manual/automatic tracking

`Kinovea.ScreenManager/Tracking/Tracking/AbstractTracker.cs`

- Generic tracker contract with `IsReady`, `TrackStep`, `CreateTrackPoint`, `CreateReferenceTrackPoint`, `Trim`, `Clear`, `UpdateImage`, `Draw`, and `Dispose`.
- `TrackStep` receives prior `List<TimedPoint>`, current timestamp and OpenCV image, and returns a `TimedPoint` plus a reliability boolean.
- The contract explicitly separates the algorithm result from creation of the stored track point and from manual reference-point creation. This maps well to a Python engine adapter interface.

`Kinovea.ScreenManager/Tracking/Tracking/DrawingTrack.cs`

- A trackable drawing containing `List<TimedPoint> positions`, a timestamp→index map, tracking status, style/keyframe labels and a concrete `AbstractTracker`.
- `StartTracking`/`StopTracking` switch between edit/interactive states.
- `PerformTracking(VideoFrame current, Mat cvImage)` updates the tracker image, rejects already-tracked timestamps, recreates algorithm state when needed, calls `tracker.TrackStep(...)`, appends the new point, updates the timestamp map, and deliberately postpones kinematics/UI label work until tracking ends.
- `UpdateTrackPoint(...)` calls `tracker.CreateReferenceTrackPoint(...)` after a manual correction so subsequent tracking uses the corrected observation.
- `Trim(...)` removes later points and synchronizes internal tracker state via `tracker.Trim(...)`.

`Kinovea.ScreenManager/Tracking/Tracking/TemplateMatching/TrackerTemplateMatching.cs`

- Concrete OpenCV `Cv2.MatchTemplate` implementation.
- `IsReady` detects whether an algorithm-specific template exists; this matters after reopening a `.kva`, because only the result is persisted and the live template must be rebuilt from the current frame.
- `TrackStep` returns a `TemplateMatchResult` with `Similarity` and `Location`, applies a similarity threshold, and uses the previous point on failure.
- `CreateReferenceTrackPoint` captures a pixel-aligned ROI as a `TrackingTemplate` with `TrackingSource.Manual` and score `1.0`.
- Template update policy intentionally avoids drift on very good/very bad matches and updates on fair-but-accepted matches.

`Kinovea.ScreenManager/Tracking/Tracking/TemplateMatching/TrackingTemplate.cs`, `TemplateMatchResult.cs`, `TrackingSource.cs`

- `TrackingTemplate` stores timestamp, location, template bitmap, score and source (`Manual`, `Auto`, `ForcedClosest`).
- Template state is explicitly marked live/non-persisted; it is reconstructed after reopening. This is a useful distinction between durable `TrackPoint` data and ephemeral engine state.

Call chain:

```text
DrawingTrack.PerformTracking
  -> AbstractTracker.UpdateImage
  -> AbstractTracker.IsReady / CreateReferenceTrackPoint
  -> TrackerTemplateMatching.TrackStep
  -> MatchTemplate -> Cv2.MatchTemplate + MinMaxLoc
  -> CreateTrackPoint -> TimedPoint(timestamp, location, source/score)
  -> DrawingTrack.positions + timestamp index
  -> UpdateKinematics after tracking
```

### Calibration and coordinate system

`Kinovea.ScreenManager/Measurement/Calibration/CalibrationHelper.cs`

- Central transform/service for image→world conversion. Holds length/speed/acceleration/angular units, capture FPS, calibrator type, distortion helper, calibration drawing ID and a `CalibrationChanged` event.
- Supports line and plane calibration through `CalibrationByLine_Initialize/Update` and `CalibrationByPlane_Initialize/Update`.
- `GetPoint(...)` transforms one image point; `GetPointAtTime(...)` applies time-varying calibration/origin when the calibration drawing or coordinate-system drawing is itself tracked.
- `WriteXml`/`ReadXml` persist calibration line/plane, drawing ID, length unit and camera distortion.

`Kinovea.ScreenManager/Measurement/Calibration/CalibratorPlane.cs`

- Implements a quad-to-quad `ProjectiveMapper` homography.
- The transform stack is documented as viewport→image→rectified image→grid/world→offset; world coordinates use a Y-up convention while image coordinates use Y-down.
- `Initialize`, `Update`, `Transform`, `Untransform`, `SetOrigin`, `ResetOrigin`, `Project` are the core methods.

`Kinovea.ScreenManager/Measurement/Calibration/ProjectiveMapper.cs`, `DistortionHelper`/lens calibration files, `DrawingLine.cs`, `DrawingPlane.cs`, `FormCalibrateLine.cs`, `FormCalibratePlane.cs`

- Provide numerical mapping and the interactive calibration UI.

### Kinematics, plotting and measurement export

`Kinovea.ScreenManager/Measurement/Kinematics/LinearKinematics.cs`

- Builds position, horizontal/vertical displacement, speed, velocity and acceleration time series from a `FilteredTrajectory`.
- Uses timestamps and calibrated coordinates, pads endpoint derivative values, and can run `MotionFilter` smoothing for high-speed data.
- `BuildKinematics(...)`, `ComputeAccelerations(...)`, `GetSpeed(...)`, and `GetAcceleration(...)` are the key entry points.

`Kinovea.ScreenManager/Tracking/Tracking/DrawingTrack.cs`

- `UpdateKinematics()` is the bridge from raw `TimedPoint` positions to `filteredTrajectory.Initialize(positions, parentMetadata.CalibrationHelper)` and `linearKinematics.BuildKinematics(...)`.

`Kinovea.ScreenManager/Metadata/Serialization/MeasurementSerializationHelper.cs`

- Converts point, distance and angle drawings to export records and switches between image and world space based on `PreferencesManager.PlayerPreferences.ExportSpace`.

### Persistence and undo

`Kinovea.ScreenManager/Metadata/Serialization/MetadataSerializer.cs`

- Saves and loads `.kva` XML sidecar metadata, with format version, source video path, image size/timing, calibration and drawings.
- Supported metadata formats include `.kva`, `.trc`, `.srt`, `.json`, and `.xml` for import/compatibility.
- The load order matters: image size and timing are read before coordinates so values can be remapped to the current video.

`Kinovea.ScreenManager/Metadata/Serialization/DrawingSerializer.cs`, `KeyframeSerializer.cs`

- Reflection plus `[XmlType]` discovers drawing types; `IKvaSerializable.WriteXml/ReadXml` is the stable serialization contract.
- Keyframe/drawing mementos are strings used by undo/redo. Tracker assignment is serialized separately through `TrackabilityManager`.

`Kinovea.ScreenManager/Tracking/Tracking/DrawingTrack.cs`

- Writes `TrackPointList`; each `TimedPoint` carries durable timestamp/position data. It writes tracker parameters but not the algorithm's live template bitmap.

`Kinovea.Services/Window/WindowDescriptor.cs`

- Persists window identity, startup mode, screen list, splitter/layout state and capture-screen backup via explicit XML read/write methods.

## Tests, build and release

- `Kinovea.Tests/Kinematics/MovingObject.cs` and `KinematicsTestData.cs` provide synthetic/object data for kinematics tests; `Kinovea.Tests/Time/*`, `HistoryStackTester/*`, `ProjectiveGeometry/*`, `KSV/*`, and `Metadata/TrackableDrawing.cs` cover timing, undo, geometry and serialization.
- `VideoTests/VideoFrameCacheTests.cs` and `VideoSectionTests.cs` exercise reader/cache behavior.
- `Kinovea.VS2019.sln` + project files define the Windows build. `Kinovea.targets` copies FFmpeg DLLs, `OpenCvSharpExtern.dll`, XSLT and drawing-tool XML into the release directory.
- `Installer/makeinstaller.py` runs MSBuild Release x64 then `makensis Installer/kinovea.nsi`. `makeportable.py` creates a portable build/zip. The NSIS script embeds the GPLv2 license and copies the complete release directory.

## License and data notes

- Code license: `GPL-2.0` (`license.md`, source headers, GitHub metadata).
- Model weights: none in the learned-model sense.
- Third-party/native runtime: FFmpeg, OpenCvSharp/OpenCV, TurboJPEG and Microsoft runtimes are copied/redistributed by the build; each needs a separate notice/license check.
- Example/drawing assets: review individual files before redistribution.

## What to reuse

- Reuse: `VideoReader` capability contract, timestamp-based `FrameTracker`, `AbstractTracker` lifecycle, durable-vs-ephemeral tracker state, calibration transform stack, metadata sidecar strategy, explicit `CalibrationChanged` event, and Windows native dependency packaging.
- Avoid: storing all GUI state and data inside WinForms drawing objects. Our domain model should keep raw observations and processed results independent of PySide6.
- Highest-value reading order: `VideoReader.cs` → `FrameTracker.cs` → `DrawingTrack.cs` → `AbstractTracker.cs` → `TrackerTemplateMatching.cs` → `CalibrationHelper.cs`/`CalibratorPlane.cs` → `LinearKinematics.cs` → `MetadataSerializer.cs`.
