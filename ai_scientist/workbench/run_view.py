"""Read-only run presentation shared by notebook and SSH execution paths."""
import hashlib
import json
import re
from pathlib import PurePosixPath

BUNDLE_FILES = ('notebook.ipynb', 'kernel-metadata.json', 'context.json', 'payload.json', 'checks.json')
ARTIFACT_FILES = (*BUNDLE_FILES, 'source/workload.py', 'journal.json', 'bundle-manifest.json', 'scope-review.json',
                  'submission-intent.json', 'launch-readiness.json', 'remote-identity.json',
                  'save-receipt.json', 'launch-diagnostic.json',
                  'collection-manifest.json', 'result-facts.json', 'report.md', 'retry-feedback.json',
                  'output/result.json', 'output/metrics.json', 'output/runner.log',
                  'submit-bundle/notebook.ipynb', 'submit-bundle/kernel-metadata.json', 'submit-bundle/bundle-manifest.json')


class RunView:
    def __init__(self, store, workspace, allow_unknown_retry):
        self.store, self.workspace = store, workspace
        self.allow_unknown_retry = allow_unknown_retry

    def root(self, project_id, run_id):
        # Validate ownership before deriving a fixed path, never accept client paths.
        self.store.run(project_id, run_id)
        root = self.store.directory(project_id) / 'runs' / run_id
        if root.is_symlink() or not root.resolve().is_relative_to(self.workspace.resolve()):
            raise ValueError('Run artifact directory must remain inside the workspace')
        return root

    def variant_baseline(self, project_id, run_id):
        """Capture bounded text and immutable references from an owned saved run."""
        run = self.store.run(project_id, run_id)
        approved = self.store.approved_snapshot(project_id, run_id)
        parent_sources = [
            {key: source[key] for key in ('id', 'title', 'kind', 'version', 'content_sha256')}
            for source in approved['snapshot']['resources']
        ]
        baseline = {
            'parent': {
                'run_id': run_id, 'proposal_id': run['proposal_id'],
                'proposal_version': run['proposal_version'], 'context_sha256': approved['context_sha256'],
                'purpose': approved['body']['objective'], 'sources': parent_sources,
            },
            'result': {'state': run['state'], 'code_sha256': run['code_sha256'], 'report_path': run['report_path']},
            'artifact_refs': [], 'text_files': [],
        }
        root = self.root(project_id, run_id).resolve()
        baseline_total = 0

        def read_text(source_path, stage_path, kind):
            nonlocal baseline_total
            path = root.joinpath(*PurePosixPath(source_path).parts)
            current = root
            for part in PurePosixPath(source_path).parts:
                current = current / part
                if current.is_symlink() or current.is_junction():
                    return {'path': source_path, 'stage_path': stage_path, 'kind': kind,
                            'available': False, 'reason': 'linked_file_refused'}
            if not path.resolve().is_relative_to(root) or not path.is_file():
                return {'path': source_path, 'stage_path': stage_path, 'kind': kind,
                        'available': False, 'reason': 'missing'}
            size = path.stat().st_size
            if size > 1_048_576:
                return {'path': source_path, 'stage_path': stage_path, 'kind': kind,
                        'available': False, 'bytes': size, 'reason': 'over_1_mib_limit'}
            if baseline_total + size > 1_048_576:
                return {'path': source_path, 'stage_path': stage_path, 'kind': kind,
                        'available': False, 'bytes': size, 'reason': 'over_1_mib_total_limit'}
            try:
                data = path.read_bytes()
                text = data.decode('utf-8')
            except (OSError, UnicodeDecodeError):
                return {'path': source_path, 'stage_path': stage_path, 'kind': kind,
                        'available': False, 'bytes': size, 'reason': 'not_utf8_text'}
            if len(data) != size:
                return {'path': source_path, 'stage_path': stage_path, 'kind': kind,
                        'available': False, 'bytes': len(data), 'reason': 'changed_during_capture'}
            sha256 = hashlib.sha256(data).hexdigest()
            if kind == 'code' and run['code_sha256'] and sha256 != run['code_sha256']:
                return {'path': source_path, 'stage_path': stage_path, 'kind': kind,
                        'available': False, 'bytes': size, 'sha256': sha256, 'reason': 'saved_hash_mismatch'}
            baseline_total += len(data)
            baseline_texts[stage_path] = text
            return {'path': source_path, 'stage_path': stage_path, 'kind': kind,
                    'available': True, 'bytes': len(data), 'sha256': sha256}

        baseline_texts = {}
        if run['report_path'] == 'report.md':
            report = read_text('report.md', 'baseline/report.md', 'report')
            baseline['text_files'].append(report)
            if report.get('available'):
                baseline['artifact_refs'].append({key: report[key] for key in ('path', 'bytes', 'sha256', 'kind')})
        else:
            baseline['text_files'].append({'path': 'report.md', 'stage_path': 'baseline/report.md',
                                           'kind': 'report', 'available': False, 'reason': 'not_saved'})
        code = read_text('source/workload.py', 'baseline/workload.py', 'code')
        baseline['text_files'].append(code)
        if code.get('available'):
            baseline['artifact_refs'].append({key: code[key] for key in ('path', 'bytes', 'sha256', 'kind')})

        facts_path = root / 'result-facts.json'
        if facts_path.is_file() and not facts_path.is_symlink() and not facts_path.is_junction() and facts_path.stat().st_size <= 100_000:
            try:
                facts = json.loads(facts_path.read_text(encoding='utf-8'))
                metric = facts.get('metric') if isinstance(facts, dict) else None
                if isinstance(metric, dict):
                    baseline['result']['metric'] = {key: metric[key] for key in ('name', 'direction', 'final_value', 'best_value') if key in metric}
            except (OSError, ValueError, TypeError):
                baseline['result']['metric_status'] = 'unavailable'
        with self.store.connection(project_id) as connection:
            if connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='working_runs'").fetchone():
                record = connection.execute('SELECT summary_json,manifest_json FROM working_runs WHERE run_id=?', (run_id,)).fetchone()
                if record:
                    if record['summary_json']:
                        try:
                            summary = json.loads(record['summary_json'])
                            if isinstance(summary, dict):
                                limitations = summary.get('limitations', [])
                                baseline['result']['working_summary'] = {
                                    'succeeded': summary.get('succeeded'),
                                    'summary': str(summary.get('summary', ''))[:4_000],
                                    'limitations': [str(value)[:300] for value in limitations[:10]] if isinstance(limitations, list) else [],
                                }
                        except (TypeError, ValueError):
                            baseline['result']['working_summary_status'] = 'unavailable'
                    if record['manifest_json']:
                        try:
                            manifest = json.loads(record['manifest_json'])
                            files = manifest.get('files', []) if isinstance(manifest, dict) else []
                            if not isinstance(files, list) or len(files) > 512:
                                raise ValueError('Invalid saved working manifest')
                            for item in files:
                                if not isinstance(item, dict) or not set(('path', 'bytes', 'sha256')).issubset(item):
                                    continue
                                relative = item['path']
                                parsed = PurePosixPath(relative) if isinstance(relative, str) else None
                                if (parsed is None or not parsed.parts or parsed.is_absolute() or parsed.parts[0] != 'output'
                                        or parsed.as_posix() != relative or any(part in {'', '.', '..'} for part in parsed.parts)
                                        or '\\' in relative or type(item['bytes']) is not int or item['bytes'] < 0
                                        or not re.fullmatch(r'[0-9a-f]{64}', str(item['sha256']))):
                                    continue
                                path = root.joinpath(*parsed.parts)
                                current = root
                                linked = False
                                for part in parsed.parts:
                                    current = current / part
                                    if current.is_symlink() or current.is_junction():
                                        linked = True
                                        break
                                if (not linked and path.resolve().is_relative_to(root)
                                        and path.is_file() and path.stat().st_size == item['bytes']):
                                    baseline['artifact_refs'].append(
                                        {key: item[key] for key in ('path', 'bytes', 'sha256')})
                            baseline['artifact_refs'] = baseline['artifact_refs'][:64]
                        except (TypeError, ValueError):
                            baseline['result']['manifest_status'] = 'unavailable'
                else:
                    baseline['result']['working_summary_status'] = 'not_saved'
        try:
            from .saved_artifacts import artifact_paths, _read_json
            collection_path = root / 'collection-manifest.json'
            verified = set(artifact_paths(root))
            if verified:
                receipt = _read_json(collection_path, 100_000)
                files = receipt.get('manifest', []) if isinstance(receipt, dict) else []
                for item in files:
                    if not isinstance(item, dict) or item.get('path') not in verified:
                        continue
                    parsed = PurePosixPath(item['path'])
                    current = root
                    linked = False
                    for part in parsed.parts:
                        current = current / part
                        if current.is_symlink() or current.is_junction():
                            linked = True
                            break
                    if not linked:
                        baseline['artifact_refs'].append(
                            {key: item[key] for key in ('path', 'bytes', 'sha256')})
        except (OSError, ValueError, KeyError, TypeError):
            baseline['result']['collection_manifest_status'] = 'unavailable'
        baseline['artifact_refs'] = baseline['artifact_refs'][:64]
        return baseline, baseline_texts

    def detail(self, project_id, run_id):
        from .saved_artifacts import artifact_paths, _collection_state, _report_limit
        run = self.store.run(project_id, run_id)
        root = self.root(project_id, run_id)
        names = (*ARTIFACT_FILES, *(f"attempts/{attempt['attempt']}/{name}" for attempt in run['attempts'] for name in (*BUNDLE_FILES, 'source/workload.py')))
        run['artifacts'] = [name for name in names if (root / name).is_file() and not (root / name).is_symlink()]
        run['artifacts'] = sorted(set(run['artifacts']) | set(artifact_paths(root)))
        run['ready'] = run['state'] == 'PREFLIGHT' and bool(run['attempts']) and bool(run['attempts'][-1]['checks'] and run['attempts'][-1]['checks']['pass'])
        run['coder_calls'] = sum(attempt['origin'] == 'CODEX' for attempt in run['attempts'])
        run['can_retry'] = not run['deleted_at'] and (run['state'] in {'FAILED','COMPLETED','REMOTE_SUCCEEDED','REMOTE_FAILED','COLLECTING'} or (run['state'] == 'UNKNOWN' and self.allow_unknown_retry()))
        approved = self.store.approved_snapshot(project_id, run_id)
        run['purpose'] = approved['body']['objective']
        run['variant'] = approved['snapshot'].get('variant')
        if run['variant']:
            parent = self.store.run(project_id, run['variant']['parent_run_id'])
            run['variant_parent_deleted_at'] = parent['deleted_at']
        run['expected_outputs'] = approved['body'].get('expected_outputs', [])
        run['identity'] = json.loads(run.pop('identity_json')) if run['identity_json'] else None
        collection = _collection_state(root / 'collection-state.json')
        phase = collection.get('phase')
        attempts = collection.get('report_attempts')
        if phase in {'COLLECTING', 'REPORTING', 'COMPLETED', 'retry_wait', 'retry_exhausted',
                     'report_uncertain', 'report_result_missing', 'report_result_invalid', 'interrupted'} and type(attempts) is int and attempts >= 0:
            run['collection'] = {'phase': phase, 'report_attempts': attempts, 'report_limit': _report_limit(collection)}
        facts_path = root / 'result-facts.json'
        if facts_path.is_file() and not facts_path.is_symlink() and facts_path.stat().st_size <= 1_000_000:
            try:
                facts = json.loads(facts_path.read_text(encoding='utf-8'))
                metric = facts.get('metric')
                if isinstance(metric, dict):
                    run['result_metric'] = {key: metric[key] for key in ('name', 'direction', 'final_value', 'best_value') if key in metric}
            except (OSError, ValueError, TypeError):
                pass
        report = root / 'report.md'
        if run.get('report_path') == 'report.md' and report.is_file() and not report.is_symlink() and report.stat().st_size <= 100_000:
            run['report_preview'] = report.read_text(encoding='utf-8')
        # The journal node is persisted in SQLite, while UI detail loads source through allowlisted files.
        run.pop('node_json', None)
        return run

    def history(self, project_id, include_deleted=False):
        history = self.store.history(project_id, include_deleted=include_deleted)
        for item in history['runs']:
            detail = self.detail(project_id, item['id'])
            approved = self.store.approved_snapshot(project_id, item['id'])
            snapshot = approved['snapshot']
            body = approved['body']
            selected_refs = set(body.get('data_refs', []))
            item['purpose'] = detail.get('purpose')
            item['result_metric'] = detail.get('result_metric')
            # History describes the approved inputs as they were pinned at approval time.
            # Current idea/resource rows may be edited or removed later.
            item['idea_id'] = snapshot['idea']['id']
            item['idea_text'] = snapshot['idea']['text']
            item['proposal_objective'] = body['objective']
            item['proposal_version'] = detail.get('proposal_version')
            item['context_sha256'] = approved['context_sha256']
            item['source_refs'] = [
                {key: resource[key] for key in ('id', 'title', 'kind', 'version', 'content_sha256')}
                for resource in snapshot['resources'] if resource['id'] in selected_refs
            ]
            item['code_sha256'] = detail.get('code_sha256')
            item['artifacts'] = detail.get('artifacts', [])
            item['report_available'] = detail.get('report_path') == 'report.md'
            variant = snapshot.get('variant')
            item['variant'] = ({key: variant[key] for key in ('parent_run_id', 'purpose', 'change_summary')}
                                if variant else None)
        return history
