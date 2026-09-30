"""领域层：student-default-v1 四点角度与共同 QC，保留完整源帧。"""

from dataclasses import dataclass
from math import atan2, cos, hypot, isfinite, sin
from statistics import median

from ai_physics_tracker.domain.pendulum import PendulumGeometry, QCExclusion, ROLE_ORDER
from ai_physics_tracker.domain.types import canonical_json_digest

CORE_VERSION = "pendulum-reconstruction-1.0.0"
STUDENT_PROFILE_SHA256 = "6b5b28065eebd0f0a26d42b6d279b4d4294af89e1a9bd5da5badaf9101e48d51"
LEGACY_PROFILE_SHA256 = "77ed02f10d2a00fc0cae5fd1ddd5fbe4a3e46f1fed2ff07ed7e8ad4be951ce51"
RADIUS_RELATIVE_TOLERANCE = 0.1
BODY_RELATIVE_TOLERANCE = 0.2


def reconstruction_config() -> dict[str, object]:
    """仅展开本核心实际消费的已冻结政策；不解释 JSON 公式字符串。"""
    return {
        "profile_id": "student-default-v1", "profile_version": "1.0.0",
        "profile_sha256": STUDENT_PROFILE_SHA256,
        "formula_profile_sha256": LEGACY_PROFILE_SHA256,
        "core_version": CORE_VERSION,
        "radius_relative_tolerance": RADIUS_RELATIVE_TOLERANCE,
        "body_relative_tolerance": BODY_RELATIVE_TOLERANCE,
        "ai_weight_floor": 0.05, "manual_weight": 1.0,
        "provenance": {
            "qc": ["policy-student-v1", "source-data_io"],
            "weighting": ["policy-student-v1", "source-fitting"],
            "theta_formula": ["source-data_io"],
        },
    }


@dataclass(frozen=True)
class AdoptedLandmark:
    """当前采用点的原始坐标与来源；confidence 不承担分析权重语义。"""

    pixel_x: float
    pixel_y: float
    source: str
    confidence: float | None

    def __post_init__(self) -> None:
        if not isinstance(self.source, str) or not self.source.strip():
            raise ValueError("adopted landmark source must not be blank")
        if any(type(value) not in (int, float) for value in (self.pixel_x, self.pixel_y)):
            raise ValueError("landmark coordinates must be numeric")
        if self.confidence is not None and type(self.confidence) not in (int, float):
            raise ValueError("landmark confidence must be numeric or null")
        if self.source == "manual" and self.confidence is not None:
            raise ValueError("manual landmark confidence must be null")
        # 请求也按 float64 数值语义归一，不只依赖应用 snapshot 的 JSON reader。
        object.__setattr__(self, "pixel_x", float(self.pixel_x))
        object.__setattr__(self, "pixel_y", float(self.pixel_y))
        if self.confidence is not None:
            object.__setattr__(self, "confidence", float(self.confidence))


@dataclass(frozen=True)
class MeasurementFrame:
    """一源帧，points 按 ROLE_ORDER；None 表示该角色缺测。"""

    frame_index: int
    time_absolute_s: float
    points: tuple[AdoptedLandmark | None, ...]

    def __post_init__(self) -> None:
        if type(self.frame_index) is not int or self.frame_index < 0:
            raise ValueError("source frame_index must be a non-negative integer")
        if len(self.points) != len(ROLE_ORDER):
            raise ValueError("measurement frame requires four ordered roles")
        if not isinstance(self.points, tuple):
            raise ValueError("measurement points must be an immutable tuple")
        if type(self.time_absolute_s) not in (int, float) or not isfinite(self.time_absolute_s):
            raise ValueError("source timestamp must be finite")
        object.__setattr__(self, "time_absolute_s", float(self.time_absolute_s))


