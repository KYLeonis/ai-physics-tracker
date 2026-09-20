"""Source-host protocol checks, never labelled frozen/DLC acceptance."""
import json
import hashlib
import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SPIKE = ROOT / 'scripts/publication_runtime_spike'


class RuntimeSpikeTests(unittest.TestCase):
    def run_probe(self, operation, *extra):
        directory = tempfile.TemporaryDirectory(prefix='ejp runtime 中文 ')
        self.addCleanup(directory.cleanup)
        output = Path(directory.name) / 'job'
        result = subprocess.run([sys.executable, str(SPIKE / 'host.py'), '--python', sys.executable,
                                 '--worker', str(SPIKE / 'worker.py'), '--output', str(output),
                                 '--operation', operation, *extra], capture_output=True, text=True, timeout=20)
        return result, json.loads((output / 'host-result.json').read_text(encoding='utf-8')), output

    def test_wrong_digest_empty_payload_and_output_hash_are_rejected(self):
        spec = importlib.util.spec_from_file_location('spike_host', SPIKE / 'host.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        request = {'protocol_version': 1, 'job_id': 'test', 'operation': 'hello'}
        digest = hashlib.sha256(json.dumps(request, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        response = dict(protocol_version=1, job_id='test', operation='hello', request_digest=digest,
                        status='success', python='3.12', executable='python', platform='test', machine='test',
                        message='external worker ready', outputs=[])
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            module.validate_response(response, request, root, 0)
            for status, code in [('success', 1), ('cancelled', 1), ('failed', 0)]:
                with self.subTest(status=status), self.assertRaisesRegex(ValueError, 'exit code'):
                    module.validate_response(response | {'status': status, 'error': {}}, request, root, code)
            for mutation in ({'request_digest': 'stale'}, {'message': None}, {'outputs': None}):
                with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                    module.validate_response(response | mutation, request, root, 0)
            cuda_request = request | {'operation': 'selftest', 'device': 'cuda'}
            cuda_digest = hashlib.sha256(json.dumps(cuda_request, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
            cuda_response = response | {'operation': 'selftest', 'request_digest': cuda_digest, 'dlc_import': True,
                                        'actual_device': 'cuda:0', 'versions': {'torch': 'probe'}}
            module.validate_response(cuda_response, cuda_request, root, 0)
            with self.assertRaisesRegex(ValueError, 'selftest'):
                module.validate_response(cuda_response | {'actual_device': 'cpu'}, cuda_request, root, 0)
            (root / 'output.json').write_text('{}')
            with self.assertRaisesRegex(ValueError, 'hash/size'):
                module.validate_response(response | {'outputs': [{'path': 'output.json', 'size': 2, 'sha256': 'wrong'}]}, request, root, 0)
            with self.assertRaisesRegex(ValueError, 'escapes'):
                module.validate_response(response | {'outputs': [{'path': '../outside', 'size': 0, 'sha256': 'wrong'}]}, request, root, 0)

    def test_external_hello_and_unicode_path(self):
        process, result, _ = self.run_probe('hello')
        self.assertEqual(process.returncode, 0)
        self.assertFalse(result['host_frozen'])
        self.assertEqual(result['job_id'], result['worker']['job_id'])
        self.assertFalse(result['worker']['worker_frozen'])

    def test_failure_retains_actionable_traceback(self):
        process, result, output = self.run_probe('fail')
        self.assertEqual(process.returncode, 1)
        self.assertEqual(result['worker']['error']['type'], 'RuntimeError')
        self.assertIn('Intentional failure', (output / 'worker.log').read_text())

    def test_cooperative_cancel_not_success(self):
        _, result, _ = self.run_probe('wait', '--cancel-after', '0.3')
        self.assertEqual(result['status'], 'cancelled')
        self.assertNotIn('worker', result)  # Late terminal record never adopted.

    def test_forced_cancel_records_tree_kill(self):
        _, result, output = self.run_probe('stubborn', '--cancel-after', '0.5')
        self.assertEqual(result['status'], 'cancelled')
        self.assertTrue(result['forced_tree_termination'])
        self.assertTrue((output / 'child.pid').is_file())
        if sys.platform != 'win32':
            process = subprocess.run(['ps', '-p', (output / 'child.pid').read_text(), '-o', 'stat='], capture_output=True, text=True)
            self.assertTrue(not process.stdout.strip() or process.stdout.strip().startswith('Z'), process.stdout)


if __name__ == '__main__':
    unittest.main()
