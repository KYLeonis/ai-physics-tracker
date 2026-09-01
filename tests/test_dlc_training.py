"""DLC 训练日志、参数转发与模型评价测试。"""

from multiprocessing import Event
from pathlib import Path
from queue import Queue
import sys
from types import ModuleType, SimpleNamespace
from uuid import uuid4

import pytest

from ai_physics_tracker.infrastructure import dlc_adapter
from ai_physics_tracker.infrastructure.dlc_adapter import DLCAdapter, dlc_train_worker
from ai_physics_tracker.infrastructure.engine_adapter import TrainingParams
from ai_physics_tracker.infrastructure.task_runner import TaskLog, TaskProgress


def test_evaluation_metric_units_use_percent_for_map_and_mar() -> None:
    assert dlc_adapter._evaluation_metric_unit("mAP") == "%"
    assert dlc_adapter._evaluation_metric_unit("mAR") == "%"


def _install_fake_dlc(monkeypatch: pytest.MonkeyPatch, **functions: object) -> ModuleType:
    module = ModuleType("deeplabcut")
    module.__version__ = "3.0.1-test"
    for name, function in functions.items():
        setattr(module, name, function)
    monkeypatch.setitem(sys.modules, "deeplabcut", module)
    return module


def test_dlc_train_worker_forwards_learning_rate_save_iters_and_real_progress(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text("config", encoding="utf-8")
    old_snapshot = tmp_path / "snapshot-001.pt"
    new_snapshot = tmp_path / "snapshot-003.pt"
    old_snapshot.write_bytes(b"old")
    snapshots = [
        [SimpleNamespace(path=old_snapshot)],
        [SimpleNamespace(path=old_snapshot), SimpleNamespace(path=new_snapshot)],
    ]
    calls: dict[str, object] = {}

    def train_network(*args: object, **kwargs: object) -> None:
        calls["args"] = args
        calls["kwargs"] = kwargs
        print("Epoch 1/3 (lr=0.0125), train loss 0.25000")
        new_snapshot.write_bytes(b"new")

    _install_fake_dlc(monkeypatch, train_network=train_network)
    monkeypatch.setattr(dlc_adapter, "_model_snapshots", lambda *args: snapshots.pop(0))
    queue = Queue()

    result = dlc_train_worker(
        uuid4(),
        queue,
        Event(),
        str(config_path),
        max_epochs=3,
        shuffle=2,
        device="cpu",
        batch_size=4,
        display_iters=6,
        save_iters=7,
        learning_rate=0.0125,
        trainingsetindex=1,
    )

    assert result["status"] == "completed"
    assert result["snapshot_path"] == str(new_snapshot.resolve())
    kwargs = calls["kwargs"]
    assert isinstance(kwargs, dict)
    assert kwargs["save_epochs"] == 7
    assert kwargs["pytorch_cfg_updates"] == {"runner.optimizer.params.lr": 0.0125}
    assert kwargs["trainingsetindex"] == 1

    messages = []
    while not queue.empty():
        messages.append(queue.get_nowait())
    progress = [message for message in messages if isinstance(message, TaskProgress)]
    logs = [message for message in messages if isinstance(message, TaskLog)]
    assert [(message.step, message.total_steps, message.loss, message.learning_rate)
            for message in progress] == [(1, 3, 0.25, 0.0125)]
    assert any("Epoch 1/3" in message.message for message in logs)


def test_dlc_adapter_train_forwards_training_parameters(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text("config", encoding="utf-8")
    calls: dict[str, object] = {}

    def worker(*args: object, **kwargs: object) -> dict[str, object]:
        calls["args"] = args
        calls["kwargs"] = kwargs
        return {
            "status": "completed",
            "epochs_completed": 3,
            "snapshot_path": str(tmp_path / "snapshot.pt"),
        }

    (tmp_path / "snapshot.pt").write_bytes(b"weights")
    _install_fake_dlc(monkeypatch)
    monkeypatch.setattr(dlc_adapter, "dlc_train_worker", worker)
    params = TrainingParams(
        epochs=3,
        batch_size=4,
        device="cpu",
        display_iters=6,
        save_iters=7,
        learning_rate=0.0125,
        shuffle=2,
        trainingsetindex=1,
    )

    outcome = DLCAdapter().train(uuid4(), Queue(), Event(), config_path, params)

    assert outcome.status == "completed"
    kwargs = calls["kwargs"]
    assert isinstance(kwargs, dict)
    assert kwargs["save_iters"] == 7
    assert kwargs["learning_rate"] == 0.0125
    assert kwargs["shuffle"] == 2
    assert kwargs["trainingsetindex"] == 1


def _install_fake_evaluation_modules(
    monkeypatch: pytest.MonkeyPatch,
    loader_type: type,
    evaluate_network: object,
    get_model_snapshots: object,
) -> None:
    loader_module = ModuleType("deeplabcut.pose_estimation_pytorch.data.dlcloader")
    loader_module.DLCLoader = loader_type
    data_module = ModuleType("deeplabcut.pose_estimation_pytorch.data")
    data_module.dlcloader = loader_module

    utils_module = ModuleType("deeplabcut.pose_estimation_pytorch.apis.utils")
    utils_module.get_model_snapshots = get_model_snapshots
    evaluation_module = ModuleType("deeplabcut.pose_estimation_pytorch.apis.evaluation")
    evaluation_module.get_model_snapshots = get_model_snapshots
    apis_module = ModuleType("deeplabcut.pose_estimation_pytorch.apis")
    apis_module.utils = utils_module
    apis_module.evaluation = evaluation_module

    pose_module = ModuleType("deeplabcut.pose_estimation_pytorch")
    pose_module.data = data_module
    pose_module.apis = apis_module
    deeplabcut = _install_fake_dlc(monkeypatch, evaluate_network=evaluate_network)
    deeplabcut.pose_estimation_pytorch = pose_module

    for name, module in (
        ("deeplabcut.pose_estimation_pytorch", pose_module),
        ("deeplabcut.pose_estimation_pytorch.data", data_module),
        ("deeplabcut.pose_estimation_pytorch.data.dlcloader", loader_module),
        ("deeplabcut.pose_estimation_pytorch.apis", apis_module),
        ("deeplabcut.pose_estimation_pytorch.apis.utils", utils_module),
        ("deeplabcut.pose_estimation_pytorch.apis.evaluation", evaluation_module),
    ):
        monkeypatch.setitem(sys.modules, name, module)


def test_evaluate_uses_exact_snapshot_and_returns_native_metrics(tmp_path: Path,
                                                                  monkeypatch: pytest.MonkeyPatch) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text("config", encoding="utf-8")
    selected_path = tmp_path / "snapshot-003.pt"
    selected_path.write_bytes(b"weights")
    selected = SimpleNamespace(path=selected_path, epochs=3, best=False)
    evaluation_dir = tmp_path / "evaluation-results-pytorch"
    calls: dict[str, object] = {}

    class FakeLoader:
        evaluation_folder = evaluation_dir
        project_cfg = {"multianimalproject": False, "bodyparts": ["target"], "cropping": False}

        def __init__(self, config, shuffle=0, trainset_index=0):
            calls["loader"] = (config, shuffle, trainset_index)

        def scorer(self, snapshot):
            calls["scorer_snapshot"] = snapshot
            return "FakeScorer"

        def snapshots(self):
            return [selected]

        @property
        def df_train(self):
            return ["train-1", "train-2"]

        @property
        def df_test(self):
            return ["test-1"]

    def get_model_snapshots(*args, **kwargs):
        return [selected]

    def evaluate_network(*args, **kwargs):
        calls["evaluate_args"] = args
        calls["evaluate_kwargs"] = kwargs
        evaluation_dir.mkdir(parents=True, exist_ok=True)
        (evaluation_dir / "FakeScorer-results.csv").write_text(
            "%Training dataset,Shuffle number,Training epochs,Detector epochs (TD only),pcutoff,"
            "train rmse,train mAP,test rmse,test mAP\n"
            "0.95,2,3,-1,0.6,1.25,0.8,2.5,0.7\n",
            encoding="utf-8",
        )
        # 评价模块直接导入了该函数，context manager 必须同时保护这一路径。
        from deeplabcut.pose_estimation_pytorch.apis import evaluation
        evaluation.get_model_snapshots(kwargs["snapshotindex"], tmp_path, "pose")

    _install_fake_evaluation_modules(monkeypatch, FakeLoader, evaluate_network, get_model_snapshots)
    params = TrainingParams(epochs=3, shuffle=2, trainingsetindex=1, device="cpu")

    result = DLCAdapter().evaluate(config_path, selected_path, params)

    assert result["snapshot_path"] == str(selected_path.resolve())
    assert result["snapshot_index"] == 0
    assert result["device"] == "cpu"
    assert result["train"]["metrics"] == {"rmse": 1.25, "mAP": 0.8}
    assert result["test"]["metrics"] == {"rmse": 2.5, "mAP": 0.7}
    assert result["train"]["sample_count"] == 2
    assert result["test"]["sample_count"] == 1
    assert result["train"]["units"] == {"rmse": "px", "mAP": "%"}
    assert result["results_csv"] == str(evaluation_dir / "FakeScorer-results.csv")
    kwargs = calls["evaluate_kwargs"]
    assert isinstance(kwargs, dict)
    assert kwargs["snapshotindex"] == 0
    assert kwargs["shuffles"] == [2]
    assert kwargs["trainingsetindex"] == 1
    assert kwargs["plotting"] is False


def test_evaluate_failure_is_raised_without_touching_model(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text("config", encoding="utf-8")
    snapshot_path = tmp_path / "snapshot-001.pt"
    snapshot_path.write_bytes(b"weights")
    selected = SimpleNamespace(path=snapshot_path, epochs=1, best=False)

    class FakeLoader:
        evaluation_folder = tmp_path / "evaluation-results-pytorch"
        project_cfg = {"multianimalproject": False, "bodyparts": ["target"], "cropping": False}

        def scorer(self, snapshot):
            return "FakeScorer"

        def snapshots(self):
            return [selected]

        @property
        def df_train(self):
            return []

        @property
        def df_test(self):
            return []

        def __init__(self, *args, **kwargs):
            pass

    def evaluate_network(*args, **kwargs):
        raise RuntimeError("evaluation unavailable")

    _install_fake_evaluation_modules(
        monkeypatch,
        FakeLoader,
        evaluate_network,
        lambda *args, **kwargs: [selected],
    )

    with pytest.raises(RuntimeError, match="DLC model evaluation failed"):
        DLCAdapter().evaluate(config_path, snapshot_path, TrainingParams(device="cpu"))
    assert snapshot_path.read_bytes() == b"weights"
