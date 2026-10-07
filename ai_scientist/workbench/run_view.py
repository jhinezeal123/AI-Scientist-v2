"""Read-only run presentation shared by notebook and SSH execution paths."""
import hashlib
import json

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
        root = self.workspace / '.workbench/projects' / project_id / 'runs' / run_id
        if root.is_symlink() or not root.resolve().is_relative_to(self.workspace.resolve()):
            raise ValueError('Run artifact directory must remain inside the workspace')
        return root

    def detail(self, project_id, run_id):
        from .saved_artifacts import artifact_paths, _collection_state, _report_limit
        run = self.store.run(project_id, run_id)
        root = self.root(project_id, run_id)
        names = (*ARTIFACT_FILES, *(f"attempts/{attempt['attempt']}/{name}" for attempt in run['attempts'] for name in (*BUNDLE_FILES, 'source/workload.py')))
        run['artifacts'] = [name for name in names if (root / name).is_file() and not (root / name).is_symlink()]
        run['artifacts'] = sorted(set(run['artifacts']) | set(artifact_paths(root)))
        run['ready'] = run['state'] == 'PREFLIGHT' and bool(run['attempts']) and bool(run['attempts'][-1]['checks'] and run['attempts'][-1]['checks']['pass'])
        run['coder_calls'] = sum(attempt['origin'] == 'CODEX' for attempt in run['attempts'])
        run['can_retry'] = run['state'] in {'FAILED','COMPLETED','REMOTE_SUCCEEDED','REMOTE_FAILED','COLLECTING'} or (run['state'] == 'UNKNOWN' and self.allow_unknown_retry())
        approved = self.store.approved_snapshot(project_id, run_id)
        run['purpose'] = approved['body']['objective']
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

    def history(self, project_id):
        history = self.store.history(project_id)
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
        return history
