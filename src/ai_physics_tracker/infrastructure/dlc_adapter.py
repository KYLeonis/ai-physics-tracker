"""DeepLabCut 3.x (PyTorch) 引擎适配器与数据转换实现。"""

import csv
from concurrent.futures import CancelledError
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from io import TextIOBase
from datetime import UTC, datetime
from math import isfinite
import re
from pathlib import Path
from typing import Any
from uuid import UUID

import cv2

from ai_physics_tracker.domain.timeline import Timeline, frame_to_time
from ai_physics_tracker.domain.track import TrackPoint
from ai_physics_tracker.infrastructure.engine_adapter import (
    InferenceRequest,
    InferenceOutcome,
    TrainingParams,
    TrainOutcome,
)
from ai_physics_tracker.infrastructure.opencv_video_reader import OpenCVVideoReader
from ai_physics_tracker.infrastructure.task_runner import (
    send_log,
    send_progress,
)


_FLOAT_PATTERN = r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?"
_TRAINING_PROGRESS_PATTERN = re.compile(
    rf"\bEpoch\s+(?P<epoch>\d+)\s*/\s*(?P<total>\d+)\s+"
    rf"\(\s*lr\s*=\s*(?P<learning_rate>{_FLOAT_PATTERN})\s*\)\s*,\s*"
    rf"train\s+loss\s+(?P<loss>{_FLOAT_PATTERN})",
    re.IGNORECASE,
)


def detect_device() -> str:
    """自动检测最佳可用计算设备：cuda -> mps -> cpu。"""

    try:
        import torch

        if torch.cuda.is_available():
            return "cuda"
        if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            return "mps"
    except (ImportError, Exception):
        pass
    return "cpu"


