"""代表帧选取（Phase 5.1 R1 / AC-1）单元测试。

使用 MockEngineAdapter，不依赖 DLC、Qt 或真实视频。
覆盖：数据类构造/校验、uniform 辅助函数、mock suggest_frames、
      后台 worker 序列化、取消语义、working zone 约束、
      candidates 不足 N、全 excluded 边界。
"""

from __future__ import annotations

import json
from concurrent.futures import CancelledError
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest

from ai_physics_tracker.application.tracking_types import (
    FrameSelectionRequest,
    FrameSelectionResult,
)
from ai_physics_tracker.infrastructure.mock_engine_adapter import MockEngineAdapter


# ---------------------------------------------------------------------------
# 辅助工厂
# ---------------------------------------------------------------------------

def _make_request(
    *,
    frame_count: int = 100,
    zone_start: int = 0,
    zone_end: int = 99,
    n_frames: int = 10,
    algorithm: str = "uniform",
    excluded: frozenset | None = None,
    seed: int = 0,
    cluster_step: int = 1,
) -> FrameSelectionRequest:
    return FrameSelectionRequest(
        video_id=uuid4(),
        track_id=uuid4(),
        video_path=Path("/tmp/fake_video.mp4"),
        frame_count=frame_count,
        zone_start=zone_start,
        zone_end=zone_end,
        n_frames=n_frames,
        algorithm=algorithm,
        excluded_frames=excluded if excluded is not None else frozenset(),
        seed=seed,
        cluster_step=cluster_step,
    )


class _FakeQueue:
    """最简 queue：只收集消息，不阻塞。"""

    def __init__(self) -> None:
        self.items: list[Any] = []

    def put(self, item: Any) -> None:
        self.items.append(item)


class _FakeCancelEvent:
    """模拟 multiprocessing.Event，支持手动置位。"""

    def __init__(self, *, preset: bool = False) -> None:
        self._set = preset

    def is_set(self) -> bool:
        return self._set

    def set(self) -> None:
        self._set = True


# ---------------------------------------------------------------------------
# FrameSelectionRequest 构造与校验
# ---------------------------------------------------------------------------

class TestFrameSelectionRequest:
    def test_valid_construction(self):
        req = _make_request()
        assert req.n_frames == 10
        assert req.zone_start == 0
        assert req.zone_end == 99
        assert req.algorithm == "uniform"

    def test_invalid_algorithm_raises(self):
        with pytest.raises(ValueError, match="algorithm"):
            _make_request(algorithm="unsupported")

    def test_n_frames_zero_raises(self):
        with pytest.raises(ValueError, match="n_frames"):
            _make_request(n_frames=0)

    def test_cluster_step_zero_raises(self):
        with pytest.raises(ValueError, match="cluster_step"):
            _make_request(cluster_step=0)

    def test_zone_out_of_range_raises(self):
        # zone_end >= frame_count
        with pytest.raises(ValueError, match="working zone"):
            _make_request(frame_count=50, zone_start=0, zone_end=50)

    def test_zone_start_gt_zone_end_raises(self):
        with pytest.raises(ValueError, match="working zone"):
            _make_request(zone_start=20, zone_end=10)

    def test_invalid_color_mode_raises(self):
        with pytest.raises(ValueError, match="color_mode"):
            FrameSelectionRequest(
                video_id=uuid4(), track_id=uuid4(),
                video_path=Path("/tmp/v.mp4"), frame_count=100,
                zone_start=0, zone_end=99, n_frames=5,
                algorithm="uniform", excluded_frames=frozenset(),
                color_mode="hsv",
            )

    def test_is_frozen(self):
        req = _make_request()
        with pytest.raises((AttributeError, TypeError)):
            req.n_frames = 99  # type: ignore[misc]


# ---------------------------------------------------------------------------
# FrameSelectionResult 构造
# ---------------------------------------------------------------------------

class TestFrameSelectionResult:
    def test_valid_construction(self):
        res = FrameSelectionResult(
            request_algorithm="uniform",
            suggested_frames=(0, 10, 20),
            actual_n=3,
            excluded_count=2,
            params_snapshot={"algorithm": "uniform"},
        )
        assert res.actual_n == 3
        assert 10 in res.suggested_frames


# ---------------------------------------------------------------------------
# MockEngineAdapter.suggest_frames
# ---------------------------------------------------------------------------

