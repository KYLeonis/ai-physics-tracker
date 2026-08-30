"""基础设施层 FFprobe 时序适配器：安全扫描完整 packet 或逐帧时间戳。"""

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

from ai_physics_tracker.application.video import TimingStatus
from ai_physics_tracker.application.video_timing import (
    MAX_APPROXIMATION_ERROR_S,
    MAX_APPROXIMATION_FRAME_FRACTION,
    TimingReport,
)

logger = logging.getLogger(__name__)

_COMMUNICATE_SLICE_S = 0.1
_PROCESS_CLEANUP_TIMEOUT_S = 1.0
_MIN_TIMESTAMP_COUNT = 2
_MAX_QUANTIZATION_ERROR_TICKS = Fraction(1, 1)
_MIN_RESOLVABLE_FRAME_INTERVAL_TICKS = Fraction(1, 1)
_NEAR_CFR_MAX_ERROR_S = Fraction(str(MAX_APPROXIMATION_ERROR_S))
_NEAR_CFR_MAX_FRAME_FRACTION = Fraction(str(MAX_APPROXIMATION_FRAME_FRACTION))
_PACKET_CONTAINER_SUFFIXES = frozenset({".mp4", ".mov"})
_PACKET_CODECS = frozenset({"h264", "hevc"})
_UNPARSEABLE_COUNT = object()


