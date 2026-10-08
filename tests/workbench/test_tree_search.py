"""Local integration evidence for the original manager; no provider/Kaggle calls."""
import asyncio
import base64
import hashlib
import json
import re
import threading
from types import SimpleNamespace
import urllib.request

import pytest

from ai_scientist.workbench.journal import restore_journal
from ai_scientist.workbench.tree_search import TreeSearchRun
from ai_scientist.workbench.named_paths import filesystem_path, display_path
from ai_scientist.workbench.agents.codex import parse_codex_jsonl
from test_working import Donor, Terminal, fixture


class SearchTerminal(Terminal):
    def request(self, action, **body):
        if action == 'exec' and 'shutil.rmtree' in body['command']:
            self.files = {name: value for name, value in self.files.items() if not name.startswith(('source/', 'output/'))}
        return super().request(action, **body)


class SearchDonor(Donor):
    def open(self, session_id, output):
        terminal = SearchTerminal(output)
        self.opens.append((session_id, terminal))
        return terminal


class SearchRuntime:
    def __init__(self, *, fail_draft=True, fail_all=False, substages=False):
        self.calls, self.fail_draft, self.fail_all, self.substages = [], fail_draft, fail_all, substages
        self.node_actions = []

    def run(self, request, progress, cancelled):
        self.calls.append(request)
        if request.role == 'mvp1_search_query':
            data = json.loads((request.workdir / 'query-request.json').read_text(encoding='utf-8'))
            function = data['function']
            if function['name'] == 'select_best_implementation':
                candidates = re.findall(r'ID: ([a-f0-9]{32})', data['system_message']['Candidates'])
                response = {'selected_id': candidates[-1], 'reasoning': 'Local fixture selection, no real experiment.'}
            elif function['name'] == 'evaluate_stage_completion':
                response = {'is_complete': self.substages and 'current sub-stage' in data['system_message'],
                            'reasoning': 'Local fixture stage evaluation.', 'missing_criteria': ['Continue within budget']}
            elif function['name'] == 'generate_substage_goals':
                response = {'goals': 'Refine the fixture comparison.', 'sub_stage_name': 'refinement'}
            else:
                raise AssertionError(function['name'])
            return SimpleNamespace(text=json.dumps({'response': json.dumps(response)}), files={}, usage={})
        assert request.role == 'mvp1_search_node'
        data = json.loads((request.workdir / 'working-request.json').read_text(encoding='utf-8'))
        search = data['search']
        self.node_actions.append((search['stage'], search['action']))
        access = json.loads((request.workdir / 'terminal-access.json').read_text())
        def call(action, **body):
            req = urllib.request.Request(access['url'], json.dumps({'action': action, **body}).encode(),
                    {'Authorization': 'Bearer ' + access['token'], 'Content-Type': 'application/json'})
            with urllib.request.urlopen(req, timeout=5) as response:
                return json.load(response)
        call('exec', command='local fixture experiment', timeout=2)
        number = len(self.node_actions)
        for path, content in {'source/general.py': f'# LOCAL FIXTURE ONLY\nprint({number})\n',
                              'output/comparison.csv': f'fixture_step\n{number}\n'}.items():
            call('write', path=path, data=base64.b64encode(content.encode()).decode())
        failed = self.fail_all or (self.fail_draft and search['action'] == 'draft')
        return SimpleNamespace(text=json.dumps({'succeeded': not failed, 'summary': f'Local fixture node {number}, not a real Kaggle result.',
            'limitations': ['Fixture only; no training was executed.'], 'output_files': ['output/comparison.csv'],
            'plan': f'{search["action"]} · fixture {number}', 'metric': None, 'datasets_tested': []}), files={}, usage={})


