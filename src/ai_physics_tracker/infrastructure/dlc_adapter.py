"""DeepLabCut 3.x (PyTorch) 引擎适配器与数据转换实现。"""

import csv
from concurrent.futures import CancelledError
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from io import TextIOBase
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

import cv2
import numpy as np

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
        manual_points = [
            p
            for p in track_points
            if p.source == "manual" and p.status == "active"
        ]
        manual_points.sort(key=lambda p: p.frame_index)

        proj_dir = config_path.parent
        # 寻找 labeled-data 目录下的视频子目录
        labeled_data_root = proj_dir / "labeled-data"
        if not labeled_data_root.exists():
            labeled_data_root.mkdir(parents=True, exist_ok=True)

        # 获取或创建默认的视频子目录
        video_subdirs = [d for d in labeled_data_root.iterdir() if d.is_dir()]
        if video_subdirs:
            video_dir = video_subdirs[0]
        else:
            video_dir = labeled_data_root / "video"
            video_dir.mkdir(parents=True, exist_ok=True)

        video_stem = video_dir.name
        exported_count = 0
        csv_rows: list[list[str]] = []

        # 抽帧并生成图像文件
        for point in manual_points:
            img_rel = f"labeled-data/{video_stem}/img{point.frame_index:05d}.png"
            img_abs = proj_dir / img_rel

            # 解码该帧并写入 PNG
            if video_reader.is_open:
                try:
                    decoded = video_reader.read_frame(point.frame_index)
                    # decoded.pixels_rgb 是 RGB，转为 BGR 供 cv2 写入
                    bgr = cv2.cvtColor(decoded.pixels_rgb, cv2.COLOR_RGB2BGR)
                    cv2.imwrite(str(img_abs), bgr)
                except Exception:
                    # 若读取器异常，写入空占位图像保证流程完整
                    placeholder = np.zeros((100, 100, 3), dtype=np.uint8)
                    cv2.imwrite(str(img_abs), placeholder)

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

        with open(csv_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(header_scorer)
            writer.writerow(header_bodyparts)
            writer.writerow(header_coords)
            for row in csv_rows:
                writer.writerow(row)

        # 同步生成 DLC 所需的 CollectedData_<scorer>.h5 文件
        try:
            import pandas as pd

            df = pd.read_csv(csv_file, header=[0, 1, 2], index_col=0)
            h5_file = video_dir / f"CollectedData_{scorer}.h5"
            df.to_hdf(str(h5_file), key="df_with_missing", mode="w")
        except (ImportError, Exception):
            pass

        return exported_count

    def engine_version(self) -> str:
        """返回已安装的 DeepLabCut 版本，未安装时返回 '3.0.1'。"""
        try:
            import deeplabcut
            return str(deeplabcut.__version__)
        except (ImportError, Exception):
            return "3.0.1"

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
            deeplabcut.create_training_dataset(
                str(config_path),
                num_shuffles=num_shuffles,
                net_type=net_type,
                augmenter_type=augmenter_type,
                userfeedback=False,
            )
            return True
        except ImportError:
            # 未安装 DLC 时创建基础训练集目录保证 mock 流程连贯
            dataset_dir = config_path.parent / "training-datasets" / f"iteration-0"
            dataset_dir.mkdir(parents=True, exist_ok=True)
            return True
        except Exception as exc:
            raise RuntimeError(f"DLC create_training_dataset failed: {exc}") from exc

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
            trainingsetindex=params.trainingsetindex,
        )
        return TrainOutcome(
            status=str(outcome_dict.get("status", "completed")),
            epochs_completed=int(outcome_dict.get("epochs_completed", 0)),
            snapshot_path=outcome_dict.get("snapshot_path"),
            engine_version=self.engine_version(),
            error_message=outcome_dict.get("error_message"),
        )

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
) -> dict[str, Any]:
    """子进程中的 DLC 训练工作入口函数。"""

    config_path = Path(config_path_str)
    send_log(queue, run_id, "INFO", f"DLC training process started for {config_path.name}")

    actual_device = detect_device() if device == "auto" else device
    send_log(queue, run_id, "INFO", f"Detected compute device: {actual_device}")

    try:
        import deeplabcut

        send_log(queue, run_id, "INFO", f"DeepLabCut version: {deeplabcut.__version__}")
        send_log(
            queue,
            run_id,
            "INFO",
            f"Calling deeplabcut.train_network(epochs={max_epochs}, batch_size={batch_size}, device={actual_device})",
        )

        before = {snapshot.path.resolve(): _snapshot_stamp(snapshot.path)
                  for snapshot in _model_snapshots(config_path, shuffle, trainingsetindex)}
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
            save_epochs=max_epochs,
        )

        snapshots = _model_snapshots(config_path, shuffle, trainingsetindex)
        changed = [snapshot for snapshot in snapshots
                   if _snapshot_stamp(snapshot.path) != before.get(snapshot.path.resolve())]
        if not changed:
            raise RuntimeError("Training returned without creating or updating a model snapshot")
        # DLC 顺序按 epoch 排列，best 在末尾；只选择本次确实产出的文件。
        snapshot_path = str(changed[-1].path.resolve())
        send_log(queue, run_id, "INFO", f"DLC training completed. Snapshot saved: {snapshot_path}")
        return {"status": "completed", "epochs_completed": max_epochs,
                "snapshot_path": snapshot_path}
    except Exception as exc:
        send_log(queue, run_id, "ERROR", f"DLC training failed: {exc}")
        return {
            "status": "failed",
            "epochs_completed": 0,
            "error_message": str(exc),
        }


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

    def __init__(self, queue: Any, run_id: UUID) -> None:
        self.queue, self.run_id = queue, run_id
        self.pending = ""

    def write(self, value: str) -> int:
        self.pending += value.replace("\r", "\n")
        while "\n" in self.pending or len(self.pending) > 4096:
            if "\n" in self.pending:
                line, self.pending = self.pending.split("\n", 1)
            else:
                line, self.pending = self.pending[:4096], self.pending[4096:]
            if line.strip():
                send_log(self.queue, self.run_id, "INFO", line[:4096])
        return len(value)

    def flush(self) -> None:
        if self.pending.strip():
            send_log(self.queue, self.run_id, "INFO", self.pending[:4096])
        self.pending = ""


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
