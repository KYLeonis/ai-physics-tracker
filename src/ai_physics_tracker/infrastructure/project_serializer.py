"""Project 的 schema v1/v2 JSON 映射，与领域模型隔离。

generic 项目按 v1 读写；publication 项目（required_capabilities 非空）按
v2 读写，v2 的 publication 集合 codecs 见 `publication_serializer`
（ADR-0017）。
"""

from dataclasses import replace
from pathlib import PurePosixPath
from typing import cast
from uuid import UUID

from ai_physics_tracker.domain.calibration import Calibration
from ai_physics_tracker.domain.derived import DerivedData, DerivedInput
from ai_physics_tracker.domain.project import Project, Registries
from ai_physics_tracker.domain.timeline import Timeline, has_time_mismatch
from ai_physics_tracker.domain.track import Track, TrackPoint
from ai_physics_tracker.domain.tracking_run import TrackingRun
from ai_physics_tracker.domain.types import JsonObject
from ai_physics_tracker.domain.video import Video
from ai_physics_tracker.infrastructure.payload_helpers import (
    boolean as _boolean,
    expect_integer as _expect_integer,
    expect_number as _expect_number,
    expect_string as _expect_string,
    format_datetime as _format_datetime,
    integer as _integer,
    json_object as _json_object,
    number as _number,
    object_ as _object,
    object_sequence as _object_sequence,
    optional_integer as _optional_integer,
    optional_string as _optional_string,
    parse_datetime as _parse_datetime,
    point as _point,
    sequence as _sequence,
    sequence_of_sequences as _sequence_of_sequences,
    string as _string,
    string_tuple as _string_tuple,
)
from ai_physics_tracker.infrastructure.publication_serializer import (
    V2_TOP_LEVEL_KEYS,
    experiment_from_payload,
    experiment_to_payload,
    keyed_object_map,
    migration_from_payload,
    migration_to_payload,
    scientific_result_from_payload,
    scientific_result_to_payload,
    tracking_run_from_payload_v2,
    tracking_run_to_payload_v2,
    validate_required_capabilities,
)

LEGACY_SCHEMA_VERSION = 1
CURRENT_SCHEMA_VERSION = 2


def project_to_payload(project: Project) -> dict[str, object]:
    """序列化 Project：publication 项目写 v2，generic 项目写 v1。"""

    if project.required_capabilities:
        return _project_to_payload_v2(project)
    return _project_to_payload_v1(project)


def _common_collections_to_payload(project: Project) -> dict[str, object]:
    """两种 schema 共用的顶层集合（不含 schema_version 与 tracking_runs）。"""

    return {
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
    }


def _project_to_payload_v1(project: Project) -> dict[str, object]:
    """schema v1 的 JSON 映射，并原样合并未知键。"""

    for run in project.tracking_runs:
        if len(run.member_track_ids) != 1 or run.experiment_id is not None:
            raise ValueError(
                "v1 project cannot carry experiment-bound or multi-member tracking runs"
            )
    payload: dict[str, object] = {"schema_version": LEGACY_SCHEMA_VERSION}
    payload.update(
        {
            key: value
            for key, value in project.extra_fields.items()
            if key != "schema_version"
        }
    )
    payload.update(_common_collections_to_payload(project))
    payload["tracking_runs"] = [
        tracking_run_to_payload(item) for item in project.tracking_runs
    ]
    payload["registries"] = _registries_to_payload(project.registries)
    payload["ui_state"] = project.ui_state
    return payload


def _project_to_payload_v2(project: Project) -> dict[str, object]:
    """schema v2：v1 集合 + required_capabilities + keyed publication 集合。"""

    payload: dict[str, object] = {
        "schema_version": CURRENT_SCHEMA_VERSION,
        "required_capabilities": list(project.required_capabilities),
    }
    payload.update(
        {
            key: value
            for key, value in project.extra_fields.items()
            if key not in {"schema_version", *V2_TOP_LEVEL_KEYS}
        }
    )
    payload.update(_common_collections_to_payload(project))
    payload["tracking_runs"] = [
        tracking_run_to_payload_v2(item) for item in project.tracking_runs
    ]
    payload["experiments"] = {
        str(experiment.experiment_id): experiment_to_payload(experiment)
        for experiment in project.experiments
    }
    payload["scientific_results"] = {
        str(result.result_id): scientific_result_to_payload(result)
        for result in project.scientific_results
    }
    if project.migration is not None:
        payload["migration"] = migration_to_payload(project.migration)
    payload["registries"] = _registries_to_payload(project.registries)
    payload["ui_state"] = project.ui_state
    return payload


def project_from_payload(payload: dict[str, object]) -> Project:
    """按 payload 的 schema_version 反序列化；未知版本拒绝。"""

    version = payload.get("schema_version")
    if isinstance(version, bool) or not isinstance(version, int):
        raise ValueError(f"schema_version must be an integer, got {version!r}")
    if version == LEGACY_SCHEMA_VERSION:
        return _project_from_payload_v1(payload)
    if version == CURRENT_SCHEMA_VERSION:
        return _project_from_payload_v2(payload)
    raise ValueError(f"unsupported schema_version: {version!r}")


