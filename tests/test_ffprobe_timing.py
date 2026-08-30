"""FFprobe 时序适配器的逐帧判定、失败安全与真实媒体测试。"""

from __future__ import annotations

import subprocess
import json
from pathlib import Path
from threading import Event
from typing import Sequence

import pytest

from ai_physics_tracker.infrastructure import ffprobe_timing
from ai_physics_tracker.infrastructure.ffprobe_timing import FFprobeTimingProbe


class _CompletedProcess:
    def __init__(self, stdout: str, stderr: str = "", returncode: int = 0) -> None:
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode
        self.kill_called = False
        self.wait_called = False
        self.commands: list[list[str]] = []

    def communicate(self, timeout: float | None = None) -> tuple[str, str]:
        return self.stdout, self.stderr

    def poll(self) -> int:
        return self.returncode

    def kill(self) -> None:
        self.kill_called = True
        self.returncode = -9

    def wait(self, timeout: float | None = None) -> int:
        self.wait_called = True
        return self.returncode


class _HangingProcess:
    def __init__(self, cancel: Event | None = None) -> None:
        self.returncode: int | None = None
        self.kill_called = False
        self.wait_called = False
        self._cancel = cancel

    def communicate(self, timeout: float | None = None) -> tuple[str, str]:
        if self._cancel is not None:
            self._cancel.set()
        raise subprocess.TimeoutExpired("ffprobe", timeout)

    def poll(self) -> int | None:
        return self.returncode

    def kill(self) -> None:
        self.kill_called = True
        self.returncode = -9

    def wait(self, timeout: float | None = None) -> int:
        self.wait_called = True
        return self.returncode or -9


def _json_output(
    timestamps: Sequence[object],
    *,
    time_base: str = "1/10",
    frame_rate: str = "10/1",
    side_data: bool = False,
) -> str:
    frames = []
    for timestamp in timestamps:
        frame = {"best_effort_timestamp": timestamp}
        if side_data:
            frame["side_data_list"] = [{"side_data_type": "H.264 metadata"}]
        frames.append(frame)
    return json.dumps(
        {
            "frames": frames,
            "streams": [{"time_base": time_base, "r_frame_rate": frame_rate}],
        }
    )


def _install_fake_process(
    monkeypatch: pytest.MonkeyPatch,
    process: _CompletedProcess | _HangingProcess,
) -> None:
    def fake_popen(command: list[str], **kwargs: object) -> _CompletedProcess | _HangingProcess:
        assert kwargs["shell"] is False
        assert "-show_frames" in command
        assert "-show_streams" in command
        assert "json" in command
        assert any("best_effort_timestamp" in item for item in command)
        return process

    monkeypatch.setattr(ffprobe_timing.subprocess, "Popen", fake_popen)


