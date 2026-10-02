"""application 层的模型 worker 封装(P1.3-S6):GUI 不直接触碰 infrastructure。

与 FrameSelectionRunner 同款模式:GUI/控制器只依赖本模块,external worker
的 request 构造与启动细节收敛在此;``ModelWorkerError`` 是
``ExternalWorkerError`` 的应用层别名,调用方按此捕获。
"""

from pathlib import Path
import re
from typing import Any
from uuid import UUID, uuid4

from ai_physics_tracker.application.experiment_inference_job import (
    ExperimentInferenceRequest,
)
from ai_physics_tracker.application.experiment_training_job import (
    ExperimentTrainingRequest,
)
from ai_physics_tracker.infrastructure.external_worker import (
    ExternalWorkerError,
    ExternalWorkerRunner,
    build_request,
)

ModelWorkerError = ExternalWorkerError


def read_inference_progress(job_dir: Path, run_id: UUID, frame_count: int) -> tuple[int, str] | None:
    """只读该run最近64KiB日志中的后处理计数；坏/截断记录不影响任务。"""

    try:
        with (job_dir / "worker.log").open("rb") as stream:
            stream.seek(0, 2)
            stream.seek(max(0, stream.tell() - 65536))
            lines = stream.read(65536).decode("utf-8", errors="replace").split("\n")[:-1]
    except OSError:
        return None
    pattern = re.compile(rf"APT_PROGRESS {run_id} (\d{{1,10}})/(\d{{1,10}}) (.*)")
    for line in reversed(lines):
        match = pattern.fullmatch(line.rstrip("\r"))
        if match is not None:
            step, total = int(match[1]), int(match[2])
            if total == frame_count and 0 <= step <= total:
                return step, match[3][:160]
    return None


class ModelWorkerRunner:
    """联合训练/自检/联合推理的 external worker 启动器(依赖注入 runtime python)。

    P6.1 起 package_root 显式注入:frozen host 的 ``__file__`` 位于 PyInstaller
    归档内,worker 源码哈希/子进程 PYTHONPATH 必须指向随包分发的受信源码根
    (``launch_context.worker_package_root``);dev 传 None 走默认 src 树。
    """

    def __init__(
        self,
        runtime_python: str | Path,
        *,
        package_root: Path | None = None,
    ) -> None:
        self._package_root = package_root
        self._runner = ExternalWorkerRunner(runtime_python, package_root=package_root)

    def start_training(
        self,
        project_root: Path,
        request: ExperimentTrainingRequest,
        *,
        device: str = "cpu",
    ) -> Any:
        """启动 train_experiment job;job 目录 = run 目录(data/engines/<run_id>)。"""

        payload, _digest = build_request(
            "train_experiment",
            job_id=UUID(request.run_id),
            device=device,
            extra=request.to_payload(),
            package_root=self._package_root,
        )
        job_dir = project_root / "data" / "engines" / request.run_id
        return self._runner.start(job_dir, payload)

    def start_inference(
        self,
        project_root: Path,
        request: ExperimentInferenceRequest,
        *,
        device: str = "cpu",
    ) -> Any:
        """启动 infer_experiment job(P1.4 一次四 bodypart analyze);目录 = run 目录。"""

        payload, _digest = build_request(
            "infer_experiment",
            job_id=UUID(request.run_id),
            device=device,
            extra=request.to_payload(),
            package_root=self._package_root,
        )
        job_dir = project_root / "data" / "engines" / request.run_id
        return self._runner.start(job_dir, payload)

    def start_selftest(
        self,
        project_root: Path,
        model_id: UUID,
        payload_fields: dict[str, Any],
        *,
        device: str = "cpu",
    ) -> Any:
        """启动 selftest_model job;目录带唯一后缀(同一模型可重复自检)。"""

        job_id = uuid4()
        payload, _digest = build_request(
            "selftest_model",
            job_id=job_id,
            device=device,
            extra=payload_fields,
            package_root=self._package_root,
        )
        job_dir = (
            project_root / "data" / "engines" / f"selftest-{model_id}-{job_id.hex[:8]}"
        )
        return self._runner.start(job_dir, payload)