class TestMockSuggestFrames:
    def _run(self, request: FrameSelectionRequest) -> FrameSelectionResult:
        adapter = MockEngineAdapter()
        queue = _FakeQueue()
        cancel = _FakeCancelEvent()
        return adapter.suggest_frames(request, queue, cancel)

    def test_uniform_returns_n_frames(self):
        result = self._run(_make_request(n_frames=5, algorithm="uniform"))
        assert result.actual_n == 5
        assert len(result.suggested_frames) == 5

    def test_kmeans_algorithm_label_preserved(self):
        result = self._run(_make_request(n_frames=3, algorithm="kmeans"))
        assert result.request_algorithm == "kmeans"

    def test_frames_within_working_zone(self):
        result = self._run(_make_request(zone_start=20, zone_end=49, n_frames=5))
        for f in result.suggested_frames:
            assert 20 <= f <= 49, f"frame {f} outside zone [20, 49]"

    def test_excluded_frames_not_in_result(self):
        excluded = frozenset({10, 20, 30, 40, 50})
        result = self._run(_make_request(n_frames=8, excluded=excluded))
        for f in result.suggested_frames:
            assert f not in excluded, f"excluded frame {f} appeared in result"

    def test_excluded_count_reported(self):
        # zone [0,99]，excluded 中有 5 帧在 zone 内
        excluded = frozenset({5, 15, 25, 35, 45})
        result = self._run(_make_request(n_frames=5, excluded=excluded))
        assert result.excluded_count == 5

    def test_no_duplicate_frames(self):
        result = self._run(_make_request(n_frames=20, zone_start=0, zone_end=19))
        assert len(result.suggested_frames) == len(set(result.suggested_frames))

    def test_frames_are_sorted(self):
        result = self._run(_make_request(n_frames=10))
        assert list(result.suggested_frames) == sorted(result.suggested_frames)

    def test_not_enough_candidates_returns_available(self):
        # zone 只有 5 帧，要求 10 帧
        result = self._run(_make_request(
            frame_count=100, zone_start=0, zone_end=4, n_frames=10
        ))
        assert result.actual_n <= 5
        assert len(result.suggested_frames) == result.actual_n

    def test_all_excluded_returns_empty(self):
        # zone [0, 4]，全部排除
        excluded = frozenset({0, 1, 2, 3, 4})
        result = self._run(_make_request(
            frame_count=100, zone_start=0, zone_end=4, n_frames=5, excluded=excluded
        ))
        assert result.actual_n == 0
        assert result.suggested_frames == ()

    def test_params_snapshot_complete(self):
        result = self._run(_make_request(n_frames=5, seed=42, cluster_step=2))
        snap = result.params_snapshot
        assert snap["algorithm"] == "uniform"
        assert snap["n_frames"] == 5
        assert snap["seed"] == 42
        assert snap["cluster_step"] == 2
        assert "zone_start" in snap
        assert "zone_end" in snap

    def test_cancel_before_start_raises(self):
        adapter = MockEngineAdapter()
        queue = _FakeQueue()
        cancel = _FakeCancelEvent(preset=True)
        with pytest.raises(CancelledError):
            adapter.suggest_frames(_make_request(), queue, cancel)

    def test_no_track_points_created(self):
        # suggest_frames 只返回帧号，不修改任何存储
        result = self._run(_make_request(n_frames=5))
        assert isinstance(result.suggested_frames, tuple)
        assert all(isinstance(f, int) for f in result.suggested_frames)

    def test_n_frames_one(self):
        result = self._run(_make_request(n_frames=1))
        assert result.actual_n == 1
        assert len(result.suggested_frames) == 1

    def test_narrow_zone_single_frame(self):
        # zone [50, 50]，只有一帧可选
        result = self._run(_make_request(
            frame_count=100, zone_start=50, zone_end=50, n_frames=5
        ))
        assert result.actual_n == 1
        assert result.suggested_frames == (50,)


# ---------------------------------------------------------------------------
# _uniform_suggest 辅助函数直接测试（通过 dlc_adapter 访问）
# ---------------------------------------------------------------------------

