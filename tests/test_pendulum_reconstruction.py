"""P2.1：已知几何、共同 QC、源时间及配置身份。"""

from dataclasses import replace
from hashlib import sha256
import json
from math import cos, pi, sin
from pathlib import Path

import pytest

from ai_physics_tracker.domain.pendulum import PendulumGeometry, QCExclusion, TrueVertical
from ai_physics_tracker.domain.pendulum_reconstruction import (
    AdoptedLandmark, MeasurementFrame, ReconstructionInput, reconstruct_pendulum,
    signed_angle_rad, reconstruction_config,
)


def _request(angles=(0.0,) * 12):
    frames = tuple(MeasurementFrame(i, 10 + i * 0.1, (
        AdoptedLandmark(100 * sin(angle), 100 * cos(angle), "manual", None),
        AdoptedLandmark(0, 10, "manual", None),
        AdoptedLandmark(0, 20, "manual", None),
        AdoptedLandmark(0, 0, "manual", None),
    )) for i, angle in enumerate(angles))
    return ReconstructionInput("a" * 64, frames, PendulumGeometry(
        (0, 0), TrueVertical((0, 0), (0, 1)).confirmed(), 100,
    ), 5)


def _point(request, frame_index, role_index, point):
    frame = request.frames[frame_index]
    points = list(frame.points)
    points[role_index] = point
    frames = list(request.frames)
    frames[frame_index] = replace(frame, points=tuple(points))
    return replace(request, frames=tuple(frames))


@pytest.mark.parametrize("angle", [-pi, -pi/2, -.2, 0, .2, pi/2, pi-1e-6])
def test_signed_geometry_and_rotated_vertical(angle):
    assert signed_angle_rad((sin(angle), cos(angle)), (0, 1)) == pytest.approx(angle, abs=1e-12)
    # 将画面两向量一同旋转，角度不变。
    beta = .7
    def rotated(x, y):
        return (cos(beta)*x-sin(beta)*y, sin(beta)*x+cos(beta)*y)
    assert signed_angle_rad(rotated(sin(angle), cos(angle)), rotated(0, 1)) == pytest.approx(angle, abs=1e-12)
    assert signed_angle_rad((0, 0), (0, 1)) is None


def test_release_and_tracked_pivot_do_not_move_angle_origin():
    request = _request((.2,) * 12)
    request = _point(request, 7, 3, AdoptedLandmark(40, 30, "manual", None))
    result = reconstruct_pendulum(request)
    assert result.frames[7].theta_rad == pytest.approx(.2, abs=1e-12)
    assert result.frames[7].pivot_displacement_px == 50
    assert all(row.is_qc_valid for row in result.frames)
    assert result.frames[0].time_release_relative_s == pytest.approx(-.5, abs=1e-12)
    assert result.frames[5].time_release_relative_s == 0
    assert result.frames[7].time_release_relative_s == pytest.approx(.2, abs=1e-12)


def test_manual_and_ai_confidence_weighting_and_preview_are_separate():
    request = _request()
    request = _point(request, 1, 0, AdoptedLandmark(0, 100, "deeplabcut", .001))
    request = _point(request, 2, 3, None)
    request = _point(request, 3, 1, AdoptedLandmark(0, 10, "deeplabcut", None))
    request = _point(request, 4, 0, AdoptedLandmark(0, 100, "manual", None))
    result = reconstruct_pendulum(request)
    assert result.frames[1].is_qc_valid and result.frames[1].relative_weight == .05
    assert result.frames[2].theta_rad == 0 and not result.frames[2].is_qc_valid
    assert "pivot:no_adopted_point" in result.frames[2].qc_reasons
    assert "body_top:invalid_ai_likelihood" in result.frames[3].qc_reasons
    assert result.frames[4].relative_weight == 1 and result.frames[4].is_qc_valid
    assert [row.frame_index for row in result.frames] == list(range(12))
    assert result.frames[3].time_release_relative_s == pytest.approx(-.2, abs=1e-12)


@pytest.mark.parametrize("radius,valid", [(90, True), (110, True), (89.99, False), (110.01, False), (0, False)])
def test_radius_boundary_and_manual_does_not_bypass_geometry(radius, valid):
    request = _point(_request(), 0, 0, AdoptedLandmark(0, radius, "manual", None))
    result = reconstruct_pendulum(request)
    assert result.frames[0].is_qc_valid is valid
    if radius == 0:
        assert result.frames[0].theta_rad is None


@pytest.mark.parametrize("length,valid", [(8, True), (12, True), (7.99, False), (12.01, False), (0, False)])
def test_body_boundary(length, valid):
    request = _point(_request(), 0, 1, AdoptedLandmark(0, 20-length, "manual", None))
    result = reconstruct_pendulum(request)
    assert result.body_reference_px == 10
    assert result.frames[0].is_qc_valid is valid


