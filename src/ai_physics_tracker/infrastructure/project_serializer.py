"""Schema-v1 JSON mapping isolated from the domain model."""

from dataclasses import replace
from datetime import datetime
from pathlib import PurePosixPath
from typing import cast
from uuid import UUID

from ai_physics_tracker.domain.calibration import Calibration
from ai_physics_tracker.domain.derived import DerivedData, DerivedInput
from ai_physics_tracker.domain.project import Project, Registries
from ai_physics_tracker.domain.timeline import Timeline, has_time_mismatch
from ai_physics_tracker.domain.track import Track, TrackPoint
from ai_physics_tracker.domain.types import JsonObject
from ai_physics_tracker.domain.video import Video

CURRENT_SCHEMA_VERSION = 1


def project_to_payload(project: Project) -> dict[str, object]:
    """Serialize a Project while faithfully merging unknown schema-v1 keys."""

    payload: dict[str, object] = {"schema_version": CURRENT_SCHEMA_VERSION}
    payload.update(
        {
            key: value
            for key, value in project.extra_fields.items()
            if key != "schema_version"
        }
    )
    payload.update(
        {
            "project_id": str(project.project_id),
            "name": project.name,
            "description": project.description,
            "created_at": _format_datetime(project.created_at),
            "modified_at": _format_datetime(project.modified_at),
            "videos": [_video_to_payload(item) for item in project.videos],
            "timelines": [_timeline_to_payload(item) for item in project.timelines],
            "tracks": [_track_to_payload(item) for item in project.tracks],
            "observations": [
                _track_point_to_payload(item) for item in project.observations
            ],
            "calibrations": [
                _calibration_to_payload(item) for item in project.calibrations
            ],
            "active_calibration_by_video": {
                str(video_id): str(calibration_id)
                for video_id, calibration_id in project.active_calibration_by_video.items()
            },
            "derived": [_derived_to_payload(item) for item in project.derived],
            "registries": _registries_to_payload(project.registries),
            "ui_state": project.ui_state,
        }
    )
    return payload


def project_from_payload(payload: dict[str, object]) -> Project:
    """Deserialize current-schema data and preserve unknown keys at every object."""

    known = {
        "schema_version",
        "project_id",
        "name",
        "description",
        "created_at",
        "modified_at",
        "videos",
        "timelines",
        "tracks",
        "observations",
        "calibrations",
        "active_calibration_by_video",
        "derived",
        "registries",
        "ui_state",
    }
    project = Project(
        project_id=UUID(_string(payload, "project_id")),
        name=_string(payload, "name"),
        description=_optional_string(payload.get("description")),
        created_at=_parse_datetime(_string(payload, "created_at")),
        modified_at=_parse_datetime(_string(payload, "modified_at")),
        videos=tuple(
            _video_from_payload(item)
            for item in _object_sequence(payload.get("videos", []), "videos")
        ),
        timelines=tuple(
            _timeline_from_payload(item)
            for item in _object_sequence(payload.get("timelines", []), "timelines")
        ),
        tracks=tuple(
            _track_from_payload(item)
            for item in _object_sequence(payload.get("tracks", []), "tracks")
        ),
        observations=tuple(
            _track_point_from_payload(item)
            for item in _object_sequence(
                payload.get("observations", []), "observations"
            )
        ),
        calibrations=tuple(
            _calibration_from_payload(item)
            for item in _object_sequence(
                payload.get("calibrations", []), "calibrations"
            )
        ),
        active_calibration_by_video={
            UUID(video_id): UUID(_expect_string(calibration_id, "calibration id"))
            for video_id, calibration_id in _object(
                payload.get("active_calibration_by_video", {}),
                "active_calibration_by_video",
            ).items()
        },
        derived=tuple(
            _derived_from_payload(item)
            for item in _object_sequence(payload.get("derived", []), "derived")
        ),
        registries=_registries_from_payload(
            _object(payload.get("registries", {}), "registries")
        ),
        ui_state=_json_object(payload.get("ui_state", {}), "ui_state"),
        extra_fields=_unknown(payload, known),
    )
    timeline_by_video = {item.video_id: item for item in project.timelines}
    observations = tuple(
        _mark_time_mismatch(point, project, timeline_by_video)
        for point in project.observations
    )
    return replace(project, observations=observations)


def _mark_time_mismatch(
    point: TrackPoint,
    project: Project,
    timeline_by_video: dict[UUID, Timeline],
) -> TrackPoint:
    track = next(item for item in project.tracks if item.track_id == point.track_id)
    timeline = timeline_by_video[track.video_id]
    if not has_time_mismatch(point.frame_index, point.time_s, timeline):
        return point
    if "time_mismatch" in point.quality_flags:
        return point
    return replace(point, quality_flags=(*point.quality_flags, "time_mismatch"))


