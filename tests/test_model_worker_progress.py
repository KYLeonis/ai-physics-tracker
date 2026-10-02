"""外部worker后处理计数→有界日志读取；不把DLC预读取日志当预测进度。"""

from uuid import uuid4

from ai_physics_tracker.application.model_worker import read_inference_progress
from ai_physics_tracker.application.tracking_types import TaskProgress
from ai_physics_tracker.worker import __main__ as worker


def test_worker_progress_log_roundtrip_and_rejects_unrelated_or_partial_records(tmp_path, monkeypatch):
    run_id = uuid4()
    assert read_inference_progress(tmp_path, run_id, 12) is None
    written = []
    monkeypatch.setattr(worker.os, "write", lambda fd, data: written.append(data))
    worker._ResultLogQueue().put(TaskProgress(run_id, 8, 12, message="Frames predicted"))
    log = tmp_path / "worker.log"
    log.write_bytes(b"x" * 70000 + b"\n100%|preprocessing| 12/12\n" + b"".join(written)
                    + f"APT_PROGRESS {uuid4()} 12/12 Frames predicted\n".encode()
                    + f"APT_PROGRESS {run_id} 10/20 wrong total\n".encode()
                    + f"APT_PROGRESS {run_id} 13/12 overflow\n".encode()
                    + f"APT_PROGRESS {run_id} 9/12 partial".encode())
    assert read_inference_progress(tmp_path, run_id, 12) == (8, "Frames predicted")
    log.write_text("100%|preprocessing| 12/12\n", encoding="utf-8")
    assert read_inference_progress(tmp_path, run_id, 12) is None