class DLCAdapter:
    """DeepLabCut 3.x 适配器，处理项目创建、标注导出与推理结果导入。"""

    def create_project(
        self,
        project_name: str,
        experimenter: str,
        video_path: Path,
        working_dir: Path,
        bodyparts: list[str] | None = None,
    ) -> Path:
        """在 working_dir 创建 DLC 项目目录结构并生成基础 config.yaml。"""

        actual_bodyparts = bodyparts or ["target"]
        proj_dir = working_dir / project_name
        video_stem = video_path.stem

        labeled_data_dir = proj_dir / "labeled-data" / video_stem
        training_datasets_dir = proj_dir / "training-datasets"
        dlc_models_dir = proj_dir / "dlc-models"

        labeled_data_dir.mkdir(parents=True, exist_ok=True)
        training_datasets_dir.mkdir(parents=True, exist_ok=True)
        dlc_models_dir.mkdir(parents=True, exist_ok=True)

        config_path = proj_dir / "config.yaml"
        now_str = datetime.now(UTC).strftime("%b%d")

        bodyparts_yaml = "\n".join(f"  - {bp}" for bp in actual_bodyparts)
        config_content = (
            f"Task: {project_name}\n"
            f"scorer: {experimenter}\n"
            f"date: {now_str}\n"
            f"multianimalproject: false\n"
            f"identity: false\n"
            f"\n"
            f"project_path: {proj_dir.as_posix()}\n"
            f"\n"
            f"bodyparts:\n"
            f"{bodyparts_yaml}\n"
            f"\n"
            f"video_sets:\n"
            f"  {video_path.as_posix()}:\n"
            f"    crop: 0, 1920, 0, 1080\n"
            f"\n"
            f"TrainingFraction:\n"
            f"  - 0.95\n"
            f"iteration: 0\n"
            f"default_net_type: resnet_50\n"
            f"default_augmenter: default\n"
            f"snapshotindex: -1\n"
            f"batch_size: 8\n"
            f"\n"
            f"cropping: false\n"
            f"engine: pytorch\n"
        )
        config_path.write_text(config_content, encoding="utf-8")
        return config_path

    def export_annotations(
        self,
        track_points: tuple[TrackPoint, ...],
        video_reader: OpenCVVideoReader,
        config_path: Path,
        scorer: str = "AIPhysicsTracker",
        bodyparts: list[str] | None = None,
    ) -> int:
        """导出 active manual 标注点为 DLC labeled-data 结构（PNG 图像与 MultiIndex CSV）。"""

        actual_bodyparts = bodyparts or ["target"]
        if not video_reader.is_open:
            raise RuntimeError("Cannot export annotations: video reader is not open")
        manual_points = [
            p
            for p in track_points
            if p.source == "manual" and p.status == "active"
        ]
        manual_points.sort(key=lambda p: p.frame_index)

        proj_dir = config_path.parent
        # labeled-data 子目录按当前视频 stem 定位（与 create_project 同约定）。
        # 出现其他视频的子目录时必须拒绝：DLC 建集会把整个 labeled-data
        # 纳入训练集，静默混入另一段视频的帧会产出无法察觉的错误数据
        #（review F6）。
        video_stem = video_reader.path.stem
        labeled_data_root = proj_dir / "labeled-data"
        labeled_data_root.mkdir(parents=True, exist_ok=True)
        foreign_dirs = sorted(
            entry.name
            for entry in labeled_data_root.iterdir()
            if entry.is_dir() and entry.name != video_stem
        )
        if foreign_dirs:
            raise RuntimeError(
                f"DLC labeled-data contains folders from another video: {foreign_dirs}; "
                f"expected only {video_stem!r}. Delete the stale folders (or retrain in "
                f"a fresh project directory) before exporting annotations."
            )
        video_dir = labeled_data_root / video_stem
        video_dir.mkdir(parents=True, exist_ok=True)
        exported_count = 0
        csv_rows: list[list[str]] = []

        # 抽帧并生成图像文件
        for point in manual_points:
            img_rel = f"labeled-data/{video_stem}/img{point.frame_index:05d}.png"
            img_abs = proj_dir / img_rel

            # 解码该帧并写入 PNG
            try:
                decoded = video_reader.read_frame(point.frame_index)
                if decoded.frame_index != point.frame_index:
                    raise ValueError(
                        f"reader returned frame {decoded.frame_index} for requested frame "
                        f"{point.frame_index}"
                    )
                # decoded.pixels_rgb 是 RGB，转为 BGR 供 cv2 写入
                bgr = cv2.cvtColor(decoded.pixels_rgb, cv2.COLOR_RGB2BGR)
            except Exception as error:
                raise RuntimeError(
                    f"Failed to decode frame {point.frame_index} for DLC annotation export: {error}"
                ) from error
            try:
                if not cv2.imwrite(str(img_abs), bgr):
                    raise OSError("cv2.imwrite returned False")
            except Exception as error:
                raise RuntimeError(
                    f"Failed to write PNG annotation frame {point.frame_index}: {img_abs}: {error}"
                ) from error

            # 对应 bodyparts 列表（单 TrackPoint 填入首个 bodypart，其余补空）
            coords_row = [img_rel]
            for i, bp in enumerate(actual_bodyparts):
                if i == 0:
                    coords_row.extend([f"{point.pixel_x:.2f}", f"{point.pixel_y:.2f}"])
                else:
                    coords_row.extend(["", ""])
            csv_rows.append(coords_row)
            exported_count += 1

        # 写入 CollectedData_<scorer>.csv
        csv_file = video_dir / f"CollectedData_{scorer}.csv"

        # MultiIndex header (3 rows)
        header_scorer = ["scorer"] + [scorer] * (len(actual_bodyparts) * 2)
        header_bodyparts = ["bodyparts"]
        for bp in actual_bodyparts:
            header_bodyparts.extend([bp, bp])
        header_coords = ["coords"] + ["x", "y"] * len(actual_bodyparts)

        try:
            with open(csv_file, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(header_scorer)
                writer.writerow(header_bodyparts)
                writer.writerow(header_coords)
                for row in csv_rows:
                    writer.writerow(row)
        except OSError as error:
            raise RuntimeError(f"Failed to write DLC annotation CSV: {csv_file}") from error

        # 同步生成 DLC 所需的 CollectedData_<scorer>.h5 文件
        h5_file = video_dir / f"CollectedData_{scorer}.h5"
        try:
            import pandas as pd

            df = pd.read_csv(csv_file, header=[0, 1, 2], index_col=0)
            df.to_hdf(str(h5_file), key="df_with_missing", mode="w")
            if not h5_file.is_file():
                raise OSError("pandas.to_hdf did not create the output file")
        except Exception as error:
            raise RuntimeError(f"Failed to create DLC annotation HDF5: {h5_file}: {error}") from error

        return exported_count

    def engine_version(self) -> str:
        """返回已安装的 DeepLabCut 版本，依赖缺失时明确报错。"""
        try:
            import deeplabcut
        except ImportError as error:
            raise RuntimeError("DeepLabCut is not installed") from error
        version = getattr(deeplabcut, "__version__", None)
        if not isinstance(version, str) or not version.strip():
            raise RuntimeError("DeepLabCut did not expose a valid version")
        return version

    def create_training_dataset(
        self,
        config_path: Path,
        num_shuffles: int = 1,
        net_type: str = "resnet_50",
        augmenter_type: str = "default",
    ) -> bool:
        """调用 deeplabcut.create_training_dataset 创建训练集。"""
        try:
            import deeplabcut
        except ImportError as error:
            raise RuntimeError("DeepLabCut is required to create a training dataset") from error
        try:
            deeplabcut.create_training_dataset(
                str(config_path),
                num_shuffles=num_shuffles,
                net_type=net_type,
                augmenter_type=augmenter_type,
                userfeedback=False,
            )
        except Exception as error:
            raise RuntimeError(f"DLC create_training_dataset failed: {error}") from error
        return True

    def train(
        self,
        run_id: UUID,
        queue: Any,
        cancel_event: Any,
        config_path: Path,
        params: TrainingParams,
    ) -> TrainOutcome:
        """在当前进程或子进程中调用 DLC 训练。"""
        outcome_dict = dlc_train_worker(
            run_id=run_id,
            queue=queue,
            cancel_event=cancel_event,
            config_path_str=str(config_path),
            max_epochs=params.epochs,
            shuffle=params.shuffle,
            device=params.device,
            batch_size=params.batch_size,
            display_iters=params.display_iters,
            save_iters=params.save_iters,
            learning_rate=params.learning_rate,
            trainingsetindex=params.trainingsetindex,
        )
        return TrainOutcome(
            status=str(outcome_dict.get("status", "completed")),
            epochs_completed=int(outcome_dict.get("epochs_completed", 0)),
            snapshot_path=outcome_dict.get("snapshot_path"),
            engine_version=self.engine_version(),
            error_message=outcome_dict.get("error_message"),
        )

    def evaluate(
        self,
        config_path: Path,
        snapshot_path: Path,
        params: TrainingParams,
    ) -> dict[str, Any]:
        """用指定快照执行 DLC 原生评价，并返回 train/test 指标摘要。"""

        config_path = Path(config_path).resolve()
        snapshot_path = Path(snapshot_path).resolve()
        if not config_path.is_file():
            raise ValueError(f"DLC config does not exist: {config_path}")
        if not snapshot_path.is_file():
            raise ValueError(f"DLC snapshot does not exist: {snapshot_path}")

        try:
            import deeplabcut
            from deeplabcut.pose_estimation_pytorch.data.dlcloader import DLCLoader
        except ImportError as error:
            raise RuntimeError("DeepLabCut is required to evaluate a model") from error

        snapshots = _model_snapshots(config_path, params.shuffle, params.trainingsetindex)
        matches = [
            index
            for index, snapshot in enumerate(snapshots)
            if snapshot.path.resolve() == snapshot_path
        ]
        if len(matches) != 1:
            raise ValueError(
                "Selected snapshot does not belong to this DLC model; "
                "retrain or select its config"
            )
        snapshot_index = matches[0]

        loader = DLCLoader(
            config_path,
            shuffle=params.shuffle,
            trainset_index=params.trainingsetindex,
        )
        selected_snapshot = snapshots[snapshot_index]
        scorer = loader.scorer(selected_snapshot)
        scores_path = loader.evaluation_folder / f"{scorer}-results.csv"
        actual_device = detect_device() if params.device == "auto" else params.device

        try:
            with _selected_evaluation_snapshot(snapshot_path):
                deeplabcut.evaluate_network(
                    str(config_path),
                    shuffles=[params.shuffle],
                    trainingsetindex=params.trainingsetindex,
                    snapshotindex=snapshot_index,
                    device=actual_device,
                    plotting=False,
                    show_errors=False,
                )
        except Exception as error:
            raise RuntimeError(f"DLC model evaluation failed: {error}") from error

        if not scores_path.is_file():
            raise RuntimeError(f"DLC evaluation did not produce its results CSV: {scores_path}")
        scores = _read_evaluation_scores(scores_path)
        try:
            train_samples = int(len(loader.df_train))
            test_samples = int(len(loader.df_test))
        except Exception as error:
            raise RuntimeError(f"DLC evaluation sample counts are unavailable: {error}") from error

        metric_units = {
            name: _evaluation_metric_unit(name)
            for split in ("train", "test")
            for name in scores[split]
        }
        return {
            "status": "completed",
            "snapshot_path": str(snapshot_path),
            "snapshot_index": snapshot_index,
            "device": actual_device,
            "train": {
                "metrics": scores["train"],
                "sample_count": train_samples,
                "units": {name: metric_units[name] for name in scores["train"]},
            },
            "test": {
                "metrics": scores["test"],
                "sample_count": test_samples,
                "units": {name: metric_units[name] for name in scores["test"]},
            },
            "metadata": scores["metadata"],
            "results_csv": str(scores_path),
        }

    def import_results(
        self, prediction_data: Any, track_id: UUID, timeline: Timeline,
        source_detail: str, bodypart: str = "target", min_confidence: float = 0.0,
    ) -> tuple[TrackPoint, ...]:
        """在适配边界严格解析 DLC 预测；缺测不造点，非法结构拒绝整批。"""
        from ai_physics_tracker.infrastructure.dlc_predictions import parse_predictions

        return parse_predictions(prediction_data, track_id, timeline, source_detail,
                                 bodypart, min_confidence).points

    def infer(
        self, run_id: UUID, queue: Any, cancel_event: Any, request: InferenceRequest,
    ) -> InferenceOutcome:
        """使用已选模型在当前子进程推理；真实完成帧数经队列上报。"""
        import deeplabcut
        from ai_physics_tracker.infrastructure.dlc_predictions import parse_predictions

        if cancel_event.is_set():
            raise CancelledError("Inference cancelled")
        if request.output_dir.exists():
            raise ValueError("Inference output directory must be new")
        snapshots = _model_snapshots(request.config_path, request.shuffle,
                                     request.trainingsetindex)
        matches = [i for i, snapshot in enumerate(snapshots)
                   if snapshot.path.resolve() == request.model_snapshot.resolve()]
        if len(matches) != 1 or not request.model_snapshot.is_file():
            raise ValueError("Selected snapshot does not belong to this DLC model; retrain or select its config")
        actual_device = detect_device() if request.params.device == "auto" else request.params.device
        request.output_dir.mkdir(parents=True, exist_ok=False)
        stream = _QueueLogStream(queue, run_id)
        send_progress(queue, run_id, 0, request.frame_count, message="Loading selected model")
        with redirect_stdout(stream), redirect_stderr(stream), _selected_snapshot(request.model_snapshot), _prediction_progress(
            queue, run_id, cancel_event, request.frame_count
        ) as progress:
            scorer = deeplabcut.analyze_videos(
                str(request.config_path), [str(request.video_path)],
                shuffle=request.shuffle, trainingsetindex=request.trainingsetindex,
                snapshot_index=matches[0], device=actual_device,
                destfolder=str(request.output_dir), batch_size=request.params.batch_size,
                save_as_csv=True, auto_track=False,
                cropping=None, dynamic=(False, 0.5, 10),
            )
        stream.flush()
        if cancel_event.is_set():
            raise CancelledError("Inference cancelled")
        if progress[0] != request.frame_count:
            raise ValueError(f"Incomplete inference: processed {progress[0]}/{request.frame_count} frames")
        if not isinstance(scorer, str) or Path(scorer).name != scorer:
            raise ValueError("DLC returned an invalid scorer")
        prediction_path = request.output_dir / f"{request.video_path.stem}{scorer}.h5"
        parsed = parse_predictions(
            prediction_path, request.track_id, request.timeline, request.source_detail,
            min_confidence=request.params.min_confidence, frame_count=request.frame_count,
        )
        return InferenceOutcome(parsed.points, prediction_path, parsed.row_count,
                                parsed.missing_count, parsed.low_confidence_count,
                                request.model_snapshot, str(deeplabcut.__version__), actual_device)


@contextmanager
def _selected_snapshot(expected_path: Path):
    """复核 DLC 在加载权重前实际解析的路径，防止快照列表变化使 index 指向别处。"""
    from deeplabcut.pose_estimation_pytorch.apis import utils

    original = utils.get_model_snapshots

    def select(*args, **kwargs):
        selected = original(*args, **kwargs)
        if len(selected) != 1 or selected[0].path.resolve() != expected_path.resolve():
            raise ValueError("DLC resolved a different snapshot; retry with the selected model")
        return selected

    utils.get_model_snapshots = select
    try:
        yield
    finally:
        utils.get_model_snapshots = original


@contextmanager
def _selected_evaluation_snapshot(expected_path: Path):
    """复核 DLC 评价阶段实际加载的快照，并在结束后恢复门面函数。"""
    from deeplabcut.pose_estimation_pytorch.apis import evaluation, utils

    targets = [(utils, "get_model_snapshots")]
    if hasattr(evaluation, "get_model_snapshots"):
        targets.append((evaluation, "get_model_snapshots"))
    originals = [(module, name, getattr(module, name)) for module, name in targets]

    def select(original, *args, **kwargs):
        selected = original(*args, **kwargs)
        if len(selected) != 1 or selected[0].path.resolve() != expected_path.resolve():
            raise ValueError("DLC resolved a different snapshot during evaluation")
        return selected

    for module, name, original in originals:
        setattr(module, name, lambda *args, _original=original, **kwargs: select(
            _original, *args, **kwargs
        ))
    try:
        yield
    finally:
        for module, name, original in originals:
            setattr(module, name, original)


def _read_evaluation_scores(path: Path) -> dict[str, dict[str, Any]]:
    """读取 DLC 原生评价 CSV 中的 train/test 指标和元数据。"""
    try:
        with path.open("r", newline="", encoding="utf-8") as stream:
            rows = list(csv.DictReader(stream))
    except OSError as error:
        raise RuntimeError(f"Failed to read DLC evaluation CSV: {path}") from error
    if not rows:
        raise RuntimeError(f"DLC evaluation CSV contains no result row: {path}")

    row = rows[0]
    scores: dict[str, dict[str, Any]] = {"train": {}, "test": {}, "metadata": {}}
    for raw_name, raw_value in row.items():
        if raw_name is None:
            continue
        name = raw_name.strip()
        value = _evaluation_csv_value(raw_value)
        lowered = name.lower()
        if lowered.startswith("train "):
            scores["train"][name[6:]] = value
        elif lowered.startswith("test "):
            scores["test"][name[5:]] = value
        else:
            scores["metadata"][name] = value
    if not scores["train"] or not scores["test"]:
        raise RuntimeError(f"DLC evaluation CSV has no train/test metrics: {path}")
    return scores


def _evaluation_csv_value(value: str | None) -> float | str | None:
    """把评价 CSV 的数值列转为 JSON 可序列化值。"""
    if value is None or not value.strip():
        return None
    try:
        number = float(value)
    except ValueError:
        return value
    return number if isfinite(number) else None


def _evaluation_metric_unit(name: str) -> str:
    """返回 DLC 原生评价指标的常用单位说明。"""
    lowered = name.lower()
    if "rmse" in lowered or "error" in lowered:
        return "px"
    if lowered in {"map", "mar"}:
        return "%"
    return "unknown"


def dlc_train_worker(
    run_id: UUID,
    queue: Any,
    cancel_event: Any,
    config_path_str: str,
    max_epochs: int = 50,
    shuffle: int = 1,
    device: str = "auto",
    batch_size: int = 8,
    display_iters: int = 10,
    trainingsetindex: int = 0,
    save_iters: int = 50,
    learning_rate: float = 0.001,
) -> dict[str, Any]:
    """子进程中的 DLC 训练工作入口函数。"""

    config_path = Path(config_path_str)
    send_log(queue, run_id, "INFO", f"DLC training process started for {config_path.name}")

    actual_device = detect_device() if device == "auto" else device
    send_log(queue, run_id, "INFO", f"Detected compute device: {actual_device}")

    stream = _TrainingLogStream(queue, run_id)
    try:
        with redirect_stdout(stream), redirect_stderr(stream):
            import deeplabcut

            send_log(queue, run_id, "INFO", f"DeepLabCut version: {deeplabcut.__version__}")
            send_log(
                queue,
                run_id,
                "INFO",
                f"Calling deeplabcut.train_network(epochs={max_epochs}, batch_size={batch_size}, "
                f"device={actual_device}, learning_rate={learning_rate}, save_epochs={save_iters})",
            )

            before = {
                snapshot.path.resolve(): _snapshot_stamp(snapshot.path)
                for snapshot in _model_snapshots(config_path, shuffle, trainingsetindex)
            }
            if cancel_event.is_set():
                return {"status": "cancelled", "epochs_completed": 0}
            deeplabcut.train_network(
                str(config_path),
                shuffle=shuffle,
                trainingsetindex=trainingsetindex,
                epochs=max_epochs,
                batch_size=batch_size,
                device=actual_device,
                display_iters=display_iters,
                save_epochs=save_iters,
                pytorch_cfg_updates={"runner.optimizer.params.lr": learning_rate},
            )

            snapshots = _model_snapshots(config_path, shuffle, trainingsetindex)
            changed = [
                snapshot
                for snapshot in snapshots
                if _snapshot_stamp(snapshot.path) != before.get(snapshot.path.resolve())
            ]
            if not changed:
                raise RuntimeError("Training returned without creating or updating a model snapshot")
            # DLC 顺序按 epoch 排列，best 在末尾；只选择本次确实产出的文件。
            snapshot_path = str(changed[-1].path.resolve())
            send_log(queue, run_id, "INFO", f"DLC training completed. Snapshot saved: {snapshot_path}")
            return {
                "status": "completed",
                "epochs_completed": max_epochs,
                "snapshot_path": snapshot_path,
            }
    except Exception as error:
        send_log(queue, run_id, "ERROR", f"DLC training failed: {error}")
        return {
            "status": "failed",
            "epochs_completed": 0,
            "error_message": str(error),
        }
    finally:
        stream.flush()


def _snapshot_stamp(path: Path) -> tuple[int, int]:
    stat = path.stat()
    return stat.st_mtime_ns, stat.st_size


def _model_snapshots(config_path: Path, shuffle: int, trainingsetindex: int) -> list[Any]:
    """通过 DLC 自身 loader 定位当前模型，避免硬编码 TF/PyTorch 目录名。"""
    from deeplabcut.pose_estimation_pytorch.data.dlcloader import DLCLoader

    loader = DLCLoader(config_path, shuffle=shuffle, trainset_index=trainingsetindex)
    if loader.project_cfg["multianimalproject"] or list(loader.project_cfg["bodyparts"]) != ["target"]:
        raise ValueError("Inference currently requires one bodypart named target")
    if loader.project_cfg.get("cropping", False):
        raise ValueError("Cropped DLC projects are not supported; use full-frame coordinates")
    return loader.snapshots()


class _QueueLogStream(TextIOBase):
    """把 DLC 标准输出转成有界日志行，兼容 tqdm 的回车刷新。"""

    def __init__(self, queue: Any, run_id: UUID, line_handler: Any | None = None) -> None:
        self.queue, self.run_id = queue, run_id
        self.line_handler = line_handler
        self.pending = ""

    def _emit_line(self, line: str) -> None:
        if line.strip():
            line = line[:4096]
            send_log(self.queue, self.run_id, "INFO", line)
            if self.line_handler is not None:
                self.line_handler(line)

    def write(self, value: str) -> int:
        self.pending += value.replace("\r", "\n")
        while "\n" in self.pending or len(self.pending) > 4096:
            if "\n" in self.pending:
                line, self.pending = self.pending.split("\n", 1)
            else:
                line, self.pending = self.pending[:4096], self.pending[4096:]
            self._emit_line(line)
        return len(value)

    def flush(self) -> None:
        if self.pending.strip():
            self._emit_line(self.pending)
        self.pending = ""


class _TrainingLogStream(_QueueLogStream):
    """转发 DLC 训练日志，并从真实 epoch 行提取 loss 与学习率。"""

    def __init__(self, queue: Any, run_id: UUID) -> None:
        super().__init__(queue, run_id, line_handler=self._handle_line)

    def _handle_line(self, line: str) -> None:
        match = _TRAINING_PROGRESS_PATTERN.search(line)
        if match is None:
            return
        send_progress(
            self.queue,
            self.run_id,
            step=int(match.group("epoch")),
            total_steps=int(match.group("total")),
            loss=float(match.group("loss")),
            learning_rate=float(match.group("learning_rate")),
            message=line,
        )


@contextmanager
def _prediction_progress(queue: Any, run_id: UUID, cancel_event: Any, total: int):
    """DLC 3.0.1 无回调；仅在独占子进程中桥接已后处理的帧，退出恢复。

    不包装读帧迭代器：异步预处理可能提前读取，不能充当已预测进度。
    上游提供正式回调后替换此局部兼容层。
    """
    from deeplabcut.pose_estimation_pytorch.runners.inference import InferenceRunner

    original = InferenceRunner._extract_results
    count = [0]

    def extract(runner, *args, **kwargs):
        if cancel_event.is_set():
            raise CancelledError("Inference cancelled")
        results = original(runner, *args, **kwargs)
        if results:
            count[0] += len(results)
            if count[0] > total:
                raise ValueError("DLC produced more frames than the registered video")
            send_progress(queue, run_id, count[0], total, message="Frames predicted")
        return results

    InferenceRunner._extract_results = extract
    try:
        yield count
    finally:
        InferenceRunner._extract_results = original
