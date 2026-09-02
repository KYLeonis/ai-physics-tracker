"""困难帧挖掘（Phase 5.2 R2 / AC-2/AC-4）单元测试。

Slice 1 覆盖：全帧 raw prediction 读取入口（低置信度/缺测不丢失、
非法批次整批拒绝）、适配器公开、MiningParams 校验与
prepare_difficult_frame_request 的 run/产物身份绑定。
"""

from __future__ import annotations

from math import isnan
from pathlib import Path
from uuid import uuid4

import pytest

from ai_physics_tracker.application.difficult_frames import MiningParams
from ai_physics_tracker.infrastructure.dlc_predictions import (
    RawPrediction,
    read_raw_predictions,
)
from ai_physics_tracker.infrastructure.mock_engine_adapter import MockEngineAdapter


# ---------------------------------------------------------------------------
# 辅助工厂
# ---------------------------------------------------------------------------

def _records(frame_count: int = 10) -> list[dict]:
    """合成全帧预测记录：帧 3 低置信度、帧 5/6 缺测（NaN），其余正常。"""
    rows = []
    for frame in range(frame_count):
        if frame in (5, 6):
            rows.append({"frame_index": frame, "x": float("nan"),
                         "y": float("nan"), "likelihood": float("nan")})
        elif frame == 3:
            rows.append({"frame_index": frame, "x": 30.0, "y": 40.0, "likelihood": 0.2})
        else:
            rows.append({"frame_index": frame, "x": 10.0 + frame, "y": 20.0, "likelihood": 0.95})
    return rows


