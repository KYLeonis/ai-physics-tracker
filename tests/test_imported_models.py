"""教师模型内容身份、真实帧探针与 schema v1 增量兼容回归。"""

from concurrent.futures import CancelledError
from dataclasses import replace
import hashlib
import json
from queue import Queue
from threading import Event
from uuid import uuid4

import cv2
import numpy as np
import pytest
import yaml

from ai_physics_tracker.domain.project import create_project
from ai_physics_tracker.domain.timeline import Timeline
from ai_physics_tracker.application.tracking_types import InferenceParams, InferenceRequest
from ai_physics_tracker.infrastructure.imported_models import (
    import_model, verify_model, runtime_identity, verified_self_test, file_sha256,
)
from ai_physics_tracker.infrastructure.imported_model_inference import (
    run_model_self_test, validated_predictions, infer_imported_model,
)
from ai_physics_tracker.infrastructure.project_repository import ProjectRepository
from ai_physics_tracker.infrastructure.project_serializer import project_to_payload, project_from_payload


def model_sources(tmp_path, parts=("tip", "other")):
    folder = tmp_path / "teacher-source"
    folder.mkdir(exist_ok=True)
    cfg = folder / "config.yaml"
    pose = folder / "pytorch_config.yaml"
    checkpoint = folder / "snapshot.pt"
    cfg.write_text(yaml.safe_dump({"engine": "pytorch", "bodyparts": list(parts)}), encoding="utf-8")
    pose.write_text(yaml.safe_dump({"method": "bu", "metadata": {
        "bodyparts": list(parts), "individuals": ["individual_1"], "with_identity": False,
        "unique_bodyparts": []}, "runner": {"load_weights_only": False}}), encoding="utf-8")
    checkpoint.write_bytes(b"test checkpoint")
    return cfg, pose, checkpoint


def evidence(model, device="auto", actual="cpu", video_id=None, video_path=None):
    result = {"manifest_hash": model.manifest_hash, "runtime": runtime_identity(),
              "requested_device": device, "actual_device": actual, "frame_sha256": "a" * 64}
    if video_path is not None:
        stat = video_path.stat()
        result.update(video_id=str(video_id), video_sha256=file_sha256(video_path),
                      video_file_info=[stat.st_size, stat.st_mtime_ns])
    return result


