"""schema v2 publication 集合的 JSON 映射（契约 §1–§3、§7）。

与 `project_serializer` 的 v1 映射分离：v2 顶层多出 required_capabilities、
keyed publication collections、migration 记录与多成员 run 形态。所有
load 侧校验 fail closed：key/id 不一致、未知 capability、悬空引用在
domain decode 前直接拒绝。
"""

from pathlib import PurePosixPath
from typing import cast
from uuid import UUID

from ai_physics_tracker.domain.pendulum import (
    ROLE_ORDER,
    ExperimentActivationRecord,
    ExperimentFixedCheck,
    ExperimentFrameSet,
    PendulumExperiment,
    PendulumGeometry,
    PendulumRoles,
    PhysicalParameters,
    RoleAdoptionCount,
    RoleBindingEditRecord,
    TrueVertical,
)
from ai_physics_tracker.domain.project import (
    PUBLICATION_REQUIRED_CAPABILITIES,
    MigrationRecord,
)
from ai_physics_tracker.domain.scientific_result import (
    ResultColumn,
    ResultPayload,
    ScientificResult,
)
from ai_physics_tracker.domain.tracking_run import TrackingRun
from ai_physics_tracker.domain.types import JsonObject
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
    string as _string,
)

# v2 payload 顶层新增键；project 级 unknown 键保留需排除这些。
V2_TOP_LEVEL_KEYS = frozenset(
    {"required_capabilities", "experiments", "scientific_results", "migration"}
)


def validate_required_capabilities(payload_value: object) -> tuple[str, ...]:
    """校验并返回 v2 required_capabilities；未知/缺失 capability 拒绝。"""

    items = payload_value
    if not isinstance(items, list) or not all(isinstance(item, str) for item in items):
        raise ValueError("v2 project must declare required_capabilities as a string array")
    declared = set(items)
    unknown = declared - set(PUBLICATION_REQUIRED_CAPABILITIES)
    if unknown:
        raise ValueError(f"unknown required capabilities: {sorted(unknown)}")
    missing = set(PUBLICATION_REQUIRED_CAPABILITIES) - declared
    if missing:
        raise ValueError(f"publication project missing required capabilities: {sorted(missing)}")
    return tuple(PUBLICATION_REQUIRED_CAPABILITIES)


def keyed_object_map(value: object, name: str, id_field: str) -> list[dict[str, object]]:
    """读取 keyed-by-UUID 集合，强制 map key 等于对象自身 ID 字段。"""

    collection = _object(value, name)
    entries: list[dict[str, object]] = []
    for key, item in collection.items():
        entry = _object(item, f"{name} item")
        if entry.get(id_field) != key:
            raise ValueError(f"{name} map key must equal the object {id_field}")
        entries.append(entry)
    return entries


def migration_to_payload(migration: MigrationRecord) -> dict[str, object]:
    return {
        "source_schema_version": migration.source_schema_version,
        "source_manifest_sha256": migration.source_manifest_sha256,
    }


def migration_from_payload(payload: dict[str, object]) -> MigrationRecord:
    return MigrationRecord(
        source_schema_version=_integer(payload, "source_schema_version"),
        source_manifest_sha256=_string(payload, "source_manifest_sha256"),
    )


def roles_to_payload(roles: PendulumRoles) -> dict[str, object]:
    return {role: str(member) for role, member in roles.by_role().items()}


def roles_from_payload(payload_value: object, name: str) -> PendulumRoles:
    obj = _object(payload_value, name)
    if set(obj) != set(ROLE_ORDER):
        raise ValueError(f"{name} must contain exactly the canonical roles")
    return PendulumRoles(
        tip=UUID(_expect_string(obj["tip"], f"{name}.tip")),
        body_top=UUID(_expect_string(obj["body_top"], f"{name}.body_top")),
        body_bottom=UUID(_expect_string(obj["body_bottom"], f"{name}.body_bottom")),
        pivot=UUID(_expect_string(obj["pivot"], f"{name}.pivot")),
    )