class TestUniformSuggest:
    def _uniform(self, request: FrameSelectionRequest) -> list[int]:
        from ai_physics_tracker.infrastructure.dlc_adapter import _uniform_suggest
        return _uniform_suggest(request)

    def test_uniform_basic(self):
        req = _make_request(zone_start=0, zone_end=99, n_frames=5)
        result = self._uniform(req)
        assert len(result) == 5
        assert result == sorted(result)

    def test_uniform_excludes_manual_frames(self):
        excluded = frozenset({10, 50, 90})
        req = _make_request(zone_start=0, zone_end=99, n_frames=5, excluded=excluded)
        result = self._uniform(req)
        for f in result:
            assert f not in excluded

    def test_uniform_zone_constraint(self):
        req = _make_request(zone_start=30, zone_end=59, n_frames=5)
        result = self._uniform(req)
        for f in result:
            assert 30 <= f <= 59

    def test_uniform_not_enough_candidates(self):
        req = _make_request(frame_count=100, zone_start=0, zone_end=2, n_frames=10)
        result = self._uniform(req)
        assert len(result) <= 3

    def test_uniform_all_excluded(self):
        excluded = frozenset({0, 1, 2})
        req = _make_request(frame_count=100, zone_start=0, zone_end=2, n_frames=5, excluded=excluded)
        result = self._uniform(req)
        assert result == []

    def test_uniform_no_duplicates(self):
        req = _make_request(zone_start=0, zone_end=9, n_frames=5)
        result = self._uniform(req)
        assert len(result) == len(set(result))


# ---------------------------------------------------------------------------
# run_frame_selection_worker（集成：不启动子进程，直接在测试进程内调用）
# ---------------------------------------------------------------------------

class TestRunFrameSelectionWorker:
    def test_worker_writes_result_json(self, tmp_path: Path):
        from ai_physics_tracker.application.tracking_job import (
            run_frame_selection_worker,
            FrameSelectionJobRequest,
        )

        # 创建假视频文件（只需存在，worker 会做 stat 校验）
        fake_video = tmp_path / "video.mp4"
        fake_video.write_bytes(b"fake")

        req = FrameSelectionRequest(
            video_id=uuid4(),
            track_id=uuid4(),
            video_path=fake_video,
            frame_count=50,
            zone_start=0,
            zone_end=49,
            n_frames=5,
            algorithm="uniform",
            excluded_frames=frozenset(),
        )
        stat = fake_video.stat()
        job = FrameSelectionJobRequest(
            selection_request=req,
            project_root=tmp_path,
            video_file_info=(stat.st_size, stat.st_mtime_ns),
        )
        request_id = uuid4()
        queue = _FakeQueue()
        cancel = _FakeCancelEvent()
        adapter = MockEngineAdapter()

        result = run_frame_selection_worker(request_id, queue, cancel, job, adapter)

        assert result["status"] == "completed"
        result_file = tmp_path / result["result_path"]
        assert result_file.is_file()
        payload = json.loads(result_file.read_text(encoding="utf-8"))
        assert payload["actual_n"] <= 5
        assert isinstance(payload["suggested_frames"], list)

    def test_worker_file_changed_raises(self, tmp_path: Path):
        from ai_physics_tracker.application.tracking_job import (
            run_frame_selection_worker,
            FrameSelectionJobRequest,
        )
        from ai_physics_tracker.application.project_session import ProjectSessionError

        fake_video = tmp_path / "video.mp4"
        fake_video.write_bytes(b"fake")
        req = FrameSelectionRequest(
            video_id=uuid4(), track_id=uuid4(), video_path=fake_video,
            frame_count=50, zone_start=0, zone_end=49, n_frames=5,
            algorithm="uniform", excluded_frames=frozenset(),
        )
        # 用篡改后的 file_info 触发校验失败
        job = FrameSelectionJobRequest(
            selection_request=req, project_root=tmp_path,
            video_file_info=(9999999, 0),
        )
        with pytest.raises(ProjectSessionError, match="changed"):
            run_frame_selection_worker(uuid4(), _FakeQueue(), _FakeCancelEvent(), job, MockEngineAdapter())

    def test_worker_cancel_before_suggest(self, tmp_path: Path):
        from ai_physics_tracker.application.tracking_job import (
            run_frame_selection_worker,
            FrameSelectionJobRequest,
        )

        fake_video = tmp_path / "video.mp4"
        fake_video.write_bytes(b"fake")
        req = FrameSelectionRequest(
            video_id=uuid4(), track_id=uuid4(), video_path=fake_video,
            frame_count=50, zone_start=0, zone_end=49, n_frames=5,
            algorithm="uniform", excluded_frames=frozenset(),
        )
        stat = fake_video.stat()
        job = FrameSelectionJobRequest(
            selection_request=req, project_root=tmp_path,
            video_file_info=(stat.st_size, stat.st_mtime_ns),
        )
        cancel = _FakeCancelEvent(preset=True)
        res = run_frame_selection_worker(uuid4(), _FakeQueue(), cancel, job, MockEngineAdapter())
        assert res.get("status") == "cancelled"


# ---------------------------------------------------------------------------
# read_frame_selection_result
# ---------------------------------------------------------------------------

