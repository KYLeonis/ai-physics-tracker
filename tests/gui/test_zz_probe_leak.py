"""临时泄漏探针（诊断用，不入库）：统计窗口堆积、decoder 与线程残留。"""

import gc
import threading

from ai_physics_tracker.application.playback import AsyncVideoSession


def test_leak_probe_reports_windows_threads_decoders(qapp) -> None:
    gc.collect()
    sessions = [obj for obj in gc.get_objects() if isinstance(obj, AsyncVideoSession)]
    alive = [s for s in sessions if s._worker.is_alive()]
    windows = [w for w in qapp.topLevelWidgets() if hasattr(w, "projectActions")]
    print(f"\nPROBE decoders_total={len(sessions)} alive_workers={len(alive)}")
    for s in alive:
        print("PROBE alive decoder:", hex(id(s)), "stopped=", s._stopped)
    print(f"PROBE mainwindows_alive={len(windows)}")
    print("PROBE threads:", [(t.name, t.daemon) for t in threading.enumerate()])
