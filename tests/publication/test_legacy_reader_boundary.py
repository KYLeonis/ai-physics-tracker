"""v1/v2 reader boundary probes（P0.2 建立，P1.1 更新为双格式语义）。

v1 unknown 字段仍原样 round-trip 且不获得语义校验；v2 缺合法
required_capabilities、未知 capability 与未来 schema 版本均被拒绝，
且拒绝不产生 manifest 改写或 backup。
"""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'src'))
from ai_physics_tracker.domain.project import create_project
from ai_physics_tracker.infrastructure.project_serializer import project_from_payload, project_to_payload
from ai_physics_tracker.infrastructure.project_repository import ProjectRepository
from ai_physics_tracker.infrastructure.errors import (
    ProjectFormatError,
    UnsupportedSchemaVersionError,
)


class LegacyReaderBoundaryTests(unittest.TestCase):
    def test_unknown_fields_round_trip_without_gaining_semantic_validation(self):
        payload = project_to_payload(create_project('legacy compatibility'))
        payload['publication'] = {'experiment': {'roles': {'tip': 'not-a-real-track'}}}
        restored = project_to_payload(project_from_payload(copy.deepcopy(payload)))
        self.assertEqual(restored['publication'], payload['publication'])
        # Accepted unknown bytes are precisely why v1 is unsafe for new semantics.

    def test_repository_rejects_v2_without_required_capabilities(self):
        payload = project_to_payload(create_project('legacy compatibility'))
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            manifest = root / 'project.json'
            manifest.write_text(json.dumps(payload), encoding='utf-8')
            loaded = ProjectRepository().load(root)
            self.assertEqual(str(loaded.project_id), payload["project_id"])
            payload['schema_version'] = 2
            data = json.dumps(payload).encode('utf-8')
            manifest.write_bytes(data)
            with self.assertRaises(ProjectFormatError):
                ProjectRepository().load(root)
            self.assertEqual(manifest.read_bytes(), data)
            self.assertFalse((root / 'project.backup.json').exists())

    def test_repository_rejects_v2_with_unknown_capability(self):
        payload = project_to_payload(create_project('legacy compatibility'))
        payload['schema_version'] = 2
        payload['required_capabilities'] = ['pendulum-four-role-v1', 'made-up-cap']
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            manifest = root / 'project.json'
            data = json.dumps(payload).encode('utf-8')
            manifest.write_bytes(data)
            with self.assertRaises(ProjectFormatError):
                ProjectRepository().load(root)
            self.assertEqual(manifest.read_bytes(), data)

    def test_repository_rejects_future_schema_versions(self):
        payload = project_to_payload(create_project('legacy compatibility'))
        payload['schema_version'] = 999
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            manifest = root / 'project.json'
            data = json.dumps(payload).encode('utf-8')
            manifest.write_bytes(data)
            with self.assertRaises(UnsupportedSchemaVersionError):
                ProjectRepository().load(root)
            self.assertEqual(manifest.read_bytes(), data)
            self.assertFalse((root / 'project.backup.json').exists())


if __name__ == '__main__':
    unittest.main()
