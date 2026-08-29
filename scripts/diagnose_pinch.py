"""诊断脚本：探测 macOS 触摸板手势事件是否到达 Qt 控件。

用法（项目根目录，正常桌面会话，勿用 offscreen）：

    .venv/bin/python scripts/diagnose_pinch.py

操作：窗口打开后，在画面区域双指捏合/拔开 2–3 秒，然后关闭窗口。
脚本会打印所有到达的手势/触摸类事件及接收控件。把终端输出发回。

判定：
- 出现 "NativeGesture Zoom ..."   → Qt 已转换手势，断点在 VideoView（报我修）
- 出现 Touch/UpdateTouch 事件     → 系统送来原始触摸，Qt 未合成手势（改用 Touch 路径）
- 什么都没有                      → QCocoa 层未转发（需要 fallback 方案）
"""

import sys

from PySide6.QtCore import QEvent, QObject
from PySide6.QtWidgets import QApplication, QMainWindow

from ai_physics_tracker.application.video_session import VideoSession
from ai_physics_tracker.gui.main_window import MainWindow
from ai_physics_tracker.gui.video_view import VideoView
from ai_physics_tracker.infrastructure.opencv_video_reader import OpenCVVideoReader

INTERESTING = (
    "Gesture",
    "Touch",
    "Wheel",
    "Scroll",
    "Zoom",
    "Native",
    "Pinch",
)


class ProbeApplication(QApplication):
    def notify(self, receiver: QObject, event: QEvent) -> bool:
        try:
            name = event.type().name
            if any(keyword in name for keyword in INTERESTING):
                target = f"{receiver.__class__.__module__}.{receiver.__class__.__name__}"
                print(f"[event] {name:<28} -> {target}", flush=True)
        except Exception:
            pass
        return super().notify(receiver, event)


def main() -> int:
    app = ProbeApplication(sys.argv)
    window = MainWindow(VideoSession(OpenCVVideoReader()))
    window.show()

    # 在控制层各对象上再挂一层打印，确认事件最终到达
    view = window.videoView
    original_view_event = VideoView.event

    def traced_view_event(self, e):
        if any(keyword in e.type().name for keyword in INTERESTING):
            print(f"[VideoView.event] {e.type().name}", flush=True)
        return original_view_event(self, e)

    VideoView.event = traced_view_event  # type: ignore[method-assign]

    original_filter = window.eventFilter

    def traced_filter(self, obj, e):
        if any(keyword in e.type().name for keyword in INTERESTING):
            print(f"[MainWindow.eventFilter] {e.type().name} from {obj!r}", flush=True)
        return original_filter(self, obj, e)

    QMainWindow.eventFilter = traced_filter  # type: ignore[method-assign]

    print("窗口已打开：请打开一个视频（或空窗口也可），在画面区域双指捏合/拔开 2-3 秒，然后关闭窗口。", flush=True)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
