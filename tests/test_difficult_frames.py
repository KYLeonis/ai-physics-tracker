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

    def test_hdf5_roundtrip_keeps_low_confidence_and_missing_rows(self, tmp_path: Path):
        """DLC h5 缺测行以 NaN 落盘（DataFrame 分支）；全帧入口必须保留它们（AC-2）。"""
        pd = pytest.importorskip("pandas")
        pytest.importorskip("tables")

        columns = [("MockDLC", "target", "x"), ("MockDLC", "target", "y"),
                   ("MockDLC", "target", "likelihood")]
        frame_index = list(range(10))
        x = [10.0 + f if f not in (5, 6) else float("nan") for f in frame_index]
        y = [20.0 if f not in (5, 6) else float("nan") for f in frame_index]
        likelihood = [0.2 if f == 3 else (float("nan") if f in (5, 6) else 0.95)
                      for f in frame_index]
        dataframe = pd.DataFrame(list(zip(x, y, likelihood)), index=frame_index,
                                 columns=pd.MultiIndex.from_tuples(columns))
        path = tmp_path / "predictions.h5"
        dataframe.to_hdf(path, key="df_with_missing")
        rows = read_raw_predictions(path, frame_count=10)
        assert len(rows) == 10
        assert rows[3].confidence == pytest.approx(0.2)
        assert isnan(rows[5].pixel_x) and isnan(rows[6].confidence)

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
        ({"weight_jump": -0.1}, "weight_jump must be finite"),
        ({"weight_uncertainty": 0.0, "weight_jump": 0.0,
          "weight_residual": 0.0, "weight_prior": 0.0}, "positive"),
    ])
    def test_invalid_params_rejected(self, kwargs, message):
        with pytest.raises(ValueError, match=message):
            MiningParams(**kwargs)


# ---------------------------------------------------------------------------
# Slice 2 — 纯挖掘策略
# ---------------------------------------------------------------------------

def _smooth_trajectory(frame_count: int = 100, *, confidence: float = 0.95,
                       step_px: float = 2.0) -> list[RawPrediction]:
    """匀速直线合成轨迹（CODE_STANDARD §9.7：解析已知解）。"""
    return [
        RawPrediction(f, 10.0 + step_px * f, 20.0, float(confidence))
        for f in range(frame_count)
    ]