def test_probe_classifies_complete_constant_timestamps_as_cfr(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    video_path = tmp_path / "video.fake"
    video_path.touch()
    process = _CompletedProcess(
        _json_output([0, 1, 2, 3], side_data=True)
    )
    _install_fake_process(monkeypatch, process)

    report = FFprobeTimingProbe(executable=Path("ffprobe")).probe(video_path)

    assert report.status == "cfr"
    assert report.frame_count == 4
    assert report.fps_measured == pytest.approx(10.0, abs=1e-9)


def test_probe_classifies_variable_intervals_as_vfr(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    video_path = tmp_path / "video.fake"
    video_path.touch()
    process = _CompletedProcess(
        _json_output([0, 1, 3, 6])
    )
    _install_fake_process(monkeypatch, process)

    report = FFprobeTimingProbe(executable=Path("ffprobe")).probe(video_path)

    assert report.status == "vfr_suspected"
    assert report.frame_count == 4
    assert report.fps_measured is None


@pytest.mark.parametrize(
    ("stdout", "stderr", "returncode", "reason_fragment"),
    [
        (_json_output([0, "N/A"]), "", 0, "invalid frame timestamp"),
        (_json_output([0, "NaN"]), "", 0, "invalid frame timestamp"),
        (_json_output([0, None]), "", 0, "invalid frame timestamp"),
        ("not-json", "", 0, "invalid JSON"),
        ("", "decoder failed", 1, "exited with status 1"),
    ],
)
def test_probe_returns_unknown_for_incomplete_or_failed_ffprobe_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    stdout: str,
    stderr: str,
    returncode: int,
    reason_fragment: str,
) -> None:
    video_path = tmp_path / "video.fake"
    video_path.touch()
    _install_fake_process(
        monkeypatch, _CompletedProcess(stdout, stderr, returncode)
    )

    report = FFprobeTimingProbe(executable=Path("ffprobe")).probe(video_path)

    assert report.status == "unknown"
    assert reason_fragment in report.reason


def test_probe_returns_unknown_when_ffprobe_is_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    video_path = tmp_path / "video.fake"
    video_path.touch()
    monkeypatch.setattr(ffprobe_timing.shutil, "which", lambda name: None)

    report = FFprobeTimingProbe().probe(video_path)

    assert report.status == "unknown"
    assert "not found" in report.reason


def test_probe_cancellation_kills_and_waits_for_ffprobe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    video_path = tmp_path / "video.fake"
    video_path.touch()
    cancel = Event()
    process = _HangingProcess(cancel)
    _install_fake_process(monkeypatch, process)

    report = FFprobeTimingProbe(executable=Path("ffprobe")).probe(
        video_path, cancel=cancel
    )

    assert report.status == "unknown"
    assert report.reason == "probe cancelled"
    assert process.kill_called
    assert process.wait_called


def test_probe_timeout_kills_and_waits_for_ffprobe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    video_path = tmp_path / "video.fake"
    video_path.touch()
    process = _HangingProcess()
    _install_fake_process(monkeypatch, process)

    report = FFprobeTimingProbe(
        executable=Path("ffprobe"), timeout_s=0.01
    ).probe(video_path)

    assert report.status == "unknown"
    assert report.reason == "ffprobe timed out"
    assert process.kill_called
    assert process.wait_called


def test_probe_returns_unknown_for_nonempty_stderr_even_with_zero_exit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    video_path = tmp_path / "video.fake"
    video_path.touch()
    process = _CompletedProcess(_json_output([0, 1]), "warning", 0)
    _install_fake_process(monkeypatch, process)

    report = FFprobeTimingProbe(executable=Path("ffprobe")).probe(video_path)

    assert report.status == "unknown"
    assert "stderr" in report.reason


def test_probe_classifies_non_monotonic_timestamps_as_vfr(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    video_path = tmp_path / "video.fake"
    video_path.touch()
    process = _CompletedProcess(_json_output([0, 1, 1, 2]))
    _install_fake_process(monkeypatch, process)

    report = FFprobeTimingProbe(executable=Path("ffprobe")).probe(video_path)

    assert report.status == "vfr_suspected"
    assert "strictly increasing" in report.reason


def test_probe_accepts_2997_fps_timestamp_quantization(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    video_path = tmp_path / "video.fake"
    video_path.touch()
    # 29.97 fps 在 1/1000 s time_base 下只能量化为 33/34 tick 的交替步长。
    process = _CompletedProcess(
        _json_output(
            [0, 33, 67, 100, 133, 167],
            time_base="1/1000",
            frame_rate="30000/1001",
        )
    )
    _install_fake_process(monkeypatch, process)

    report = FFprobeTimingProbe(executable=Path("ffprobe")).probe(video_path)

    assert report.status == "cfr"
    assert report.frame_count == 6
    assert report.fps_measured == pytest.approx(1000 * 5 / 167, rel=1e-3)


def test_probe_returns_unknown_when_time_base_is_too_coarse(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    video_path = tmp_path / "video.fake"
    video_path.touch()
    process = _CompletedProcess(
        _json_output([0, 1, 2], time_base="1/20", frame_rate="30/1")
    )
    _install_fake_process(monkeypatch, process)

    report = FFprobeTimingProbe(executable=Path("ffprobe")).probe(video_path)

    assert report.status == "unknown"
    assert "too coarse" in report.reason


def test_probe_detects_runtime_synthetic_video_with_local_ffprobe(
    synthetic_video_path: Path,
) -> None:
    executable = ffprobe_timing.shutil.which("ffprobe")
    if executable is None:
        pytest.fail("ffprobe is required for the real synthetic-video probe test")

    report = FFprobeTimingProbe(executable=Path(executable)).probe(
        synthetic_video_path
    )

    assert report.status == "cfr"
    assert report.frame_count == 5
    assert report.fps_measured == pytest.approx(10.0, abs=1e-9)
