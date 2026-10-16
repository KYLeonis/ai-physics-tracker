"""生成明确标为合成数据的P6.3真人体验工程；不覆盖已有目录。"""

import argparse
from dataclasses import replace
from pathlib import Path
from threading import Event
from uuid import uuid4

import cv2
import numpy as np

from ai_physics_tracker.application.project_session import ProjectSession
from ai_physics_tracker.application.signal_analysis_job import (
    SignalSelection, prepare_signal_analysis, run_signal_analysis,
)
from ai_physics_tracker.application.video import VideoStreamInfo
from ai_physics_tracker.domain.function_fit import FitParameter, FitSpec
from ai_physics_tracker.domain.recurrence import RecurrenceSpec
from ai_physics_tracker.domain.timeline import frame_to_time
from ai_physics_tracker.domain.track import TrackPoint
from ai_physics_tracker.domain.types import utc_now
from ai_physics_tracker.infrastructure.project_repository import ProjectRepository


def prepare(output: Path) -> Path:
    """创建水平往复运动示例，两个分析族均已保存，便于从恢复设置开始体验。"""
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    video_path = output / "synthetic-horizontal.avi"
    fps_nominal, frame_count = 20.0, 180
    coordinates = 160 + 70*np.sin(2*np.pi*(np.arange(frame_count)-10)/fps_nominal/1.3)
    writer = cv2.VideoWriter(str(video_path), cv2.VideoWriter_fourcc(*"MJPG"), fps_nominal, (320, 200))
    if not writer.isOpened():
        raise RuntimeError("MJPEG writer unavailable")
    try:
        for frame_index, pixel_x in enumerate(coordinates):
            image = np.full((200, 320, 3), 240, dtype=np.uint8)
            cv2.line(image, (160, 20), (160, 180), (150, 150, 150), 1)
            cv2.circle(image, (round(float(pixel_x)), 100), 8, (30, 80, 200), -1)
            cv2.putText(image, f"SYNTHETIC frame {frame_index}", (8, 190), cv2.FONT_HERSHEY_SIMPLEX, .5, (20, 20, 20), 1)
            writer.write(image)
    finally:
        writer.release()
    repository = ProjectRepository()
    session = ProjectSession.start(repository, "P6.3 synthetic horizontal motion (not manual observations)")
    video, timeline = session.register_external_video(video_path, VideoStreamInfo(320, 200, fps_nominal, frame_count, "avi", "cfr"))
    track = session.add_track(video.video_id, "Synthetic translating dot")
    now = utc_now()
    points = tuple(TrackPoint(uuid4(), track.track_id, frame_index, frame_to_time(frame_index, timeline),
                              float(pixel_x), 100., "template", "visible", "active", now, now,
                              source_detail="analytic synthetic fixture; not human ground truth")
                   for frame_index, pixel_x in enumerate(coordinates))
    project = replace(session.project, observations=points)
    # 重新构造store后通过公开时序授权入口恢复本合成CFR的测量权限。
    session = ProjectSession(repository, project)
    from ai_physics_tracker.application.video_timing import TimingReport
    session.confirm_video_timing(video.video_id, TimingReport("cfr", "analytic CFR fixture", frame_count, fps_nominal, fps_nominal))
    session.compute_kinematics(track.track_id)
    selection = SignalSelection(track.track_id, "x", 10, 179)
    fit = FitSpec("c+A*cos(Omega*t+phi)", (FitParameter("c", 150), FitParameter("A", 60),
                                           FitParameter("Omega", 4.8, 1, 10), FitParameter("phi", -1.4)))
    fitted = run_signal_analysis(prepare_signal_analysis(session, selection, fit, (("T", "2*pi/Omega"),)), Event())
    assert fitted.fit_outcome.is_publishable and fitted.fit_outcome.rmse < 1e-7
    session.apply_analysis_result(fitted)
    recurrence = run_signal_analysis(prepare_signal_analysis(session, selection, RecurrenceSpec(160, "rising", 5, .2)), Event())
    summary = recurrence.record.extra_fields["analysis"]["summary"]
    assert len(summary["intervals_s"]) >= 5 and abs(summary["mean_interval_s"]/1.3-1) < .01
    session.apply_analysis_result(recurrence)
    root = output / "project"
    repository.create_from_project(root, session.project)
    assert repository.load(root).derived == session.project.derived
    return root


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    print(prepare(parser.parse_args().output))
