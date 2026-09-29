"""P1.3-S4 教师模型导入测试(Qt-free)。

覆盖:happy path(managed copy + manifest + 路径重写 + 原目录移走仍可用)、
身份校验 fail-closed 清单(missing/duplicate/extra/multi-animal/identity/
cropping/非 pytorch)、路径逃逸、同名冲突、半拷贝故障注入(staging 残留/
重试)、Unicode basename、undo/save-reopen。
"""

from __future__ import annotations

import shutil
from pathlib import Path
from uuid import uuid4

import pytest

from ai_physics_tracker.application.project_session import (
    ProjectSession,
    ProjectSessionError,
)
from ai_physics_tracker.application.teacher_import import (
    TeacherImportError,
    parse_teacher_config,
)
from ai_physics_tracker.application.teacher_models import (
    resolve_pose_cfg_path,
    teacher_model_availability,
)
from ai_physics_tracker.application.video import VideoStreamInfo
from ai_physics_tracker.domain.pendulum import ROLE_ORDER, PendulumRoles
from ai_physics_tracker.domain.project import create_project
from ai_physics_tracker.infrastructure.project_repository import ProjectRepository

IDENTITY = tuple((role, role) for role in ROLE_ORDER)


def _session(tmp_path: Path, synthetic_video_path: Path) -> ProjectSession:
    session = ProjectSession(ProjectRepository(), create_project("import models"))
    info = VideoStreamInfo(
        width_px=64, height_px=48, fps_container=10.0, frame_count=8,
        container_format="avi", timing_status="cfr",
    )
    video, _timeline = session.register_external_video(synthetic_video_path, info)
    tracks = {role: session.add_track(video.video_id, role) for role in ROLE_ORDER}
    session.save_as_publication(
        tmp_path / "publication",
        PendulumRoles(
            tip=tracks["tip"].track_id, body_top=tracks["body_top"].track_id,
            body_bottom=tracks["body_bottom"].track_id, pivot=tracks["pivot"].track_id,
        ),
    )
    return session


def _bundle(
    root: Path,
    *,
    bodyparts: tuple[str, ...] = ROLE_ORDER,
    checkpoint_name: str = "snapshot-100.pt",
    extra: dict[str, bytes] | None = None,
    config_overrides: dict | None = None,
) -> Path:
    """构造最小合法 DLC 教师 bundle(config + checkpoint + 附加文件)。"""

    bundle = root / "teacher-bundle"
    bundle.mkdir(parents=True)
    config = {
        "Task": "teacher", "scorer": "Teacher",
        "multianimalproject": False, "identity": False,
        "project_path": bundle.as_posix(),
        "bodyparts": list(bodyparts),
        "cropping": False, "engine": "pytorch",
        **(config_overrides or {}),
    }
    import yaml

    (bundle / "config.yaml").write_text(
        yaml.safe_dump(config, sort_keys=False), encoding="utf-8"
    )
    (bundle / checkpoint_name).write_bytes(b"teacher-checkpoint-bytes")
    for name, data in (extra or {}).items():
        (bundle / name).write_bytes(data)
    return bundle


class TestHappyPath:
    def test_import_creates_managed_reference(self, tmp_path, synthetic_video_path):
        session = _session(tmp_path, synthetic_video_path)
        bundle = _bundle(tmp_path, extra={"pose_cfg.yaml": b"pose: cfg"})
        reference = session.import_teacher_model(
            bundle, "config.yaml", "snapshot-100.pt", IDENTITY,
            extra_files=("pose_cfg.yaml",),
        )
        assert reference.origin == "imported"
        assert reference.source_train_run_id is None
        assert reference.bodypart_mapping == IDENTITY
        assert reference.compatibility_state == "unverified"
        assert len(reference.manifest) == 3
        managed = session.project_root / "models" / str(reference.model_id)
        assert (managed / "config.yaml").is_file()
        assert (managed / "snapshot-100.pt").is_file()
        assert (managed / "pose_cfg.yaml").is_file()
        assert not list((session.project_root / "models").glob(f"{reference.model_id}.staging"))

        # 路径已重写到 managed 目录;原 config SHA 入 provenance
        import yaml

        copied = yaml.safe_load(
            (managed / "config.yaml").read_text(encoding="utf-8")
        )
        assert copied["project_path"] == managed.as_posix()
        assert reference.extra_fields["original_checkpoint_basename"] == "snapshot-100.pt"
        assert len(reference.extra_fields["original_config_sha256"]) == 64

        # undo 移除引用(受管文件按 §6 留存)
        assert session.undo()
        assert session.project.model_references == ()
        assert managed.is_dir()

    def test_bundle_moved_away_after_import(self, tmp_path, synthetic_video_path):
        session = _session(tmp_path, synthetic_video_path)
        bundle = _bundle(tmp_path)
        reference = session.import_teacher_model(
            bundle, "config.yaml", "snapshot-100.pt", IDENTITY
        )
        shutil.rmtree(bundle)
        state, reason = teacher_model_availability(session.project_root, reference)
        assert state == "unverified"
        assert reason is None

    def test_save_reopen_preserves_imported_reference(
        self, tmp_path, synthetic_video_path
    ):
        session = _session(tmp_path, synthetic_video_path)
        bundle = _bundle(tmp_path)
        reference = session.import_teacher_model(
            bundle, "config.yaml", "snapshot-100.pt", IDENTITY
        )
        session.save()
        reopened = ProjectSession.load(ProjectRepository(), session.project_root)
        assert len(reopened.project.model_references) == 1
        restored = reopened.project.model_references[0]
        assert restored.model_id == reference.model_id
        assert restored.origin == "imported"
        state, _reason = teacher_model_availability(reopened.project_root, restored)
        assert state == "unverified"


