"""Real imported-model joint inference through host verification and adoption."""

import argparse
import json
import shutil
import tempfile
from dataclasses import replace
from pathlib import Path

import cv2

from ai_physics_tracker.application.experiment_inference_job import (
    prepare_experiment_inference, verify_experiment_inference_result,
)
from ai_physics_tracker.application.project_session import ProjectSession
from ai_physics_tracker.application.tracking_types import InferenceParams
from ai_physics_tracker.domain.tracking_run import mark_run_cancelled, mark_run_running
from ai_physics_tracker.infrastructure.external_worker import ExternalWorkerRunner, build_request
from ai_physics_tracker.infrastructure.errors import ExternalWorkerError
from ai_physics_tracker.infrastructure.ffprobe_timing import FFprobeTimingProbe
from ai_physics_tracker.infrastructure.hashing import file_sha256
from ai_physics_tracker.infrastructure.project_repository import ProjectRepository


def _short_project(root: Path) -> None:
    """Keep the compatible imported model, but measure a real ten-frame clip."""

    repository = ProjectRepository()
    project = repository.load(root)
    video = project.videos[0]
    source = repository.resolve_video_path(root, video)
    if source is None:
        raise RuntimeError("source project video is unavailable")
    destination = root / "p14-short.mp4"
    capture = cv2.VideoCapture(str(source))
    writer = cv2.VideoWriter(
        str(destination), cv2.VideoWriter_fourcc(*"mp4v"),
        capture.get(cv2.CAP_PROP_FPS), (320, 180),
    )
    if not capture.isOpened() or not writer.isOpened():
        raise RuntimeError("cannot create short lifecycle video")
    try:
        for frame_index in range(10):
            ok, frame = capture.read()
            if not ok:
                raise RuntimeError(f"source video stops before frame {frame_index}")
            writer.write(cv2.resize(frame, (320, 180)))
    finally:
        writer.release()
        capture.release()
    shortened = replace(
        video, original_path=str(destination), frame_count=10,
        width_px=320, height_px=180, sha256=file_sha256(destination),
    )
    timeline = replace(project.timelines[0], working_zone=(0, 9))
    updated = replace(project, videos=(shortened,), timelines=(timeline,), observations=())
    repository.save(root, updated)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source_project", type=Path)
    parser.add_argument("runtime_python", type=Path)
    parser.add_argument("evidence_dir", type=Path)
    args = parser.parse_args()
    evidence = args.evidence_dir.resolve()
    evidence.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="p14-lifecycle-") as directory:
        root = Path(directory) / "project"
        shutil.copytree(args.source_project.resolve(), root)
        _short_project(root)
        session = ProjectSession.load(ProjectRepository(), root)
        experiment = session.pendulum_experiments()[0]
        model = next(item for item in session.project.model_references
                     if item.compatibility_state == "compatible")
        video = next(item for item in session.project.videos
                     if item.video_id == experiment.video_id)
        report = FFprobeTimingProbe().probe(session.video_path(video))
        if report.status != "cfr" or report.frame_count != video.frame_count:
            raise RuntimeError(f"smoke video timing is not verified CFR: {report}")
        session.confirm_video_timing(video.video_id, report)
        baseline_observations = session.project.observations
        runner = ExternalWorkerRunner(args.runtime_python, grace_s=1.0)
        params = InferenceParams(min_confidence=0.0, device="cpu")

        cancelled, cancelled_request = prepare_experiment_inference(
            session, experiment.experiment_id, model.model_id, params,
        )
        request, _ = build_request(
            "infer_experiment", job_id=cancelled.run_id, device="cpu",
            extra=cancelled_request.to_payload(),
        )
        cancelled_job = runner.start(root / "data" / "engines" / str(cancelled.run_id), request)
        session.update_tracking_run(mark_run_running(cancelled))
        cancelled_job.cancel()
        cancelled_result = None
        try:
            cancelled_result = cancelled_job.read_result()["status"]
        except ExternalWorkerError as error:  # forced cancellation may leave no result.json
            cancelled_result = type(error).__name__
        if cancelled_result == "success":
            raise RuntimeError("cancelled worker produced a successful result")
        session.update_tracking_run(mark_run_cancelled(
            next(item for item in session.tracking_runs() if item.run_id == cancelled.run_id)
        ))
        if (session.project.observations != baseline_observations
                or session.pendulum_experiment(experiment.experiment_id).active_infer_run_id is not None):
            raise RuntimeError("cancelled inference changed adopted measurements")

        pending, inference_request = prepare_experiment_inference(
            session, experiment.experiment_id, model.model_id, params,
        )
        request, _ = build_request(
            "infer_experiment", job_id=pending.run_id, device="cpu",
            extra=inference_request.to_payload(),
        )
        job = runner.start(root / "data" / "engines" / str(pending.run_id), request)
        running = mark_run_running(pending)
        session.update_tracking_run(running)
        if not job.join(timeout_s=600):
            job.cancel()
            raise RuntimeError("real joint inference timed out")
        result = job.read_result()
        completed = verify_experiment_inference_result(
            session, running, inference_request, result, job.job_dir,
        )
        session.update_tracking_run(completed)
        if (session.project.observations != baseline_observations
                or session.pendulum_experiment(experiment.experiment_id).active_infer_run_id is not None):
            raise RuntimeError("completed candidate activated without user action")
        queue = session.create_experiment_review_queue(pending.run_id)
        candidate = next((item for item in queue
                          if item.predictions["tip"] is not None), None)
        if candidate is None:
            raise RuntimeError("real candidate yielded no reviewable tip frame")
        frame_index = candidate.frame_index
        role_prediction = candidate.predictions["tip"]
        pixel_x = role_prediction.pixel_x + 1.0
        pixel_y = role_prediction.pixel_y + 1.0
        manual = session.review_experiment_frame(
            pending.run_id, frame_index, "corrected", role="tip",
            pixel_x=pixel_x, pixel_y=pixel_y,
        )
        activation = session.activate_experiment_candidate(
            experiment.experiment_id, pending.run_id,
        )
        adopted_before_clear = len(session.project.observations)
        session.clear_experiment_candidate(experiment.experiment_id)
        if session.effective_point(experiment.roles.tip, frame_index) != manual:
            raise RuntimeError("Clear removed the manual correction")
        if not session.undo():
            raise RuntimeError("Clear was not undoable")
        session.save()
        reopened = ProjectSession.load(ProjectRepository(), root)
        if (reopened.pendulum_experiment(experiment.experiment_id).active_infer_run_id
                != pending.run_id):
            raise RuntimeError("save/reopen lost the active joint candidate")
        if reopened.effective_point(experiment.roles.tip, frame_index) != manual:
            raise RuntimeError("save/reopen lost the manual correction")
        shutil.copyfile(job.worker_log_path, evidence / "p14-lifecycle-worker.txt")
        report_data = {
            "source_project": str(args.source_project.resolve()),
            "model_id": str(model.model_id), "model_origin": model.origin,
            "video_frame_count": video.frame_count,
            "timing_status": report.status,
            "cancelled_result": cancelled_result,
            "cancel_marker_present": (cancelled_job.job_dir / "cancel.request").is_file(),
            "cancelled_process_exit_code": cancelled_job.returncode,
            "cancelled_run_status": "cancelled",
            "successful_run_id": str(pending.run_id),
            "worker_status": result["status"],
            "complete_count": completed.extra_fields["complete_count"],
            "missing_by_role": completed.extra_fields["missing_by_role"],
            "prediction_sha256": completed.extra_fields["prediction_sha256"],
            "review_frame_index": frame_index,
            "manual_point_id": str(manual.point_id),
            "activation_input_digest": activation.input_digest,
            "adopted_point_count_before_clear": adopted_before_clear,
            "clear_undo_reopen": "pass",
        }
    path = evidence / "p14-lifecycle-smoke.json"
    path.write_text(json.dumps(report_data, indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8")
    print(path)


if __name__ == "__main__":
    main()
