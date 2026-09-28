"""P1.3-S6 真实 DLC 双路径 smoke(macOS arm64,DLC 3.0.1)。

路径 A(trained):合成四标记视频 → publication experiment → complete 帧
+ frozen fixed check → prepare → external worker train_experiment(1 epoch
CPU)→ verify → register reference → selftest → compatible。
路径 B(imported):从 A 产出的 DLC 项目构造最小教师 bundle(config +
snapshot + pytorch_config)→ import_teacher_model → selftest → compatible。

不设精度目标;只证明协议/数据/模型链路在真实 runtime 下闭环。
运行:PYTHONPATH=src python scripts/smoke_test_dlc_p13_joint.py
"""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import sys
import tempfile
from uuid import uuid4

import cv2
import numpy as np

repo_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(repo_root / "src"))

from ai_physics_tracker.application.experiment_training_job import (  # noqa: E402
    prepare_experiment_training,
    verify_experiment_training_result,
)
from ai_physics_tracker.application.model_worker import ModelWorkerRunner  # noqa: E402
from ai_physics_tracker.application.project_session import (  # noqa: E402
    ProjectSession,
    ProjectSessionError,
)
from ai_physics_tracker.application.teacher_models import (  # noqa: E402
    build_model_selftest_payload,
    model_effective_state,
    resolve_pose_cfg_path,
)
from ai_physics_tracker.application.tracking_types import TrainingParams  # noqa: E402
from ai_physics_tracker.application.video import VideoStreamInfo  # noqa: E402
from ai_physics_tracker.domain.pendulum import ROLE_ORDER, PendulumRoles  # noqa: E402
from ai_physics_tracker.domain.project import create_project  # noqa: E402
from ai_physics_tracker.infrastructure.project_repository import (  # noqa: E402
    ProjectRepository,
)

FRAME_COUNT = 12
TRAIN_FRAMES = (1, 4, 7, 10)
CHECK_FRAMES = (2, 5, 8)
ALL_COMPLETE = tuple(sorted(TRAIN_FRAMES + CHECK_FRAMES))
JOIN_TIMEOUT_S = 2400  # 1 epoch × 7 帧远小于此;只防挂死

FRAME_MARKS = {
    frame: tuple(
        (float(18 + frame * 2 + role * 7), float(22.0 + role * 12))
        for role in range(4)
    )
    for frame in range(FRAME_COUNT)
}


def create_synthetic_video(video_path: Path) -> None:
    writer = cv2.VideoWriter(
        str(video_path), cv2.VideoWriter_fourcc(*"mp4v"), 10.0, (120, 100)
    )
    if not writer.isOpened():
        raise RuntimeError("Cannot create synthetic video")
    try:
        for frame_index in range(FRAME_COUNT):
            img = np.zeros((100, 120, 3), dtype=np.uint8)
            for role, (x, y) in enumerate(FRAME_MARKS[frame_index]):
                cv2.circle(
                    img, (int(x), int(y)), 4,
                    (60 * (role + 1), 255 - 60 * role, 128), -1,
                )
            writer.write(img)
    finally:
        writer.release()


def _session_with_experiment(root: Path, video_path: Path) -> ProjectSession:
    session = ProjectSession(ProjectRepository(), create_project("p13 smoke"))
    info = VideoStreamInfo(
        width_px=120, height_px=100, fps_container=10.0,
        frame_count=FRAME_COUNT, container_format="mp4", timing_status="cfr",
    )
    video, _timeline = session.register_external_video(video_path, info)
    tracks = {role: session.add_track(video.video_id, role) for role in ROLE_ORDER}
    session.save_as_publication(
        root / "publication",
        PendulumRoles(
            tip=tracks["tip"].track_id, body_top=tracks["body_top"].track_id,
            body_bottom=tracks["body_bottom"].track_id,
            pivot=tracks["pivot"].track_id,
        ),
    )
    experiment = session.pendulum_experiments()[0]
    for frame in ALL_COMPLETE:
        for role, (x, y) in zip(ROLE_ORDER, FRAME_MARKS[frame]):
            session.mark_point(experiment.roles.track_id_for(role), frame, x, y)
    session.freeze_experiment_fixed_check(experiment.experiment_id, CHECK_FRAMES)
    session.save()
    return session


def _run_job(runner: ModelWorkerRunner, start, *, label: str) -> dict:
    handle = start()
    print(f"[{label}] job started: {handle.job_dir}")
    if not handle.join(timeout_s=JOIN_TIMEOUT_S):
        try:
            handle.cancel()
        except Exception as error:  # 超时取消失败不掩盖原始超时信息
            print(f"[{label}] cancel after timeout raised: {error}", file=sys.stderr)
        raise SystemExit(f"[{label}] timed out after {JOIN_TIMEOUT_S}s")
    section = result.get("model_selftest") or result.get("experiment_training") or {}
    print(
        f"[{label}] evidence: device={result.get('actual_device')} "
        f"versions={section.get('versions')} "
        f"platform={result.get('platform')} python={result.get('python', '')[:20]}"
    )
    result = handle.read_result()
    log_tail = Path(handle.worker_log_path).read_text(encoding="utf-8", errors="replace")
    tail = "\n".join(log_tail.splitlines()[-6:])
    print(f"[{label}] status={result.get('status')} log tail:\n{tail}")
    if result.get("status") != "success":
        raise SystemExit(f"[{label}] failed: {result.get('error')}")
    return result