class TestMineDifficultFramesPolicy:
    @staticmethod
    def _mine(rows, *, params=None, zone=(0, 99), fps=10.0, prior=frozenset(), manual=frozenset()):
        from ai_physics_tracker.application.difficult_frames import mine_difficult_frames

        return mine_difficult_frames(
            tuple(rows), zone_start=zone[0], zone_end=zone[1], fps_nominal=fps,
            params=params or MiningParams(top_n=5),
            prior_correct_frames=prior, manual_frames=manual,
        )

    def test_single_jump_point_ranks_first_with_reasons(self):
        rows = _smooth_trajectory()
        rows[40] = RawPrediction(40, 10.0 + 2.0 * 40 + 50.0, 70.0, 0.95)
        outcome = self._mine(rows)
        assert outcome.pool_size >= 1
        # MAD=0 分支下跳变帧两侧 link 同样异常：39/40/41 并列，帧号打破并列
        top = outcome.shortlist[0]
        assert top.frame_index in {39, 40, 41}
        assert "jump_outlier" in top.reasons
        assert "residual_outlier" in top.reasons
        assert top.raw_components["jump"] == pytest.approx(1.0)
        assert 0.0 <= top.components["jump"] <= 1.0
        flagged = {c.frame_index for c in outcome.shortlist if "jump_outlier" in c.reasons}
        assert flagged <= {39, 40, 41}
        assert 40 in {c.frame_index for c in outcome.shortlist}

    def test_consecutive_low_confidence_burst_does_not_monopolize_top_n(self):
        """连续异常段不垄断 Top N：不足时才放宽间隔并如实记录（AC-3）。"""
        rows = _smooth_trajectory()
        for frame in range(60, 71):
            rows[frame] = RawPrediction(frame, 10.0 + 2.0 * frame, 20.0, 0.2)
        params = MiningParams(top_n=3, min_gap_s=1.0)  # 10 fps → 初始间隔 10 帧
        outcome = self._mine(rows, params=params)
        frames = [c.frame_index for c in outcome.shortlist]
        assert frames == [60, 65, 70]
        assert outcome.gap_relaxed is True
        assert outcome.actual_min_gap_frames == 5
        assert outcome.params_snapshot["actual_min_gap_frames"] == 5

    def test_missing_frames_enter_pool_with_missing_reason(self):
        rows = _smooth_trajectory()
        rows[50] = RawPrediction(50, float("nan"), float("nan"), float("nan"))
        outcome = self._mine(rows)
        missing = [c for c in outcome.shortlist if c.frame_index == 50]
        assert missing and "missing" in missing[0].reasons
        assert missing[0].raw_components["uncertainty"] == pytest.approx(1.0)

    def test_prior_correction_neighborhood_flagged(self):
        rows = _smooth_trajectory()
        outcome = self._mine(rows, prior=frozenset({30}))
        prior_frames = {c.frame_index for c in outcome.shortlist
                        if "prior_correction_neighborhood" in c.reasons}
        assert prior_frames  # 28..32 中至少一个进入 shortlist
        assert all(28 <= f <= 32 for f in prior_frames)

    def test_manual_frames_excluded_from_pool(self):
        rows = _smooth_trajectory()
        for frame in (60, 61, 62):
            rows[frame] = RawPrediction(frame, 10.0 + 2.0 * frame, 20.0, 0.2)
        outcome = self._mine(rows, manual=frozenset({60, 61, 62}))
        assert outcome.pool_size == 0  # 唯一异常帧已有 manual 标注 → 池为空
        assert outcome.shortlist == ()

    def test_empty_pool_for_clean_trajectory(self):
        outcome = self._mine(_smooth_trajectory())
        assert outcome.pool_size == 0
        assert outcome.shortlist == ()
        assert outcome.actual_min_gap_frames is None

    def test_zone_bounds_respected(self):
        rows = _smooth_trajectory()
        rows[5] = RawPrediction(5, 10.0 + 2.0 * 5 + 80.0, 90.0, 0.95)
        outcome = self._mine(rows, zone=(50, 99))
        assert all(50 <= c.frame_index <= 99 for c in outcome.shortlist)
        assert outcome.pool_size == 0  # 异常在 zone 外，不进入池

    def test_shortlist_capped_by_diversity_factor(self):
        rows = [
            RawPrediction(f, 10.0 + 2.0 * f, 20.0, 0.2) for f in range(100)
        ]
        params = MiningParams(top_n=3, min_gap_s=0.05)  # 间隔 1 帧不约束
        outcome = self._mine(rows, params=params)
        assert len(outcome.shortlist) <= params.diversity_shortlist_factor * params.top_n

    def test_robust_scores_zscore_branch_hand_computed(self):
        """MAD>0 主统计路径：z 公式（1.4826 常数）与 3.5 阈值边界被手算值钉住。"""
        import numpy as np

        from ai_physics_tracker.application.difficult_frames import _robust_scores

        values = np.array([1.0, 1.2, 0.8, 1.1, 0.9, 1.15, 0.85, 10.0])
        # median = 1.05；|dev| = [.05,.15,.25,.05,.15,.1,.2,8.95] → MAD = 0.15
        scores, anomalies = _robust_scores(values, 3.5)
        expected_z = (10.0 - 1.05) / (1.4826 * 0.15)
        assert scores[-1] == pytest.approx(expected_z, rel=1e-12)
        assert anomalies[-1] is True or anomalies[-1]  # bool 数组
        # 正常抖动的 z ≈ ±1.1 < 3.5，不得判异常；负 z 截断为 0
        assert not anomalies[:7].any()
        assert scores.min() == pytest.approx(0.0)

    def test_noisy_trajectory_jump_flagged_via_zscore(self):
        """带噪轨迹（MAD>0）上单点大位移被 z>=3.5 判为 jump 异常。"""
        rows = []
        for f in range(100):
            x = 10.0 + 2.0 * f + (0.4 if f % 2 else -0.4)  # 距离在 1.2/2.8 交替 → MAD>0
            rows.append(RawPrediction(f, x, 20.0, 0.95))
        rows[50] = RawPrediction(50, 10.0 + 2.0 * 50 + 25.0, 20.0, 0.95)
        outcome = self._mine(rows)
        jump_frames = {c.frame_index for c in outcome.shortlist if "jump_outlier" in c.reasons}
        assert 50 in jump_frames
        assert jump_frames <= {49, 50, 51}  # 正常抖动帧不得误报

    def test_single_candidate_pool_degenerates_to_zero_ranks(self):
        rows = _smooth_trajectory()
        rows[50] = RawPrediction(50, float("nan"), float("nan"), float("nan"))
        outcome = self._mine(rows, params=MiningParams(top_n=3))
        # 池只含缺测帧 50：池内排名无区分度，分量全 0、总分 0，但原因保留
        assert outcome.pool_size == 1
        candidate = outcome.shortlist[0]
        assert candidate.frame_index == 50
        assert set(candidate.components.values()) == {0.0}
        assert candidate.total_score == pytest.approx(0.0)
        assert "missing" in candidate.reasons

    def test_single_frame_zone_and_all_missing_zone(self):
        rows = _smooth_trajectory()
        rows[50] = RawPrediction(50, float("nan"), float("nan"), float("nan"))
        single = self._mine(rows, zone=(50, 50),
                            params=MiningParams(top_n=2, min_gap_s=0.05))
        assert [c.frame_index for c in single.shortlist] == [50]

        all_missing = [RawPrediction(f, float("nan"), float("nan"), float("nan"))
                       for f in range(10)]
        outcome = self._mine(all_missing, zone=(0, 9), params=MiningParams(top_n=2))
        assert outcome.pool_size == 10
        # 全并列 → 归一化 0.5、总分 0.5×权重和；shortlist 是去重排名表（Top N 截断在多样性阶段）
        assert 2 <= len(outcome.shortlist) <= 4 * 2
        assert outcome.shortlist[0].total_score == pytest.approx(0.5)
        frames = sorted(c.frame_index for c in outcome.shortlist)
        assert all(b - a >= 3 for a, b in zip(frames, frames[1:]))  # gap=3 被遵守

    def test_min_gap_seconds_rounds_up_to_frames(self):
        """0.25 s @ 10 fps → 3 帧（ceil），不得低于请求的最小间隔（review M2）。"""
        rows = [RawPrediction(f, 10.0 + 2.0 * f, 20.0, 0.2) for f in range(10)]
        outcome = self._mine(rows, zone=(0, 9),
                             params=MiningParams(top_n=2, min_gap_s=0.25))
        assert outcome.min_gap_frames == 3
        assert outcome.params_snapshot["effective_gap_frames"] == 3

    def test_effective_gap_recorded_after_relaxation(self):
        rows = _smooth_trajectory()
        for frame in range(60, 71):
            rows[frame] = RawPrediction(frame, 10.0 + 2.0 * frame, 20.0, 0.2)
        outcome = self._mine(rows, params=MiningParams(top_n=3, min_gap_s=1.0))
        assert outcome.gap_relaxed is True
        assert outcome.min_gap_frames == 10
        assert outcome.effective_gap_frames == 5  # 10 → 5 后凑齐 3 个
        assert outcome.params_snapshot["effective_gap_frames"] == 5

    def test_same_inputs_same_outcome(self):
        rows = _smooth_trajectory()
        rows[40] = RawPrediction(40, 10.0 + 2.0 * 40 + 50.0, 70.0, 0.9)
        for frame in (60, 62, 64):
            rows[frame] = RawPrediction(frame, 10.0 + 2.0 * frame, 20.0, 0.3)
        first = self._mine(rows)
        second = self._mine(rows)
        assert first == second

    def test_rejects_non_contiguous_predictions(self):
        rows = _smooth_trajectory()
        rows.pop(50)
        with pytest.raises(ValueError, match="contiguous"):
            self._mine(rows, zone=(0, 98))

    def test_rejects_zone_out_of_range(self):
        with pytest.raises(ValueError, match="working zone"):
            self._mine(_smooth_trajectory(), zone=(0, 100))

    def test_component_scores_finite_and_normalized(self):
        rows = _smooth_trajectory()
        rows[40] = RawPrediction(40, 10.0 + 2.0 * 40 + 50.0, 70.0, 0.9)
        for frame in range(60, 71):
            rows[frame] = RawPrediction(frame, 10.0 + 2.0 * frame, 20.0, 0.3)
        outcome = self._mine(rows)
        for candidate in outcome.shortlist:
            assert candidate.reasons
            for value in candidate.components.values():
                assert -1e-12 <= value <= 1.0 + 1e-12
            for value in candidate.raw_components.values():
                assert value == value and abs(value) != float("inf")
            assert candidate.total_score >= 0.0


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

        run = create_tracking_run(
            video.video_id, track.track_id, "infer", engine="dlc",
            engine_version="3.0.1-mock", config={},
        )
        run_dir = root / "data" / "engines" / str(run.run_id)
        run_dir.mkdir(parents=True)
        prediction_path = _write_prediction_csv(run_dir / "predictions.csv")
        model_path = run_dir / "model-snapshot.pt"
        model_path.write_bytes(b"fake model weights")
        model_stat = model_path.stat()
        prediction_stat = prediction_path.stat()

        run = mark_run_completed(
            run, model_snapshot=f"data/engines/{run.run_id}/model-snapshot.pt",
        )
        run = replace(run, extra_fields={
            "prediction_path": f"data/engines/{run.run_id}/predictions.csv",
            "model_file_info": [model_stat.st_size, model_stat.st_mtime_ns],
            "prediction_file_info": [prediction_stat.st_size, prediction_stat.st_mtime_ns],
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

    def test_reject_absolute_prediction_reference(self, tmp_path: Path, synthetic_video_path: Path):
        from ai_physics_tracker.application.difficult_frame_job import prepare_difficult_frame_request
        from dataclasses import replace

        session, _video, _track, run, prediction_path, _m = \
            self._make_session_with_infer_run(tmp_path, synthetic_video_path)
        absolute = replace(run, run_id=uuid4(), extra_fields={
            **run.extra_fields, "prediction_path": str(prediction_path.resolve())})
        session.record_tracking_run(absolute)
        with pytest.raises(Exception, match="project-relative"):
            prepare_difficult_frame_request(session, absolute.run_id, MiningParams())

    def test_reject_artifact_from_another_run_directory(self, tmp_path: Path, synthetic_video_path: Path):
        """R2.1 不混合不同 run：指向别的 run 目录的预测产物被拒绝。"""
        from ai_physics_tracker.application.difficult_frame_job import prepare_difficult_frame_request
        from dataclasses import replace

        session, _video, _track, run, _p, _m = \
            self._make_session_with_infer_run(tmp_path, synthetic_video_path)
        foreign_dir = session.project_root / "data" / "engines" / str(uuid4())
        foreign_dir.mkdir(parents=True)
        foreign = replace(run, run_id=uuid4(), extra_fields={
            **run.extra_fields, "prediction_path": f"data/engines/{foreign_dir.name}/predictions.csv"})
        session.record_tracking_run(foreign)
        with pytest.raises(Exception, match="does not belong to this run"):
            prepare_difficult_frame_request(session, foreign.run_id, MiningParams())

    def test_reject_tampered_prediction_fingerprint(self, tmp_path: Path, synthetic_video_path: Path):
        from ai_physics_tracker.application.difficult_frame_job import prepare_difficult_frame_request

        session, _video, _track, run, prediction_path, _m = \
            self._make_session_with_infer_run(tmp_path, synthetic_video_path)
        _write_prediction_csv(prediction_path, frame_count=10)  # 重写 → mtime 变化
        with pytest.raises(Exception, match="artifact has changed"):
            prepare_difficult_frame_request(session, run.run_id, MiningParams())

    def test_legacy_run_without_fingerprints_is_tolerated(self, tmp_path: Path, synthetic_video_path: Path):
        """旧 run 无指纹基线：按现状采集指纹，不拒绝（兼容语义被测试钉住）。"""
        from ai_physics_tracker.application.difficult_frame_job import prepare_difficult_frame_request
        from dataclasses import replace

        session, _video, _track, _run, _p, _m = \
            self._make_session_with_infer_run(tmp_path, synthetic_video_path)
        legacy_id = uuid4()
        legacy_dir = session.project_root / "data" / "engines" / str(legacy_id)
        legacy_dir.mkdir(parents=True)
        legacy_prediction = _write_prediction_csv(legacy_dir / "predictions.csv")
        (legacy_dir / "model-snapshot.pt").write_bytes(b"legacy model")
        legacy = replace(
            _run, run_id=legacy_id,
            model_snapshot=f"data/engines/{legacy_id}/model-snapshot.pt",
            extra_fields={"prediction_path": f"data/engines/{legacy_id}/predictions.csv"},
        )
        session.record_tracking_run(legacy)
        job = prepare_difficult_frame_request(session, legacy_id, MiningParams())
        stat = legacy_prediction.stat()
        assert job.prediction_file_info == (stat.st_size, stat.st_mtime_ns)

    def test_reject_missing_model_snapshot_file(self, tmp_path: Path, synthetic_video_path: Path):
        from ai_physics_tracker.application.difficult_frame_job import prepare_difficult_frame_request

        session, _video, _track, run, _p, model_path = \
            self._make_session_with_infer_run(tmp_path, synthetic_video_path)
        model_path.unlink()
        with pytest.raises(Exception, match="model snapshot of this run is missing"):
            prepare_difficult_frame_request(session, run.run_id, MiningParams())

    def test_reject_missing_video_file(self, tmp_path: Path, synthetic_video_path: Path):
        from ai_physics_tracker.application.difficult_frame_job import prepare_difficult_frame_request

        session, _video, _track, run, _p, _m = \
            self._make_session_with_infer_run(tmp_path, synthetic_video_path)
        synthetic_video_path.unlink()
        with pytest.raises(Exception, match="Video file is missing"):
            prepare_difficult_frame_request(session, run.run_id, MiningParams())

    def test_reject_run_without_prediction_reference(self, tmp_path: Path, synthetic_video_path: Path):
        from ai_physics_tracker.application.difficult_frame_job import prepare_difficult_frame_request
        from dataclasses import replace

        session, _video, _track, run, _p, _m = \
            self._make_session_with_infer_run(tmp_path, synthetic_video_path)
        no_ref = replace(run, run_id=uuid4(),
                         extra_fields={"model_file_info": run.extra_fields["model_file_info"]})
        session.record_tracking_run(no_ref)
        with pytest.raises(Exception, match="no stored raw prediction artifact"):
            prepare_difficult_frame_request(session, no_ref.run_id, MiningParams())


# ---------------------------------------------------------------------------
# Slice 3 — 显式候选集（视觉多样性复用 5.1 K-means）
# ---------------------------------------------------------------------------

class _FakeQueue:
    """最简 queue：只收集消息，不阻塞。"""

    def __init__(self) -> None:
        self.items: list = []

    def put(self, item) -> None:
        self.items.append(item)


class _FakeCancelEvent:
    def __init__(self, *, preset: bool = False) -> None:
        self._set = preset

    def is_set(self) -> bool:
        return self._set

    def set(self) -> None:
        self._set = True


class TestFrameSelectionCandidateSet:
    def _request(self, tmp_path: Path, **overrides):
        from ai_physics_tracker.application.tracking_types import FrameSelectionRequest

        kwargs = dict(
            video_id=uuid4(), track_id=uuid4(),
            video_path=tmp_path / "v.mp4", frame_count=10,
            zone_start=0, zone_end=9, n_frames=3, algorithm="kmeans",
            excluded_frames=frozenset(),
        )
        kwargs.update(overrides)
        return FrameSelectionRequest(**kwargs)

    def test_candidate_frames_out_of_range_rejected(self, tmp_path: Path):
        with pytest.raises(ValueError, match="candidate_frames"):
            self._request(tmp_path, candidate_frames=frozenset({10}))

    def test_candidate_frames_zone_intersection(self):
        """显式候选集与 working zone/排除集取交集，不越界、不选排除帧。"""
        from ai_physics_tracker.infrastructure.mock_engine_adapter import MockEngineAdapter

        request = self._request(
            Path("/tmp"), frame_count=12, zone_start=4, zone_end=9, algorithm="uniform",
            excluded_frames=frozenset({5}), candidate_frames=frozenset({1, 5, 6, 8, 11}),
        )
        result = MockEngineAdapter().suggest_frames(request, _FakeQueue(), _FakeCancelEvent())
        assert set(result.suggested_frames) <= {6, 8}

    def test_kmeans_honors_explicit_candidates_on_synthetic_video(self, tmp_path: Path):
        import cv2
        import numpy as np

        from ai_physics_tracker.infrastructure.dlc_adapter import DLCAdapter

        video_path = tmp_path / "motion.mp4"
        writer = cv2.VideoWriter(str(video_path), cv2.VideoWriter_fourcc(*"mp4v"),
                                 30.0, (64, 64))
        for i in range(12):
            img = np.zeros((64, 64, 3), dtype=np.uint8)
            cv2.circle(img, (8 + 4 * i, 32), 5, (0, 255, 0), -1)
            writer.write(img)
        writer.release()

        candidates = frozenset({2, 5, 8, 11})
        request = self._request(
            tmp_path, video_path=video_path, frame_count=12, zone_start=0, zone_end=11,
            n_frames=2, candidate_frames=candidates, seed=7,
        )
        result = DLCAdapter().suggest_frames(request, _FakeQueue(), _FakeCancelEvent())
        assert set(result.suggested_frames) <= candidates
        assert len(result.suggested_frames) == result.actual_n
        repeat = DLCAdapter().suggest_frames(request, _FakeQueue(), _FakeCancelEvent())
        assert repeat.suggested_frames == result.suggested_frames  # 同 seed 可复现


# ---------------------------------------------------------------------------
# Slice 3 — 后台挖掘 worker / 结果读取
# ---------------------------------------------------------------------------

class TestDifficultFrameWorker:
    @staticmethod
    def _prepared(tmp_path: Path, synthetic_video_path: Path, *, top_n: int = 3,
                  low_conf_frames=range(1, 9), params: MiningParams | None = None):
        from ai_physics_tracker.application.difficult_frame_job import (
            prepare_difficult_frame_request,
        )

        session, video, track, run, prediction_path, _model = \
            TestPrepareDifficultFrameRequest._make_session_with_infer_run(
                tmp_path, synthetic_video_path)
        # 写入更多低置信度帧，保证 pool > top_n 以触发视觉多样性路径
        lines = [
            "scorer,MockDLC,MockDLC,MockDLC",
            "bodyparts,target,target,target",
            "coords,x,y,likelihood",
        ]
        for frame in range(10):
            if frame in (5, 6):
                x, y, likelihood = "NaN", "NaN", "NaN"
            elif frame in low_conf_frames:
                x, y, likelihood = f"{10.0 + 2.0 * frame}", "20.0", "0.2"
            else:
                x, y, likelihood = f"{10.0 + 2.0 * frame}", "20.0", "0.95"
            lines.append(f"{frame},{x},{y},{likelihood}")
        prediction_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

        # 重写后同步更新 run 的指纹基线（模拟真实推理完成时的记录语义）
        from dataclasses import replace as _replace

        stat = prediction_path.stat()
        session.update_tracking_run(_replace(run, extra_fields={
            **run.extra_fields,
            "prediction_file_info": [stat.st_size, stat.st_mtime_ns],
        }))

        job = prepare_difficult_frame_request(
            session, run.run_id, params or MiningParams(top_n=top_n, min_gap_s=0.05))
        return session, run, job

    def test_worker_completes_writes_and_reads_result(self, tmp_path: Path, synthetic_video_path: Path):
        from ai_physics_tracker.application.difficult_frame_job import (
            read_difficult_frame_result, run_difficult_frame_worker,
        )

        session, run, job = self._prepared(tmp_path, synthetic_video_path)
        request_id = uuid4()
        payload = run_difficult_frame_worker(
            request_id, _FakeQueue(), _FakeCancelEvent(), job, MockEngineAdapter())
        assert payload["status"] == "completed"

        result = read_difficult_frame_result(session.project_root, request_id)
        assert result.run_id == run.run_id
        assert result.request_id == request_id
        assert 0 < len(result.candidates) <= 3
        assert result.actual_n == len(result.candidates)
        assert result.diversity_status == "applied"  # pool(≈9) > top_n(3)
        scores = [c.total_score for c in result.candidates]
        assert scores == sorted(scores, reverse=True)
        assert all(c.reasons for c in result.candidates)
        assert result.params_snapshot["diversity_status"] == "applied"

    def test_worker_skips_diversity_when_shortlist_small(self, tmp_path: Path, synthetic_video_path: Path):
        from ai_physics_tracker.application.difficult_frame_job import (
            read_difficult_frame_result, run_difficult_frame_worker,
        )

        # 只有 2 个异常帧（NaN 5/6），top_n=3 → shortlist ≤ top_n，无需多样性
        session, run, job = self._prepared(
            tmp_path, synthetic_video_path, top_n=3, low_conf_frames=range(0))
        request_id = uuid4()
        run_difficult_frame_worker(request_id, _FakeQueue(), _FakeCancelEvent(),
                                   job, MockEngineAdapter())
        result = read_difficult_frame_result(session.project_root, request_id)
        assert result.diversity_status == "not_needed"

    def test_worker_cancelled_before_start(self, tmp_path: Path, synthetic_video_path: Path):
        from concurrent.futures import CancelledError as _CancelledError

        from ai_physics_tracker.application.difficult_frame_job import run_difficult_frame_worker

        _session, _run, job = self._prepared(tmp_path, synthetic_video_path)
        with pytest.raises(_CancelledError):
            run_difficult_frame_worker(uuid4(), _FakeQueue(), _FakeCancelEvent(preset=True),
                                       job, MockEngineAdapter())

    def test_worker_rejects_tampered_prediction(self, tmp_path: Path, synthetic_video_path: Path):
        from ai_physics_tracker.application.difficult_frame_job import run_difficult_frame_worker
        from ai_physics_tracker.application.project_session import ProjectSessionError

        session, _run, job = self._prepared(tmp_path, synthetic_video_path)
        job.mining_request.prediction_path.write_text("tampered", encoding="utf-8")
        with pytest.raises(ProjectSessionError, match="Prediction file changed"):
            run_difficult_frame_worker(uuid4(), _FakeQueue(), _FakeCancelEvent(),
                                       job, MockEngineAdapter())

    def test_worker_deterministic_with_same_seed(self, tmp_path: Path, synthetic_video_path: Path):
        from ai_physics_tracker.application.difficult_frame_job import (
            read_difficult_frame_result, run_difficult_frame_worker,
        )
        from ai_physics_tracker.infrastructure.dlc_adapter import DLCAdapter

        session, run, job = self._prepared(
            tmp_path, synthetic_video_path, top_n=3,
            params=MiningParams(top_n=3, min_gap_s=0.05, seed=11))
        # 两次运行（真实 DLCAdapter K-means，固定 seed）→ 相同候选帧
        first_id, second_id = uuid4(), uuid4()
        run_difficult_frame_worker(first_id, _FakeQueue(), _FakeCancelEvent(), job, DLCAdapter())
        run_difficult_frame_worker(second_id, _FakeQueue(), _FakeCancelEvent(), job, DLCAdapter())
        first = read_difficult_frame_result(session.project_root, first_id)
        second = read_difficult_frame_result(session.project_root, second_id)
        assert [c.frame_index for c in first.candidates] == [c.frame_index for c in second.candidates]

    def test_worker_writes_only_inside_request_directory(self, tmp_path: Path, synthetic_video_path: Path):
        from ai_physics_tracker.application.difficult_frame_job import run_difficult_frame_worker

        session, _run, job = self._prepared(tmp_path, synthetic_video_path)
        root = session.project_root
        before = {p.relative_to(root) for p in root.rglob("*") if p.is_file()}
        request_id = uuid4()
        run_difficult_frame_worker(request_id, _FakeQueue(), _FakeCancelEvent(),
                                   job, MockEngineAdapter())
        after = {p.relative_to(root) for p in root.rglob("*") if p.is_file()}
        added = after - before
        assert added == {Path("data/engines") / str(request_id) / "difficult-frames-result.json"}
