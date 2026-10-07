"""Build and statically check a private notebook bundle without running its source."""
import ast
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import urlsplit
import nbformat
from .models import WorkloadConfig


def competition_slug(snapshot):
    slugs = set()
    for resource in snapshot['resources']:
        url = urlsplit(resource.get('url') or '')
        match = re.match(r'^/competitions/([a-z0-9-]+)(?:/|$)', url.path)
        if url.hostname in {'www.kaggle.com', 'kaggle.com'} and match:
            slugs.add(match[1])
    if len(slugs) != 1:
        raise ValueError('Approved sources must identify exactly one Kaggle competition')
    return slugs.pop()


def check_source(source):
    errors = []
    try:
        tree = ast.parse(source, filename='workload.py')
        compile(tree, 'workload.py', 'exec')  # Compile only: no imports or execution.
    except (SyntaxError, ValueError, TypeError) as exc:
        return [f'Source syntax: {exc}']
    entry = next((n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'run'), None)
    if entry is None or [a.arg for a in entry.args.args] != ['context', 'emit'] or entry.args.vararg or entry.args.kwarg or entry.args.kwonlyargs:
        errors.append('Entry must be exactly def run(context, emit)')
    forbidden_modules = {'subprocess', 'requests', 'httpx', 'urllib', 'socket', 'kaggle', 'kagglesdk'}
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names = [a.name for a in node.names] if isinstance(node, ast.Import) else [node.module or '']
            if any(name.split('.')[0] in forbidden_modules for name in names):
                errors.append('Network/process imports are outside approved workload scope')
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in {'exec', 'eval', '__import__', 'compile'}:
            errors.append('Dynamic code execution is outside workload scope')
    if not any(isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == 'emit' for n in ast.walk(tree)):
        errors.append('Source must call emit for per-epoch measurements')
    if entry is None or not any(isinstance(n, ast.Return) for n in ast.walk(entry)):
        errors.append('run must return measurements/split/artifacts')
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom, ast.FunctionDef, ast.ClassDef)):
            continue
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            continue
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            try:
                ast.literal_eval(node.value)
                continue
            except (ValueError, TypeError):
                pass
        errors.append('Top-level executable statements are not permitted; move I/O into run')
    return list(dict.fromkeys(errors))