@dataclass(frozen=True)
class ReconstructionInput:
    """完整源视频事实与当前测量摘要；无 session、widget 或文件引用。"""

    measurement_digest: str
    frames: tuple[MeasurementFrame, ...]
    geometry: PendulumGeometry
    release_frame_index: int
    qc_overrides: tuple[QCExclusion, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.frames, tuple) or not isinstance(self.qc_overrides, tuple):
            raise ValueError("reconstruction arrays must be immutable tuples")
        if (len(self.measurement_digest) != 64
                or any(c not in "0123456789abcdef" for c in self.measurement_digest)):
            raise ValueError("measurement_digest must be a SHA256 digest")
        if not self.frames or tuple(f.frame_index for f in self.frames) != tuple(range(len(self.frames))):
            raise ValueError("reconstruction requires every source frame in order")
        if any(b.time_absolute_s <= a.time_absolute_s
               for a, b in zip(self.frames, self.frames[1:])):
            raise ValueError("source timestamps must be strictly increasing")
        if not isfinite(self.frames[-1].time_absolute_s - self.frames[0].time_absolute_s):
            raise ValueError("source time span must be finite")
        if type(self.release_frame_index) is not int or not 0 <= self.release_frame_index < len(self.frames):
            raise ValueError("release frame must be in the source video")
        excluded = tuple(item.frame_index for item in self.qc_overrides)
        if excluded != tuple(sorted(set(excluded))) or any(f >= len(self.frames) for f in excluded):
            raise ValueError("QC exclusions must be unique ordered source frames within the video")
        g = self.geometry
        if (g.fixed_pivot_px is None or g.tip_radius_reference_px is None
                or g.true_vertical is None or not g.true_vertical.direction_confirmed):
            raise ValueError("reconstruction requires fixed pivot, confirmed vertical and tip radius reference")
        vertical_length = hypot(g.true_vertical.bottom_px[0] - g.true_vertical.top_px[0],
                                g.true_vertical.bottom_px[1] - g.true_vertical.top_px[1])
        if not isfinite(vertical_length) or vertical_length <= 0:
            raise ValueError("true vertical vector must have a finite positive length")


@dataclass(frozen=True)
class ReconstructedFrame:
    """None 为几何不可用；共同 QC false 不抹掉有效 preview。"""

    frame_index: int
    time_absolute_s: float
    time_release_relative_s: float
    theta_rad: float | None
    phi_rad: float | None
    radius_px: float | None
    body_length_px: float | None
    pivot_displacement_px: float | None
    relative_weight: float | None
    is_qc_valid: bool
    qc_reasons: tuple[str, ...]


@dataclass(frozen=True)
class PendulumReconstruction:
    """数值、配置及参考支持集的冻结交付；全部缺测保持源帧位置。"""

    input_digest: str
    measurement_digest: str
    frames: tuple[ReconstructedFrame, ...]
    body_reference_px: float | None
    body_reference_frames: tuple[int, ...]
    body_reference_digest: str


def _finite_point(point: AdoptedLandmark | None) -> bool:
    return point is not None and isfinite(point.pixel_x) and isfinite(point.pixel_y)


def _source_valid(point: AdoptedLandmark | None) -> bool:
    if not _finite_point(point):
        return False
    return point.source == "manual" or (
        point.confidence is not None and type(point.confidence) is not bool
        and isfinite(point.confidence) and 0 <= point.confidence <= 1
    )


def signed_angle_rad(vector: tuple[float, float], vertical: tuple[float, float]) -> float | None:
    """图像 x 右 / y 下；角度来自固定 pivot 与真实 vertical，零向量无定义。"""
    norm_d, norm_v = hypot(*vector), hypot(*vertical)
    if (not all(isfinite(v) for v in (*vector, *vertical, norm_d, norm_v))
            or norm_d <= 0 or norm_v <= 0):
        return None
    dx, dy = vector
    vx, vy = vertical
    dx, dy, vx, vy = dx / norm_d, dy / norm_d, vx / norm_v, vy / norm_v
    return atan2(vy * dx - vx * dy, vx * dx + vy * dy)


def _body_vector(frame: MeasurementFrame) -> tuple[float, float] | None:
    top, bottom = frame.points[1:3]
    if not _finite_point(top) or not _finite_point(bottom):
        return None
    return top.pixel_x - bottom.pixel_x, top.pixel_y - bottom.pixel_y


