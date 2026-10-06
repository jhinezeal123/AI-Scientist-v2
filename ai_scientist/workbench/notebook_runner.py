"""Fixed notebook instrumentation. Embedded as text, never run by the backend."""
import hashlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import sys
import threading
import time

# Set before workload imports torch or initializes CUDA. Required by deterministic GEMM.
os.environ.setdefault('CUBLAS_WORKSPACE_CONFIG', ':4096:8')


def execute_workload(context, source):
    output = Path(context['output_dir'])
    output.mkdir(parents=True, exist_ok=True)
    root = output.parent
    assert hashlib.sha256(source.encode('utf-8')).hexdigest() == context['code_sha256']
    (root / 'workload.py').write_text(source, encoding='utf-8')
    records = []
    start = time.monotonic()
    limit = context['budget']['output_bytes']
    original_out, original_err = sys.stdout, sys.stderr
    log = (output / 'runner.log').open('w', encoding='utf-8', buffering=1)

    def check_size():
        if sum(p.stat().st_size for p in output.rglob('*') if p.is_file()) > limit:
            raise ValueError('Output budget exceeded')

    class Tee:
        def __init__(self, original):
            self.original = original
        def write(self, text):
            self.original.write(text)
            log.write(text)
            check_size()
            return len(text)
        def flush(self):
            self.original.flush()
            log.flush()

    def finite_mapping(mapping):
        if not isinstance(mapping, dict) or not mapping:
            raise ValueError('Nonempty measurements required')
        for key, value in mapping.items():
            if not isinstance(key, str) or isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError('Measurements must be finite numbers')
        return mapping

    def emit(step, metrics, total_steps=None):
        if type(step) is not int or step < 1 or (records and step <= records[-1]['step']):
            raise ValueError('Epoch steps must be strictly increasing positive integers')
        if step > context['config']['max_epochs'] or total_steps != context['config']['max_epochs']:
            raise ValueError('Epoch count differs from configured budget')
        elapsed = time.monotonic() - start
        if elapsed > context['config']['training_seconds']:
            raise TimeoutError('Training time budget exceeded')
        record = {'step': step, 'epoch': step, 'elapsed_seconds': elapsed,
                  'metrics': finite_mapping(metrics), 'total_steps': total_steps}
        if context['metric']['name'] not in metrics:
            raise ValueError('Primary metric missing from telemetry')
        records.append(record)
        (output / 'metrics.json').write_text(json.dumps(records, allow_nan=False), encoding='utf-8')
        print('AILAB_METRIC ' + json.dumps(record, allow_nan=False), flush=True)
        check_size()

    def deadline():
        # Hard stop applies to this remote kernel only. No retry of training.
        try:
            message = 'AILAB_FAILED training wall-clock budget exceeded\n'
            original_err.write(message)
            original_err.flush()
            log.write(message)
            log.flush()
        finally:
            os._exit(124)

    timer = threading.Timer(context['config']['training_seconds'], deadline)
    timer.daemon = True
    sys.stdout, sys.stderr = Tee(original_out), Tee(original_err)
    try:
        timer.start()
        if context['competition_slug'] == 'soil-grain-size-from-photos':
            mounts = []
            for name in context['input_mounts']:
                mount = Path(name)
                if not mount.is_dir():
                    raise FileNotFoundError('Approved competition mount unavailable: ' + name)
                mounts.append({'path':name,'files':sum(1 for p in mount.rglob('*') if p.is_file())})
            print('AILAB_MOUNT ' + json.dumps(mounts), flush=True)
        namespace = {'__name__': 'ailab_workload'}
        exec(compile(source, str(root / 'workload.py'), 'exec'), namespace)
        result = namespace['run'](context, emit)
        if not isinstance(result, dict) or set(result) != {'measurements', 'split', 'artifacts'}:
            raise ValueError('Invalid workload result fields')
        measurements = finite_mapping(result['measurements'])
        metric_name = context['metric']['name']
        if metric_name not in measurements or not records or len(records) != context['config']['max_epochs']:
            raise ValueError('Missing final metric or per-epoch evidence')
        if measurements[metric_name] != records[-1]['metrics'][metric_name]:
            raise ValueError('Final metric does not match last epoch')
        evidence = result['split']
        train, validation = evidence['train_sample_ids'], evidence['validation_sample_ids']
        if not train or not validation or len(set(train)) != len(train) or len(set(validation)) != len(validation) or set(train) & set(validation):
            raise ValueError('Invalid or overlapping split groups')
        if any(not isinstance(group, str) or not group for group in train + validation):
            raise ValueError('Split group IDs must be nonempty strings')
        if any(type(evidence[key]) is not int or evidence[key] < 1 for key in ('train_images', 'validation_images')):
            raise ValueError('Split image counts must be positive integers')
        if context['competition_slug'] == 'soil-grain-size-from-photos':
            if len(train) != 20 or len(validation) != 4 or evidence['train_images'] + evidence['validation_images'] != 127:
                raise ValueError('Real Soil split/counts differ from approved baseline')
        if not isinstance(result['artifacts'], list):
            raise ValueError('Artifacts must be a list')
        artifacts = []
        reserved = {'result.json', 'metrics.json', 'runner.log'}
        for artifact in result['artifacts']:
            if not isinstance(artifact, dict) or set(artifact) != {'path', 'purpose'}:
                raise ValueError('Invalid artifact declaration')
            relative = artifact['path']
            path = output / relative
            if not isinstance(relative, str) or '\\' in relative or Path(relative).is_absolute() or '..' in Path(relative).parts or relative in reserved:
                raise ValueError('Unsafe or reserved artifact path')
            if not path.is_file() or path.is_symlink() or not path.resolve().is_relative_to(output.resolve()):
                raise ValueError('Artifact is missing or outside output')
            artifacts.append({'path': relative, 'purpose': artifact['purpose'], 'bytes': path.stat().st_size,
                              'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
        if len({a['path'] for a in artifacts}) != len(artifacts):
            raise ValueError('Duplicate artifact paths')
        actual = {p.relative_to(output).as_posix() for p in output.rglob('*') if p.is_file()}
        if actual - reserved != {a['path'] for a in artifacts}:
            raise ValueError('Undeclared output files')
        elapsed = time.monotonic() - start
        if elapsed > context['config']['training_seconds']:
            raise TimeoutError('Training time budget exceeded')
        versions = {}
        for package in ('torch', 'numpy', 'pandas', 'Pillow'):
            try:
                versions[package] = importlib.metadata.version(package)
            except importlib.metadata.PackageNotFoundError:
                versions[package] = 'not installed'
        payload = {key: context[key] for key in ('run_id', 'proposal_id', 'proposal_version', 'code_sha256',
                    'context_sha256', 'data_refs', 'input_mounts', 'config')}
        payload.update(schema_version=1, split={'approved': context['split'], 'observed': evidence},
                       seed=context['config']['seed'], metric=context['metric'], measurements=measurements,
                       artifacts=artifacts, elapsed_seconds=elapsed, environment={'python': sys.version, **versions})
        (output / 'result.json').write_text(json.dumps(payload, allow_nan=False, indent=2), encoding='utf-8')
        print('AILAB_COMPLETE ' + context['run_id'], flush=True)
        check_size()
    except BaseException:
        import traceback
        traceback.print_exc()
        raise
    finally:
        timer.cancel()
        sys.stdout, sys.stderr = original_out, original_err
        log.close()