@pytest.fixture
def imported(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    return root, import_model(root, *model_sources(tmp_path))


def test_import_copy_and_safe_weights(imported, tmp_path):
    root, model = imported
    pose, checkpoint = verify_model(root, model)
    assert model.bodyparts == ("tip", "other")
    assert pose["runner"]["load_weights_only"] is True
    assert checkpoint.read_bytes() == b"test checkpoint"
    assert not model.self_test
    # 源模型移动/删除不会影响受管副本。
    for source in model_sources(tmp_path):
        source.unlink()
    verify_model(root, model)


@pytest.mark.parametrize("change", ["order", "multi", "tensorflow", "crop", "identity", "td", "color"])
def test_reject_incompatible_configs(tmp_path, change):
    paths = model_sources(tmp_path)
    config = yaml.safe_load(paths[0].read_text())
    pose = yaml.safe_load(paths[1].read_text())
    if change == "order": pose["metadata"]["bodyparts"].reverse()
    if change == "multi": config["multianimalproject"] = True
    if change == "tensorflow": config["engine"] = "tensorflow"
    if change == "crop": config["cropping"] = True
    if change == "identity": pose["metadata"]["with_identity"] = True
    if change == "td": pose["method"] = "td"
    if change == "color": pose["data"] = {"colormode": "BGR"}
    paths[0].write_text(yaml.safe_dump(config), encoding="utf-8")
    paths[1].write_text(yaml.safe_dump(pose), encoding="utf-8")
    with pytest.raises(ValueError):
        import_model(tmp_path, *paths)
    assert not (tmp_path / "models").exists()


def test_unsafe_yaml_and_cancel_leave_no_registered_assets(tmp_path):
    paths = model_sources(tmp_path)
    paths[0].write_text("!!python/object/apply:builtins.print ['bad']", encoding="utf-8")
    with pytest.raises(yaml.YAMLError): import_model(tmp_path, *paths)
    paths = model_sources(tmp_path)
    cancel = Event(); cancel.set()
    with pytest.raises(CancelledError): import_model(tmp_path, *paths, cancel)
    assert not list((tmp_path / "models").iterdir())


def test_model_tampering_same_size_is_detected(imported):
    root, model = imported
    checkpoint = root / model.directory / "checkpoint.pt"
    checkpoint.write_bytes(b"x" * checkpoint.stat().st_size)
    with pytest.raises(ValueError, match="changed or missing"):
        verify_model(root, model)


def test_v1_roundtrip_unknown_fields_and_save_as(imported, tmp_path):
    root, model = imported
    model = replace(model, self_test=evidence(model), extra_fields={"future": {"kept": True}})
    project = replace(create_project("import test"), imported_models=(model,))
    payload = project_to_payload(project)
    assert payload["schema_version"] == 1
    assert project_from_payload(payload) == project
    repo = ProjectRepository()
    repo.save(root, project)
    destination = tmp_path / "copied"
    repo.save_as(root, destination, project)
    loaded = repo.load(destination)
    assert loaded.imported_models == (model,)
    verify_model(destination, loaded.imported_models[0])
    assert loaded.imported_models[0].self_test == model.self_test
    assert not verified_self_test(loaded.imported_models[0], "auto")  # 旧证据缺少视频身份须重测。
    assert "imported_models" not in project_to_payload(create_project("old"))


@pytest.mark.parametrize("field,value", [("bodyparts", []), ("bodyparts", ["a", "a"]),
                                         ("sha256", {}), ("self_test", []), ("model_id", "invalid")])
def test_malformed_persisted_model_rejected(imported, field, value):
    _, model = imported
    payload = project_to_payload(replace(create_project("test"), imported_models=(model,)))
    payload["imported_models"][0][field] = value
    with pytest.raises((ValueError, TypeError)):
        project_from_payload(payload)


def test_self_test_identity_needs_matching_environment_and_device(imported, synthetic_video_path):
    _, model = imported
    video_id = uuid4()
    model = replace(model, self_test=evidence(model, video_id=video_id, video_path=synthetic_video_path))
    assert verified_self_test(model, "auto", video_id, synthetic_video_path)
    assert not verified_self_test(model, "cpu", video_id, synthetic_video_path)
    bad = {**model.self_test, "runtime": {"torch": "changed"}}
    assert not verified_self_test(replace(model, self_test=bad), "auto", video_id, synthetic_video_path)
    bad = {**model.self_test, "manifest_hash": "changed"}
    assert not verified_self_test(replace(model, self_test=bad), "auto", video_id, synthetic_video_path)

    assert not verified_self_test(model, "auto", uuid4(), synthetic_video_path)
    synthetic_video_path.write_bytes(b"changed")
    assert not verified_self_test(model, "auto", video_id, synthetic_video_path)


class PoseRunner:
    def __init__(self, array=None):
        self.array = array
        self.inputs = []
        self.device = "cpu"

    def inference(self, frames):
        self.inputs.extend(frames)
        array = self.array if self.array is not None else np.array([[[12, 20, 0.9], [30, 40, 0.2]]])
        return [{"bodyparts": array} for _ in frames]


def test_probe_decodes_requested_actual_frame(imported, synthetic_video_path, monkeypatch):
    root, model = imported
    runner = PoseRunner()
    monkeypatch.setattr("ai_physics_tracker.infrastructure.imported_model_inference.load_runner",
                        lambda *_: (runner, "cpu"))
    result = run_model_self_test(uuid4(), Queue(), Event(), root, model, synthetic_video_path, uuid4(), 3, "auto")
    capture = cv2.VideoCapture(str(synthetic_video_path)); capture.set(cv2.CAP_PROP_POS_FRAMES, 3)
    ok, frame = capture.read(); capture.release()
    assert ok and result["evidence"]["frame_index"] == 3
    assert result["evidence"]["frame_sha256"] == hashlib.sha256(frame.tobytes()).hexdigest()
    assert np.array_equal(runner.inputs[0], cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
    assert result["evidence"]["actual_device"] == "cpu"
    with pytest.raises(ValueError, match="decode"):
        run_model_self_test(uuid4(), Queue(), Event(), root, model, synthetic_video_path, uuid4(), 99, "auto")


@pytest.mark.parametrize("array", [np.zeros((2,3)), np.zeros((1,3,3)),
                                  np.array([[[1,2,1.1],[2,3,0.5]]]),
                                  np.array([[[float("inf"),2,0.1],[2,3,0.5]]])])
def test_predictions_reject_wrong_schema(array):
    with pytest.raises(ValueError):
        validated_predictions(PoseRunner(array), [np.zeros((2,2,3), np.uint8)], 2)


def test_imported_inference_maps_selected_bodypart_and_keeps_raw_rows(imported, synthetic_video_path, monkeypatch):
    root, model = imported
    video_id = uuid4()
    model = replace(model, self_test=evidence(model, video_id=video_id, video_path=synthetic_video_path))
    monkeypatch.setattr("ai_physics_tracker.infrastructure.imported_model_inference.load_runner",
                        lambda *_: (PoseRunner(), "cpu"))
    req = InferenceRequest(root/model.directory/"config.yaml", synthetic_video_path,
        root/model.directory/"checkpoint.pt", root/"prediction", uuid4(), Timeline(video_id,10,(0,4)),
        "teacher:test", 5, InferenceParams(0.5), imported_model=model, model_root=root, bodypart="other")
    result = infer_imported_model(uuid4(), Queue(), Event(), req)
    assert result.row_count == 5 and result.low_confidence_count == 5 and not result.points
    text = result.prediction_path.read_text()
    assert "target,target,target" in text and "30.0,40.0,0.2" in text
    with pytest.raises(ValueError, match="Auto device changed"):
        infer_imported_model(uuid4(), Queue(), Event(), replace(req,
            imported_model=replace(model, self_test={**model.self_test, "actual_device": "mps"}), output_dir=root/"another"))


def test_full_video_identity_rejects_same_size_and_mtime_replacement(imported, synthetic_video_path, monkeypatch):
    import os
    root, model = imported
    video_id = uuid4()
    model = replace(model, self_test=evidence(model, video_id=video_id, video_path=synthetic_video_path))
    stat = synthetic_video_path.stat()
    original = synthetic_video_path.read_bytes()
    synthetic_video_path.write_bytes(original[:-1] + bytes([original[-1] ^ 1]))
    os.utime(synthetic_video_path, ns=(stat.st_atime_ns, stat.st_mtime_ns))
    assert verified_self_test(model, "auto", video_id, synthetic_video_path)  # 轻量 GUI 状态不读完整视频。
    def must_not_load(*_args):
        raise AssertionError("full content identity must be checked before loading the engine")
    monkeypatch.setattr("ai_physics_tracker.infrastructure.imported_model_inference.load_runner", must_not_load)
    req = InferenceRequest(root/model.directory/"config.yaml", synthetic_video_path,
        root/model.directory/"checkpoint.pt", root/"prediction", uuid4(), Timeline(video_id,10,(0,4)),
        "teacher:test", 5, InferenceParams(0.5), imported_model=model, model_root=root, bodypart="tip")
    with pytest.raises(ValueError, match="self-test"):
        infer_imported_model(uuid4(), Queue(), Event(), req)
    assert not req.output_dir.exists()