class TestIdentityValidation:
    def test_mapping_must_cover_four_roles(self, tmp_path, synthetic_video_path):
        session = _session(tmp_path, synthetic_video_path)
        bundle = _bundle(tmp_path)
        bad = IDENTITY[:3]
        with pytest.raises(ProjectSessionError, match="four canonical roles"):
            session.import_teacher_model(bundle, "config.yaml", "snapshot-100.pt", bad)

    def test_extra_bodypart_rejected(self, tmp_path, synthetic_video_path):
        session = _session(tmp_path, synthetic_video_path)
        bundle = _bundle(tmp_path, bodyparts=(*ROLE_ORDER, "extra"))
        with pytest.raises(ProjectSessionError, match="missing/duplicate/extra"):
            session.import_teacher_model(bundle, "config.yaml", "snapshot-100.pt", IDENTITY)

    def test_renamed_bodyparts_need_explicit_mapping(self, tmp_path, synthetic_video_path):
        session = _session(tmp_path, synthetic_video_path)
        renamed = ("bob", "top", "bottom", "axis")
        bundle = _bundle(tmp_path, bodyparts=renamed)
        # identity 映射不匹配改名 config → 拒绝
        with pytest.raises(ProjectSessionError, match="missing/duplicate/extra"):
            session.import_teacher_model(bundle, "config.yaml", "snapshot-100.pt", IDENTITY)
        # 显式映射通过
        mapping = tuple(zip(ROLE_ORDER, renamed))
        reference = session.import_teacher_model(
            bundle, "config.yaml", "snapshot-100.pt", mapping
        )
        assert reference.bodypart_mapping == mapping

    @pytest.mark.parametrize(
        "key,value,pattern",
        [
            ("multianimalproject", True, "multi-animal"),
            ("identity", True, "identity"),
            ("cropping", True, "cropped"),
            ("engine", "tensorflow", "unsupported or missing"),
        ],
    )
    def test_config_flags_rejected(
        self, tmp_path, synthetic_video_path, key, value, pattern
    ):
        session = _session(tmp_path, synthetic_video_path)
        bundle = _bundle(tmp_path, config_overrides={key: value})
        with pytest.raises(ProjectSessionError, match=pattern):
            session.import_teacher_model(bundle, "config.yaml", "snapshot-100.pt", IDENTITY)

    def test_non_mapping_yaml_rejected(self, tmp_path):
        bad = tmp_path / "bad.yaml"
        bad.write_text("- just\n- a\n- list\n", encoding="utf-8")
        with pytest.raises(TeacherImportError, match="not a YAML mapping"):
            parse_teacher_config(bad)

    def test_missing_bodyparts_rejected(self, tmp_path):
        bad = tmp_path / "bad.yaml"
        bad.write_text("Task: x\n", encoding="utf-8")
        with pytest.raises(TeacherImportError, match="bodyparts"):
            parse_teacher_config(bad)