def path_a_trained(root: Path, video_path: Path) -> None:
    print("=== P1.3-S6 path A: joint training → reference → self-test ===")
    session = _session_with_experiment(root, video_path)
    experiment = session.pendulum_experiments()[0]
    run, request = prepare_experiment_training(
        session, experiment.experiment_id,
        params=TrainingParams(
            epochs=1, batch_size=2, device="cpu",
            display_iters=1, save_iters=1,
        ),
    )
    print(f"prepared run {run.run_id}: rows={len(request.rows)} digest={request.label_digest[:12]}")
    runner = ModelWorkerRunner(sys.executable)
    result = _run_job(
        runner,
        lambda: runner.start_training(session.project_root, request, device="cpu"),
        label="train",
    )
    completed = verify_experiment_training_result(
        session, run, request, result,
        session.project_root / "data" / "engines" / str(run.run_id),
    )
    session.update_tracking_run(completed)
    reference = session.register_trained_model_reference(run.run_id)
    print(f"reference {reference.model_id} registered (unverified)")

    pose_cfg = resolve_pose_cfg_path(session.project_root, reference)
    print(f"pose_cfg resolved: {pose_cfg}")
    if pose_cfg is None:
        raise SystemExit("trained model pose_cfg not found (B1 regression?)")

    payload = build_model_selftest_payload(
        session.project_root, reference, video_path
    )
    result = _run_job(
        runner,
        lambda: runner.start_selftest(
            session.project_root, reference.model_id, payload, device="cpu"
        ),
        label="selftest-trained",
    )
    session.apply_model_selftest(reference.model_id, result)
    state, reason = model_effective_state(session.project_root, session.project.model_references[0])
    print(f"trained model effective state: {state} ({reason})")
    if state != "compatible":
        raise SystemExit(f"path A ended in {state}")
    _export_teacher_bundle(root, session, reference)


def _export_teacher_bundle(root: Path, session: ProjectSession, reference) -> Path:
    """从 trained 产物构造最小教师 bundle(config/snapshot/pytorch_config)。"""
    bundle = root / "teacher-bundle"
    bundle.mkdir(exist_ok=True)
    project_root = session.project_root
    shutil.copy2(project_root / reference.config_path, bundle / "config.yaml")
    shutil.copy2(project_root / reference.checkpoint_path, bundle / "snapshot.pt")
    pose_cfg = resolve_pose_cfg_path(project_root, reference)
    shutil.copy2(pose_cfg, bundle / "pose_cfg.yaml")
    print(f"teacher bundle built: {bundle}")
    return bundle


def path_b_imported(root: Path, video_path: Path) -> None:
    print("=== P1.3-S6 path B: import teacher bundle → self-test ===")
    host_root = root / "host-b"          # 独立宿主项目,path A 已占用 publication
    host_root.mkdir(exist_ok=True)
    session = _session_with_experiment(host_root, video_path)
    bundle = root / "teacher-bundle"
    reference = session.import_teacher_model(
        bundle, "config.yaml", "snapshot.pt",
        tuple((role, role) for role in ROLE_ORDER),
        extra_files=("pose_cfg.yaml",),
    )
    print(f"imported reference {reference.model_id} (unverified)")
    moved = root / "teacher-bundle-moved"
    shutil.move(bundle, moved)  # 原目录移走,受管副本必须自足
    payload = build_model_selftest_payload(
        session.project_root, reference, video_path
    )
    runner = ModelWorkerRunner(sys.executable)
    result = _run_job(
        runner,
        lambda: runner.start_selftest(
            session.project_root, reference.model_id, payload, device="cpu"
        ),
        label="selftest-imported",
    )
    session.apply_model_selftest(reference.model_id, result)
    state, reason = model_effective_state(
        session.project_root, session.project.model_references[0]
    )
    print(f"imported model effective state: {state} ({reason}); source dir moved away")
    if state != "compatible":
        raise SystemExit(f"path B ended in {state}")


def main() -> int:
    print("=== P1.3-S6 real DLC dual-path smoke ===")
    tmp_dir = Path(tempfile.mkdtemp(prefix="p13_smoke_"))
    print(f"Working directory: {tmp_dir}")
    try:
        video_path = tmp_dir / "synthetic_p13.mp4"
        create_synthetic_video(video_path)
        path_a_trained(tmp_dir, video_path)
        path_b_imported(tmp_dir, video_path)
        print("=== P1.3-S6 smoke PASS ===")
        return 0
    except SystemExit as error:
        print(f"SMOKE FAILED: {error}", file=sys.stderr)
        return 1
    finally:
        if not os.environ.get("P13_SMOKE_KEEP"):
            shutil.rmtree(tmp_dir, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
