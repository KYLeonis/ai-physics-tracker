"""在新建合成工程中验证受管解释器的训练→自检→CPU/MPS 推理，不读取用户工程。"""

import argparse
import json
from pathlib import Path
import shutil
import time

from smoke_test_dlc_p13_joint import create_synthetic_video, _session_with_experiment
from ai_physics_tracker.application.experiment_training_job import prepare_experiment_training, verify_experiment_training_result
from ai_physics_tracker.application.experiment_inference_job import prepare_experiment_inference, verify_experiment_inference_result
from ai_physics_tracker.application.model_worker import ModelWorkerRunner
from ai_physics_tracker.application.teacher_models import build_model_selftest_payload
from ai_physics_tracker.application.tracking_types import TrainingParams, InferenceParams
from ai_physics_tracker.application.project_session import ProjectSession
from ai_physics_tracker.infrastructure.project_repository import ProjectRepository
from ai_physics_tracker.infrastructure.ffprobe_timing import FFprobeTimingProbe


def run_job(handle, label: str) -> dict:
    print(label, handle.job_dir, flush=True)
    deadline = time.monotonic() + 900
    while handle.is_alive() and time.monotonic() < deadline:
        time.sleep(1)
    if handle.is_alive():
        handle.cancel()
        raise RuntimeError(f"{label} timed out")
    result = handle.read_result()
    if result["status"] != "success":
        raise RuntimeError(f"{label}: {result.get('error')}; see {handle.worker_log_path}")
    print(label, result["status"], result["actual_device"], flush=True)
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("runtime_python", type=Path)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--devices", nargs="+", default=["cpu", "mps"])
    parser.add_argument("--offline-existing", type=Path)
    args = parser.parse_args()
    root = args.root.absolute()
    root.mkdir(parents=True, exist_ok=False)
    if args.offline_existing:
        # 测试专用启动钩子封锁 Python socket；产品 worker 源码逐字节复制、不修改。
        source = Path(__file__).resolve().parents[1] / "src"
        offline = root / "offline-src"
        shutil.copytree(source / "ai_physics_tracker", offline / "ai_physics_tracker",
                        ignore=shutil.ignore_patterns("__pycache__"))
        (offline / "sitecustomize.py").write_text(
            "import socket\ndef deny(*a, **k):\n    raise OSError('Offline smoke: network blocked')\n"
            "socket.socket.connect = deny\nsocket.create_connection = deny\n", encoding="utf-8")
        session = ProjectSession.load(ProjectRepository(), args.offline_existing.resolve())
        model = session.project.model_references[0]
        experiment = session.pendulum_experiments()[0]
        video = next(v for v in session.project.videos if v.video_id == experiment.video_id)
        report = FFprobeTimingProbe().probe(session.video_path(video))
        session.confirm_video_timing(video.video_id, report)
        runner = ModelWorkerRunner(args.runtime_python, package_root=offline)
        run, request = prepare_experiment_inference(session, experiment.experiment_id, model.model_id,
                                                    InferenceParams(min_confidence=0.0, device="mps", batch_size=4))
        result = run_job(runner.start_inference(session.project_root, request, device=request.expected_device), "offline inference")
        completed = verify_experiment_inference_result(session, run, request, result,
                                                        session.project_root / "data/engines" / str(run.run_id))
        session.update_tracking_run(completed)
        session.save()
        (root / "smoke-result.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        return
    video = root / "synthetic.mp4"
    create_synthetic_video(video)
    session = _session_with_experiment(root, video)
    experiment = session.pendulum_experiments()[0]
    runner = ModelWorkerRunner(args.runtime_python, package_root=Path(__file__).resolve().parents[1] / "src")
    run, request = prepare_experiment_training(session, experiment.experiment_id,
        params=TrainingParams(epochs=1, batch_size=2, device="cpu", display_iters=1, save_iters=1))
    train_result = run_job(runner.start_training(session.project_root, request, device="cpu"), "training")
    completed = verify_experiment_training_result(session, run, request, train_result,
                                                  session.project_root / "data/engines" / str(run.run_id))
    session.update_tracking_run(completed)
    model = session.register_trained_model_reference(run.run_id)
    results = {"runtime_python": str(args.runtime_python), "training": train_result, "devices": {}}
    for device in args.devices:
        payload = build_model_selftest_payload(session.project_root, model, video)
        checked = run_job(runner.start_selftest(session.project_root, model.model_id, payload, device=device), f"selftest {device}")
        session.apply_model_selftest(model.model_id, checked)
        run, request = prepare_experiment_inference(session, experiment.experiment_id, model.model_id,
                                                    InferenceParams(min_confidence=0.0, device=device, batch_size=4))
        inferred = run_job(runner.start_inference(session.project_root, request, device=device), f"inference {device}")
        completed = verify_experiment_inference_result(session, run, request, inferred,
                                                        session.project_root / "data/engines" / str(run.run_id))
        session.update_tracking_run(completed)
        results["devices"][device] = {"selftest": checked, "inference": inferred}
    session.save()
    (root / "smoke-result.json").write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    print("Evidence:", root / "smoke-result.json", flush=True)


if __name__ == "__main__":
    main()