def test_original_manager_four_stages_debug_substages_and_experiment_layout(tmp_path):
    async def check():
        runtime, donor = SearchRuntime(substages=True), SearchDonor()
        store, project, run, worker, planner, service, _, mcp, _ = fixture(tmp_path, runtime=runtime, donor=donor)
        service.config.codex_model = 'fixture-model'
        await service.start(project, run, search={'stage_iterations': [2,2,2,1], 'debug_prob': 1.0})
        await service.tasks[project, run]
        detail = service.detail(project, run)
        assert detail['state'] == 'COMPLETED', detail
        assert detail['working']['stop_confirmed']
        assert len(donor.opens) == len(mcp.calls) == 1
        assert runtime.node_actions[:2] == [('1_initial_implementation_1_preliminary', 'draft'), ('1_initial_implementation_1_preliminary', 'debug')]
        assert {int(stage[0]) for stage, _ in runtime.node_actions} == {1,2,3,4}
        assert len(runtime.node_actions) == 7
        assert detail['artifact_dir'].startswith('experiment/') and detail['artifact_dir'].endswith('_attempt_0')
        root = service.view.root(project, run)
        assert root.parent == filesystem_path(store.directory(project) / 'experiment')
        assert detail['search']['directory'] == display_path(root)
        assert not (tmp_path / 'experiments').exists()
        assert all((root / path).is_file() for path in ('idea.md','idea.json','token_tracker.json','review_text.txt','logs/0-run/unified_tree_viz.html'))
        saved = json.loads((root / 'logs/0-run/search-state.json').read_text())
        assert saved['status'] == 'completed'
        for stage in saved['stages']:
            assert stage['stage_number'] == int(stage['name'][0])
        first = restore_journal(saved['journals'][saved['stages'][0]['name']])
        assert first[1].parent is first[0] and first[1] in first[0].children
        assert 'terminal-access.json' not in '|'.join(detail['artifacts'])
        for node in root.glob('logs/0-run/nodes/*'):
            manifest = json.loads((node / 'manifest.json').read_text())
            for item in manifest['files']:
                assert hashlib.sha256((node / item['path']).read_bytes()).hexdigest() == item['sha256']
        assert json.loads((root / 'token_tracker.json').read_text())['usage_status'] == 'unavailable'
        before = {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
                  for path in root.glob('logs/0-run/nodes/*/source/*')}
        new = await service.retry(project, run, 'e' * 32)
        await service.start(project, new['id'], search={'stage_iterations': [1,1,1,1]})
        await service.tasks[project, new['id']]
        assert service.view.root(project, new['id']).name.endswith('_attempt_1')
        assert before == {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
                          for path in root.glob('logs/0-run/nodes/*/source/*')}
        roots = [root, service.view.root(project, new['id'])]
        source = store.resources(project)[0]
        copies = [path for location in roots for workspace in ('working-agent', 'query-agent')
                  for path in (location / workspace / 'library').rglob('source.md')]
        assert len(copies) == 4
        store.delete_resource(project, source['id'])
        assert all(not path.exists() for path in copies)
        assert all((location / 'report.md').is_file() for location in roots)
        await service.close(1)
        await worker.close(1)
    asyncio.run(check())


def test_all_failed_drafts_stop_without_claiming_four_stage_success(tmp_path):
    async def check():
        runtime = SearchRuntime(fail_all=True)
        _, project, run, worker, _, service, _, _, donor = fixture(tmp_path, runtime=runtime, donor=SearchDonor())
        service.config.codex_model = 'fixture-model'
        await service.start(project, run, search={'stage_iterations':[1,1,1,1]})
        await service.tasks[project, run]
        detail = service.detail(project, run)
        assert detail['state'] == 'FAILED' and detail['working']['stop_confirmed']
        assert len(runtime.node_actions) == len(donor.opens) == 1
        assert len(detail['search']['stages']) == 1
        assert json.loads((service.view.root(project, run) / 'logs/0-run/search-state.json').read_text())['status'] == 'failed'
        await service.close(1)
        await worker.close(1)
    asyncio.run(check())


def test_stop_cancels_exact_search_without_opening_another_session(tmp_path):
    class PausedRuntime(SearchRuntime):
        entered = threading.Event()
        def run(self, request, progress, cancelled):
            if request.role == 'mvp1_search_node':
                self.entered.set()
                while not cancelled():
                    threading.Event().wait(.01)
                raise RuntimeError('Local fixture cancelled')
            return super().run(request, progress, cancelled)
    async def check():
        runtime = PausedRuntime()
        _, project, run, worker, _, service, _, mcp, donor = fixture(tmp_path, runtime=runtime, donor=SearchDonor())
        service.config.codex_model = 'fixture-model'
        await service.start(project, run, search={'stage_iterations':[2,2,2,1]})
        assert await asyncio.to_thread(runtime.entered.wait, 5)
        await service.stop(project, run)
        await asyncio.wait_for(service.tasks[project, run], 10)
        assert service.detail(project, run)['state'] == 'CANCELLED'
        assert service.record(project, run)['stop_confirmed']
        assert len(mcp.calls) == len(donor.opens) == 1
        assert not (service.view.root(project, run) / 'working-agent/terminal-access.json').exists()
        assert json.loads((service.view.root(project, run) / 'logs/0-run/search-state.json').read_text())['status'] == 'interrupted'
        await service.close(1)
        await worker.close(1)
    asyncio.run(check())


def test_codex_usage_is_measured_from_turn_event_for_search_roles():
    raw = '\n'.join(json.dumps(event) for event in [
        {'type':'item.completed','item':{'type':'agent_message','text':json.dumps({'response':'fixture'})}},
        {'type':'turn.completed','usage':{'input_tokens':10,'cached_input_tokens':3,'output_tokens':2}}]).encode()
    result = parse_codex_jsonl(raw, role='mvp1_search_query')
    assert result['usage'] == {'input_tokens':10,'cached_input_tokens':3,'output_tokens':2}
    assert json.loads(result['text']) == {'response':'fixture'}