def experiment_to_payload(experiment: PendulumExperiment) -> dict[str, object]:
    geometry_payload: dict[str, object] = {
        "fixed_pivot_px": None
        if experiment.geometry.fixed_pivot_px is None
        else list(experiment.geometry.fixed_pivot_px),
        "true_vertical": None
        if experiment.geometry.true_vertical is None
        else true_vertical_to_payload(experiment.geometry.true_vertical),
        "tip_radius_reference_px": experiment.geometry.tip_radius_reference_px,
    }
    return _merge_publication_extra(
        experiment.extra_fields,
        {
            "experiment_id": str(experiment.experiment_id),
            "video_id": str(experiment.video_id),
            "mode": experiment.mode,
            "contract_version": experiment.contract_version,
            "roles": roles_to_payload(experiment.roles),
            "measurement_revision": experiment.measurement_revision,
            "geometry": geometry_payload,
            "physical": None
            if experiment.physical is None
            else physical_to_payload(experiment.physical),
            "release_frame_index": experiment.release_frame_index,
            "frame_set": None
            if experiment.frame_set is None
            else frame_set_to_payload(experiment.frame_set),
            "fixed_check": None
            if experiment.fixed_check is None
            else fixed_check_to_payload(experiment.fixed_check),
            "active_infer_run_id": None
            if experiment.active_infer_run_id is None
            else str(experiment.active_infer_run_id),
            "activation_history": [
                history_record_to_payload(record)
                for record in experiment.activation_history
            ],
            "created_at": _format_datetime(experiment.created_at),
        },
    )


def experiment_from_payload(payload: dict[str, object]) -> PendulumExperiment:
    known = {
        "experiment_id",
        "video_id",
        "mode",
        "contract_version",
        "roles",
        "measurement_revision",
        "geometry",
        "physical",
        "release_frame_index",
        "frame_set",
        "fixed_check",
        "active_infer_run_id",
        "activation_history",
        "created_at",
    }
    active_run = _optional_string(payload.get("active_infer_run_id"))
    return PendulumExperiment(
        experiment_id=UUID(_string(payload, "experiment_id")),
        video_id=UUID(_string(payload, "video_id")),
        roles=roles_from_payload(payload.get("roles"), "roles"),
        created_at=_parse_datetime(_string(payload, "created_at")),
        measurement_revision=_integer(payload, "measurement_revision"),
        geometry=geometry_from_payload(_object(payload.get("geometry", {}), "geometry")),
        physical=None
        if payload.get("physical") is None
        else physical_from_payload(_object(payload.get("physical"), "physical")),
        release_frame_index=_optional_integer(payload.get("release_frame_index")),
        frame_set=None
        if payload.get("frame_set") is None
        else frame_set_from_payload(_object(payload.get("frame_set"), "frame_set")),
        fixed_check=None
        if payload.get("fixed_check") is None
        else fixed_check_from_payload(_object(payload.get("fixed_check"), "fixed_check")),
        active_infer_run_id=UUID(active_run) if active_run is not None else None,
        activation_history=tuple(
            history_record_from_payload(item)
            for item in _object_sequence(
                payload.get("activation_history", []), "activation_history"
            )
        ),
        mode=_string(payload, "mode"),
        contract_version=_integer(payload, "contract_version"),
        extra_fields=cast(JsonObject, _unknown(payload, known)),
    )


def true_vertical_to_payload(vertical: TrueVertical) -> dict[str, object]:
    return {
        "top_px": list(vertical.top_px),
        "bottom_px": list(vertical.bottom_px),
        "direction_confirmed": vertical.direction_confirmed,
        "confirmed_digest": vertical.confirmed_digest,
    }


def geometry_from_payload(payload: dict[str, object]) -> PendulumGeometry:
    vertical_payload = payload.get("true_vertical")
    return PendulumGeometry(
        fixed_pivot_px=None
        if payload.get("fixed_pivot_px") is None
        else _point(payload.get("fixed_pivot_px"), "fixed_pivot_px"),
        true_vertical=None
        if vertical_payload is None
        else true_vertical_from_payload(_object(vertical_payload, "true_vertical")),
        tip_radius_reference_px=None
        if payload.get("tip_radius_reference_px") is None
        else _expect_number(
            payload.get("tip_radius_reference_px"), "tip_radius_reference_px"
        ),
    )


def true_vertical_from_payload(payload: dict[str, object]) -> TrueVertical:
    return TrueVertical(
        top_px=_point(payload.get("top_px"), "top_px"),
        bottom_px=_point(payload.get("bottom_px"), "bottom_px"),
        direction_confirmed=_boolean(
            payload.get("direction_confirmed", False), "direction_confirmed"
        ),
        confirmed_digest=_optional_string(payload.get("confirmed_digest")),
    )


def physical_to_payload(physical: PhysicalParameters) -> dict[str, object]:
    return {
        "length_m": physical.length_m,
        "g_m_s2": physical.g_m_s2,
        "length_source": physical.length_source,
        "g_source": physical.g_source,
    }


def physical_from_payload(payload: dict[str, object]) -> PhysicalParameters:
    return PhysicalParameters(
        length_m=_number(payload, "length_m"),
        g_m_s2=_number(payload, "g_m_s2"),
        length_source=_string(payload, "length_source"),
        g_source=_string(payload, "g_source"),
    )


