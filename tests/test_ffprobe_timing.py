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
    avg_frame_rate: str | None = None,
    nb_frames: int | str | None = None,
    side_data: bool = False,
) -> str:
    frames = []
    for timestamp in timestamps:
        frame = {"best_effort_timestamp": timestamp}
        if side_data:
            frame["side_data_list"] = [{"side_data_type": "H.264 metadata"}]
        frames.append(frame)
    stream: dict[str, object] = {
        "time_base": time_base,
        "r_frame_rate": frame_rate,
    }
    if avg_frame_rate is not None:
        stream["avg_frame_rate"] = avg_frame_rate
    if nb_frames is not None:
        stream["nb_frames"] = nb_frames
    return json.dumps({"frames": frames, "streams": [stream]})


def _packet_json_output(
    timestamps: Sequence[object],
    *,
    time_base: str = "1/10",
    frame_rate: str = "10/1",
    avg_frame_rate: str | None = None,
    codec_name: str = "h264",
    duration: object = "1",
    flags: object = "__",
    format_name: str = "mov,mp4,m4a,3gp,3g2,mj2",
    field_order: str | None = None,
) -> str:
    packets = [
        {"pts": timestamp, "duration": duration, "flags": flags}
        for timestamp in timestamps
    ]
    stream: dict[str, object] = {
        "codec_name": codec_name,
        "time_base": time_base,
        "r_frame_rate": frame_rate,
        "nb_frames": str(len(packets)),
    }
    if avg_frame_rate is not None:
        stream["avg_frame_rate"] = avg_frame_rate
    if field_order is not None:
        stream["field_order"] = field_order
    return json.dumps(
        {
            "packets": packets,
            "streams": [stream],
            "format": {"format_name": format_name},
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


def _install_fake_processes(
    monkeypatch: pytest.MonkeyPatch,
    processes: list[_CompletedProcess | _HangingProcess],
) -> list[list[str]]:
    commands: list[list[str]] = []

    def fake_popen(
        command: list[str], **kwargs: object
    ) -> _CompletedProcess | _HangingProcess:
        assert kwargs["shell"] is False
        commands.append(command)
        return processes.pop(0)

    monkeypatch.setattr(ffprobe_timing.subprocess, "Popen", fake_popen)
    return commands


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


def test_probe_uses_complete_packet_pts_fast_path_and_sorts_presentation_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    video_path = tmp_path / "video.mp4"
    video_path.touch()
    commands = _install_fake_processes(
        monkeypatch,
        [_CompletedProcess(_packet_json_output([3, 1, 2, 0]))],
    )

    report = FFprobeTimingProbe(executable=Path("ffprobe")).probe(video_path)

    assert report.status == "cfr"
    assert report.frame_count == 4
    assert report.fps_reference == pytest.approx(10.0, abs=1e-9)
    assert report.max_grid_error_s == pytest.approx(0.0, abs=1e-12)
    assert report.max_interval_error_s == pytest.approx(0.0, abs=1e-12)
    assert len(commands) == 1
    assert "-show_packets" in commands[0]
    assert "-show_frames" not in commands[0]


@pytest.mark.parametrize("guard", [
    "missing_format",
    "unsupported_codec",
    "missing_pts",
    "invalid_duration",
    "missing_flags",
    "unsafe_flags",
    "unknown_flags",
    "interlaced",
    "count_mismatch",
    "duplicate_pts",
])
def test_probe_falls_back_to_full_frames_for_ambiguous_packet_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    guard: str,
) -> None:
    video_path = tmp_path / "video.mp4"
    video_path.touch()
    packet_payload = json.loads(_packet_json_output([0, 1, 2, 3]))
    stream = packet_payload["streams"][0]
    packets = packet_payload["packets"]
    if guard == "missing_format":
        del packet_payload["format"]
    elif guard == "unsupported_codec":
        stream["codec_name"] = "mpeg4"
    elif guard == "missing_pts":
        del packets[1]["pts"]
    elif guard == "invalid_duration":
        packets[1]["duration"] = "N/A"
    elif guard == "missing_flags":
        del packets[1]["flags"]
    elif guard == "unsafe_flags":
        packets[1]["flags"] = "C_"
    elif guard == "unknown_flags":
        packets[1]["flags"] = "garbage"
    elif guard == "interlaced":
        stream["field_order"] = "tt"
    elif guard == "count_mismatch":
        stream["nb_frames"] = "5"
    elif guard == "duplicate_pts":
        packets[1]["pts"] = packets[0]["pts"]

    commands = _install_fake_processes(
        monkeypatch,
        [
            _CompletedProcess(json.dumps(packet_payload)),
            _CompletedProcess(_json_output([0, 1, 2, 3])),
        ],
    )

    report = FFprobeTimingProbe(executable=Path("ffprobe")).probe(video_path)

    assert report.status == "cfr"
    assert report.frame_count == 4
    assert len(commands) == 2
    assert "-show_packets" in commands[0]
    assert "-show_frames" in commands[1]
    assert any("avg_frame_rate" in item for item in commands[1])


def test_probe_does_not_hide_packet_probe_stderr_with_frame_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    video_path = tmp_path / "video.mp4"
    video_path.touch()
    commands = _install_fake_processes(
        monkeypatch,
        [_CompletedProcess(_packet_json_output([0, 1]), "packet warning", 0)],
    )

    report = FFprobeTimingProbe(executable=Path("ffprobe")).probe(video_path)

    assert report.status == "unknown"
    assert "stderr" in report.reason
    assert len(commands) == 1


def test_probe_reports_near_cfr_with_full_frame_count_and_error_bounds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    video_path = tmp_path / "video.fake"
    video_path.touch()
    timestamps = [0, 10033, 20067, 30100]
    process = _CompletedProcess(
        _json_output(
            timestamps,
            time_base="1/100000",
            frame_rate="10/1",
            avg_frame_rate="10/1",
            nb_frames=len(timestamps),
        )
    )
    _install_fake_process(monkeypatch, process)

    report = FFprobeTimingProbe(executable=Path("ffprobe")).probe(video_path)

    assert report.status == "near_cfr"
    assert report.frame_count == len(timestamps)
    assert report.fps_reference == pytest.approx(10.0, abs=1e-9)
    assert report.max_grid_error_s == pytest.approx(0.001, abs=1e-12)
    assert report.max_interval_error_s == pytest.approx(0.00034, abs=1e-12)


def test_probe_rejects_near_cfr_when_grid_error_exceeds_absolute_bound(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    video_path = tmp_path / "video.fake"
    video_path.touch()
    timestamps = [0, 10033, 20067, 30101]
    process = _CompletedProcess(
        _json_output(
            timestamps,
            time_base="1/100000",
            frame_rate="10/1",
            avg_frame_rate="10/1",
            nb_frames=len(timestamps),
        )
    )
    _install_fake_process(monkeypatch, process)

    report = FFprobeTimingProbe(executable=Path("ffprobe")).probe(video_path)

    assert report.status == "vfr_suspected"


def test_probe_uses_relative_near_cfr_bound_at_high_frame_rate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    video_path = tmp_path / "video.fake"
    video_path.touch()
    # 30 FPS 的 1% 帧周期为 1/90000*30 tick，边界误差取 30 tick。
    timestamps = [0, 3000, 6030]
    process = _CompletedProcess(
        _json_output(
            timestamps,
            time_base="1/90000",
            frame_rate="30/1",
            avg_frame_rate="30/1",
            nb_frames=len(timestamps),
        )
    )
    _install_fake_process(monkeypatch, process)

    report = FFprobeTimingProbe(executable=Path("ffprobe")).probe(video_path)

    assert report.status == "near_cfr"
    assert report.max_grid_error_s == pytest.approx(30 / 90000, abs=1e-12)
    assert report.max_interval_error_s == pytest.approx(30 / 90000, abs=1e-12)


def test_probe_does_not_accept_dropped_frame_with_one_tick_strict_tolerance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    video_path = tmp_path / "video.fake"
    video_path.touch()
    process = _CompletedProcess(
        _json_output([0, 1, 3, 4], nb_frames=4)
    )
    _install_fake_process(monkeypatch, process)

    report = FFprobeTimingProbe(executable=Path("ffprobe")).probe(video_path)

    assert report.status == "vfr_suspected"