def _write_prediction_csv(path: Path, frame_count: int = 10) -> Path:
    """写一个 DLC 三行表头 CSV；帧 3 低置信度、帧 5/6 以 NaN 缺测。"""
    lines = [
        "scorer,MockDLC,MockDLC,MockDLC",
        "bodyparts,target,target,target",
        "coords,x,y,likelihood",
    ]
    for frame in range(frame_count):
        if frame in (5, 6):
            x, y, likelihood = "NaN", "NaN", "NaN"
        elif frame == 3:
            x, y, likelihood = "30.0", "40.0", "0.2"
        else:
            x, y, likelihood = f"{10.0 + frame}", "20.0", "0.95"
        lines.append(f"{frame},{x},{y},{likelihood}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Slice 1 — read_raw_predictions
# ---------------------------------------------------------------------------

class TestReadRawPredictions:
    def test_keeps_low_confidence_and_missing_rows(self):
        rows = read_raw_predictions(_records(), frame_count=10)
        assert len(rows) == 10
        assert [r.frame_index for r in rows] == list(range(10))
        assert rows[3].confidence == pytest.approx(0.2)   # 低于导入阈值仍保留（AC-2）
        assert isnan(rows[5].pixel_x) and isnan(rows[5].confidence)  # 缺测不丢（AC-2）
        assert isnan(rows[6].pixel_y)
        assert rows[0].confidence == pytest.approx(0.95)

    def test_rejects_duplicate_frames(self):
        records = _records()
        records.append(dict(records[-1]))
        with pytest.raises(ValueError, match="duplicate frame_index"):
            read_raw_predictions(records, frame_count=11)

    def test_rejects_incomplete_coverage(self):
        records = _records(frame_count=10)[:-1]
        with pytest.raises(ValueError, match="cover every source frame"):
            read_raw_predictions(records, frame_count=10)

    def test_rejects_out_of_range_confidence(self):
        records = _records()
        records[0] = {"frame_index": 0, "x": 1.0, "y": 1.0, "likelihood": 1.5}
        with pytest.raises(ValueError, match="likelihood"):
            read_raw_predictions(records)

    def test_csv_roundtrip_keeps_all_rows(self, tmp_path: Path):
        path = _write_prediction_csv(tmp_path / "predictions.csv")
        rows = read_raw_predictions(path, frame_count=10)
        assert len(rows) == 10
        assert rows[3].confidence == pytest.approx(0.2)
        assert isnan(rows[5].confidence)
        assert isnan(rows[6].pixel_x)

    def test_raw_prediction_value_object_validation(self):
        assert RawPrediction(0, 1.0, 2.0, 0.5).frame_index == 0
        with pytest.raises(ValueError, match="confidence"):
            RawPrediction(0, 1.0, 2.0, 1.5)
        with pytest.raises(ValueError, match="finite or NaN"):
            RawPrediction(0, float("inf"), 2.0, 0.5)
        with pytest.raises(ValueError, match="frame_index"):
            RawPrediction(-1, 1.0, 2.0, 0.5)


class TestAdaptersExposeRawRead:
    def test_mock_and_dlc_adapters_delegate_identically(self, tmp_path: Path):
        from ai_physics_tracker.infrastructure.dlc_adapter import DLCAdapter

        path = _write_prediction_csv(tmp_path / "predictions.csv")
        mock_rows = MockEngineAdapter().read_raw_predictions(path, frame_count=10)
        dlc_rows = DLCAdapter().read_raw_predictions(path, frame_count=10)
        assert len(mock_rows) == len(dlc_rows) == 10
        for mock_row, dlc_row in zip(mock_rows, dlc_rows):
            assert mock_row.frame_index == dlc_row.frame_index
            for a, b in ((mock_row.pixel_x, dlc_row.pixel_x),
                         (mock_row.pixel_y, dlc_row.pixel_y),
                         (mock_row.confidence, dlc_row.confidence)):
                if isnan(a) or isnan(b):
                    assert isnan(a) and isnan(b)
                else:
                    assert a == pytest.approx(b)


# ---------------------------------------------------------------------------
# Slice 1 — MiningParams
# ---------------------------------------------------------------------------

class TestMiningParams:
    def test_defaults_are_valid(self):
        params = MiningParams()
        snapshot = params.to_snapshot()
        assert snapshot["weight_uncertainty"] == pytest.approx(0.40)
        assert snapshot["min_gap_s"] == pytest.approx(0.25)

    @pytest.mark.parametrize("kwargs, message", [
        ({"top_n": 0}, "top_n"),
        ({"confidence_threshold": 1.2}, "confidence_threshold"),
        ({"smooth_window_length": 6}, "smooth_window_length"),
        ({"smooth_polyorder": 7}, "smooth_polyorder"),
        ({"min_gap_s": 0.0}, "min_gap_s"),
        ({"weight_jump": -0.1}, "weights"),
        ({"weight_uncertainty": 0.0, "weight_jump": 0.0,
          "weight_residual": 0.0, "weight_prior": 0.0}, "positive"),
    ])
    def test_invalid_params_rejected(self, kwargs, message):
        with pytest.raises(ValueError, match=message):
            MiningParams(**kwargs)


# ---------------------------------------------------------------------------
# Slice 1 — prepare_difficult_frame_request
# ---------------------------------------------------------------------------

class TestPrepareDifficultFrameRequest:
    @staticmethod
    def _make_session_with_infer_run(tmp_path: Path, synthetic_video_path: Path, **run_overrides):
        from ai_physics_tracker.application.project_session import ProjectSession
        from ai_physics_tracker.application.video import VideoStreamInfo
        from ai_physics_tracker.domain.project import create_project
        from ai_physics_tracker.domain.tracking_run import (
            create_tracking_run, mark_run_completed,
        )
        from dataclasses import replace
        from ai_physics_tracker.infrastructure.project_repository import ProjectRepository

        session = ProjectSession(ProjectRepository(), create_project("mining_proj"))
        info = VideoStreamInfo(
            width_px=64, height_px=48, fps_container=10.0, frame_count=10,
            container_format="avi", timing_status="cfr",
        )
        video, _timeline = session.register_external_video(synthetic_video_path, info)
        track = session.add_track(video.video_id, "TrackA")
        session.save_as(tmp_path / "proj")
        root = session.project_root

        run_dir = root / "data" / "engines" / "artifacts"
        run_dir.mkdir(parents=True)
        prediction_path = _write_prediction_csv(run_dir / "predictions.csv")
        model_path = run_dir / "model-snapshot.pt"
        model_path.write_bytes(b"fake model weights")
        model_stat = model_path.stat()

        run = create_tracking_run(
            video.video_id, track.track_id, "infer", engine="dlc",
            engine_version="3.0.1-mock", config={},
        )
        run = mark_run_completed(
            run, model_snapshot="data/engines/artifacts/model-snapshot.pt",
        )
        run = replace(run, extra_fields={
            "prediction_path": "data/engines/artifacts/predictions.csv",
            "model_file_info": [model_stat.st_size, model_stat.st_mtime_ns],
        })
        run = replace(run, **run_overrides) if run_overrides else run
        session.record_tracking_run(run)
        return session, video, track, run, prediction_path, model_path

    def test_prepare_valid_request(self, tmp_path: Path, synthetic_video_path: Path):
        from ai_physics_tracker.application.difficult_frame_job import prepare_difficult_frame_request

        session, video, track, run, prediction_path, model_path = \
            self._make_session_with_infer_run(tmp_path, synthetic_video_path)
        session.mark_point(track.track_id, 2, 5.0, 5.0)

        job = prepare_difficult_frame_request(
            session, run.run_id, MiningParams(top_n=5),
            prior_correct_frames=frozenset({7}),
        )
        mining = job.mining_request
        assert mining.run_id == run.run_id
        assert mining.video_id == video.video_id
        assert mining.track_id == track.track_id
        assert mining.prediction_path == prediction_path.resolve()
        assert mining.model_path == model_path.resolve()
        assert (mining.zone_start, mining.zone_end) == (0, 9)
        assert mining.fps_nominal == pytest.approx(10.0)
        assert mining.manual_frames == frozenset({2})
        assert mining.prior_correct_frames == frozenset({7})
        stat = prediction_path.stat()
        assert job.prediction_file_info == (stat.st_size, stat.st_mtime_ns)
        assert job.project_root == session.project_root.resolve()

    def test_reject_unsaved_project(self, tmp_path: Path, synthetic_video_path: Path):
        from ai_physics_tracker.application.difficult_frame_job import prepare_difficult_frame_request
        from ai_physics_tracker.application.project_session import ProjectSession
        from ai_physics_tracker.application.video import VideoStreamInfo
        from ai_physics_tracker.domain.project import create_project
        from ai_physics_tracker.infrastructure.project_repository import ProjectRepository

        session = ProjectSession(ProjectRepository(), create_project("unsaved"))
        info = VideoStreamInfo(
            width_px=64, height_px=48, fps_container=10.0, frame_count=10,
            container_format="avi", timing_status="cfr",
        )
        video, _ = session.register_external_video(synthetic_video_path, info)
        with pytest.raises(Exception, match="Save the project"):
            prepare_difficult_frame_request(session, uuid4(), MiningParams())

    def test_reject_non_infer_or_incomplete_run(self, tmp_path: Path, synthetic_video_path: Path):
        from ai_physics_tracker.application.difficult_frame_job import prepare_difficult_frame_request

        session, _video, _track, run, _p, _m = \
            self._make_session_with_infer_run(tmp_path, synthetic_video_path)

        with pytest.raises(Exception, match="completed inference run"):
            prepare_difficult_frame_request(session, uuid4(), MiningParams())

        from dataclasses import replace
        train_run = replace(run, run_id=uuid4(), task_type="train")
        session.record_tracking_run(train_run)
        with pytest.raises(Exception, match="completed inference run"):
            prepare_difficult_frame_request(session, train_run.run_id, MiningParams())

        from ai_physics_tracker.domain.tracking_run import create_tracking_run, mark_run_running
        running = mark_run_running(create_tracking_run(
            run.video_id, run.track_id, "infer", engine="dlc",
            engine_version="3.0.1-mock", config={},
        ))
        session.record_tracking_run(running)
        with pytest.raises(Exception, match="completed inference run"):
            prepare_difficult_frame_request(session, running.run_id, MiningParams())

    def test_reject_missing_prediction_file(self, tmp_path: Path, synthetic_video_path: Path):
        from ai_physics_tracker.application.difficult_frame_job import prepare_difficult_frame_request

        session, _video, _track, run, prediction_path, _m = \
            self._make_session_with_infer_run(tmp_path, synthetic_video_path)
        prediction_path.unlink()
        with pytest.raises(Exception, match="Raw prediction artifact is missing"):
            prepare_difficult_frame_request(session, run.run_id, MiningParams())

    def test_reject_tampered_model_fingerprint(self, tmp_path: Path, synthetic_video_path: Path):
        from ai_physics_tracker.application.difficult_frame_job import prepare_difficult_frame_request

        session, _video, _track, run, _p, model_path = \
            self._make_session_with_infer_run(tmp_path, synthetic_video_path)
        model_path.write_bytes(b"tampered model weights")  # size 变化 → 指纹不符
        with pytest.raises(Exception, match="model snapshot of this run has changed"):
            prepare_difficult_frame_request(session, run.run_id, MiningParams())

    def test_reject_prediction_path_escape(self, tmp_path: Path, synthetic_video_path: Path):
        from ai_physics_tracker.application.difficult_frame_job import prepare_difficult_frame_request
        from dataclasses import replace

        session, _video, _track, run, _p, _m = \
            self._make_session_with_infer_run(tmp_path, synthetic_video_path)
        escaped = replace(run, run_id=uuid4(), extra_fields={
            **run.extra_fields, "prediction_path": "../outside.csv"})
        session.record_tracking_run(escaped)
        with pytest.raises(Exception, match="escapes the project directory"):
            prepare_difficult_frame_request(session, escaped.run_id, MiningParams())
