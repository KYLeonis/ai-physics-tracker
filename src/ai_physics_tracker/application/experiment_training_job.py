"""experiment 四 role 联合训练的请求构造与结果验证（P1.3-S2，Qt-free 纯应用层）。

契约 §4/§6 与 P1.2 review EX4：训练请求必须走**唯一路径**
`build_experiment_export_plan`（内部即 join → rows → split_indices），
并冻结全量 complete label digest；worker 只消费序列化请求，绝不持有
session。结果验证在 host 侧 fail closed：digest 回显、stale 复核、
bodyparts 身份与 run-owned 输出一处不满足即拒绝登记 completed。
"""

from dataclasses import dataclass, replace
import logging
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from ai_physics_tracker.application.annotation_join import (
    canonical_label_digest,
    join_complete_frames,
)
from ai_physics_tracker.application.experiment_export import (
    ExperimentExportRow,
    build_experiment_export_plan,
)
from ai_physics_tracker.application.project_session import (
    ProjectSession,
    ProjectSessionError,
)
from ai_physics_tracker.application.tracking_types import TrainingParams
from ai_physics_tracker.domain.pendulum import ROLE_ORDER
from ai_physics_tracker.domain.tracking_run import (
    TrackingRun,
    create_tracking_run,
    mark_run_completed,
)

logger = logging.getLogger(__name__)

#: result payload 中联合训练专属字段的键名（worker 写入、verifier 读取）
RESULT_SECTION = "experiment_training"


from ai_physics_tracker.infrastructure.hashing import file_sha256 as _file_sha256


@dataclass(frozen=True)
class ExperimentTrainingRequest:
    """不可变联合训练请求；prepare 构建、worker 消费、verifier 对照。"""

    run_id: str
    experiment_id: str
    video_id: str
    video_path: str
    video_sha256: str
    rows: tuple[ExperimentExportRow, ...]
    train_indices: tuple[int, ...]
    test_indices: tuple[int, ...]
    label_digest: str
    check_frames: tuple[int, ...]
    params_config: dict[str, Any]

    def to_payload(self) -> dict[str, Any]:
        """worker 协议 payload（canonical JSON 可序列化；行序 = 帧号升序）。"""

        return {
            "run_id": self.run_id,
            "experiment_id": self.experiment_id,
            "video_id": self.video_id,
            "video_path": self.video_path,
            "video_sha256": self.video_sha256,
            "rows": [
                {
                    "frame_index": row.frame_index,
                    "coordinates": [
                        [float(x), float(y)] for x, y in row.coordinates
                    ],
                }
                for row in self.rows
            ],
            "train_indices": list(self.train_indices),
            "test_indices": list(self.test_indices),
            "label_digest": self.label_digest,
            "check_frames": list(self.check_frames),
            "params": dict(self.params_config),
        }

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "ExperimentTrainingRequest":
        rows = tuple(
            ExperimentExportRow(
                frame_index=int(item["frame_index"]),
                coordinates=tuple(
                    (float(pair[0]), float(pair[1])) for pair in item["coordinates"]
                ),
            )
            for item in payload["rows"]
        )
        return cls(
            run_id=str(payload["run_id"]),
            experiment_id=str(payload["experiment_id"]),
            video_id=str(payload["video_id"]),
            video_path=str(payload["video_path"]),
            video_sha256=str(payload["video_sha256"]),
            rows=rows,
            train_indices=tuple(int(i) for i in payload["train_indices"]),
            test_indices=tuple(int(i) for i in payload["test_indices"]),
            label_digest=str(payload["label_digest"]),
            check_frames=tuple(int(f) for f in payload.get("check_frames", ())),
            params_config=dict(payload["params"]),
        )