def frame_set_to_payload(frame_set: ExperimentFrameSet) -> dict[str, object]:
    return _merge_publication_extra(
        frame_set.extra_fields,
        {
            "frames": list(frame_set.frames),
            "algorithm": frame_set.algorithm,
            "seed": frame_set.seed,
            "working_zone": list(frame_set.working_zone)
            if frame_set.working_zone is not None
            else None,
            "source_video_sha256": frame_set.source_video_sha256,
            "created_at": _format_datetime(frame_set.created_at),
        },
    )


def frame_set_from_payload(payload: dict[str, object]) -> ExperimentFrameSet:
    known = {
        "frames",
        "algorithm",
        "seed",
        "working_zone",
        "source_video_sha256",
        "created_at",
    }
    zone = payload.get("working_zone")
    if zone is None:
        working_zone = None
    elif isinstance(zone, list) and len(zone) == 2:
        working_zone = (
            _expect_integer(zone[0], "working_zone[0]"),
            _expect_integer(zone[1], "working_zone[1]"),
        )
    else:
        # 与 _timeline_from_payload 同标准:畸形 zone fail closed,
        # 不静默降级为 None(会造成不可逆的数据形态丢失)
        raise ValueError("frame_set working_zone must be null or two frame indices")
    return ExperimentFrameSet(
        frames=tuple(
            _expect_integer(item, "frames item")
            for item in _sequence(payload.get("frames"), "frames")
        ),
        algorithm=_string(payload, "algorithm"),
        seed=_optional_integer(payload.get("seed")),
        working_zone=working_zone,
        source_video_sha256=_optional_string(payload.get("source_video_sha256")),
        created_at=_parse_datetime(_string(payload, "created_at")),
        extra_fields=cast(JsonObject, _unknown(payload, known)),
    )


def fixed_check_to_payload(fixed_check: ExperimentFixedCheck) -> dict[str, object]:
    return {
        "frames": list(fixed_check.frames),
        "label_digest": fixed_check.label_digest,
        "created_at": _format_datetime(fixed_check.created_at),
    }


def fixed_check_from_payload(payload: dict[str, object]) -> ExperimentFixedCheck:
    return ExperimentFixedCheck(
        frames=tuple(
            _expect_integer(item, "frames item")
            for item in _sequence(payload.get("frames"), "frames")
        ),
        label_digest=_string(payload, "label_digest"),
        created_at=_parse_datetime(_string(payload, "created_at")),
    )


def history_record_to_payload(
    record: RoleBindingEditRecord | ExperimentActivationRecord,
) -> dict[str, object]:
    if isinstance(record, RoleBindingEditRecord):
        return {
            "kind": "role_binding_edit",
            "record_id": str(record.record_id),
            "timestamp": _format_datetime(record.timestamp),
            "old_roles": None
            if record.old_roles is None
            else roles_to_payload(record.old_roles),
            "new_roles": roles_to_payload(record.new_roles),
            "revision": record.revision,
        }
    return {
        "kind": "activation",
        "record_id": str(record.record_id),
        "timestamp": _format_datetime(record.timestamp),
        "action": record.action,
        "from_run_id": None
        if record.from_run_id is None
        else str(record.from_run_id),
        "to_run_id": None if record.to_run_id is None else str(record.to_run_id),
        "role_counts": [
            {
                "role": count.role,
                "adopted_count": count.adopted_count,
                "manual_preserved_count": count.manual_preserved_count,
            }
            for count in record.role_counts
        ],
        "input_digest": record.input_digest,
    }


def history_record_from_payload(
    payload: dict[str, object],
) -> RoleBindingEditRecord | ExperimentActivationRecord:
    kind = _string(payload, "kind")
    record_id = UUID(_string(payload, "record_id"))
    timestamp = _parse_datetime(_string(payload, "timestamp"))
    if kind == "role_binding_edit":
        return RoleBindingEditRecord(
            record_id=record_id,
            timestamp=timestamp,
            old_roles=None
            if payload.get("old_roles") is None
            else roles_from_payload(payload.get("old_roles"), "old_roles"),
            new_roles=roles_from_payload(payload.get("new_roles"), "new_roles"),
            revision=_integer(payload, "revision"),
        )
    if kind == "activation":
        from_run = _optional_string(payload.get("from_run_id"))
        to_run = _optional_string(payload.get("to_run_id"))
        return ExperimentActivationRecord(
            record_id=record_id,
            timestamp=timestamp,
            action=_string(payload, "action"),
            from_run_id=UUID(from_run) if from_run is not None else None,
            to_run_id=UUID(to_run) if to_run is not None else None,
            role_counts=tuple(
                RoleAdoptionCount(
                    role=_string(count, "role"),
                    adopted_count=_integer(count, "adopted_count"),
                    manual_preserved_count=_integer(count, "manual_preserved_count"),
                )
                for count in _object_sequence(payload.get("role_counts", []), "role_counts")
            ),
            input_digest=_string(payload, "input_digest"),
        )
    raise ValueError(f"unknown activation history record kind: {kind}")