class TestReadFrameSelectionResult:
    def test_roundtrip(self, tmp_path: Path):
        from ai_physics_tracker.application.tracking_job import (
            read_frame_selection_result,
            run_frame_selection_worker,
            FrameSelectionJobRequest,
        )

        fake_video = tmp_path / "video.mp4"
        fake_video.write_bytes(b"fake")
        req = FrameSelectionRequest(
            video_id=uuid4(), track_id=uuid4(), video_path=fake_video,
            frame_count=50, zone_start=0, zone_end=49, n_frames=5,
            algorithm="uniform", excluded_frames=frozenset(),
        )
        stat = fake_video.stat()
        job = FrameSelectionJobRequest(
            selection_request=req, project_root=tmp_path,
            video_file_info=(stat.st_size, stat.st_mtime_ns),
        )
        request_id = uuid4()
        run_frame_selection_worker(request_id, _FakeQueue(), _FakeCancelEvent(), job, MockEngineAdapter())

        result = read_frame_selection_result(tmp_path, request_id)
        assert isinstance(result, FrameSelectionResult)
        assert result.actual_n >= 0
        assert all(isinstance(f, int) for f in result.suggested_frames)

    def test_missing_file_raises(self, tmp_path: Path):
        from ai_physics_tracker.application.tracking_job import read_frame_selection_result
        from ai_physics_tracker.application.project_session import ProjectSessionError

        with pytest.raises(ProjectSessionError, match="not found"):
            read_frame_selection_result(tmp_path, uuid4())


# ---------------------------------------------------------------------------
# prepare_frame_selection_request 单元测试
# ---------------------------------------------------------------------------

class TestPrepareFrameSelectionRequest:
    def _make_session_with_video_and_track(self, tmp_path: Path, synthetic_video_path: Path):
        from ai_physics_tracker.application.project_session import ProjectSession
        from ai_physics_tracker.application.video import VideoStreamInfo
        from ai_physics_tracker.domain.project import create_project
        from ai_physics_tracker.infrastructure.project_repository import ProjectRepository

        repo = ProjectRepository()
        session = ProjectSession(repo, create_project("test_proj"))
        info = VideoStreamInfo(
            width_px=64,
            height_px=48,
            fps_container=10.0,
            frame_count=10,
            container_format="avi",
            timing_status="cfr",
        )
        video, timeline = session.register_external_video(synthetic_video_path, info)
        track = session.add_track(video.video_id, "TrackA")

        proj_dir = tmp_path / "proj"
        session.save_as(proj_dir)
        return session, video, track

    def test_prepare_valid_request(self, tmp_path: Path, synthetic_video_path: Path):
        from ai_physics_tracker.application.tracking_job import prepare_frame_selection_request

        session, video, track = self._make_session_with_video_and_track(tmp_path, synthetic_video_path)
        session.mark_point(track.track_id, 2, 10.0, 10.0)
        session.mark_point(track.track_id, 4, 20.0, 20.0)

        job_req = prepare_frame_selection_request(
            session, track.track_id, n_frames=3, algorithm="uniform", seed=42
        )
        sel = job_req.selection_request
        assert sel.video_id == video.video_id
        assert sel.track_id == track.track_id
        assert sel.n_frames == 3
        assert sel.algorithm == "uniform"
        assert sel.seed == 42
        assert 2 in sel.excluded_frames
        assert 4 in sel.excluded_frames
        assert sel.zone_start == 0
        assert sel.zone_end == 9
        assert sel.frame_count == 10

    def test_prepare_unsaved_project_raises(self, tmp_path: Path):
        from ai_physics_tracker.application.project_session import ProjectSession, ProjectSessionError
        from ai_physics_tracker.application.tracking_job import prepare_frame_selection_request
        from ai_physics_tracker.domain.project import create_project
        from ai_physics_tracker.infrastructure.project_repository import ProjectRepository

        session = ProjectSession(ProjectRepository(), create_project("unsaved"))
        with pytest.raises(ProjectSessionError, match="Save the project"):
            prepare_frame_selection_request(session, uuid4(), 5)

    def test_prepare_missing_track_raises(self, tmp_path: Path, synthetic_video_path: Path):
        from ai_physics_tracker.application.project_session import ProjectSessionError
        from ai_physics_tracker.application.tracking_job import prepare_frame_selection_request

        session, video, track = self._make_session_with_video_and_track(tmp_path, synthetic_video_path)
        with pytest.raises(ProjectSessionError, match="Track not found"):
            prepare_frame_selection_request(session, uuid4(), 5)


# ---------------------------------------------------------------------------
# DLCAdapter.suggest_frames 合成视频测试（Uniform & K-means）
# ---------------------------------------------------------------------------

