"""Regression guards against mixing archived releases, units and profile policies."""
import copy
import csv
import gzip
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('publication_evidence', ROOT / 'scripts/verify_publication_evidence.py')
evidence = importlib.util.module_from_spec(spec)
spec.loader.exec_module(evidence)


class EvidenceContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        directory = ROOT / 'publication/evidence/golden'
        cls.rows = list(csv.DictReader(io.StringIO(gzip.decompress((directory / 'P011-effective.csv.gz').read_bytes()).decode('utf-8-sig'))))
        cls.meta = next(row for row in json.loads((directory / 'inputs24.json').read_text()) if row['video_id'] == 'P011')
        with (directory / 'formal-fit48.csv').open(encoding='utf-8-sig', newline='') as stream:
            cls.fits = [row for row in csv.DictReader(stream) if row['video_id'] == 'P011']

    def test_frozen_evidence_and_profiles(self):
        self.assertEqual(evidence.verify()['formal_fit_rows'], 48)

    def test_old_led_origin_cannot_replace_effective_release(self):
        with self.assertRaisesRegex(ValueError, 'row count'):
            evidence.check_trajectory(self.rows[1:], self.meta, self.fits)

    def test_absolute_time_cannot_be_mislabeled_relative(self):
        rows = copy.deepcopy(self.rows)
        rows[0]['time_s'] = str(self.meta['release_frame'] / self.meta['fps'])
        with self.assertRaisesRegex(ValueError, 'relative time'):
            evidence.check_trajectory(rows, self.meta, self.fits)

    def test_compressed_gap_time_is_rejected(self):
        rows = copy.deepcopy(self.rows)
        rows[100]['frame_index_0based'] = str(int(rows[100]['frame_index_0based']) + 1)
        with self.assertRaisesRegex(ValueError, 'frame mismatch'):
            evidence.check_trajectory(rows, self.meta, self.fits)

    def test_degree_radian_mixing_is_rejected(self):
        rows = copy.deepcopy(self.rows)
        rows[0]['theta_observed_deg'] = str(float(rows[0]['theta_observed_deg']) * 3.141592653589793 / 180)
        with self.assertRaisesRegex(ValueError, 'residual sign/units'):
            evidence.check_trajectory(rows, self.meta, self.fits)

    def test_mask_not_python_truthiness(self):
        rows = copy.deepcopy(self.rows)
        rows[0]['geometry_valid'] = '1'
        with self.assertRaisesRegex(ValueError, 'invalid mask'):
            evidence.check_trajectory(rows, self.meta, self.fits)

    def test_missing_likelihood_not_unit_weight(self):
        rows = copy.deepcopy(self.rows)
        rows[0]['marker_likelihood'] = 'nan'
        with self.assertRaisesRegex(ValueError, 'likelihood'):
            evidence.check_trajectory(rows, self.meta, self.fits)

    def test_json_missing_cannot_be_nan_or_duplicate(self):
        for value in ('{"x":NaN}', '{"x":Infinity}', '{"x":0,"x":1}'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                evidence.strict_json(value)

    def test_manual_override_cannot_require_superseded_ai_likelihood(self):
        with tempfile.TemporaryDirectory() as name:
            directory = Path(name)
            for path in (ROOT / 'publication/profiles').glob('*.json'):
                content = json.loads(path.read_text())
                if content['id'] == 'student-default-v1':
                    content['weighting']['manual_requires_ai_likelihood'] = True
                (directory / path.name).write_text(json.dumps(content), encoding='utf-8')
            manifest = json.loads((ROOT / 'publication/evidence/source-map.json').read_text())
            with self.assertRaisesRegex(ValueError, 'manual points must not depend'):
                evidence.check_profiles(directory, {item['id'] for item in manifest['sources']})

    def test_golden_schema_unit_and_column_mutations_rejected(self):
        manifest = json.loads((ROOT / 'publication/evidence/source-map.json').read_text())
        item = next(row for row in manifest['local_files'] if row['id'] == 'trajectory-P011')
        invalid_unit = copy.deepcopy(item)
        invalid_unit['fields']['theta_observed_deg']['unit'] = 'rad'
        with self.assertRaisesRegex(ValueError, 'degree unit metadata'):
            evidence.check_fields(self.rows, invalid_unit)
        rows = copy.deepcopy(self.rows[:1])
        rows[0]['unversioned_column'] = '0'
        with self.assertRaisesRegex(ValueError, 'column schema'):
            evidence.check_fields(rows, item)

    def test_same_count_wrong_extrema_identity_rejected(self):
        with (ROOT / 'publication/evidence/golden/P011-information-extrema.csv').open(newline='') as stream:
            rows = list(csv.DictReader(stream))
        rows[3]['frame_index_0based'] = str(int(rows[3]['frame_index_0based']) + 1)
        with self.assertRaisesRegex(ValueError, 'Extremum source join'):
            evidence.check_extrema(rows, self.rows)

    def test_zero_and_pre_release_time_are_not_positive_time_guards(self):
        student = json.loads((ROOT / 'publication/profiles/student-default-v1.json').read_text())
        self.assertIs(student['conventions']['timestamp_zero_allowed'], True)
        self.assertEqual(float(self.rows[0]['time_s']), 0.0)
        self.assertLess((self.meta['initial_frames'][0] - self.meta['release_frame']) / self.meta['fps'], 0)
        evidence.check_trajectory(self.rows, self.meta, self.fits)

    def test_unknown_provenance_rejected(self):
        with tempfile.TemporaryDirectory() as name:
            directory = Path(name)
            for path in (ROOT / 'publication/profiles').glob('*.json'):
                content = json.loads(path.read_text())
                if content['id'] == 'student-default-v1':
                    content['qc']['sources'] = ['invented-manuscript-default']
                (directory / path.name).write_text(json.dumps(content), encoding='utf-8')
            manifest = json.loads((ROOT / 'publication/evidence/source-map.json').read_text())
            with self.assertRaisesRegex(ValueError, 'Unknown provenance'):
                evidence.check_profiles(directory, {item['id'] for item in manifest['sources']})


if __name__ == '__main__':
    unittest.main()