def reconstruct_pendulum(request: ReconstructionInput) -> PendulumReconstruction:
    """共同 QC 与 preview 分开；无置信度硬切，人工点仍须通过几何门。"""
    excluded = {item.frame_index: item.reason for item in request.qc_overrides}
    body_lengths = [None if (v := _body_vector(f)) is None else hypot(*v) for f in request.frames]
    body_lengths = [v if v is not None and isfinite(v) else None for v in body_lengths]
    supports = tuple(f.frame_index for f, length in zip(request.frames, body_lengths)
                     if all(_finite_point(p) for p in f.points) and length is not None
                     and length > 0 and f.frame_index not in excluded)
    reference = median(body_lengths[i] for i in supports) if supports else None
    support_digest = canonical_json_digest({"frames": list(supports), "body_reference_px": reference})
    identity = canonical_json_digest({
        "measurement_digest": request.measurement_digest,
        "source_frames": [
            {"frame_index": f.frame_index, "time_absolute_s": f.time_absolute_s,
             "points": [None if p is None else {
                 "pixel_x": p.pixel_x if isfinite(p.pixel_x) else None,
                 "pixel_y": p.pixel_y if isfinite(p.pixel_y) else None,
                 "source": p.source,
                 "confidence": p.confidence if p.confidence is not None and isfinite(p.confidence) else None,
             } for p in f.points]}
            for f in request.frames
        ],
        "config": reconstruction_config(), "body_reference_digest": support_digest,
        "geometry": {
            "fixed_pivot_px": [float(v) for v in request.geometry.fixed_pivot_px],
            "radius_reference_px": float(request.geometry.tip_radius_reference_px),
            "vertical_top_px": [float(v) for v in request.geometry.true_vertical.top_px],
            "vertical_bottom_px": [float(v) for v in request.geometry.true_vertical.bottom_px],
        },
        "release_frame_index": request.release_frame_index,
        "qc_overrides": [{"frame_index": i, "reason": reason} for i, reason in excluded.items()],
    })
    pivot = request.geometry.fixed_pivot_px
    v = request.geometry.true_vertical
    vertical = (v.bottom_px[0] - v.top_px[0], v.bottom_px[1] - v.top_px[1])
    release_time = request.frames[request.release_frame_index].time_absolute_s
    rows = []
    previous_phi = None
    for frame, body_length in zip(request.frames, body_lengths):
        tip, _, _, tracked_pivot = frame.points
        d = (tip.pixel_x - pivot[0], tip.pixel_y - pivot[1]) if _finite_point(tip) else None
        radius = hypot(*d) if d is not None else None
        if radius is not None and not isfinite(radius):
            radius = None
        theta = signed_angle_rad(d, vertical) if d is not None else None
        body = _body_vector(frame)
        phi = signed_angle_rad(body, vertical) if body is not None else None
        if phi is not None and previous_phi is not None:
            phi = previous_phi + atan2(sin(phi - previous_phi), cos(phi - previous_phi))
        previous_phi = phi
        reasons = _qc_reasons(frame, radius, body_length, reference, request, excluded)
        displacement = hypot(tracked_pivot.pixel_x - pivot[0], tracked_pivot.pixel_y - pivot[1]) if _finite_point(tracked_pivot) else None
        if displacement is not None and not isfinite(displacement):
            displacement = None
        weight = None if not _source_valid(tip) else (1.0 if tip.source == "manual" else max(0.05, tip.confidence))
        rows.append(ReconstructedFrame(
            frame.frame_index, frame.time_absolute_s, frame.time_absolute_s - release_time,
            theta, phi, radius, body_length, displacement, weight, not reasons, reasons,
        ))
    return PendulumReconstruction(identity, request.measurement_digest, tuple(rows), reference, supports, support_digest)


def _qc_reasons(
    frame: MeasurementFrame, radius: float | None, body_length: float | None,
    reference: float | None, request: ReconstructionInput, excluded: dict[int, str],
) -> tuple[str, ...]:
    reasons = []
    for role, point in zip(ROLE_ORDER, frame.points):
        if point is None:
            reasons.append(f"{role}:no_adopted_point")
        elif not _finite_point(point):
            reasons.append(f"{role}:nonfinite_coordinates")
        elif not _source_valid(point):
            reasons.append(f"{role}:invalid_ai_likelihood")
    if radius is None or radius <= 0:
        reasons.append("nonpositive_tip_radius")
    elif abs(radius - request.geometry.tip_radius_reference_px) > RADIUS_RELATIVE_TOLERANCE * request.geometry.tip_radius_reference_px:
        reasons.append("radius_out_of_tolerance")
    if body_length is None or body_length <= 0:
        reasons.append("nonpositive_body_length")
    if reference is None:
        reasons.append("body_reference_unavailable")
    elif body_length is not None and abs(body_length - reference) > BODY_RELATIVE_TOLERANCE * reference:
        reasons.append("body_length_out_of_tolerance")
    if frame.frame_index in excluded:
        reasons.append(f"user_excluded:{excluded[frame.frame_index]}")
    return tuple(reasons)
