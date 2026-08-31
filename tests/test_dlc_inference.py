"""DLC 推理适配器边界测试（不加载真实 DeepLabCut/PyTorch）。"""

from concurrent.futures import CancelledError
from contextlib import contextmanager
from multiprocessing import Event
from pathlib import Path
from queue import Queue
import sys
from types import ModuleType, SimpleNamespace
from uuid import uuid4

import pytest

from ai_physics_tracker.domain.timeline import Timeline
from ai_physics_tracker.infrastructure import dlc_adapter
from ai_physics_tracker.infrastructure.dlc_adapter import DLCAdapter, dlc_train_worker
from ai_physics_tracker.infrastructure.engine_adapter import InferenceParams, InferenceRequest
from ai_physics_tracker.infrastructure.task_runner import TaskProgress


def _fake_deeplabcut(*, analyze_videos=None, train_network=None) -> ModuleType:
    module = ModuleType("deeplabcut")
    module.__version__ = "3.0.1-test"
    if analyze_videos is not None:
        module.analyze_videos = analyze_videos
    if train_network is not None:
        module.train_network = train_network
    return module


def _request(tmp_path: Path, snapshot: Path, *, output_dir: Path | None = None) -> InferenceRequest:
    config_path = tmp_path / "config.yaml"
    video_path = tmp_path / "clip.mp4"
    config_path.touch()
    video_path.touch()
    return InferenceRequest(
        config_path=config_path,
        video_path=video_path,
        model_snapshot=snapshot,
        output_dir=output_dir or (tmp_path / "run-output"),
        track_id=uuid4(),
        timeline=Timeline(uuid4(), 30.0, (0, 4)),
        source_detail="dlc:run-test",
        frame_count=5,
        params=InferenceParams(min_confidence=0.6, device="cpu", batch_size=4),
        shuffle=3,
        trainingsetindex=7,
    )


def test_infer_passes_selected_snapshot_and_all_dlc_parameters(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    selected = tmp_path / "snapshot-10.pt"
    latest = tmp_path / "snapshot-20.pt"
    selected.touch()
    latest.touch()
    request = _request(tmp_path, selected)
    calls: dict[str, object] = {}

    def analyze_videos(*args: object, **kwargs: object) -> str:
        calls["args"] = args
        calls["kwargs"] = kwargs
        return "scorer"

    monkeypatch.setitem(
        sys.modules,
        "deeplabcut",
        _fake_deeplabcut(analyze_videos=analyze_videos),
    )
    monkeypatch.setattr(
        dlc_adapter,
        "_model_snapshots",
        lambda config, shuffle, trainingsetindex: [
            SimpleNamespace(path=selected), SimpleNamespace(path=latest)
        ],
    )

    @contextmanager
    def completed_progress(queue: object, run_id: object, cancel_event: object, total: int):
        yield [total]

    monkeypatch.setattr(dlc_adapter, "_prediction_progress", completed_progress)
    monkeypatch.setattr(
        "ai_physics_tracker.infrastructure.dlc_predictions.parse_predictions",
        lambda *args, **kwargs: SimpleNamespace(
            points=(), row_count=5, missing_count=0, low_confidence_count=0
        ),
    )

    outcome = DLCAdapter().infer(uuid4(), Queue(), Event(), request)

    assert outcome.model_snapshot == selected
    assert outcome.device == "cpu"
    assert calls["args"] == (
        str(request.config_path),
        [str(request.video_path)],
    )
    kwargs = calls["kwargs"]
    assert isinstance(kwargs, dict)
    assert kwargs["snapshot_index"] == 0
    assert kwargs["shuffle"] == 3
    assert kwargs["trainingsetindex"] == 7
    assert kwargs["device"] == "cpu"
    assert kwargs["batch_size"] == 4
    assert kwargs["destfolder"] == str(request.output_dir)
    assert kwargs["save_as_csv"] is True
    # DLC 3.0.1 compat.py 自带 overwrite=False，重复传入会使真实调用失败。
    assert "overwrite" not in kwargs
    assert request.output_dir.is_dir()


@pytest.mark.parametrize("snapshot_exists, belongs", [(False, True), (True, False)])
def test_infer_rejects_missing_or_foreign_snapshot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    snapshot_exists: bool,
    belongs: bool,
) -> None:
    requested = tmp_path / "requested.pt"
    if snapshot_exists and belongs:
        requested.touch()
    current = requested if belongs else (tmp_path / "current.pt")
    if not belongs:
        current.touch()
    monkeypatch.setitem(sys.modules, "deeplabcut", _fake_deeplabcut())
    monkeypatch.setattr(
        dlc_adapter,
        "_model_snapshots",
        lambda config, shuffle, trainingsetindex: (
            [SimpleNamespace(path=current)] if belongs else [SimpleNamespace(path=current)]
        ),
    )
    request = _request(tmp_path, requested)

    with pytest.raises(ValueError, match="Selected snapshot"):
        DLCAdapter().infer(uuid4(), Queue(), Event(), request)
    assert not request.output_dir.exists()