def prepare_experiment_training(
    session: ProjectSession,
    experiment_id: UUID,
    *,
    run_id: UUID | None = None,
    params: TrainingParams | None = None,
) -> tuple[TrackingRun, ExperimentTrainingRequest]:
    """从 P1.2 complete/fixed split 构建不可变联合训练请求并登记 pending run。

    EX4 唯一路径：rows 与 split_indices 只来自一次 `build_experiment_export_plan`
    调用（fixed-check 无效即整体拒绝）；全量 label digest 在此刻冻结，worker
    回显、verifier 复核均对照该值。
    """

    experiment = session.pendulum_experiment(experiment_id)
    members = experiment.roles.track_ids()

    active = [
        run.run_id
        for run in session.tracking_runs()
        if any(member in run.member_track_ids for member in members)
        and run.status in {"pending", "running"}
    ]
    if active:
        raise ProjectSessionError(
            "This experiment already has an active engine task "
            f"(run {active[0]}); cancel or wait for it before training"
        )

    # EX4：唯一路径 join → rows → split_indices；fixed-check 失效在此整体拒绝
    try:
        plan = build_experiment_export_plan(session.project, experiment)
    except ValueError as error:
        raise ProjectSessionError(str(error)) from error
    if not plan.train_rows:
        raise ProjectSessionError(
            "All complete frames belong to the fixed-check set; "
            "at least one training frame is required"
        )

    video = next(
        (
            video
            for video in session.project.videos
            if video.video_id == experiment.video_id
        ),
        None,
    )
    if video is None:
        raise ProjectSessionError("Experiment video is not registered")
    video_path = session.video_path(video)
    if video_path is None or not video_path.is_file():
        raise ProjectSessionError(
            f"Cannot resolve local video file for: {video.display_name}"
        )

    label_digest = canonical_label_digest(
        join_complete_frames(session.project, experiment)
    )
    actual_params = params or TrainingParams()
    train_indices, test_indices = plan.split_indices()
    check_frames = tuple(row.frame_index for row in plan.test_rows)
    resolved_run_id = run_id or uuid4()
    # 行序 = 帧号升序(split_indices 的行序约定);rows/train/test 三者同源同序
    ordered_rows = tuple(
        sorted((*plan.train_rows, *plan.test_rows), key=lambda row: row.frame_index)
    )
    request = ExperimentTrainingRequest(
        run_id=str(resolved_run_id),
        experiment_id=str(experiment_id),
        video_id=str(video.video_id),
        video_path=str(video_path),
        video_sha256=_file_sha256(video_path),
        rows=ordered_rows,
        train_indices=train_indices,
        test_indices=test_indices,
        label_digest=label_digest,
        check_frames=check_frames,
        params_config=actual_params.to_config(),
    )

    config: dict[str, Any] = dict(actual_params.to_config())
    config.update(
        {
            "experiment_id": str(experiment_id),
            "label_digest": label_digest,
            "check_frames": list(check_frames),
            "train_rows": len(plan.train_rows),
            "test_rows": len(plan.test_rows),
            "request_kind": "experiment-joint-training-v1",
        }
    )
    run = create_tracking_run(
        video_id=video.video_id,
        member_track_ids=members,
        task_type="train",
        config=config,
        experiment_id=experiment_id,
        role_bindings=experiment.roles,
        run_id=resolved_run_id,
    )
    session.record_tracking_run(run)
    logger.info(
        "prepared experiment joint training run %s: %d train rows / %d test rows, digest %s",
        resolved_run_id, len(plan.train_rows), len(plan.test_rows),
        label_digest[:12],
    )
    return run, request


