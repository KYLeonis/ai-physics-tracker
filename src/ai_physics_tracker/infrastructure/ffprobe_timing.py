"""基础设施层 FFprobe 时序适配器：只读扫描视频的完整逐帧时间戳。"""

from __future__ import annotations

import json
import logging
import math
import shutil
import subprocess
import time
from fractions import Fraction
from pathlib import Path
from threading import Event
from typing import cast

from ai_physics_tracker.application.video_timing import TimingReport

logger = logging.getLogger(__name__)

_COMMUNICATE_SLICE_S = 0.1
_PROCESS_CLEANUP_TIMEOUT_S = 1.0
_MIN_TIMESTAMP_COUNT = 2
_MAX_QUANTIZATION_ERROR_TICKS = Fraction(1, 1)
_MIN_RESOLVABLE_FRAME_INTERVAL_TICKS = Fraction(1, 1)


class FFprobeTimingProbe:
    """通过 FFprobe 的完整逐帧输出判断视频是否为 CFR。

    FFprobe 只读取媒体，不会改写视频。若工具不可用、探测被取消、进程
    超时，或输出无法完整解析，均返回 ``unknown``，不会猜测为 CFR。
    """

    def __init__(self, executable: Path | None = None, timeout_s: float = 120) -> None:
        if not math.isfinite(timeout_s) or timeout_s <= 0:
            raise ValueError("timeout_s must be a finite positive value")
        self._executable = executable
        self._timeout_s = timeout_s

    def probe(self, path: Path, cancel: Event | None = None) -> TimingReport:
        """扫描 ``path`` 的全部视频帧并返回时序结论。"""

        if cancel is not None and cancel.is_set():
            return self._unknown("probe cancelled")
        if not path.is_file():
            return self._unknown(f"video file not found: {path}")

        executable = self._resolve_executable()
        if executable is None:
            return self._unknown("ffprobe executable was not found")

        command = [
            str(executable),
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_frames",
            "-show_streams",
            "-show_entries",
            "stream=time_base,r_frame_rate:frame=best_effort_timestamp",
            "-of",
            "json",
            str(path),
        ]

        try:
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                shell=False,
            )
        except (OSError, ValueError) as error:
            logger.warning("could not start ffprobe path=%s: %s", path, error)
            return self._unknown(f"could not start ffprobe: {error}")

        try:
            stdout, stderr, returncode, terminal_reason = self._communicate(
                process, cancel
            )
        finally:
            # 正常 communicate 已经回收进程；异常路径仍必须清理子进程。
            if process.poll() is None:
                self._terminate_process(process)

        if terminal_reason is not None:
            return self._unknown(terminal_reason)
        if cancel is not None and cancel.is_set():
            return self._unknown("probe cancelled")
        if returncode != 0:
            detail = self._stderr_detail(stderr)
            suffix = f": {detail}" if detail else ""
            return self._unknown(
                f"ffprobe exited with status {returncode}{suffix}"
            )
        if returncode is None:
            return self._unknown("ffprobe did not report an exit status")
        if stderr:
            detail = self._stderr_detail(stderr)
            suffix = f": {detail}" if detail else ""
            return self._unknown(f"ffprobe wrote to stderr{suffix}")

        return self._classify_output(stdout)

    def _resolve_executable(self) -> Path | None:
        if self._executable is not None:
            return self._executable
        resolved = shutil.which("ffprobe")
        return Path(resolved) if resolved is not None else None

    def _communicate(
        self,
        process: subprocess.Popen[str],
        cancel: Event | None,
    ) -> tuple[str, str, int | None, str | None]:
        """以小步 communicate 轮询，令取消和总超时都能及时生效。"""

        deadline = time.monotonic() + self._timeout_s
        while True:
            if cancel is not None and cancel.is_set():
                self._terminate_process(process)
                return "", "", process.poll(), "probe cancelled"

            remaining_s = deadline - time.monotonic()
            if remaining_s <= 0:
                self._terminate_process(process)
                return "", "", process.poll(), "ffprobe timed out"

            try:
                stdout, stderr = process.communicate(
                    timeout=min(_COMMUNICATE_SLICE_S, remaining_s)
                )
            except subprocess.TimeoutExpired:
                continue
            except (OSError, ValueError) as error:
                self._terminate_process(process)
                return "", "", process.poll(), f"ffprobe communication failed: {error}"

            return (
                self._coerce_output(stdout),
                self._coerce_output(stderr),
                process.poll(),
                None,
            )

    def _terminate_process(self, process: subprocess.Popen[str]) -> None:
        """杀死并等待 FFprobe，避免取消或超时留下孤儿进程。"""

        if process.poll() is not None:
            return
        try:
            process.kill()
        except (OSError, ProcessLookupError):
            # 进程可能恰好在 poll 与 kill 之间退出，后续 wait 仍负责回收。
            pass

        try:
            process.communicate(timeout=_PROCESS_CLEANUP_TIMEOUT_S)
        except subprocess.TimeoutExpired:
            logger.warning("ffprobe did not finish after kill")
        except (OSError, ValueError):
            pass

        try:
            process.wait(timeout=_PROCESS_CLEANUP_TIMEOUT_S)
        except subprocess.TimeoutExpired:
            logger.error("ffprobe process could not be reaped after kill")
        except (OSError, ChildProcessError):
            pass

    def _classify_output(self, stdout: str) -> TimingReport:
        try:
            payload = json.loads(stdout)
        except (json.JSONDecodeError, TypeError):
            return self._unknown("ffprobe returned invalid JSON")
        if not isinstance(payload, dict):
            return self._unknown("ffprobe JSON root is not an object")

        stream = self._first_object(payload.get("streams"))
        if stream is None:
            return self._unknown("ffprobe returned no stream metadata")
        time_base = self._parse_positive_fraction(stream.get("time_base"))
        if time_base is None:
            return self._unknown("ffprobe returned missing or invalid time_base")
        frame_rate = self._parse_positive_fraction(stream.get("r_frame_rate"))
        if frame_rate is None:
            return self._unknown("ffprobe returned missing or invalid r_frame_rate")

        frames = payload.get("frames")
        if not isinstance(frames, list):
            return self._unknown("ffprobe returned no frame list")
        timestamps: list[int] = []
        for frame_index, frame in enumerate(frames):
            if not isinstance(frame, dict):
                return self._unknown(
                    f"invalid frame record at index {frame_index}",
                    frame_count=len(timestamps),
                )
            if "best_effort_timestamp" not in frame:
                return self._unknown(
                    f"missing frame timestamp at index {frame_index}",
                    frame_count=len(timestamps),
                )
            timestamp = self._parse_timestamp_tick(frame["best_effort_timestamp"])
            if timestamp is None:
                return self._unknown(
                    f"invalid frame timestamp at index {frame_index}",
                    frame_count=len(timestamps),
                )
            timestamps.append(timestamp)

        if len(timestamps) < _MIN_TIMESTAMP_COUNT:
            return self._unknown(
                "insufficient frame timestamps: need at least two",
                frame_count=len(timestamps),
            )
        return self._classify_timestamps(timestamps, time_base, frame_rate)

    def _classify_timestamps(
        self,
        timestamps: list[int],
        time_base: Fraction,
        frame_rate: Fraction,
    ) -> TimingReport:
        deltas = [right - left for left, right in zip(timestamps, timestamps[1:])]
        if any(delta <= 0 for delta in deltas):
            return TimingReport(
                status="vfr_suspected",
                reason="frame timestamps are not strictly increasing",
                frame_count=len(timestamps),
            )

        expected_step_ticks = Fraction(1, 1) / (frame_rate * time_base)
        if expected_step_ticks < _MIN_RESOLVABLE_FRAME_INTERVAL_TICKS:
            return self._unknown(
                "time_base resolution is too coarse to verify frame timing",
                frame_count=len(timestamps),
            )

        interval_residuals = [
            abs(Fraction(delta, 1) - expected_step_ticks) for delta in deltas
        ]
        if any(
            residual > _MAX_QUANTIZATION_ERROR_TICKS
            for residual in interval_residuals
        ):
            return TimingReport(
                status="vfr_suspected",
                reason="frame timestamp intervals are not consistent with CFR",
                frame_count=len(timestamps),
            )

        origin = timestamps[0]
        cumulative_residuals = [
            abs(
                Fraction(timestamp - origin, 1)
                - (frame_index * expected_step_ticks)
            )
            for frame_index, timestamp in enumerate(timestamps[1:], start=1)
        ]
        if any(
            residual > _MAX_QUANTIZATION_ERROR_TICKS
            for residual in cumulative_residuals
        ):
            return TimingReport(
                status="vfr_suspected",
                reason="frame timestamp drift is not consistent with CFR",
                frame_count=len(timestamps),
            )

        elapsed_ticks = timestamps[-1] - origin
        elapsed_s = Fraction(elapsed_ticks, 1) * time_base
        fps_measured = (
            float(Fraction(len(timestamps) - 1, 1) / elapsed_s)
            if elapsed_s > 0
            else None
        )
        return TimingReport(
            status="cfr",
            reason="all frame timestamps are consistent with a constant frame rate",
            frame_count=len(timestamps),
            fps_measured=fps_measured,
        )

    @staticmethod
    def _first_object(value: object) -> dict[str, object] | None:
        if not isinstance(value, list) or not value:
            return None
        first = value[0]
        return cast(dict[str, object], first) if isinstance(first, dict) else None

    @staticmethod
    def _parse_positive_fraction(value: object) -> Fraction | None:
        if isinstance(value, bool) or not isinstance(value, (int, float, str)):
            return None
        try:
            if isinstance(value, float):
                if not math.isfinite(value):
                    return None
                parsed = Fraction(str(value))
            else:
                parsed = Fraction(value)
        except (TypeError, ValueError, ZeroDivisionError, OverflowError):
            return None
        return parsed if parsed > 0 else None

    @staticmethod
    def _parse_timestamp_tick(value: object) -> int | None:
        if isinstance(value, bool):
            return None
        if isinstance(value, int):
            return value
        if isinstance(value, str):
            try:
                return int(value.strip(), 10)
            except ValueError:
                return None
        return None

    @staticmethod
    def _coerce_output(value: str | bytes | None) -> str:
        if value is None:
            return ""
        if isinstance(value, bytes):
            return value.decode("utf-8", errors="replace")
        return value

    @staticmethod
    def _stderr_detail(stderr: str) -> str:
        detail = " ".join(stderr.split())
        return detail[:240]

    @staticmethod
    def _unknown(reason: str, frame_count: int = 0) -> TimingReport:
        return TimingReport(
            status="unknown",
            reason=reason,
            frame_count=frame_count,
        )


__all__ = ["FFprobeTimingProbe"]