def _install_fake_inference_runner(monkeypatch: pytest.MonkeyPatch, runner_type: type) -> None:
    import sys

    inference = ModuleType("deeplabcut.pose_estimation_pytorch.runners.inference")
    inference.InferenceRunner = runner_type
    runners = ModuleType("deeplabcut.pose_estimation_pytorch.runners")
    pose = ModuleType("deeplabcut.pose_estimation_pytorch")
    dlc = ModuleType("deeplabcut")
    runners.inference = inference
    pose.runners = runners
    dlc.pose_estimation_pytorch = pose
    for name, module in (
        ("deeplabcut", dlc),
        ("deeplabcut.pose_estimation_pytorch", pose),
        ("deeplabcut.pose_estimation_pytorch.runners", runners),
        ("deeplabcut.pose_estimation_pytorch.runners.inference", inference),
    ):
        monkeypatch.setitem(sys.modules, name, module)


def test_prediction_progress_counts_extracted_results_and_restores_runner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Runner:
        def __init__(self, batches: list[list[int]]) -> None:
            self.batches = iter(batches)

        def _extract_results(self) -> list[int]:
            return next(self.batches)

    _install_fake_inference_runner(monkeypatch, Runner)
    original = Runner._extract_results
    queue = Queue()
    run_id = uuid4()

    with dlc_adapter._prediction_progress(queue, run_id, Event(), total=5) as progress:
        runner = Runner([[1, 2], [3, 4, 5]])
        assert runner._extract_results() == [1, 2]
        assert runner._extract_results() == [3, 4, 5]
        assert progress == [5]
        messages = [queue.get_nowait(), queue.get_nowait()]
        assert [message.step for message in messages if isinstance(message, TaskProgress)] == [2, 5]

    assert Runner._extract_results is original


def test_prediction_progress_restores_runner_and_raises_on_cancel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Runner:
        def _extract_results(self) -> list[int]:
            return [1]

    _install_fake_inference_runner(monkeypatch, Runner)
    original = Runner._extract_results
    cancel_event = Event()
    cancel_event.set()

    with pytest.raises(CancelledError):
        with dlc_adapter._prediction_progress(Queue(), uuid4(), cancel_event, total=1):
            Runner()._extract_results()

    assert Runner._extract_results is original


def test_dlc_train_worker_selects_snapshot_created_by_this_training(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.touch()
    old_snapshot = tmp_path / "old.pt"
    new_snapshot = tmp_path / "new.pt"
    old_snapshot.write_bytes(b"old")
    snapshots = [
        [SimpleNamespace(path=old_snapshot)],
        [SimpleNamespace(path=old_snapshot), SimpleNamespace(path=new_snapshot)],
    ]

    def train_network(*args: object, **kwargs: object) -> None:
        new_snapshot.write_bytes(b"new")

    monkeypatch.setitem(
        sys.modules,
        "deeplabcut",
        _fake_deeplabcut(train_network=train_network),
    )
    monkeypatch.setattr(dlc_adapter, "_model_snapshots", lambda *args: snapshots.pop(0))

    result = dlc_train_worker(
        uuid4(), Queue(), Event(), str(config_path), max_epochs=2, device="cpu"
    )

    assert result["status"] == "completed"
    assert result["snapshot_path"] == str(new_snapshot.resolve())


def test_dlc_train_worker_fails_when_training_creates_no_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.touch()
    existing = tmp_path / "existing.pt"
    existing.write_bytes(b"existing")

    def train_network(*args: object, **kwargs: object) -> None:
        return None

    monkeypatch.setitem(
        sys.modules,
        "deeplabcut",
        _fake_deeplabcut(train_network=train_network),
    )
    monkeypatch.setattr(
        dlc_adapter,
        "_model_snapshots",
        lambda *args: [SimpleNamespace(path=existing)],
    )

    result = dlc_train_worker(
        uuid4(), Queue(), Event(), str(config_path), max_epochs=2, device="cpu"
    )

    assert result["status"] == "failed"
    assert "snapshot_path" not in result
    assert "without creating or updating" in str(result["error_message"])
