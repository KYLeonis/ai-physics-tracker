"""Stdlib-only host to freeze separately from the disposable AI worker."""
import argparse
import ctypes
import hashlib
import json
import os
import re
import math
from pathlib import Path
import signal
import subprocess
import sys
import time
from uuid import uuid4


def validate_response(response, request, root, returncode):
    """Reject wrong identity/configuration, malformed success and escaped/missing outputs."""
    digest = hashlib.sha256(json.dumps(request, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()
    if response.get('protocol_version') != 1 or response.get('job_id') != request['job_id']:
        raise ValueError('Worker result identity/version mismatch')
    if response.get('request_digest') != digest or response.get('operation') != request['operation']:
        raise ValueError('Worker result configuration digest mismatch')
    if response.get('status') not in ('success', 'failed', 'cancelled'):
        raise ValueError('Invalid worker terminal status')
    expected_code = 1 if response['status'] == 'failed' else 0
    if returncode != expected_code:
        raise ValueError('Worker terminal status conflicts with exit code')
    if response['status'] == 'success':
        if not all(isinstance(response.get(key), str) and response[key] for key in ('python', 'executable', 'platform', 'machine')):
            raise ValueError('Incomplete runtime metadata')
        operation = request['operation']
        if operation == 'hello' and response.get('message') != 'external worker ready':
            raise ValueError('Missing hello payload')
        if operation == 'selftest' and (response.get('dlc_import') is not True or re.fullmatch(re.escape(request['device']) + r'(?::[0-9]+)?', str(response.get('actual_device'))) is None or not isinstance(response.get('versions'), dict)):
            raise ValueError('Invalid selftest payload')
        if operation == 'dlc_smoke' and response.get('dlc_training_verified') is not True:
            raise ValueError('DLC smoke not verified')
        outputs = response.get('outputs')
        if not isinstance(outputs, list):
            raise ValueError('Missing declared output list')
        if operation == 'dlc_smoke' and {item.get('path') for item in outputs} != {'dlc-artifacts/project/project.json'}:
            raise ValueError('Missing required DLC project manifest')
        for item in outputs:
            relative = Path(item['path'])
            path = root / relative
            if relative.is_absolute() or '..' in relative.parts or path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
                raise ValueError('Output path escapes job directory')
            data = path.read_bytes()
            if len(data) != item['size'] or hashlib.sha256(data).hexdigest() != item['sha256']:
                raise ValueError('Output hash/size mismatch')
    elif response['status'] == 'failed' and not isinstance(response.get('error'), dict):
        raise ValueError('Missing worker failure diagnostics')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--python', type=Path, required=True)
    parser.add_argument('--worker', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True, help='New per-job directory')
    parser.add_argument('--operation', choices=['hello', 'selftest', 'wait', 'stubborn', 'fail', 'dlc_smoke'], default='hello')
    parser.add_argument('--device', choices=['cpu', 'mps', 'cuda'], default='cpu')
    parser.add_argument('--repo', type=Path)
    parser.add_argument('--timeout', type=float, default=30)
    parser.add_argument('--cancel-after', type=float)
    args = parser.parse_args()
    if not math.isfinite(args.timeout) or args.timeout <= 0 or (args.cancel_after is not None and (not math.isfinite(args.cancel_after) or args.cancel_after < 0)):
        parser.error('timeout must be positive; cancel-after must be nonnegative')
    interpreter, worker = args.python.absolute(), args.worker.resolve()
    if not interpreter.is_file() or not worker.is_file():
        parser.error('Existing external interpreter and trusted worker script required')
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=False)
    job_id = str(uuid4())
    request = dict(worker_sha256=hashlib.sha256(worker.read_bytes()).hexdigest(), protocol_version=1, job_id=job_id, operation=args.operation, device=args.device,
                   repo=str(args.repo.resolve()) if args.repo else None)
    request_path = root / 'request.json'
    request_path.write_text(json.dumps(request, indent=2)+'\n', encoding='utf-8')
    environment = os.environ.copy()
    for key in list(environment):
        if key in ('PYTHONHOME', 'PYTHONPATH') or key.startswith('_PYI_'):
            environment.pop(key, None)
    if 'LD_LIBRARY_PATH_ORIG' in environment:
        environment['LD_LIBRARY_PATH'] = environment['LD_LIBRARY_PATH_ORIG']
    else:
        environment.pop('LD_LIBRARY_PATH', None)
    environment['PYTHONUTF8'] = '1'
    # Disposable CLI host exits after one job; no GUI threads race DLL-path state.
    if os.name == 'nt' and getattr(sys, 'frozen', False):
        ctypes.windll.kernel32.SetDllDirectoryW(None)
    outcome = dict(protocol_version=1, job_id=job_id, host_frozen=bool(getattr(sys, 'frozen', False)),
                   host_executable=sys.executable, operation=args.operation, status='failed')
    started = time.monotonic()
    cancellation = None
    process = None
    try:
        with (root / 'worker.log').open('wb') as log:
            process = subprocess.Popen([str(interpreter), '-I', str(worker), '--request', str(request_path)],
                                       stdout=log, stderr=subprocess.STDOUT, env=environment,
                                       start_new_session=os.name != 'nt',
                                       creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == 'nt' else 0)
            while process.poll() is None:
                elapsed = time.monotonic() - started
                if cancellation is None and (elapsed >= args.timeout or (args.cancel_after is not None and elapsed >= args.cancel_after)):
                    cancellation = time.monotonic()
                    outcome['cancel_reason'] = 'timeout' if elapsed >= args.timeout else 'requested'
                    (root / 'cancel.request').touch()
                if cancellation is not None and time.monotonic() - cancellation >= 1:
                    if os.name == 'nt':
                        subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], stdout=log, stderr=log, check=True)
                    else:
                        os.killpg(process.pid, signal.SIGKILL)
                    outcome['forced_tree_termination'] = True
                    process.wait(timeout=10)
                    break
                time.sleep(0.05)
        outcome['exit_code'] = process.returncode
        if cancellation is not None:
            outcome['status'] = 'cancelled'
        else:
            response = json.loads((root / 'result.json').read_text(encoding='utf-8'))
            validate_response(response, request, root, process.returncode)
            outcome['status'] = response['status']
            outcome['worker'] = response
    except Exception as error:
        outcome['error'] = dict(type=type(error).__name__, message=str(error))
        if process is not None and process.poll() is None:
            if os.name == 'nt':
                subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], capture_output=True)
            else:
                os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=10)
    outcome['elapsed_s'] = time.monotonic() - started
    outcome['log_path'] = str(root / 'worker.log')
    (root / 'host-result.json').write_text(json.dumps(outcome, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(outcome, ensure_ascii=False))
    return 1 if outcome['status'] == 'failed' else 0


if __name__ == '__main__':
    raise SystemExit(main())
