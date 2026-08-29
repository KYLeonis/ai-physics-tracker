"""Calibration value object and invertible pixel/world transform."""

from dataclasses import dataclass, field
from datetime import datetime
from math import cos, hypot, isfinite, radians, sin
from uuid import UUID

from ai_physics_tracker.domain.types import JsonObject, require_aware_datetime

_UNIT_TO_M = {"m": 1.0, "cm": 0.01, "mm": 0.001}


@dataclass(frozen=True)
class Calibration:
    """Line-scale calibration for one video."""

    calibration_id: UUID
    video_id: UUID
    name: str
    scale_end_1_px: tuple[float, float]
    scale_end_2_px: tuple[float, float]
    known_length: float
    unit: str
    created_at: datetime
    type: str = "line_scale"
    origin_px: tuple[float, float] | None = None
    rotation_deg: float = 0.0
    applies_from_frame: int | None = None
    applies_to_frame: int | None = None
    notes: str | None = None
    extra_fields: JsonObject = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("calibration name must not be blank")
        if self.type != "line_scale":
            raise ValueError("Phase 1 supports only line_scale calibration")
        if not isfinite(self.known_length) or self.known_length <= 0:
            raise ValueError("known_length must be a finite positive value")
        if self.unit not in _UNIT_TO_M:
            raise ValueError(f"unsupported calibration unit: {self.unit}")
        if not isfinite(self.rotation_deg):
            raise ValueError("rotation_deg must be finite")
        coordinates = (*self.scale_end_1_px, *self.scale_end_2_px)
        if self.origin_px is not None:
            coordinates += self.origin_px
        if not all(isfinite(value) for value in coordinates):
            raise ValueError("calibration coordinates must be finite")
        if hypot(
            self.scale_end_2_px[0] - self.scale_end_1_px[0],
            self.scale_end_2_px[1] - self.scale_end_1_px[1],
        ) <= 0:
            raise ValueError("calibration scale endpoints must not coincide")
        if self.applies_from_frame is not None or self.applies_to_frame is not None:
            raise ValueError("time-varying calibration is reserved for a later phase")
        require_aware_datetime(self.created_at, "created_at")


@dataclass(frozen=True)
class CalibrationTransform:
    """Pure invertible transform defined by data-model.md §6.2."""

    calibration: Calibration
    height_px: int

    def __post_init__(self) -> None:
        if self.height_px <= 0:
            raise ValueError("height_px must be positive")

    @property
    def pixels_per_unit(self) -> float:
        """Return the line-scale ratio in pixels per calibration unit."""

        first = self.calibration.scale_end_1_px
        second = self.calibration.scale_end_2_px
        return hypot(second[0] - first[0], second[1] - first[1]) / self.calibration.known_length

    @property
    def origin_px(self) -> tuple[float, float]:
        """Use the image lower-left corner when no explicit origin is stored."""

        return self.calibration.origin_px or (0.0, float(self.height_px))

    def pixel_to_world(self, point_px: tuple[float, float]) -> tuple[float, float]:
        """Convert pixel coordinates to the calibration's declared unit."""

        origin_x, origin_y = self.origin_px
        scale = self.pixels_per_unit
        unrotated_x = (point_px[0] - origin_x) / scale
        unrotated_y = -(point_px[1] - origin_y) / scale
        angle = radians(self.calibration.rotation_deg)
        return (
            cos(angle) * unrotated_x - sin(angle) * unrotated_y,
            sin(angle) * unrotated_x + cos(angle) * unrotated_y,
        )

    def world_to_pixel(self, point_world: tuple[float, float]) -> tuple[float, float]:
        """Apply the exact inverse of :meth:`pixel_to_world`."""

        angle = radians(self.calibration.rotation_deg)
        unrotated_x = cos(angle) * point_world[0] + sin(angle) * point_world[1]
        unrotated_y = -sin(angle) * point_world[0] + cos(angle) * point_world[1]
        origin_x, origin_y = self.origin_px
        scale = self.pixels_per_unit
        return (
            origin_x + scale * unrotated_x,
            origin_y - scale * unrotated_y,
        )

    def world_to_si(self, point_world: tuple[float, float]) -> tuple[float, float]:
        """Convert a world point from the declared unit to metres."""

        factor = _UNIT_TO_M[self.calibration.unit]
        return point_world[0] * factor, point_world[1] * factor