def _video_to_payload(video: Video) -> dict[str, object]:
    return _merge_extra(
        video.extra_fields,
        {
            "video_id": str(video.video_id),
            "file_path": video.file_path.as_posix()
            if video.file_path is not None
            else None,
            "original_path": video.original_path,
            "display_name": video.display_name,
            "width_px": video.width_px,
            "height_px": video.height_px,
            "fps_container": video.fps_container,
            "frame_count": video.frame_count,
            "container_format": video.container_format,
            "sha256": video.sha256,
            "vfr_suspected": video.vfr_suspected,
        },
    )


def _video_from_payload(payload: dict[str, object]) -> Video:
    known = {
        "video_id",
        "file_path",
        "original_path",
        "display_name",
        "width_px",
        "height_px",
        "fps_container",
        "frame_count",
        "container_format",
        "sha256",
        "vfr_suspected",
    }
    return Video(
        video_id=UUID(_string(payload, "video_id")),
        file_path=None
        if payload.get("file_path") is None
        else PurePosixPath(_string(payload, "file_path")),
        original_path=_optional_string(payload.get("original_path")),
        display_name=_string(payload, "display_name"),
        width_px=_integer(payload, "width_px"),
        height_px=_integer(payload, "height_px"),
        fps_container=_number(payload, "fps_container"),
        frame_count=_integer(payload, "frame_count"),
        container_format=_optional_string(payload.get("container_format")),
        sha256=_optional_string(payload.get("sha256")),
        vfr_suspected=_boolean(payload.get("vfr_suspected", False), "vfr_suspected"),
        extra_fields=_unknown(payload, known),
    )


def _timeline_to_payload(timeline: Timeline) -> dict[str, object]:
    return _merge_extra(
        timeline.extra_fields,
        {
            "video_id": str(timeline.video_id),
            "fps_nominal": timeline.fps_nominal,
            "frame_indexing": timeline.frame_indexing,
            "working_zone": list(timeline.working_zone),
        },
    )


def _timeline_from_payload(payload: dict[str, object]) -> Timeline:
    known = {"video_id", "fps_nominal", "frame_indexing", "working_zone"}
    zone = _sequence(payload.get("working_zone"), "working_zone")
    if len(zone) != 2:
        raise ValueError("working_zone must contain two frame indices")
    return Timeline(
        video_id=UUID(_string(payload, "video_id")),
        fps_nominal=_number(payload, "fps_nominal"),
        frame_indexing=_string(payload, "frame_indexing"),
        working_zone=(
            _expect_integer(zone[0], "working_zone[0]"),
            _expect_integer(zone[1], "working_zone[1]"),
        ),
        extra_fields=_unknown(payload, known),
    )


def _track_to_payload(track: Track) -> dict[str, object]:
    return _merge_extra(
        track.extra_fields,
        {
            "track_id": str(track.track_id),
            "video_id": str(track.video_id),
            "name": track.name,
            "color": track.color,
            "kind": track.kind,
            "keypoint_group": track.keypoint_group,
            "notes": track.notes,
            "created_at": _format_datetime(track.created_at),
        },
    )


def _track_from_payload(payload: dict[str, object]) -> Track:
    known = {
        "track_id",
        "video_id",
        "name",
        "color",
        "kind",
        "keypoint_group",
        "notes",
        "created_at",
    }
    return Track(
        track_id=UUID(_string(payload, "track_id")),
        video_id=UUID(_string(payload, "video_id")),
        name=_string(payload, "name"),
        color=_string(payload, "color"),
        kind=_string(payload, "kind"),
        keypoint_group=_optional_string(payload.get("keypoint_group")),
        notes=_optional_string(payload.get("notes")),
        created_at=_parse_datetime(_string(payload, "created_at")),
        extra_fields=_unknown(payload, known),
    )


def _track_point_to_payload(point: TrackPoint) -> dict[str, object]:
    return _merge_extra(
        point.extra_fields,
        {
            "point_id": str(point.point_id),
            "track_id": str(point.track_id),
            "frame_index": point.frame_index,
            "time_s": point.time_s,
            "pixel_x": point.pixel_x,
            "pixel_y": point.pixel_y,
            "source": point.source,
            "source_detail": point.source_detail,
            "confidence": point.confidence,
            "visibility": point.visibility,
            "quality_flags": list(point.quality_flags),
            "status": point.status,
            "superseded_by": (
                str(point.superseded_by) if point.superseded_by is not None else None
            ),
            "created_at": _format_datetime(point.created_at),
            "modified_at": _format_datetime(point.modified_at),
        },
    )