def _project_from_payload_v1(payload: dict[str, object]) -> Project:
    """反序列化 schema v1 数据，并在每个对象上保留未知键。"""

    known = _V1_TOP_LEVEL_KEYS
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
        tracking_runs=tuple(
            tracking_run_from_payload(item)
            for item in _object_sequence(
                payload.get("tracking_runs", []), "tracking_runs"
            )
        ),
        registries=_registries_from_payload(
            _object(payload.get("registries", {}), "registries")
        ),
        ui_state=_json_object(payload.get("ui_state", {}), "ui_state"),
        extra_fields=_unknown(payload, known),
    )
    return _with_time_mismatch_flags(project)


def _project_from_payload_v2(payload: dict[str, object]) -> Project:
    """反序列化 schema v2：required capability 与 keyed 集合 fail closed。"""

    capabilities = validate_required_capabilities(payload.get("required_capabilities"))
    known = _V1_TOP_LEVEL_KEYS | V2_TOP_LEVEL_KEYS
    migration_payload = payload.get("migration")
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
        tracking_runs=tuple(
            tracking_run_from_payload_v2(item)
            for item in _object_sequence(
                payload.get("tracking_runs", []), "tracking_runs"
            )
        ),
        required_capabilities=capabilities,
        migration=None
        if migration_payload is None
        else migration_from_payload(_object(migration_payload, "migration")),
        experiments=tuple(
            experiment_from_payload(item)
            for item in keyed_object_map(
                payload.get("experiments", {}), "experiments", "experiment_id"
            )
        ),
        scientific_results=tuple(
            scientific_result_from_payload(item)
            for item in keyed_object_map(
                payload.get("scientific_results", {}),
                "scientific_results",
                "result_id",
            )
        ),
        registries=_registries_from_payload(
            _object(payload.get("registries", {}), "registries")
        ),
        ui_state=_json_object(payload.get("ui_state", {}), "ui_state"),
        extra_fields=_unknown(payload, known),
    )
    return _with_time_mismatch_flags(project)


def _with_time_mismatch_flags(project: Project) -> Project:
    timeline_by_video = {item.video_id: item for item in project.timelines}
    observations = tuple(
        _mark_time_mismatch(point, project, timeline_by_video)
        for point in project.observations
    )
    return replace(project, observations=observations)


_V1_TOP_LEVEL_KEYS = {
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
    "tracking_runs",
    "registries",
    "ui_state",
}


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


def tracking_run_to_payload(run: TrackingRun) -> dict[str, object]:
    """TrackingRun 的 schema v1 JSON 映射；任务结果交换文件复用。

    只接受单成员 run：多成员/experiment 绑定 run 是 v2 manifest 语义，
    经 `publication_serializer.tracking_run_to_payload_v2` 写出。
    """

    if len(run.member_track_ids) != 1:
        raise ValueError(
            "v1 tracking run payload requires a single-member run; "
            "multi-member runs only exist in v2 publication projects"
        )

    return _merge_extra(
        run.extra_fields,
        {
            "run_id": str(run.run_id),
            "video_id": str(run.video_id),
            "track_id": str(run.member_track_ids[0]),
            "engine": run.engine,
            "engine_version": run.engine_version,
            "task_type": run.task_type,
            "config": run.config,
            "source_detail": run.source_detail,
            "model_snapshot": run.model_snapshot,
            "status": run.status,
            "error_message": run.error_message,
            "created_at": _format_datetime(run.created_at),
            "completed_at": (
                _format_datetime(run.completed_at)
                if run.completed_at is not None
                else None
            ),
        },
    )


def tracking_run_from_payload(payload: dict[str, object]) -> TrackingRun:
    """从 schema v1 JSON 记录重建单成员 TrackingRun；未知键保留。"""

    known = {
        "run_id",
        "video_id",
        "track_id",
        "engine",
        "engine_version",
        "task_type",
        "config",
        "source_detail",
        "model_snapshot",
        "status",
        "error_message",
        "created_at",
        "completed_at",
    }
    completed_at = _optional_string(payload.get("completed_at"))
    return TrackingRun(
        run_id=UUID(_string(payload, "run_id")),
        video_id=UUID(_string(payload, "video_id")),
        member_track_ids=(UUID(_string(payload, "track_id")),),
        engine=_string(payload, "engine"),
        engine_version=_string(payload, "engine_version"),
        task_type=_string(payload, "task_type"),
        config=_json_object(payload.get("config", {}), "config"),
        source_detail=_string(payload, "source_detail"),
        model_snapshot=_optional_string(payload.get("model_snapshot")),
        status=_string(payload, "status"),
        error_message=_optional_string(payload.get("error_message")),
        created_at=_parse_datetime(_string(payload, "created_at")),
        completed_at=(
            _parse_datetime(completed_at) if completed_at is not None else None
        ),
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