class TestPathSafety:
    def test_checkpoint_escape_rejected(self, tmp_path, synthetic_video_path):
        session = _session(tmp_path, synthetic_video_path)
        bundle = _bundle(tmp_path)
        with pytest.raises(ProjectSessionError, match="escapes|'..'"):
            session.import_teacher_model(
                bundle, "config.yaml", "../outside.pt", IDENTITY
            )

    def test_absolute_path_rejected(self, tmp_path, synthetic_video_path):
        session = _session(tmp_path, synthetic_video_path)
        bundle = _bundle(tmp_path)
        with pytest.raises(ProjectSessionError, match="relative"):
            session.import_teacher_model(
                bundle, "config.yaml", str(bundle / "snapshot-100.pt"), IDENTITY
            )

    def test_symlink_escape_rejected(self, tmp_path, synthetic_video_path):
        session = _session(tmp_path, synthetic_video_path)
        bundle = _bundle(tmp_path)
        outside = tmp_path / "outside.pt"
        outside.write_bytes(b"x")
        (bundle / "link.pt").symlink_to(outside)
        with pytest.raises(ProjectSessionError, match="escapes"):
            session.import_teacher_model(bundle, "config.yaml", "link.pt", IDENTITY)

    def test_reimport_with_new_id_allowed(
        self, tmp_path, synthetic_video_path
    ):
        session = _session(tmp_path, synthetic_video_path)
        bundle = _bundle(tmp_path)
        reference = session.import_teacher_model(
            bundle, "config.yaml", "snapshot-100.pt", IDENTITY
        )
        session.undo()  # 引用移除但受管目录仍在 → 同 id 不会重建(uuid),但目录占用检查由构造验证
        # 直接再次导入新 id:目录不冲突,应成功(验证目录占用检查不影响新导入)
        second = session.import_teacher_model(
            bundle, "config.yaml", "snapshot-100.pt", IDENTITY
        )
        assert second.model_id != reference.model_id


class TestFaultInjection:
    def test_half_copy_leaves_staging_and_retry_succeeds(
        self, tmp_path, synthetic_video_path, monkeypatch
    ):
        from ai_physics_tracker.application import teacher_import

        session = _session(tmp_path, synthetic_video_path)
        bundle = _bundle(
            tmp_path, extra={"pose_cfg.yaml": b"pose"}
        )
        original_copy = teacher_import._copy_file
        calls = {"n": 0}

        def flaky(source, destination):
            calls["n"] += 1
            if calls["n"] == 2:  # checkpoint 复制中途失败
                raise OSError("simulated disk failure")
            return original_copy(source, destination)

        monkeypatch.setattr(teacher_import, "_copy_file", flaky)
        with pytest.raises(ProjectSessionError, match="disk failure"):
            session.import_teacher_model(
                bundle, "config.yaml", "snapshot-100.pt", IDENTITY,
                extra_files=("pose_cfg.yaml",),
            )
        # 未发布任何受管目录;引用未登记;staging 残留存在
        models_root = session.project_root / "models"
        assert list(models_root.glob("*")) and all(
            p.name.endswith(".staging") for p in models_root.glob("*")
        )
        assert session.project.model_references == ()

        # 重试:清 staging 重来,成功
        monkeypatch.setattr(teacher_import, "_copy_file", original_copy)
        reference = session.import_teacher_model(
            bundle, "config.yaml", "snapshot-100.pt", IDENTITY,
            extra_files=("pose_cfg.yaml",),
        )
        managed = models_root / str(reference.model_id)
        assert (managed / "snapshot-100.pt").is_file()

    def test_unicode_checkpoint_basename(self, tmp_path, synthetic_video_path):
        session = _session(tmp_path, synthetic_video_path)
        bundle = _bundle(tmp_path, checkpoint_name="快照-100.pt")
        reference = session.import_teacher_model(
            bundle, "config.yaml", "快照-100.pt", IDENTITY
        )
        assert reference.checkpoint_path.endswith("快照-100.pt")
        state, _reason = teacher_model_availability(session.project_root, reference)
        assert state == "unverified"