def _track_point_from_payload(payload: dict[str, object]) -> TrackPoint:
    known = {
        "point_id",
        "track_id",
        "frame_index",
        "time_s",
        "pixel_x",
        "pixel_y",
        "source",
        "source_detail",
        "confidence",
        "visibility",
        "quality_flags",
        "status",
        "superseded_by",
        "created_at",
        "modified_at",
    }
    superseded = _optional_string(payload.get("superseded_by"))
    confidence = payload.get("confidence")
    return TrackPoint(
        point_id=UUID(_string(payload, "point_id")),
        track_id=UUID(_string(payload, "track_id")),
        frame_index=_integer(payload, "frame_index"),
        time_s=_number(payload, "time_s"),
        pixel_x=_number(payload, "pixel_x"),
        pixel_y=_number(payload, "pixel_y"),
        source=_string(payload, "source"),
        source_detail=_optional_string(payload.get("source_detail")),
        confidence=None
        if confidence is None
        else _expect_number(confidence, "confidence"),
        visibility=_string(payload, "visibility"),
        quality_flags=tuple(
            _expect_string(item, "quality_flags item")
            for item in _sequence(payload.get("quality_flags", []), "quality_flags")
        ),
        status=_string(payload, "status"),
        superseded_by=UUID(superseded) if superseded is not None else None,
        created_at=_parse_datetime(_string(payload, "created_at")),
        modified_at=_parse_datetime(_string(payload, "modified_at")),
        extra_fields=_unknown(payload, known),
    )


def _calibration_to_payload(calibration: Calibration) -> dict[str, object]:
    return _merge_extra(
        calibration.extra_fields,
        {
            "calibration_id": str(calibration.calibration_id),
            "video_id": str(calibration.video_id),
            "name": calibration.name,
            "type": calibration.type,
            "scale_end_1_px": list(calibration.scale_end_1_px),
            "scale_end_2_px": list(calibration.scale_end_2_px),
            "known_length": calibration.known_length,
            "unit": calibration.unit,
            "origin_px": list(calibration.origin_px)
            if calibration.origin_px is not None
            else None,
            "rotation_deg": calibration.rotation_deg,
            "applies_from_frame": calibration.applies_from_frame,
            "applies_to_frame": calibration.applies_to_frame,
            "notes": calibration.notes,
            "created_at": _format_datetime(calibration.created_at),
        },
    )


def _calibration_from_payload(payload: dict[str, object]) -> Calibration:
    known = {
        "calibration_id",
        "video_id",
        "name",
        "type",
        "scale_end_1_px",
        "scale_end_2_px",
        "known_length",
        "unit",
        "origin_px",
        "rotation_deg",
        "applies_from_frame",
        "applies_to_frame",
        "notes",
        "created_at",
    }
    return Calibration(
        calibration_id=UUID(_string(payload, "calibration_id")),
        video_id=UUID(_string(payload, "video_id")),
        name=_string(payload, "name"),
        type=_string(payload, "type"),
        scale_end_1_px=_point(payload.get("scale_end_1_px"), "scale_end_1_px"),
        scale_end_2_px=_point(payload.get("scale_end_2_px"), "scale_end_2_px"),
        known_length=_number(payload, "known_length"),
        unit=_string(payload, "unit"),
        origin_px=None
        if payload.get("origin_px") is None
        else _point(payload.get("origin_px"), "origin_px"),
        rotation_deg=_number(payload, "rotation_deg"),
        applies_from_frame=_optional_integer(payload.get("applies_from_frame")),
        applies_to_frame=_optional_integer(payload.get("applies_to_frame")),
        notes=_optional_string(payload.get("notes")),
        created_at=_parse_datetime(_string(payload, "created_at")),
        extra_fields=_unknown(payload, known),
    )


def _derived_to_payload(item: DerivedData) -> dict[str, object]:
    input_payload = _merge_extra(
        item.input.extra_fields,
        {
            "track_id": str(item.input.track_id),
            "source_filter": item.input.source_filter,
            "include_superseded": item.input.include_superseded,
        },
    )
    return _merge_extra(
        item.extra_fields,
        {
            "derived_id": str(item.derived_id),
            "track_id": str(item.track_id),
            "kind": item.kind,
            "input": input_payload,
            "calibration_ref": (
                str(item.calibration_ref) if item.calibration_ref is not None else None
            ),
            "pipeline": list(item.pipeline),
            "frames": list(item.frames),
            "values": [list(row) for row in item.values]
            if item.values is not None
            else None,
            "payload_ref": item.payload_ref,
            "unit": item.unit,
            "produced_by": item.produced_by,
            "created_at": _format_datetime(item.created_at),
            "status": item.status,
        },
    )