def verify_experiment_training_result(
    session: ProjectSession,
    run: TrackingRun,
    request: ExperimentTrainingRequest,
    result: dict[str, Any],
    job_dir: Path,
) -> TrackingRun:
    """验证 external worker 的联合训练 result 并把 run 置为 completed。

    输入 `result` 已经过 S1 host 侧协议验证（身份/exit/outputs containment
    +size/SHA）；本函数补领域校验：digest 回显、stale 复核（当前项目重新
    join 后 digest 必须仍等于请求冻结值）、bodyparts 身份、config/snapshot
    两个 run-owned 文件存在。任何一项不满足 → ProjectSessionError，run
    保持非 completed。
    """

    if run.run_id != UUID(request.run_id):
        raise ProjectSessionError(
            f"run identity mismatch: verifier got run {run.run_id} for request {request.run_id}"
        )
    if run.status not in {"pending", "running"}:
        raise ProjectSessionError(
            f"cannot complete a run in status {run.status!r}; "
            "only pending/running runs accept training results"
        )
    if all(r.run_id != run.run_id for r in session.tracking_runs()):
        raise ProjectSessionError(
            "the run is no longer registered in the project; "
            "refusing to complete an unregistered run"
        )
    section = result.get(RESULT_SECTION)
    if not isinstance(section, dict):
        raise ProjectSessionError(
            f"result misses the {RESULT_SECTION!r} section"
        )

    # digest 回显链：worker 只回显请求冻结值;此处再对照当前项目事实(stale 拒绝)
    if section.get("label_digest") != request.label_digest:
        raise ProjectSessionError(
            "worker echoed a different label digest; the request and worker "
            "disagree on training labels"
        )
    if section.get("video_sha256") != request.video_sha256:
        raise ProjectSessionError(
            "worker echoed a different video digest; the request and worker "
            "disagree on the training video"
        )
    if list(section.get("check_frames") or []) != list(request.check_frames):
        raise ProjectSessionError(
            "worker echoed a different fixed-check split; the request and "
            "worker disagree on the evaluation frames"
        )
    video_file = Path(request.video_path)
    if not video_file.is_file() or _file_sha256(video_file) != request.video_sha256:
        raise ProjectSessionError(
            "the training video changed or disappeared after the request was "
            "prepared; the completed model's provenance is broken"
        )
    experiment = session.pendulum_experiment(UUID(request.experiment_id))
    current_digest = canonical_label_digest(
        join_complete_frames(session.project, experiment)
    )
    if current_digest != request.label_digest:
        raise ProjectSessionError(
            "labels changed since the training request was prepared; "
            "the completed model was trained on stale labels"
        )
    if section.get("bodyparts") != list(ROLE_ORDER):
        raise ProjectSessionError(
            f"trained bodyparts must be exactly {list(ROLE_ORDER)}, "
            f"got {section.get('bodyparts')!r}"
        )

    config_relative = section.get("config_path")
    snapshot_relative = section.get("model_snapshot")
    for name, relative in (("config_path", config_relative),
                           ("model_snapshot", snapshot_relative)):
        if not isinstance(relative, str) or not relative:
            raise ProjectSessionError(
                f"result {RESULT_SECTION}.{name} must be a non-empty relative path"
            )
    declared = {
        item.get("path")
        for item in result.get("outputs", [])
        if isinstance(item, dict)
    }
    for relative in (config_relative, snapshot_relative):
        if relative not in declared:
            raise ProjectSessionError(
                f"declared training outputs do not cover {relative!r}; "
                "the result's output integrity chain is broken"
            )
    job_dir = Path(job_dir).resolve()
    config_file = (job_dir / config_relative).resolve()
    snapshot_file = (job_dir / snapshot_relative).resolve()
    for name, candidate in (("config", config_file), ("snapshot", snapshot_file)):
        if not candidate.is_file() or not candidate.is_relative_to(job_dir):
            raise ProjectSessionError(
                f"trained {name} file is missing or escapes the run directory: {candidate}"
            )

    runtime_identity = {
        key: result.get(key)
        for key in ("python", "executable", "platform", "machine")
    }
    extras = {
        **run.extra_fields,
        "device": result.get("actual_device"),
        "requested_device": request.params_config.get("device"),
        "worker_engine_version": section.get("engine_version"),
        "config_path": config_relative,
        "model_file_info": [
            snapshot_file.stat().st_size, snapshot_file.stat().st_mtime_ns
        ],
        "runtime_identity": runtime_identity,
        "label_digest": request.label_digest,
    }
    try:
        completed = mark_run_completed(run, model_snapshot=snapshot_relative)
    except ValueError as error:
        raise ProjectSessionError(f"cannot complete the training run: {error}") from error
    completed = replace(
        completed,
        engine_version=str(section.get("engine_version") or run.engine_version),
        extra_fields=extras,
    )
    logger.info(
        "experiment joint training run %s verified: snapshot %s",
        run.run_id, snapshot_relative,
    )
    return completed
