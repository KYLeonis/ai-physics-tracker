"""在临时 10 帧视频上验证自训/导入模型的四点 external-worker 推理。"""

import argparse
import json
import platform
import shutil
import sys
import tempfile
from pathlib import Path
from uuid import uuid4

import cv2
import deeplabcut

from ai_physics_tracker.application.teacher_models import resolve_pose_cfg_path
from ai_physics_tracker.domain.types import canonical_json_digest
from ai_physics_tracker.infrastructure.dlc_predictions import read_joint_raw_predictions
from ai_physics_tracker.infrastructure.external_worker import ExternalWorkerRunner, build_request
from ai_physics_tracker.infrastructure.hashing import file_sha256
from ai_physics_tracker.infrastructure.project_repository import ProjectRepository


def _short_video(source: Path, destination: Path) -> None:
    capture = cv2.VideoCapture(str(source))
    fps = capture.get(cv2.CAP_PROP_FPS)
    writer = cv2.VideoWriter(str(destination), cv2.VideoWriter_fourcc(*"mp4v"), fps, (320, 180))
    if not capture.isOpened() or not writer.isOpened():
        raise RuntimeError("Cannot open smoke input or output video")
    try:
        for frame_index in range(10):
            ok, frame = capture.read()
            if not ok:
                raise RuntimeError(f"Source video stops before frame {frame_index}")
            writer.write(cv2.resize(frame, (320, 180)))
    finally:
        writer.release()
        capture.release()


def _run_one(root: Path, origin: str, video: Path, work: Path, evidence: Path) -> dict:
    project = ProjectRepository().load(root)
    models = [model for model in project.model_references if model.origin == origin]
    if not models:
        raise RuntimeError(f"No {origin} model in {root}")
    model = next((item for item in models if item.compatibility_state == "compatible"), models[0])
    pose_cfg = resolve_pose_cfg_path(root, model)
    if pose_cfg is None:
        raise RuntimeError(f"Model {model.model_id} has no pose configuration")
    paths = {
        "video": video,
        "config": root / model.config_path,
        "checkpoint": root / model.checkpoint_path,
        "pose_cfg": pose_cfg,
    }
    job_id = uuid4()
    extra = {
        "run_id": str(job_id), "frame_count": 10, "batch_size": 4,
        "bodypart_mapping": [list(pair) for pair in model.bodypart_mapping],
        "model_manifest_hash": model.manifest_hash,
    }
    for key, path in paths.items():
        extra[f"{key}_path"] = str(path)
        extra[f"{key}_sha256"] = file_sha256(path)
    extra["input_digest"] = canonical_json_digest({
        "model_manifest_hash": model.manifest_hash,
        "video_sha256": extra["video_sha256"],
        "bodypart_mapping": extra["bodypart_mapping"],
    })
    request, _ = build_request("infer_experiment", job_id=job_id, device="cpu", extra=extra)
    handle = ExternalWorkerRunner(Path(sys.executable)).start(work / origin, request)
    if not handle.join(timeout_s=180):
        handle.cancel()
        raise RuntimeError(f"{origin} worker timed out")
    result = handle.read_result()
    log_path = evidence / f"p14-{origin}-worker.txt"
    shutil.copyfile(handle.worker_log_path, log_path)
    if result["status"] != "success":
        raise RuntimeError(f"{origin} worker {result['status']}: {result.get('error')}; see {log_path}")
    section = result["experiment_inference"]
    artifact = handle.job_dir / section["prediction_path"]
    parsed = read_joint_raw_predictions(
        artifact, model.bodypart_mapping, frame_count=10,
        expected_scorer=section["scorer"],
    )
    if parsed.complete_count != section["complete_count"]:
        raise RuntimeError("Worker and host completeness summaries disagree")
    return {
        "origin": origin, "model_id": str(model.model_id),
        "model_manifest_hash": model.manifest_hash,
        "source_file_hashes": {key: extra[f"{key}_sha256"] for key in paths},
        "status": result["status"], "device": result["actual_device"],
        "engine_version": section["engine_version"],
        "runtime_versions": section["versions"],
        "frame_count": parsed.frame_count, "complete_count": parsed.complete_count,
        "missing_by_role": dict(parsed.missing_by_role),
        "prediction_sha256": file_sha256(artifact),
        "worker_log": log_path.name,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("trained_project", type=Path)
    parser.add_argument("imported_project", type=Path)
    parser.add_argument("source_video", type=Path)
    parser.add_argument("evidence_dir", type=Path)
    args = parser.parse_args()
    evidence = args.evidence_dir.resolve()
    evidence.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="p14-joint-smoke-") as name:
        work = Path(name)
        video = work / "short.mp4"
        _short_video(args.source_video.resolve(), video)
        results = [
            _run_one(args.trained_project.resolve(), "trained", video, work, evidence),
            _run_one(args.imported_project.resolve(), "imported", video, work, evidence),
        ]
        report = {
            "python": sys.version.split()[0], "platform": platform.platform(),
            "deeplabcut": deeplabcut.__version__,
            "source_video_sha256": file_sha256(args.source_video),
            "short_video_sha256": file_sha256(video),
            "results": results,
        }
    report_path = evidence / "p14-joint-inference-smoke.json"
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n",
                           encoding="utf-8")
    print(report_path)


if __name__ == "__main__":
    main()
