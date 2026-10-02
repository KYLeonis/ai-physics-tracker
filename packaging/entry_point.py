"""PyInstaller 入口（P6.1）：freeze_support + 组合根调用 + 构建冒烟模式。

冒烟模式（``--apt-smoke``）：offscreen 构造完整 MainWindow、验证 host 依赖
分离红线（未加载 torch/DeepLabCut）与随包 FFprobe 可执行，把 JSON 结果写到
``APT_SMOKE_RESULT`` 指定的文件——windowed 可执行文件的 stdout 不可靠，
判定一律读结果文件 + 退出码。本文件随 PyInstaller 打包，不进产品包导入路径。
"""

import json
import multiprocessing
import os
import sys
import traceback


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
        app = QApplication(sys.argv[:1])
        window = MainWindow(
            lambda: VideoSession(OpenCVVideoReader()),
            ProjectRepository(),
            FFprobeTimingProbe(bundled_ffprobe()),
        )
        window.show()
        app.processEvents()
        window.close()

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