class FFprobeTimingProbe:
    """通过 FFprobe 判断视频的完整时序。

    对 MP4/MOV 的 H.264/HEVC，先读取完整 packet PTS；packet 元数据不满足
    全部安全门禁时才回退到完整逐帧输出。工具错误、标准错误、取消、超时和
    完整逐帧输出解析失败都返回 ``unknown``，不会把失败静默当作可用时序。
    """

    def __init__(self, executable: Path | None = None, timeout_s: float = 120) -> None:
        if not math.isfinite(timeout_s) or timeout_s <= 0:
            raise ValueError("timeout_s must be a finite positive value")
        self._executable = executable
        self._timeout_s = timeout_s

    def probe(self, path: Path, cancel: Event | None = None) -> TimingReport:
        """扫描 ``path`` 的完整时间戳并返回时序结论。"""

        if cancel is not None and cancel.is_set():
            return self._unknown("probe cancelled")
        if not path.is_file():
            return self._unknown(f"video file not found: {path}")

        executable = self._resolve_executable()
        if executable is None:
            return self._unknown("ffprobe executable was not found")
        deadline = time.monotonic() + self._timeout_s

        if path.suffix.lower() in _PACKET_CONTAINER_SUFFIXES:
            packet_result = self._run_ffprobe(
                self._packet_command(executable, path), cancel, deadline
            )
            packet_failure = self._result_failure(packet_result)
            if packet_failure is not None:
                # packet 探测若自身失败，不能用较慢路径掩盖工具或媒体错误。
                return self._unknown(packet_failure)

            packet_report = self._classify_packet_output(packet_result[0])
            if packet_report is not None:
                if cancel is not None and cancel.is_set():
                    return self._unknown("probe cancelled")
                return packet_report
            logger.debug(
                "packet PTS fast path is unavailable; falling back to frames path=%s",
                path,
            )
            if cancel is not None and cancel.is_set():
                return self._unknown("probe cancelled")

        return self._probe_full_frames(executable, path, cancel, deadline)

    def _probe_full_frames(
        self,
        executable: Path,
        path: Path,
        cancel: Event | None,
        deadline: float | None = None,
    ) -> TimingReport:
        result = self._run_ffprobe(
            self._frame_command(executable, path), cancel, deadline
        )
        failure = self._result_failure(result)
        if failure is not None:
            return self._unknown(failure)
        return self._classify_output(result[0])

    @staticmethod
    def _packet_command(executable: Path, path: Path) -> list[str]:
        return [
            str(executable),
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_packets",
            "-show_streams",
            "-show_format",
            "-count_packets",
            "-show_entries",
            (
                "stream=codec_name,time_base,r_frame_rate,avg_frame_rate,nb_frames,"
                "nb_read_packets,field_order:"
                "packet=pts,duration,flags:format=format_name"
            ),
            "-of",
            "json",
            str(path),
        ]

    @staticmethod
    def _frame_command(executable: Path, path: Path) -> list[str]:
        return [
            str(executable),
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-count_frames",
            "-show_frames",
            "-show_streams",
            "-show_entries",
            (
                "stream=time_base,r_frame_rate,avg_frame_rate,nb_frames,nb_read_frames:"
                "frame=best_effort_timestamp"
            ),
            "-of",
            "json",
            str(path),
        ]

    def _resolve_executable(self) -> Path | None:
        if self._executable is not None:
            return self._executable
        resolved = shutil.which("ffprobe")
        return Path(resolved) if resolved is not None else None

    def _run_ffprobe(
        self,
        command: list[str],
        cancel: Event | None,
        deadline: float | None = None,
    ) -> tuple[str, str, int | None, str | None]:
        if cancel is not None and cancel.is_set():
            return "", "", None, "probe cancelled"
        if deadline is not None and time.monotonic() >= deadline:
            return "", "", None, "ffprobe timed out"
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
            logger.warning("could not start ffprobe command=%s: %s", command, error)
            return "", "", None, f"could not start ffprobe: {error}"

        try:
            return self._communicate(process, cancel, deadline)
        finally:
            # 正常 communicate 已经回收进程；异常路径仍必须清理子进程。
            if process.poll() is None:
                self._terminate_process(process)

    @staticmethod
    def _result_failure(
        result: tuple[str, str, int | None, str | None],
    ) -> str | None:
        stdout, stderr, returncode, terminal_reason = result
        del stdout
        if terminal_reason is not None:
            return terminal_reason
        if returncode != 0:
            detail = FFprobeTimingProbe._stderr_detail(stderr)
            suffix = f": {detail}" if detail else ""
            return f"ffprobe exited with status {returncode}{suffix}"
        if returncode is None:
            return "ffprobe did not report an exit status"
        if stderr:
            detail = FFprobeTimingProbe._stderr_detail(stderr)
            suffix = f": {detail}" if detail else ""
            return f"ffprobe wrote to stderr{suffix}"
        return None

    def _communicate(
        self,
        process: subprocess.Popen[str],
        cancel: Event | None,
        deadline: float | None = None,
    ) -> tuple[str, str, int | None, str | None]:
        """以小步 communicate 轮询，令取消和总超时都能及时生效。"""

        if deadline is None:
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

    def _classify_packet_output(self, stdout: str) -> TimingReport | None:
        """解析 packet 输出；``None`` 表示可安全回退而非探测进程失败。"""

        try:
            payload = json.loads(stdout)
        except (json.JSONDecodeError, TypeError):
            return None
        if not isinstance(payload, dict):
            return None

        stream = self._first_object(payload.get("streams"))
        if stream is None:
            return None
        codec_name = stream.get("codec_name")
        if not isinstance(codec_name, str) or codec_name.lower() not in _PACKET_CODECS:
            return None

        format_metadata = payload.get("format")
        if not self._is_mp4_mov_format(format_metadata):
            return None
        field_order = stream.get("field_order")
        if field_order is not None and not self._is_safe_field_order(field_order):
            return None

        time_base = self._parse_positive_fraction(stream.get("time_base"))
        frame_rate = self._parse_positive_fraction(stream.get("r_frame_rate"))
        frame_count = self._parse_frame_count(stream.get("nb_frames"))
        if time_base is None or frame_rate is None or frame_count is None:
            return None

        packets = payload.get("packets")
        if not isinstance(packets, list) or frame_count < _MIN_TIMESTAMP_COUNT:
            return None
        declared_packet_count = self._parse_optional_frame_count(
            stream, "nb_read_packets"
        )
        if declared_packet_count is _UNPARSEABLE_COUNT or (
            declared_packet_count is not None and declared_packet_count != len(packets)
        ):
            return None
        packet_timestamps: list[int] = []
        for packet in packets:
            if not isinstance(packet, dict):
                return None
            timestamp = self._parse_timestamp_tick(packet.get("pts"))
            duration = self._parse_positive_tick(packet.get("duration"))
            flags = packet.get("flags")
            if (
                timestamp is None
                or duration is None
                or not isinstance(flags, str)
                or self._has_unsafe_packet_flag(flags)
            ):
                return None
            packet_timestamps.append(timestamp)

        if len(packet_timestamps) != frame_count:
            return None
        if len(set(packet_timestamps)) != len(packet_timestamps):
            return None

        timestamps = sorted(packet_timestamps)
        return self._classify_timestamps(
            timestamps,
            time_base,
            frame_rate,
            self._parse_positive_fraction(stream.get("avg_frame_rate")),
        )

    @staticmethod
    def _is_mp4_mov_format(value: object) -> bool:
        if not isinstance(value, dict):
            return False
        format_name = value.get("format_name")
        if not isinstance(format_name, str):
            return False
        names = {item.strip().lower() for item in format_name.split(",")}
        return bool(names & {"mp4", "mov"})

    @staticmethod
    def _is_safe_field_order(value: object) -> bool:
        if not isinstance(value, str):
            return False
        normalized = value.strip().lower()
        return normalized in {"", "unknown", "n/a", "progressive"}

    @staticmethod
    def _has_unsafe_packet_flag(flags: str) -> bool:
        # FFprobe 6/8 的 flags 分别常见为两字符/三字符；未知编码不能冒险放行。
        normalized = flags.upper()
        if len(normalized) not in {2, 3}:
            return True
        if normalized[0] not in {"K", "_"}:
            return True
        # C/D 分别表示 corrupt/discard；其余位置目前必须是无标志占位符。
        return any(character != "_" for character in normalized[1:])

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

        declared_count, count_metadata_present = self._full_frame_count(stream)
        if declared_count is not None and declared_count != len(timestamps):
            return self._unknown(
                "ffprobe frame count does not match stream metadata",
                frame_count=len(timestamps),
            )
        if count_metadata_present and declared_count is None:
            return self._unknown("ffprobe returned missing or invalid nb_frames")

        if len(timestamps) < _MIN_TIMESTAMP_COUNT:
            return self._unknown(
                "insufficient frame timestamps: need at least two",
                frame_count=len(timestamps),
            )
        return self._classify_timestamps(
            timestamps,
            time_base,
            frame_rate,
            self._parse_positive_fraction(stream.get("avg_frame_rate")),
            allow_near_cfr=declared_count is not None,
        )

    def _classify_timestamps(
        self,
        timestamps: list[int],
        time_base: Fraction,
        frame_rate: Fraction,
        avg_frame_rate: Fraction | None = None,
        allow_near_cfr: bool = True,
    ) -> TimingReport:
        if len(timestamps) < _MIN_TIMESTAMP_COUNT:
            return self._unknown(
                "insufficient frame timestamps: need at least two",
                frame_count=len(timestamps),
            )
        deltas = [right - left for left, right in zip(timestamps, timestamps[1:])]
        if any(delta <= 0 for delta in deltas):
            return TimingReport(
                status="vfr_suspected",
                reason="frame timestamps are not strictly increasing",
                frame_count=len(timestamps),
            )

        strict_step_ticks = Fraction(1, 1) / (frame_rate * time_base)
        strict_errors = self._timing_errors(timestamps, strict_step_ticks, time_base)
        strict_deltas_are_quantized = self._strict_deltas_are_quantized(
            deltas, strict_step_ticks
        )
        if (
            strict_step_ticks >= _MIN_RESOLVABLE_FRAME_INTERVAL_TICKS
            and strict_deltas_are_quantized
        ):
            strict_grid_s, strict_interval_s = strict_errors
            if (
                strict_grid_s <= _MAX_QUANTIZATION_ERROR_TICKS * time_base
                and strict_interval_s <= _MAX_QUANTIZATION_ERROR_TICKS * time_base
            ):
                return self._timing_report(
                    status="cfr",
                    reason="all frame timestamps are consistent with a constant frame rate",
                    timestamps=timestamps,
                    fps_reference=frame_rate,
                    time_base=time_base,
                    errors=strict_errors,
                )

        if allow_near_cfr and avg_frame_rate is not None:
            near_step_ticks = Fraction(1, 1) / (avg_frame_rate * time_base)
            if near_step_ticks >= _MIN_RESOLVABLE_FRAME_INTERVAL_TICKS:
                near_errors = self._timing_errors(
                    timestamps, near_step_ticks, time_base
                )
                tolerance_s = min(
                    _NEAR_CFR_MAX_ERROR_S,
                    _NEAR_CFR_MAX_FRAME_FRACTION / avg_frame_rate,
                )
                if near_errors[0] <= tolerance_s and near_errors[1] <= tolerance_s:
                    return self._timing_report(
                        status="near_cfr",
                        reason=(
                            "frame timestamps are within the bounded average-frame-rate "
                            "approximation"
                        ),
                        timestamps=timestamps,
                        fps_reference=avg_frame_rate,
                        time_base=time_base,
                        errors=near_errors,
                    )

        if strict_step_ticks < _MIN_RESOLVABLE_FRAME_INTERVAL_TICKS:
            return self._unknown(
                "time_base resolution is too coarse to verify frame timing",
                frame_count=len(timestamps),
            )
        if strict_errors[1] > _MAX_QUANTIZATION_ERROR_TICKS * time_base:
            reason = "frame timestamp intervals are not consistent with CFR"
        else:
            reason = "frame timestamp drift is not consistent with CFR"
        return TimingReport(
            status="vfr_suspected",
            reason=reason,
            frame_count=len(timestamps),
        )

    @staticmethod
    def _timing_errors(
        timestamps: list[int],
        expected_step_ticks: Fraction,
        time_base: Fraction,
    ) -> tuple[Fraction, Fraction]:
        deltas = [right - left for left, right in zip(timestamps, timestamps[1:])]
        interval_error_ticks = max(
            (abs(Fraction(delta, 1) - expected_step_ticks) for delta in deltas),
            default=Fraction(0, 1),
        )
        origin = timestamps[0]
        grid_error_ticks = max(
            (
                abs(
                    Fraction(timestamp - origin, 1)
                    - (frame_index * expected_step_ticks)
                )
                for frame_index, timestamp in enumerate(timestamps[1:], start=1)
            ),
            default=Fraction(0, 1),
        )
        return grid_error_ticks * time_base, interval_error_ticks * time_base

    @staticmethod
    def _strict_deltas_are_quantized(
        deltas: list[int], expected_step_ticks: Fraction
    ) -> bool:
        lower_ticks = expected_step_ticks.numerator // expected_step_ticks.denominator
        upper_ticks = -(
            -expected_step_ticks.numerator // expected_step_ticks.denominator
        )
        return all(lower_ticks <= delta <= upper_ticks for delta in deltas)

    @staticmethod
    def _timing_report(
        *,
        status: TimingStatus,
        reason: str,
        timestamps: list[int],
        fps_reference: Fraction,
        time_base: Fraction,
        errors: tuple[Fraction, Fraction],
    ) -> TimingReport:
        origin = timestamps[0]
        elapsed_s = Fraction(timestamps[-1] - origin, 1) * time_base
        fps_measured = (
            float(Fraction(len(timestamps) - 1, 1) / elapsed_s)
            if elapsed_s > 0
            else None
        )
        return TimingReport(
            status=status,
            reason=reason,
            frame_count=len(timestamps),
            fps_measured=fps_measured,
            fps_reference=float(fps_reference),
            max_grid_error_s=float(errors[0]),
            max_interval_error_s=float(errors[1]),
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
    def _parse_frame_count(value: object) -> int | None:
        if isinstance(value, bool):
            return None
        if isinstance(value, int):
            return value if value >= 0 else None
        if isinstance(value, str):
            try:
                parsed = int(value.strip(), 10)
            except ValueError:
                return None
            return parsed if parsed >= 0 else None
        return None

    @classmethod
    def _parse_optional_frame_count(
        cls,
        stream: dict[str, object],
        field_name: str,
    ) -> int | None | object:
        if field_name not in stream:
            return None
        parsed = cls._parse_frame_count(stream.get(field_name))
        return parsed if parsed is not None else _UNPARSEABLE_COUNT

    @classmethod
    def _full_frame_count(
        cls,
        stream: dict[str, object],
    ) -> tuple[int | None, bool]:
        """取得逐帧输出的独立计数；``nb_read_frames`` 优先于容器声明值。"""

        values: list[int] = []
        metadata_present = False
        for field_name in ("nb_read_frames", "nb_frames"):
            parsed = cls._parse_optional_frame_count(stream, field_name)
            if field_name in stream:
                metadata_present = True
            if parsed is _UNPARSEABLE_COUNT:
                continue
            if parsed is not None:
                values.append(parsed)
        if len(set(values)) > 1:
            return None, True
        return (values[0] if values else None), metadata_present

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

    @classmethod
    def _parse_positive_tick(cls, value: object) -> int | None:
        parsed = cls._parse_timestamp_tick(value)
        return parsed if parsed is not None and parsed > 0 else None

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