class TestDLCAdapterSuggestFramesSynthetic:
    @pytest.fixture
    def synthetic_video(self, tmp_path: Path) -> tuple[Path, int]:
        import cv2
        import numpy as np

        video_path = tmp_path / "synthetic_motion.mp4"
        fps = 30.0
        frame_count = 30
        writer = cv2.VideoWriter(str(video_path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (64, 64))
        for i in range(frame_count):
            img = np.zeros((64, 64, 3), dtype=np.uint8)
            # 每一帧画一个移动的圆，使各帧具有不同视觉特征
            cv2.circle(img, (10 + i, 10 + i), 5, (0, 255, 0), -1)
            writer.write(img)
        writer.release()
        return video_path, frame_count

    def test_dlc_adapter_uniform_synthetic(self, synthetic_video):
        from ai_physics_tracker.infrastructure.dlc_adapter import DLCAdapter

        video_path, frame_count = synthetic_video
        adapter = DLCAdapter()
        req = FrameSelectionRequest(
            video_id=uuid4(),
            track_id=uuid4(),
            video_path=video_path,
            frame_count=frame_count,
            zone_start=0,
            zone_end=frame_count - 1,
            n_frames=5,
            algorithm="uniform",
            excluded_frames=frozenset({10, 20}),
        )
        res = adapter.suggest_frames(req, _FakeQueue(), _FakeCancelEvent())
        assert res.request_algorithm == "uniform"
        assert res.actual_n == 5
        assert len(res.suggested_frames) == 5
        for f in res.suggested_frames:
            assert 0 <= f < frame_count
            assert f not in {10, 20}

    def test_dlc_adapter_kmeans_synthetic(self, synthetic_video):
        from ai_physics_tracker.infrastructure.dlc_adapter import DLCAdapter

        video_path, frame_count = synthetic_video
        adapter = DLCAdapter()
        req = FrameSelectionRequest(
            video_id=uuid4(),
            track_id=uuid4(),
            video_path=video_path,
            frame_count=frame_count,
            zone_start=0,
            zone_end=frame_count - 1,
            n_frames=4,
            algorithm="kmeans",
            excluded_frames=frozenset({0}),
            seed=42,
            cluster_step=1,
            color_mode="rgb",
        )
        res = adapter.suggest_frames(req, _FakeQueue(), _FakeCancelEvent())
        assert res.request_algorithm == "kmeans"
        assert 1 <= res.actual_n <= 4
        assert len(res.suggested_frames) == res.actual_n
        for f in res.suggested_frames:
            assert 0 <= f < frame_count
            assert f != 0
        assert list(res.suggested_frames) == sorted(set(res.suggested_frames))

    def test_dlc_adapter_kmeans_cancelled(self, synthetic_video):
        from ai_physics_tracker.infrastructure.dlc_adapter import DLCAdapter

        video_path, frame_count = synthetic_video
        adapter = DLCAdapter()
        req = FrameSelectionRequest(
            video_id=uuid4(),
            track_id=uuid4(),
            video_path=video_path,
            frame_count=frame_count,
            zone_start=0,
            zone_end=frame_count - 1,
            n_frames=5,
            algorithm="kmeans",
            excluded_frames=frozenset(),
        )
        cancel = _FakeCancelEvent(preset=True)
        with pytest.raises(CancelledError):
            adapter.suggest_frames(req, _FakeQueue(), cancel)


# ---------------------------------------------------------------------------
# FrameSelectionRunner 测试
# ---------------------------------------------------------------------------

class TestFrameSelectionRunner:
    def test_runner_start_dispatches_task(self, tmp_path: Path):
        from ai_physics_tracker.application.tracking_job import (
            FrameSelectionJobRequest,
            FrameSelectionRunner,
        )

        class _SpyRunner:
            def __init__(self):
                self.calls = []

            def start_task(self, req_id, worker_fn, job_req, adapter):
                self.calls.append((req_id, worker_fn, job_req, adapter))
                return "mock_handle"

        spy = _SpyRunner()
        runner = FrameSelectionRunner(adapter=MockEngineAdapter(), runner=spy)
        req = FrameSelectionRequest(
            video_id=uuid4(), track_id=uuid4(), video_path=tmp_path / "v.mp4",
            frame_count=30, zone_start=0, zone_end=29, n_frames=5,
            algorithm="uniform", excluded_frames=frozenset(),
        )
        job_req = FrameSelectionJobRequest(req, tmp_path, (100, 100))
        rid = uuid4()
        handle = runner.start(job_req, rid)
        assert handle == "mock_handle"
        assert len(spy.calls) == 1
        assert spy.calls[0][0] == rid
