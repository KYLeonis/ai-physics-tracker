"""近似时序预算、授权边界与原始观测来源的回归测试。"""

from dataclasses import replace
import json
import math
from pathlib import Path

import pytest

from ai_physics_tracker.application.project_session import (
    ProjectSession,
    ProjectSessionError,
)
from ai_physics_tracker.application.video import VideoStreamInfo
from ai_physics_tracker.domain.video import Video
from ai_physics_tracker.application.video_timing import (
    TimingReport,
    approximation_errors,
)
from ai_physics_tracker.infrastructure.project_repository import ProjectRepository


def _near_report(
    *,
    frame_count: int = 5,
    fps_measured: float | None = 10.0,
    fps_reference: float | None = 10.0,
    max_grid_error_s: float | None = 0.0001,
    max_interval_error_s: float | None = 0.0002,
) -> TimingReport:
    """构造与五帧、10 FPS 合成媒体对应的近似结论。"""

    return TimingReport(
        status="near_cfr",
        reason="bounded near-CFR test result",
        frame_count=frame_count,
        fps_measured=fps_measured,
        fps_reference=fps_reference,
        max_grid_error_s=max_grid_error_s,
        max_interval_error_s=max_interval_error_s,
    )


@pytest.mark.parametrize(
    "report",
    [
        TimingReport("unknown", "probe unavailable", frame_count=5),
        TimingReport("vfr_suspected", "variable intervals", frame_count=5),
        _near_report(frame_count=0),
        _near_report(frame_count=1),
        _near_report(frame_count=-1),
        _near_report(fps_measured=math.nan),
        _near_report(fps_reference=math.nan),
        _near_report(max_grid_error_s=math.nan),
        _near_report(max_interval_error_s=math.inf),
    ],
)
def test_approximation_errors_rejects_non_usable_timing_reports(
    report: TimingReport,
) -> None:
    """unknown/VFR、坏帧数和非有限数值都不能进入近似测量。"""

    assert approximation_errors(report, 10.0) is None


@pytest.mark.parametrize("fps_nominal", [0.0, -10.0, math.nan, math.inf])
def test_approximation_errors_rejects_bad_saved_timeline_fps(
    fps_nominal: float,
) -> None:
    report = _near_report()

    assert approximation_errors(report, fps_nominal) is None


def test_approximation_errors_uses_inclusive_budget_and_rejects_over_budget() -> None:
    # fps=10 时预算为 min(1 ms, 1% * 100 ms)=1 ms；边界应可接受。
    at_budget = _near_report(max_grid_error_s=0.001, max_interval_error_s=0.001)
    assert approximation_errors(at_budget, 10.0) == pytest.approx((0.001, 0.001))

    over_budget = _near_report(
        max_grid_error_s=0.001 + 1e-12,
        max_interval_error_s=0.001,
    )
    assert approximation_errors(over_budget, 10.0) is None


def test_approximation_errors_uses_frame_fraction_budget_at_high_fps() -> None:
    # fps=100 时 1% 帧周期（0.1 ms）小于 1 ms 的绝对上限。
    at_budget = _near_report(
        fps_measured=100.0,
        fps_reference=100.0,
        max_grid_error_s=0.0001,
        max_interval_error_s=0.0001,
    )
    assert approximation_errors(at_budget, 100.0) == pytest.approx(
        (0.0001, 0.0001)
    )

    over_budget = replace(at_budget, max_interval_error_s=0.0001 + 1e-12)
    assert approximation_errors(over_budget, 100.0) is None


def test_approximation_errors_recomputes_error_for_changed_saved_fps() -> None:
    report = _near_report(max_grid_error_s=0.0001, max_interval_error_s=0.0002)

    errors = approximation_errors(report, 10.01)

    assert errors is not None
    period_delta_s = abs(1 / 10.01 - 1 / 10.0)
    assert errors == pytest.approx(
        (0.0001 + 4 * period_delta_s, 0.0002 + period_delta_s),
        abs=1e-12,
    )


def _near_session(
    repository: ProjectRepository,
    path: Path,
    *,
    fps_nominal: float = 10.0,
) -> tuple[ProjectSession, Video]:
    """创建尚未获得近似授权的项目会话。"""

    session = ProjectSession.start(repository, name="approximation regression")
    video, _timeline = session.register_preview_video(
        path,
        VideoStreamInfo(64, 48, 10.0, 5, "synthetic", "near_cfr"),
    )
    if fps_nominal != 10.0:
        timeline = replace(
            session.project.timelines[0],
            fps_nominal=fps_nominal,
        )
        # Phase 2 尚无 ProjectSession.update_timeline 公共入口；测试通过
        # 不可变 Project 快照构造一个“保存后的 Timeline 被改写”场景。
        session._project = replace(session.project, timelines=(timeline,))
    return session, video


@pytest.mark.parametrize(
    "report",
    [
        TimingReport("unknown", "unknown timing", frame_count=5),
        TimingReport("vfr_suspected", "VFR timing", frame_count=5),
        _near_report(frame_count=4),
        _near_report(fps_reference=math.nan),
    ],
)
def test_accept_approximate_timing_rejects_invalid_or_stale_reports(
    tmp_path: Path,
    report: TimingReport,
) -> None:
    session, video = _near_session(ProjectRepository(), tmp_path / "media.avi")

    with pytest.raises(ProjectSessionError, match="approximation"):
        session.accept_approximate_timing(video.video_id, report)


def test_accept_approximate_timing_rejects_saved_fps_that_exceeds_budget(
    tmp_path: Path,
) -> None:
    session, video = _near_session(
        ProjectRepository(), tmp_path / "media.avi", fps_nominal=9.0
    )

    with pytest.raises(ProjectSessionError, match="approximation"):
        session.accept_approximate_timing(video.video_id, _near_report())


def test_accepted_approximate_timing_survives_raw_point_roundtrip(
    tmp_path: Path,
    synthetic_video_path: Path,
) -> None:
    repository = ProjectRepository()
    session, video = _near_session(repository, synthetic_video_path)
    report = _near_report(max_grid_error_s=0.0001, max_interval_error_s=0.0002)

    session.accept_approximate_timing(video.video_id, report)
    track = session.add_track(video.video_id)
    point = session.mark_point(track.track_id, 2, 17.5, 21.25)
    assert point.source_detail is not None
    detail = json.loads(point.source_detail)
    assert detail["timing_method"] == "near_cfr_user_accepted_v1"
    assert detail["fps_nominal"] == pytest.approx(10.0)
    assert detail["max_grid_error_s"] == pytest.approx(0.0001)
    assert detail["max_interval_error_s"] == pytest.approx(0.0002)

    root = tmp_path / "approximation-project"
    session.save_as(root)
    reopened = ProjectSession.load(repository, root)

    assert len(reopened.project.observations) == 1
    restored = reopened.project.observations[0]
    assert restored.point_id == point.point_id
    assert restored.frame_index == point.frame_index
    assert restored.time_s == pytest.approx(point.time_s, abs=1e-12)
    assert restored.pixel_x == pytest.approx(point.pixel_x, abs=1e-12)
    assert restored.pixel_y == pytest.approx(point.pixel_y, abs=1e-12)
    assert restored.source == "manual"
    assert restored.source_detail == point.source_detail
