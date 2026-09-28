"""application 层的模型 worker 封装(P1.3-S6):GUI 不直接触碰 infrastructure。

与 FrameSelectionRunner 同款模式:GUI/控制器只依赖本模块,external worker
的 request 构造与启动细节收敛在此;``ModelWorkerError`` 是
``ExternalWorkerError`` 的应用层别名,调用方按此捕获。
"""

from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from ai_physics_tracker.application.experiment_training_job import (
    ExperimentTrainingRequest,
)
from ai_physics_tracker.infrastructure.external_worker import (
    ExternalWorkerError,
    ExternalWorkerRunner,
    build_request,
)

ModelWorkerError = ExternalWorkerError


class ModelWorkerRunner:
    """联合训练/模型自检的 external worker 启动器(依赖注入 runtime python)。"""

    def __init__(self, runtime_python: str | Path) -> None:
        self._runner = ExternalWorkerRunner(runtime_python)

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
            "selftest_model", job_id=job_id, device=device, extra=payload_fields
        )
        job_dir = (
            project_root / "data" / "engines" / f"selftest-{model_id}-{job_id.hex[:8]}"
        )
        return self._runner.start(job_dir, payload)
