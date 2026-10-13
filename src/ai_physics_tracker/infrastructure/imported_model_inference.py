"""教师模型共用的真实帧探针与全视频推理；不依赖原训练工程目录。"""

import csv
import hashlib
from pathlib import Path
from typing import Any
from uuid import UUID

import cv2
import numpy as np

from ai_physics_tracker.domain.imported_model import ImportedModel
from ai_physics_tracker.application.tracking_types import InferenceRequest, InferenceOutcome
from ai_physics_tracker.infrastructure.imported_models import (
    check_cancel, file_sha256, runtime_identity, verify_model, verified_self_test,
)
from ai_physics_tracker.infrastructure.task_runner import send_progress


def load_runner(root: Path, model: ImportedModel, device: str, batch_size: int,
                cancel: Any) -> tuple[Any, str]:
    from ai_physics_tracker.infrastructure.dlc_adapter import detect_device, create_teacher_model_runner

    pose, checkpoint = verify_model(root, model, cancel)
    actual = detect_device() if device == "auto" else device
    runner = create_teacher_model_runner(pose, checkpoint, actual, batch_size)
    if str(runner.device) != actual:
        raise ValueError("Model runner changed the requested device")
    check_cancel(cancel)
    return runner, actual


def validated_predictions(runner: Any, frames: list[np.ndarray], count: int) -> list[np.ndarray]:
    results = runner.inference([cv2.cvtColor(f, cv2.COLOR_BGR2RGB) for f in frames])
    if not isinstance(results, list) or len(results) != len(frames):
        raise ValueError("Model returned an incomplete frame batch")
    poses = []
    for result in results:
        array = np.asarray(result.get("bodyparts")) if isinstance(result, dict) else np.array([])
        if (array.shape != (1, count, 3) or not np.issubdtype(array.dtype, np.number)
                or np.isinf(array).any()):
            raise ValueError("Model returned invalid bodypart dimensions or coordinates")
        confidence = array[..., 2]
        if ((confidence < 0) | (confidence > 1)).any():
            raise ValueError("Model confidence must be in [0, 1]")
        poses.append(array[0])
    return poses


def run_model_self_test(run_id: UUID, queue: Any, cancel: Any, root: Path, model: ImportedModel,
                        video_path: Path, video_id: UUID, frame_index: int, device: str) -> dict[str, Any]:
    """独占 spawn 进程；只返回小型可审计证据，不产生训练记录。"""
    check_cancel(cancel)
    before = video_path.stat()
    video_hash = file_sha256(video_path, cancel)
    capture = cv2.VideoCapture(str(video_path))
    try:
        if not capture.isOpened() or not capture.set(cv2.CAP_PROP_POS_FRAMES, frame_index):
            raise ValueError("Cannot seek to the selected actual video frame")
        ok, frame = capture.read()
        if not ok or frame is None or int(capture.get(cv2.CAP_PROP_POS_FRAMES)) != frame_index + 1:
            raise ValueError("Cannot decode the selected actual video frame")
    finally:
        capture.release()
    send_progress(queue, run_id, 0, 1, message="Loading teacher model")
    runner, actual = load_runner(root, model, device, 1, cancel)
    prediction = validated_predictions(runner, [frame], len(model.bodyparts))[0]
    if not np.isfinite(prediction).all():
        raise ValueError("Self-test requires a finite prediction for every declared bodypart")
    verify_model(root, model, cancel)
    after = video_path.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns) or file_sha256(video_path, cancel) != video_hash:
        raise ValueError("Self-test video changed during inference")
    check_cancel(cancel)
    return {"status": "completed", "evidence": {
        "manifest_hash": model.manifest_hash, "runtime": runtime_identity(),
        "requested_device": device, "actual_device": actual,
        "video_id": str(video_id), "frame_index": frame_index,
        "video_sha256": video_hash, "video_file_info": [after.st_size, after.st_mtime_ns],
        "frame_sha256": hashlib.sha256(frame.tobytes()).hexdigest(),
        "frame_shape": list(frame.shape), "predictions": prediction.tolist(),
    }}


def infer_imported_model(run_id: UUID, queue: Any, cancel: Any, request: InferenceRequest) -> InferenceOutcome:
    from ai_physics_tracker.infrastructure.dlc_predictions import parse_predictions

    model = request.imported_model
    if (not verified_self_test(model, request.params.device, request.timeline.video_id, request.video_path)
            or file_sha256(request.video_path, cancel) != model.self_test["video_sha256"]):
        raise ValueError("Teacher model requires a successful self-test in this environment/device")
    runner, actual = load_runner(request.model_root, model, request.params.device,
                                 request.params.batch_size, cancel)
    if model.self_test["actual_device"] != actual:
        raise ValueError("Auto device changed; repeat the actual-frame self-test")
    request.output_dir.mkdir(parents=True, exist_ok=False)
    output = request.output_dir / "predictions.csv"
    capture = cv2.VideoCapture(str(request.video_path))
    index = 0
    try:
        if not capture.isOpened():
            raise ValueError("Cannot open inference video")
        with output.open("x", encoding="utf-8", newline="") as stream:
            writer = csv.writer(stream)
            # 单 Track 使用内部 target 列；原关键点名与完整模型身份保存在 run config。
            writer.writerows([["scorer", "teacher", "teacher", "teacher"],
                              ["bodyparts", "target", "target", "target"],
                              ["coords", "x", "y", "likelihood"]])
            while index < request.frame_count:
                check_cancel(cancel)
                frames = []
                for _ in range(min(request.params.batch_size, request.frame_count - index)):
                    ok, frame = capture.read()
                    if not ok:
                        raise ValueError("Video ended before the expected frame count")
                    frames.append(frame)
                predictions = validated_predictions(runner, frames, len(model.bodyparts))
                for pose in predictions:
                    writer.writerow([index, *pose[model.bodyparts.index(request.bodypart)].tolist()])
                    index += 1
                send_progress(queue, run_id, index, request.frame_count, message="Teacher model inference")
            if capture.read()[0]:
                raise ValueError("Video contains more frames than registered")
    finally:
        capture.release()
    verify_model(request.model_root, model, cancel)
    if file_sha256(request.video_path, cancel) != model.self_test["video_sha256"]:
        raise ValueError("Teacher inference video changed; repeat self-test")
    parsed = parse_predictions(output, request.track_id, request.timeline, request.source_detail,
                              min_confidence=request.params.min_confidence, frame_count=request.frame_count)
    return InferenceOutcome(parsed.points, output, parsed.row_count, parsed.missing_count,
                            parsed.low_confidence_count, request.model_snapshot,
                            runtime_identity()["deeplabcut"], actual)