def scientific_result_to_payload(result: ScientificResult) -> dict[str, object]:
    return _merge_publication_extra(
        result.extra_fields,
        {
            "result_id": str(result.result_id),
            "experiment_id": str(result.experiment_id),
            "kind": result.kind,
            "contract_version": result.contract_version,
            "created_at": _format_datetime(result.created_at),
            "input_digest": result.input_digest,
            "core_version": result.core_version,
            "execution_status": result.execution_status,
            "freshness": result.freshness,
            "payload": None
            if result.payload is None
            else result_payload_to_payload(result.payload),
        },
    )


def scientific_result_from_payload(payload: dict[str, object]) -> ScientificResult:
    known = {
        "result_id",
        "experiment_id",
        "kind",
        "contract_version",
        "created_at",
        "input_digest",
        "core_version",
        "execution_status",
        "freshness",
        "payload",
    }
    return ScientificResult(
        result_id=UUID(_string(payload, "result_id")),
        experiment_id=UUID(_string(payload, "experiment_id")),
        kind=_string(payload, "kind"),
        contract_version=_integer(payload, "contract_version"),
        created_at=_parse_datetime(_string(payload, "created_at")),
        input_digest=_string(payload, "input_digest"),
        core_version=_string(payload, "core_version"),
        execution_status=_string(payload, "execution_status"),
        freshness=_string(payload, "freshness"),
        payload=None
        if payload.get("payload") is None
        else result_payload_from_payload(_object(payload.get("payload"), "payload")),
        extra_fields=cast(JsonObject, _unknown(payload, known)),
    )


def result_payload_to_payload(payload: ResultPayload) -> dict[str, object]:
    merged: dict[str, object] = dict(payload.extra_fields)
    merged.update(
        {
            "format": payload.format,
            "path": payload.path.as_posix(),
            "size_bytes": payload.size_bytes,
            "sha256": payload.sha256,
            "columns": [
                {"name": column.name, "dtype": column.dtype, "unit": column.unit}
                for column in payload.columns
            ],
        }
    )
    return merged


def result_payload_from_payload(payload: dict[str, object]) -> ResultPayload:
    known = {"format", "path", "size_bytes", "sha256", "columns"}
    return ResultPayload(
        format=_string(payload, "format"),
        path=PurePosixPath(_string(payload, "path")),
        size_bytes=_integer(payload, "size_bytes"),
        sha256=_string(payload, "sha256"),
        columns=tuple(
            ResultColumn(
                name=_string(column, "name"),
                dtype=_string(column, "dtype"),
                unit=_optional_string(column.get("unit")),
            )
            for column in _object_sequence(payload.get("columns", []), "columns")
        ),
        extra_fields=cast(JsonObject, _unknown(payload, known)),
    )


def tracking_run_to_payload_v2(run: TrackingRun) -> dict[str, object]:
    payload: dict[str, object] = dict(run.extra_fields)
    payload.update(
        {
            "run_id": str(run.run_id),
            "video_id": str(run.video_id),
            "member_track_ids": [str(member) for member in run.member_track_ids],
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
        }
    )
    if run.experiment_id is not None:
        payload["experiment_id"] = str(run.experiment_id)
        payload["role_bindings"] = roles_to_payload(run.role_bindings)
    return payload


def tracking_run_from_payload_v2(payload: dict[str, object]) -> TrackingRun:
    known = {
        "run_id",
        "video_id",
        "member_track_ids",
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
        "experiment_id",
        "role_bindings",
    }
    members_raw = _sequence(payload.get("member_track_ids"), "member_track_ids")
    experiment_id = _optional_string(payload.get("experiment_id"))
    role_bindings_payload = payload.get("role_bindings")
    completed_at = _optional_string(payload.get("completed_at"))
    return TrackingRun(
        run_id=UUID(_string(payload, "run_id")),
        video_id=UUID(_string(payload, "video_id")),
        member_track_ids=tuple(
            UUID(_expect_string(item, "member_track_ids item"))
            for item in members_raw
        ),
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
        experiment_id=UUID(experiment_id) if experiment_id is not None else None,
        role_bindings=None
        if role_bindings_payload is None
        else roles_from_payload(role_bindings_payload, "role_bindings"),
        extra_fields=cast(JsonObject, _unknown(payload, known)),
    )


def _merge_publication_extra(extra: JsonObject, known: dict[str, object]) -> dict[str, object]:
    payload: dict[str, object] = dict(extra)
    payload.update(known)
    return payload


def _unknown(payload: dict[str, object], known: set[str]) -> JsonObject:
    return cast(
        JsonObject, {key: value for key, value in payload.items() if key not in known}
    )
