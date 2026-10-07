"""PyInstaller 入口（P6.1）：freeze_support + 组合根调用 + 构建冒烟模式。

冒烟模式（``--apt-smoke``）：offscreen 构造完整 MainWindow、验证 host 依赖
分离红线（未加载 torch/DeepLabCut）与随包 FFprobe 可执行，把 JSON 结果写到
``APT_SMOKE_RESULT`` 指定的文件——windowed 可执行文件的 stdout 不可靠，
判定一律读结果文件 + 退出码。本文件随 PyInstaller 打包，不进产品包导入路径。
"""

import csv
import json
import multiprocessing
import os
import sys
import traceback
from pathlib import Path
import tempfile
from uuid import uuid4


def _smoke() -> int:
    result_path = os.environ.get("APT_SMOKE_RESULT")
    report: dict = {"status": "failed"}

    def _finish(code: int) -> int:
        if result_path:
            with open(result_path, "w", encoding="utf-8") as stream:
                json.dump(report, stream, ensure_ascii=False, indent=2)
        return code

    try:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication

        from ai_physics_tracker.application.video_session import VideoSession
        from ai_physics_tracker.gui.launch_context import (
            FORBIDDEN_HOST_ROOTS,
            bundled_ffprobe,
            set_application_identity,
            worker_package_root,
        )
        from ai_physics_tracker.gui.main_window import MainWindow
        from ai_physics_tracker.infrastructure.ffprobe_timing import FFprobeTimingProbe
        from ai_physics_tracker.infrastructure.opencv_video_reader import (
            OpenCVVideoReader,
        )
        from ai_physics_tracker.infrastructure.project_repository import (
            ProjectRepository,
        )

        set_application_identity()
        # 在真实 frozen host 检查视频读写/seek；原 OpenCV build-info 不代表替换后的库。
        import cv2
        import numpy as np

        with tempfile.TemporaryDirectory(prefix="apt-video-smoke-") as temporary:
            for extension, codec in (("mp4", "mp4v"), ("avi", "MJPG")):
                video = str(Path(temporary) / ("synthetic." + extension))
                writer = cv2.VideoWriter(video, cv2.CAP_FFMPEG, cv2.VideoWriter_fourcc(*codec), 10.0, (64, 48))
                if not writer.isOpened():
                    raise RuntimeError(f"Packaged {codec} encoder unavailable")
                for index in range(24):
                    writer.write(np.full((48, 64, 3), index * 6, dtype=np.uint8))
                writer.release()
                capture = cv2.VideoCapture(video, cv2.CAP_FFMPEG)
                capture.set(cv2.CAP_PROP_POS_FRAMES, 17)
                ok, pixels = capture.read()
                count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
                capture.release()
                if not ok or count != 24 or abs(float(pixels.mean()) - 102) > 5:
                    raise RuntimeError(f"Packaged {extension} decoding/seek failed")
        report["video_read_write_seek"] = ["MP4/mp4v", "AVI/MJPEG"]
        if sys.platform == "darwin":
            import ctypes

            libs = Path(cv2.__file__).parent
            codec_path = next(libs.rglob("libavcodec.*.dylib"))
            codec_lib = ctypes.CDLL(str(codec_path))
            codec_lib.avcodec_license.restype = ctypes.c_char_p
            report["opencv_ffmpeg_license"] = codec_lib.avcodec_license().decode()
            if report["opencv_ffmpeg_license"] != "LGPL version 2.1 or later":
                raise RuntimeError("Packaged OpenCV FFmpeg is not LGPL")
        app = QApplication(sys.argv[:1])
        window = MainWindow(
            lambda: VideoSession(OpenCVVideoReader()),
            ProjectRepository(),
            FFprobeTimingProbe(bundled_ffprobe()),
        )
        window.show()
        app.processEvents()
        # P6.2 随包清单必须覆盖当前平台，并能实际打开 setup；不真实安装。
        window.runtimeSetup.open()
        app.processEvents()
        report["runtime_profiles"] = [p["id"] for p in window.runtimeSetup.profiles]
        if not report["runtime_profiles"]:
            report["detail"] = window.runtimeSetup.manifest_error or "No compatible runtime profile"
            window.close()
            return _finish(4)
        window.runtimeSetup.dialog.close()
        window.close()

        # 交付格式须在真正host中可读；hello不覆盖推理产物解析依赖。
        from ai_physics_tracker.domain.pendulum import ROLE_ORDER
        from ai_physics_tracker.infrastructure.dlc_predictions import read_joint_raw_predictions

        with tempfile.TemporaryDirectory(prefix="apt-frozen-predictions-") as directory:
            artifact = Path(directory) / "predictions.csv"
            with artifact.open("w", newline="", encoding="utf-8") as stream:
                writer = csv.writer(stream)
                writer.writerow(["scorer", *["DLC"] * 12])
                writer.writerow(["bodyparts", *[role for role in ROLE_ORDER for _ in range(3)]])
                writer.writerow(["coords", *[coord for _ in ROLE_ORDER for coord in ("x", "y", "likelihood")]])
                writer.writerow([0, *[value for _ in ROLE_ORDER for value in (1.25, 2.5, 0.9)]])
            parsed = read_joint_raw_predictions(
                artifact, tuple((role, role) for role in ROLE_ORDER),
                frame_count=1, expected_scorer="DLC",
            )
            if parsed.complete_count != 1 or "tables" in sys.modules:
                raise RuntimeError("Frozen host cannot validate joint CSV without PyTables")
            report["joint_csv_frames"] = parsed.complete_count

        loaded = sorted(
            {
                module.partition(".")[0]
                for module in sys.modules
                if module.partition(".")[0] in set(FORBIDDEN_HOST_ROOTS)
            }
        )
        report["forbidden_modules"] = loaded
        if loaded:
            report["detail"] = f"host imported AI-stack modules: {loaded}"
            return _finish(2)

        ffprobe = bundled_ffprobe()
        report["ffprobe"] = str(ffprobe)
        if ffprobe is None or not os.access(ffprobe, os.X_OK):
            report["detail"] = "bundled ffprobe missing or not executable"
            return _finish(3)

        # 真正从 frozen host 启动外部 Python，覆盖 Windows DLL 清理与随包源码身份。
        external_python = os.environ.get("APT_SMOKE_PYTHON")
        if external_python:
            from ai_physics_tracker.infrastructure.external_worker import ExternalWorkerRunner, build_request

            source_root = worker_package_root()
            if source_root is None:
                raise RuntimeError("Bundled worker source is missing")
            request, _ = build_request("hello", job_id=uuid4(), package_root=source_root)
            with tempfile.TemporaryDirectory(prefix="apt-frozen-worker-") as directory:
                handle = ExternalWorkerRunner(Path(external_python), package_root=source_root).start(Path(directory), request)
                if not handle.join(timeout_s=30):
                    handle.cancel()
                    raise RuntimeError("Frozen external worker timed out")
                evidence = handle.read_result()
                if evidence["status"] != "success":
                    raise RuntimeError(f"Frozen external worker failed: {evidence.get('error')}")
                report["external_worker"] = {"status": evidence["status"], "executable": evidence["executable"],
                                             "worker_sha256": request["worker_sha256"]}

        report["status"] = "ok"
        return _finish(0)
    except BaseException:  # 冒烟的任何异常都必须落盘，避免 windowed 下吞错
        report["detail"] = traceback.format_exc()
        return _finish(1)


if __name__ == "__main__":
    multiprocessing.freeze_support()
    if "--apt-smoke" in sys.argv[1:]:
        raise SystemExit(_smoke())
    from ai_physics_tracker.__main__ import main

    raise SystemExit(main(sys.argv))