def build_bundle(root, run, approved, payload, username):
    root.mkdir(parents=True, exist_ok=True)
    source_dir = root / 'source'
    source_dir.mkdir(exist_ok=True)
    source = payload.source
    code_hash = hashlib.sha256(source.encode('utf-8')).hexdigest()
    (source_dir / 'workload.py').write_text(source, encoding='utf-8', newline='\n')
    (root / 'payload.json').write_text(payload.model_dump_json(indent=2), encoding='utf-8')
    errors = check_source(source)
    if any('checkpoint' in item.lower() for item in approved['body']['expected_outputs']):
        try:
            tree = ast.parse(source)
            saves = [node for node in ast.walk(tree) if isinstance(node, ast.Call) and (
                isinstance(node.func, ast.Attribute) and node.func.attr == 'save' or
                isinstance(node.func, ast.Name) and node.func.id == 'save')]
            if not saves:
                errors.append('Approved expected outputs include a checkpoint, but source has no serialization call')
        except SyntaxError:
            pass  # The syntax failure above is already explicit.
    try:
        config = WorkloadConfig.model_validate(payload.config).model_dump()
        budget = approved['body']['budget']
        if config['seed'] != approved['body']['split']['seed']:
            errors.append('Config seed differs from approved seed')
        if config['training_seconds'] > budget['training_seconds'] or config['output_bytes'] > budget['output_bytes']:
            errors.append('Config exceeds approved budget')
        slug = competition_slug(approved['snapshot'])
        if slug == 'soil-grain-size-from-photos' and config['max_epochs'] > 3:
            errors.append('Approved Soil baseline permits at most 3 epochs')
        if not username or not re.fullmatch(r'[a-zA-Z0-9_-]+', username):
            raise ValueError('Configure the verified kaggle_username before building metadata')
        context = {'run_id': run['id'], 'proposal_id': run['proposal_id'], 'proposal_version': run['proposal_version'],
                   'code_sha256': code_hash, 'context_sha256': approved['context_sha256'],
                   'data_refs': [{k: s[k] for k in ('id', 'version', 'content_sha256', 'url')} for s in approved['snapshot']['resources']
                                 if s['id'] in approved['body']['data_refs']],
                   'competition_slug': slug, 'input_mounts': ['/kaggle/input/competitions/' + slug],
                   'runtime_contract': {'input_mounts': ['/kaggle/input/competitions/' + slug]},
                   'output_dir': '/kaggle/working/ailab_bundle/output', 'config': config,
                   'split': approved['body']['split'], 'metric': approved['body']['metric'],
                   'budget': {key: value for key, value in budget.items() if key not in {'coder_calls', 'training_attempts'}},
                   'objective': approved['body']['objective'], 'expected_outputs': approved['body']['expected_outputs']}
        runner_source = Path(__file__).with_name('notebook_runner.py').read_text(encoding='utf-8')
        notebook = nbformat.v4.new_notebook(cells=[
            nbformat.v4.new_markdown_cell('AI-assisted implementation. Proposal/context are pinned. Mount remains unverified until runtime.'),
            nbformat.v4.new_code_cell('import json\ncontext = json.loads(' + repr(json.dumps(context, ensure_ascii=False)) + ')'),
            nbformat.v4.new_code_cell(runner_source),
            nbformat.v4.new_code_cell('source = ' + repr(source) + '\nexecute_workload(context, source)')],
            metadata={'kernelspec': {'name': 'python3', 'display_name': 'Python 3', 'language': 'python'},
                      'language_info': {'name': 'python'}, 'workbench': {'context_sha256': approved['context_sha256'], 'code_sha256': code_hash}})
        nbformat.validate(notebook)
        for index, cell in enumerate(notebook.cells):
            if cell.cell_type == 'code':
                compile(cell.source, f'notebook-cell-{index}', 'exec')
        with (root/'notebook.ipynb').open('w',encoding='utf-8',newline='\n') as notebook_file:
            nbformat.write(notebook, notebook_file)
        metadata = {'id': username + '/ailab-' + run['id'], 'title': 'ailab-' + run['id'],
                    'code_file': 'notebook.ipynb', 'language': 'python', 'kernel_type': 'notebook',
                    'is_private': True, 'enable_gpu': True, 'enable_tpu': False, 'enable_internet': False,
                    'dataset_sources': [], 'kernel_sources': [], 'competition_sources': [slug]}
        (root / 'kernel-metadata.json').write_text(json.dumps(metadata, indent=2), encoding='utf-8')
        (root / 'context.json').write_text(json.dumps(context, ensure_ascii=False, indent=2), encoding='utf-8')
        if metadata['code_file'] != 'notebook.ipynb' or metadata['competition_sources'] != [slug] or metadata['is_private'] is not True:
            errors.append('Invalid notebook metadata')
    except Exception as exc:
        errors.append(f'Config/notebook/metadata: {type(exc).__name__}: {exc}')
    checks = {'pass': not errors, 'errors': errors, 'code_sha256': code_hash,
              'checks': ['source syntax/compile', 'run(context, emit)', 'config bounds/seed', 'nbformat/cell syntax',
                         'private metadata/competition source', 'fixed telemetry/result runner', 'approved checkpoint serialization when requested'],
              'limitations': ['Static checks do not prove ML correctness or absence of leakage',
                              'Mount and installed runtime packages still require Kaggle execution']}
    (root / 'checks.json').write_text(json.dumps(checks, ensure_ascii=False, indent=2), encoding='utf-8')
    return checks