def test_body_reference_excludes_user_and_incomplete_frames_and_reports_unavailable():
    request = _point(_request(), 0, 1, AdoptedLandmark(0, -100, "manual", None))
    request = replace(request, qc_overrides=(QCExclusion(0, "occlusion"),))
    request = _point(request, 1, 3, None)
    result = reconstruct_pendulum(request)
    assert result.body_reference_frames == tuple(range(2, 12))
    assert result.body_reference_px == 10
    assert "user_excluded:occlusion" in result.frames[0].qc_reasons
    assert result.input_digest != reconstruct_pendulum(_request()).input_digest
    frames = tuple(replace(f, points=(*f.points[:3], None)) for f in request.frames)
    result = reconstruct_pendulum(replace(request, frames=frames))
    assert result.body_reference_px is None
    assert all("body_reference_unavailable" in row.qc_reasons for row in result.frames)


def test_phi_unwrap_resets_at_missing_body_pair():
    request = _request()
    for i, angle in [(0, 3), (1, -3), (3, -3)]:
        request = _point(request, i, 1, AdoptedLandmark(10*sin(angle), 20+10*cos(angle), "manual", None))
    request = _point(request, 2, 1, None)
    result = reconstruct_pendulum(request)
    assert result.frames[1].phi_rad == pytest.approx(2*pi-3, abs=1e-12)
    assert result.frames[2].phi_rad is None
    assert result.frames[3].phi_rad == pytest.approx(-3, abs=1e-12)


def test_nonfinite_points_are_explicit_missing_and_identity_tracks_coordinates():
    request = _point(_request(), 0, 0, AdoptedLandmark(float('nan'), 100, "manual", None))
    row = reconstruct_pendulum(request).frames[0]
    assert row.theta_rad is None and "tip:nonfinite_coordinates" in row.qc_reasons
    base = _request()
    changed = _point(base, 0, 0, AdoptedLandmark(1, 100, "manual", None))
    assert reconstruct_pendulum(base).input_digest != reconstruct_pendulum(changed).input_digest


def test_invalid_time_frames_release_and_exclusions_fail_closed():
    request = _request()
    for changes in [
        {"frames": request.frames[1:]}, {"release_frame_index": True},
        {"release_frame_index": 12}, {"qc_overrides": (QCExclusion(12, 'outside'),)},
        {"qc_overrides": (QCExclusion(1, 'x'), QCExclusion(1, 'y'))},
        {"frames": (replace(request.frames[0], time_absolute_s=11), *request.frames[1:])},
        {"geometry": replace(request.geometry, true_vertical=TrueVertical((0, 0), (0, 1)))},
    ]:
        with pytest.raises(ValueError):
            replace(request, **changes)
    for frame in [-1, True, 1.5]:
        with pytest.raises(ValueError):
            QCExclusion(frame, 'invalid')
    with pytest.raises(ValueError):
        QCExclusion(1, ' ')


def test_compiled_policy_matches_frozen_profile_bytes_and_values():
    root = Path(__file__).resolve().parents[1] / 'publication' / 'profiles'
    config = reconstruction_config()
    student_bytes = (root / 'student-default-v1.json').read_bytes()
    legacy_bytes = (root / 'legacy-publication-v1.json').read_bytes()
    assert config['profile_sha256'] == sha256(student_bytes).hexdigest()
    assert config['formula_profile_sha256'] == sha256(legacy_bytes).hexdigest()
    profile = json.loads(student_bytes)
    assert config['radius_relative_tolerance'] == profile['qc']['radius_relative_tolerance']
    assert config['body_relative_tolerance'] == profile['qc']['body_relative_tolerance']
    assert config['provenance']['qc'] == profile['qc']['sources']
    assert config['provenance']['weighting'] == profile['weighting']['sources']


@pytest.mark.parametrize('confidence', [0, 1, .5, float('nan'), float('inf')])
def test_manual_landmark_never_carries_confidence(confidence):
    with pytest.raises(ValueError, match='manual landmark confidence must be null'):
        AdoptedLandmark(0, 100, 'manual', confidence)


def test_direct_core_digest_uses_float64_numeric_semantics():
    request = _request()
    def numeric_request(convert):
        frames = tuple(MeasurementFrame(f.frame_index, convert(f.frame_index), tuple(
            AdoptedLandmark(convert(p.pixel_x), convert(p.pixel_y), p.source, p.confidence)
            for p in f.points
        )) for f in request.frames)
        geometry = PendulumGeometry((convert(0), convert(0)),
            TrueVertical((convert(0), convert(0)), (convert(0), convert(1))).confirmed(), convert(100))
        return replace(request, frames=frames, geometry=geometry)
    ints, floats = numeric_request(int), numeric_request(float)
    assert reconstruct_pendulum(ints) == reconstruct_pendulum(floats)
    assert type(ints.frames[0].points[0].pixel_x) is float
    assert type(ints.frames[0].time_absolute_s) is float