def _derived_from_payload(payload: dict[str, object]) -> DerivedData:
    known = {
        "derived_id",
        "track_id",
        "kind",
        "input",
        "calibration_ref",
        "pipeline",
        "frames",
        "values",
        "payload_ref",
        "unit",
        "produced_by",
        "created_at",
        "status",
    }
    input_payload = _object(payload.get("input"), "input")
    input_known = {"track_id", "source_filter", "include_superseded"}
    calibration_ref = _optional_string(payload.get("calibration_ref"))
    values_payload = payload.get("values")
    values = None
    if values_payload is not None:
        values = tuple(
            tuple(_expect_number(value, "derived value") for value in row)
            for row in _sequence_of_sequences(values_payload, "values")
        )
    return DerivedData(
        derived_id=UUID(_string(payload, "derived_id")),
        track_id=UUID(_string(payload, "track_id")),
        kind=_string(payload, "kind"),
        input=DerivedInput(
            track_id=UUID(_string(input_payload, "track_id")),
            source_filter=_optional_string(input_payload.get("source_filter")),
            include_superseded=_boolean(
                input_payload.get("include_superseded", False),
                "include_superseded",
            ),
            extra_fields=_unknown(input_payload, input_known),
        ),
        calibration_ref=UUID(calibration_ref) if calibration_ref is not None else None,
        pipeline=tuple(
            _json_object(item, "pipeline item")
            for item in _sequence(payload.get("pipeline", []), "pipeline")
        ),
        frames=tuple(
            _expect_integer(item, "frame")
            for item in _sequence(payload.get("frames", []), "frames")
        ),
        values=values,
        payload_ref=_optional_string(payload.get("payload_ref")),
        unit=_string(payload, "unit"),
        produced_by=_string(payload, "produced_by"),
        created_at=_parse_datetime(_string(payload, "created_at")),
        status=_string(payload, "status"),
        extra_fields=_unknown(payload, known),
    )


def _registries_to_payload(registries: Registries) -> dict[str, object]:
    return _merge_extra(
        registries.extra_fields,
        {
            "sources": list(registries.sources),
            "units": list(registries.units),
            "quality_flags": list(registries.quality_flags),
        },
    )


def _registries_from_payload(payload: dict[str, object]) -> Registries:
    known = {"sources", "units", "quality_flags"}
    return Registries(
        sources=_string_tuple(payload.get("sources", []), "sources"),
        units=_string_tuple(payload.get("units", []), "units"),
        quality_flags=_string_tuple(
            payload.get("quality_flags", []), "quality_flags"
        ),
        extra_fields=_unknown(payload, known),
    )


def _merge_extra(extra: JsonObject, known: dict[str, object]) -> dict[str, object]:
    payload: dict[str, object] = dict(extra)
    payload.update(known)
    return payload


def _unknown(payload: dict[str, object], known: set[str]) -> JsonObject:
    return cast(JsonObject, {key: value for key, value in payload.items() if key not in known})


def _format_datetime(value: datetime) -> str:
    return value.isoformat()


def _parse_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value)


def _string(payload: dict[str, object], key: str) -> str:
    return _expect_string(payload[key], key)


def _integer(payload: dict[str, object], key: str) -> int:
    return _expect_integer(payload[key], key)


def _number(payload: dict[str, object], key: str) -> float:
    return _expect_number(payload[key], key)


def _expect_string(value: object, name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{name} must be a string")
    return value


def _optional_string(value: object) -> str | None:
    if value is None:
        return None
    return _expect_string(value, "optional string")


def _expect_integer(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be an integer")
    return value


def _optional_integer(value: object) -> int | None:
    if value is None:
        return None
    return _expect_integer(value, "optional integer")


def _expect_number(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be numeric")
    return float(value)


def _boolean(value: object, name: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{name} must be boolean")
    return value


def _sequence(value: object, name: str) -> list[object]:
    if not isinstance(value, list):
        raise ValueError(f"{name} must be an array")
    return value


def _object(value: object, name: str) -> dict[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"{name} must be an object")
    return cast(dict[str, object], value)


def _json_object(value: object, name: str) -> JsonObject:
    return cast(JsonObject, _object(value, name))


def _object_sequence(value: object, name: str) -> list[dict[str, object]]:
    return [_object(item, f"{name} item") for item in _sequence(value, name)]


def _sequence_of_sequences(value: object, name: str) -> list[list[object]]:
    return [
        _sequence(item, f"{name} row") for item in _sequence(value, name)
    ]


def _string_tuple(value: object, name: str) -> tuple[str, ...]:
    return tuple(
        _expect_string(item, f"{name} item") for item in _sequence(value, name)
    )


def _point(value: object, name: str) -> tuple[float, float]:
    coordinates = _sequence(value, name)
    if len(coordinates) != 2:
        raise ValueError(f"{name} must contain two coordinates")
    return (
        _expect_number(coordinates[0], f"{name}[0]"),
        _expect_number(coordinates[1], f"{name}[1]"),
    )