class TestReviewRegressions:
    def test_m1_config_bodypart_duplicates_rejected(self, tmp_path, synthetic_video_path):
        session = _session(tmp_path, synthetic_video_path)
        bundle = _bundle(tmp_path, bodyparts=("tip", "tip", "body_top", "body_bottom", "pivot"))
        with pytest.raises(ProjectSessionError, match="duplicates"):
            session.import_teacher_model(bundle, "config.yaml", "snapshot-100.pt", IDENTITY)

    def test_m2_missing_engine_key_rejected(self, tmp_path, synthetic_video_path):
        session = _session(tmp_path, synthetic_video_path)
        bundle = _bundle(tmp_path, config_overrides={"engine": None})
        (bundle / "config.yaml").write_text(
            (bundle / "config.yaml").read_text(encoding="utf-8").replace(
                "engine: null\n", "").replace("engine: pytorch\n", ""),
            encoding="utf-8",
        )
        with pytest.raises(ProjectSessionError, match="unsupported or missing"):
            session.import_teacher_model(bundle, "config.yaml", "snapshot-100.pt", IDENTITY)

    def test_m2_checkpoint_basename_collides_with_extra(self, tmp_path, synthetic_video_path):
        # config 与 checkpoint 在源目录必然是不同文件,"撞名"的可达分支是
        # checkpoint/extra 或 extra/extra;extra 换个子目录但同名 basename
        session = _session(tmp_path, synthetic_video_path)
        sub = tmp_path / "teacher-bundle" / "sub"
        bundle = _bundle(tmp_path, extra={})
        sub.mkdir(exist_ok=True)
        (sub / "snapshot-100.pt").write_bytes(b"duplicate-basename")
        with pytest.raises(ProjectSessionError, match="share the basename"):
            session.import_teacher_model(
                bundle, "config.yaml", "snapshot-100.pt", IDENTITY,
                extra_files=("sub/snapshot-100.pt",),
            )
        assert not list((session.project_root / "models").glob("*.pt"))

    def test_m2_two_extras_same_basename_rejected(self, tmp_path, synthetic_video_path):
        session = _session(tmp_path, synthetic_video_path)
        sub1 = tmp_path / "teacher-bundle" / "a"
        sub2 = tmp_path / "teacher-bundle" / "b"
        bundle = _bundle(tmp_path, extra={})
        sub1.mkdir(exist_ok=True); sub2.mkdir(exist_ok=True)
        (sub1 / "pose.yaml").write_bytes(b"a")
        (sub2 / "pose.yaml").write_bytes(b"b")
        with pytest.raises(ProjectSessionError, match="share the basename"):
            session.import_teacher_model(
                bundle, "config.yaml", "snapshot-100.pt", IDENTITY,
                extra_files=("a/pose.yaml", "b/pose.yaml"),
            )

    def test_m1_stale_staging_swept_on_next_import(
        self, tmp_path, synthetic_video_path
    ):
        # 直接制造一个历史 staging 残留 → 新导入开始时被清扫
        session = _session(tmp_path, synthetic_video_path)
        models = session.project_root / "models"
        models.mkdir(parents=True, exist_ok=True)
        stale = models / f"{uuid4()}.staging"
        stale.mkdir()
        (stale / "junk").write_bytes(b"x")
        bundle = _bundle(tmp_path)
        reference = session.import_teacher_model(
            bundle, "config.yaml", "snapshot-100.pt", IDENTITY
        )
        assert not stale.exists()
        assert (models / str(reference.model_id) / "config.yaml").is_file()


class TestNestedDlcBundle:
    """HR 2026-09-29:用户直接选 DLC 项目目录(config.yaml 在根,checkpoint
    与 pytorch_config.yaml 在 dlc-models-pytorch/**/train/ 深层)。"""

    def _nested_bundle(self, root: Path) -> Path:
        bundle = root / "dlc-project"
        train_dir = (
            bundle / "dlc-models-pytorch" / "iteration-0"
            / "dlc-projectSep29-trainset83shuffle1" / "train"
        )
        train_dir.mkdir(parents=True)
        import yaml

        (bundle / "config.yaml").write_text(yaml.safe_dump({
            "Task": "t", "multianimalproject": False, "identity": False,
            "project_path": str(bundle), "bodyparts": list(ROLE_ORDER),
            "cropping": False, "engine": "pytorch",
        }), encoding="utf-8")
        (train_dir / "snapshot-best-020.pt").write_bytes(b"nested-weights")
        (train_dir / "pytorch_config.yaml").write_text(
            "net_type: resnet_50\n", encoding="utf-8")
        return bundle

    def test_wizard_finds_nested_checkpoint(self, qtbot, tmp_path):
        from ai_physics_tracker.gui.teacher_import_dialog import TeacherImportDialog

        bundle = self._nested_bundle(tmp_path)

        class _Win:
            statusBar = lambda self: None

        dialog = TeacherImportDialog(_Win())
        qtbot.addWidget(dialog)
        assert dialog.load_bundle(bundle)
        # checkpoint 下拉含深层相对路径,默认选中第一项
        assert dialog.checkpoint_box.count() == 1
        assert dialog.checkpoint_box.currentText() == (
            "dlc-models-pytorch/iteration-0/dlc-projectSep29-trainset83shuffle1/"
            "train/snapshot-best-020.pt"
        )
        assert "detected" in dialog.pose_cfg_label.text()

    def test_session_imports_nested_bundle(self, tmp_path, synthetic_video_path):
        session = _session(tmp_path, synthetic_video_path)
        bundle = self._nested_bundle(tmp_path)
        reference = session.import_teacher_model(
            bundle, "config.yaml",
            "dlc-models-pytorch/iteration-0/dlc-projectSep29-trainset83shuffle1/"
            "train/snapshot-best-020.pt",
            IDENTITY, extra_files=(
                "dlc-models-pytorch/iteration-0/dlc-projectSep29-trainset83shuffle1/"
                "train/pytorch_config.yaml",
            ),
        )
        # managed 副本保留 basename;pytorch_config 在 manifest 里供自检
        names = [Path(e.relative_path).name for e in reference.manifest]
        assert "snapshot-best-020.pt" in names
        assert "pytorch_config.yaml" in names
        assert resolve_pose_cfg_path(session.project_root, reference) is not None
