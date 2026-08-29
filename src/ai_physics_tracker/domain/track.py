"""Track identity and immutable raw observation value objects."""

from dataclasses import dataclass, field
from datetime import datetime
from math import isfinite
import re
from uuid import UUID

from ai_physics_tracker.domain.types import JsonObject, require_aware_datetime

_COLOR_PATTERN = re.compile(r"^#[0-9A-Fa-f]{6}$")
_VISIBILITIES = {"visible", "occluded", "unknown"}
_STATUSES = {"active", "superseded"}


@dataclass(frozen=True)
class Track:
    """Identity metadata for one physical point in one video."""

    track_id: UUID
    video_id: UUID
    name: str
    color: str
    created_at: datetime
    kind: str = "point"
    keypoint_group: str | None = None
    notes: str | None = None
    extra_fields: JsonObject = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("track name must not be blank")
        if not _COLOR_PATTERN.fullmatch(self.color):
            raise ValueError("track color must use #RRGGBB format")
        if self.kind != "point":
            raise ValueError("Phase 1 supports only point tracks")
        if self.keypoint_group is not None:
            raise ValueError("keypoint_group is reserved for a later phase")
        require_aware_datetime(self.created_at, "created_at")


@dataclass(frozen=True)
class TrackPoint:
    """Single-frame raw pixel observation with provenance."""

    point_id: UUID
    track_id: UUID
    frame_index: int
    time_s: float
    pixel_x: float
    pixel_y: float
    source: str
    visibility: str
    status: str
    created_at: datetime
    modified_at: datetime
    source_detail: str | None = None
    confidence: float | None = None
    quality_flags: tuple[str, ...] = ()
    superseded_by: UUID | None = None
    extra_fields: JsonObject = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        if self.frame_index < 0:
            raise ValueError("frame_index must be non-negative")
        for field_name, value in (
            ("time_s", self.time_s),
            ("pixel_x", self.pixel_x),
            ("pixel_y", self.pixel_y),
        ):
            if not isfinite(value):
                raise ValueError(f"{field_name} must be finite")
        if not self.source.strip():
            raise ValueError("source must not be blank")
        if self.source == "manual" and self.confidence is not None:
            raise ValueError("manual observations must not set confidence")
        if self.confidence is not None and not 0 <= self.confidence <= 1:
            raise ValueError("confidence must be in [0, 1]")
        if self.visibility not in _VISIBILITIES:
            raise ValueError(f"unsupported visibility: {self.visibility}")
        if self.status not in _STATUSES:
            raise ValueError(f"unsupported status: {self.status}")
        if self.status == "active" and self.superseded_by is not None:
            raise ValueError("active observations cannot set superseded_by")
        if self.status == "superseded" and self.superseded_by is None:
            raise ValueError("superseded observations must identify their replacement")
        require_aware_datetime(self.created_at, "created_at")
        require_aware_datetime(self.modified_at, "modified_at")
