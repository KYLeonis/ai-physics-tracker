"""Disposable external-runtime probe. Never imported by the frozen host."""
import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import time
import traceback


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--request', type=Path, required=True)
    args = parser.parse_args()
    root = args.request.resolve().parent
    request = json.loads(args.request.read_text(encoding='utf-8'))
    digest = hashlib.sha256(json.dumps(request, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()
    result = dict(request_digest=digest, operation=request['operation'], outputs=[], protocol_version=1, job_id=request['job_id'], status='failed',
                  python=sys.version, executable=sys.executable, platform=platform.platform(),
                  machine=platform.machine(), worker_frozen=bool(getattr(sys, 'frozen', False)))
    try:
        if request['worker_sha256'] != hashlib.sha256(Path(__file__).read_bytes()).hexdigest():
            raise ValueError('Worker source changed since request capture')
        if request['protocol_version'] != 1:
            raise ValueError('Unsupported protocol')
        operation = request['operation']
        if operation == 'hello':
            result['message'] = 'external worker ready'
        elif operation == 'stubborn':
            child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(600)'])
            (root / 'child.pid').write_text(str(child.pid), encoding='utf-8')
            child.wait()
        elif operation == 'wait':
            while not (root / 'cancel.request').exists():
                time.sleep(0.05)
            result['status'] = 'cancelled'
        elif operation == 'fail':
            raise RuntimeError('Intentional failure to verify actionable logs')
        elif operation == 'selftest':
            os.environ['DLClight'] = 'True'
            import torch
            import deeplabcut
            result['versions'] = {name: importlib.metadata.version(name) for name in ('torch', 'torchvision', 'deeplabcut')}
            result['hardware'] = dict(cuda=torch.cuda.is_available(), mps=torch.backends.mps.is_available())
            device = request['device']
            x = torch.ones(4, device=device, requires_grad=True)
            (x*x).sum().backward()
            if not torch.isfinite(x.grad).all().item():
                raise RuntimeError('Nonfinite tensor self-test')
            result['actual_device'] = str(x.device)
            result['dlc_import'] = True
            result['dlc_training_verified'] = False
        elif operation == 'dlc_smoke':
            repo = Path(request['repo']).resolve()
            script = repo / 'scripts/smoke_test_dlc_infer.py'
            if not script.is_file():
                raise ValueError('Existing trusted repository smoke script missing')
            environment = os.environ.copy()
            environment['PYTHONPATH'] = str(repo / 'src')
            environment['QT_QPA_PLATFORM'] = 'offscreen'
            subprocess.run([sys.executable, str(script), '--output', str(root / 'dlc-artifacts')],
                           env=environment, check=True)
            manifest = root / 'dlc-artifacts/project/project.json'
            data = manifest.read_bytes()
            result['outputs'] = [dict(path='dlc-artifacts/project/project.json', size=len(data), sha256=hashlib.sha256(data).hexdigest())]
            result['dlc_training_verified'] = True
            result['scope'] = 'existing single-track 1-epoch CPU train/infer; not four-landmark or accuracy acceptance'
        else:
            raise ValueError('Unsupported operation')
        if result['status'] != 'cancelled':
            result['status'] = 'success'
    except Exception as error:
        traceback.print_exc()
        result['error'] = dict(type=type(error).__name__, message=str(error))
    temporary = root / 'result.tmp'
    temporary.write_text(json.dumps(result, ensure_ascii=False, allow_nan=False, indent=2)+'\n', encoding='utf-8')
    temporary.replace(root / 'result.json')
    return 1 if result['status'] == 'failed' else 0


if __name__ == '__main__':
    raise SystemExit(main())
