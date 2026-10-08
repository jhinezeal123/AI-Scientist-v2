"""Run the upstream AgentManager with Codex and one persistent Kaggle terminal."""
import asyncio
from dataclasses import asdict
import hashlib
import json
import math
import re
from pathlib import Path
import shlex
import time

import jsonschema
from omegaconf import OmegaConf

from ai_scientist.treesearch.agent_manager import AgentManager
from ai_scientist.treesearch.backend import FunctionSpec, use_query_provider
from ai_scientist.treesearch.journal import Node
from ai_scientist.treesearch.search_policy import select_parallel_nodes
from ai_scientist.treesearch.utils.config import save_run
from ai_scientist.treesearch.utils.metric import MetricValue
from ai_scientist.utils.token_tracker import TokenTracker

from .journal import journal_snapshot, restore_journal
from .models import WorkingPayload
from .ssh_terminal import AgentTerminalBridge, collect_files
from .system_prompt import load_prompt


class SearchInterrupted(BaseException):
    """Cancellation must pass through upstream provider fallback handlers."""


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    temporary.replace(path)


class RemoteSearchAgent:
    """Stage agent contract used by AgentManager; branch selection stays upstream."""
    def __init__(self, owner, task_desc, cfg, journal, stage_name=None,
                 best_stage1_node=None, best_stage2_node=None, best_stage3_node=None):
        self.owner, self.task_desc, self.cfg, self.journal = owner, task_desc, cfg, journal
        self.stage_name = stage_name
        self.best_stage1_node, self.best_stage2_node, self.best_stage3_node = best_stage1_node, best_stage2_node, best_stage3_node
        self.num_workers = 1  # One persistent shell owns cwd/env; no local GPU pool.

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def step(self, exec_callback):
        self.owner.check_running()
        if self.journal.nodes and self.stage_name.startswith('2_'):
            self.best_stage1_node = self.journal.nodes[0]
        if self.journal.nodes and self.stage_name.startswith('4_'):
            self.best_stage3_node = self.journal.nodes[0]
        selected = select_parallel_nodes(self)[0]
        # The upstream manager copies stage baselines. Relink the selected copy
        # to this journal's canonical object so the exporter sees its children.
        parent = self.journal.get_node_by_id(selected.id) if selected else None
        if selected and parent is None:
            raise ValueError('Selected baseline is missing from its stage journal')
        action = 'draft' if parent is None else 'debug' if parent.is_buggy else 'improve'
        node = self.owner.execute_node(self.stage_name, self.task_desc, parent, action)
        self.journal.append(node)


class TreeSearchRun:
    def __init__(self, service, key, approved, descriptor, terminal, options):
        self.service, self.key, self.approved = service, key, approved
        self.descriptor, self.terminal, self.options = descriptor, terminal, options
        self.root = service.view.root(*key)
        self.logs = self.root / 'logs/0-run'
        self.workdir = self.root / 'working-agent'
        self.querydir = self.root / 'query-agent'
        self.querydir.mkdir(exist_ok=True)
        service.store.library(key[0]).stage(approved['snapshot'], self.querydir,
                                          service.store.variant_stage_files(approved['snapshot']))
        self.deadline = time.monotonic() + min(getattr(service.config, 'working_seconds', 900), descriptor['ttl_seconds'] - 60)
        self.loop = asyncio.get_running_loop()
        self.tracker = TokenTracker()
        self.calls, self.cache, self.nodes, self.stage_results, self.node_stages = [], {}, {}, {}, {}
        self.manager = None
        self.status = 'running'

    def check_running(self):
        if self.key in self.service.stop_requests or self.service.closed:
            raise SearchInterrupted('User stopped tree search')
        if time.monotonic() >= self.deadline:
            raise SearchInterrupted('Working search deadline reached')

    def call_agent(self, role, prompt, workdir):
        self.check_running()
        request = self.service.planner.bindings.request_type(self.key[1], role, prompt, workdir,
            timeout_seconds=max(1, int(self.deadline - time.monotonic())), max_output_bytes=3_000_000)
        result, payload = asyncio.run_coroutine_threadsafe(self.service.planner.worker.run(request), self.loop).result()
        usage = getattr(result, 'usage', {}) or {}
        measured = all(type(usage.get(key)) is int and usage[key] >= 0 for key in ('input_tokens', 'output_tokens'))
        if measured:
            self.tracker.add_tokens(self.service.config.codex_model, usage['input_tokens'], usage['output_tokens'],
                                    0, usage.get('cached_input_tokens', 0))
        self.calls.append({'role': role, 'session_id': getattr(result, 'session_id', None),
                           'usage': usage if measured else None})
        write_json(self.root / 'token_tracker.json', {
            'usage_status': 'complete' if all(call['usage'] is not None for call in self.calls) else 'partial' if any(call['usage'] for call in self.calls) else 'unavailable',
            'models': {name: {'tokens': {**dict(counts), 'reasoning': None}, 'cost (USD)': None}
                       for name, counts in self.tracker.token_counts.items()}, 'calls': self.calls})
        return payload

    def query(self, *, system_message, user_message, func_spec=None, **kwargs):
        self.check_running()
        spec = (asdict(func_spec) if isinstance(func_spec, FunctionSpec) else func_spec) if func_spec else None
        data = {'approved': {**self.approved, 'snapshot': self.service.store.library(self.key[0]).agent_snapshot(self.approved['snapshot'])},
                'system_message': system_message, 'user_message': user_message, 'function': spec,
                'search_evidence': self.stage_results}
        if spec and spec['name'] == 'select_best_implementation':
            candidate_ids = set(re.findall(r'ID: ([0-9a-f]{32})', system_message.get('Candidates', '')))
            data['search_evidence'] = {node_id: self.nodes[node_id][2].model_dump()
                                       for node_id in sorted(candidate_ids) if node_id in self.nodes}
        digest = hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        if digest in self.cache:
            return self.cache[digest]
        write_json(self.querydir / 'query-request.json', data)
        payload = self.call_agent('mvp1_search_query', load_prompt('search.query', workdir=self.querydir), self.querydir)
        response = json.loads(payload.response) if spec else payload.response
        if spec:
            jsonschema.validate(response, spec['json_schema'])
            if spec['name'] == 'generate_substage_goals' and not re.fullmatch(r'[A-Za-z-]{1,64}', response['sub_stage_name']):
                raise ValueError('Substage name must be a safe single name without numbers')
        write_json(self.logs / 'feedback' / f'{len(self.calls):04d}-{digest[:10]}.json',
                   {'request': data, 'response': response})
        self.cache[digest] = response
        return response

    def execute_node(self, stage_name, task_desc, parent, action):
        node = Node(plan=action, code='', parent=parent)
        node_root = self.logs / 'nodes' / node.id
        node_root.mkdir(parents=True)
        self.service.records.update(*self.key, phase=stage_name)
        record = self.service.record(*self.key)
        self.service.records.update(*self.key, agent_called=record['agent_called'] + 1)
        self.service.records.append_log(*self.key, f'Giai đoạn {stage_name}: {action} · node {node.id[:8]}\n', 'backend')
        remote = self.descriptor['remote_directory']
        # Reset only the two backend-owned implementation/result folders, never
        # the notebook, Library, SSH process, or credentials. Commands keep SSH.
        cleanup = "import pathlib,shutil; [(shutil.rmtree(p) if p.is_dir() and not p.is_symlink() else p.unlink()) for p in [pathlib.Path('source'),pathlib.Path('output')] if p.exists() or p.is_symlink()]"
        self.terminal.request('exec', command=f'cd {shlex.quote(remote)} && python -c {shlex.quote(cleanup)}', timeout=30)
        if parent and parent.id in self.nodes:
            baseline_root, baseline_manifest, _ = self.nodes[parent.id]
            import base64
            for item in baseline_manifest['files']:
                data = (baseline_root / item['path']).read_bytes()
                if hashlib.sha256(data).hexdigest() != item['sha256']:
                    raise ValueError('Saved node baseline was changed')
                self.terminal.request('write', path=item['path'], data=base64.b64encode(data).decode())
        before_commands = self.terminal.request('manifest', limit=self.approved['body'].get('budget', {}).get('output_bytes'))['command_count']
        request = self.service._request(self.key, self.approved, self.descriptor, self.workdir)
        data_path = self.workdir / 'working-request.json'
        data = json.loads(data_path.read_text(encoding='utf-8'))
        data['search'] = {'stage': stage_name, 'stage_task': task_desc, 'action': action,
                          'parent_id': parent.id if parent else None,
                          'parent_analysis': parent.analysis if parent else None,
                          'parent_metric': parent.metric.to_dict() if parent and parent.metric else None}
        data['instructions'].append(load_prompt('search.node_instructions'))
        data.pop('previous_source', None)
        write_json(data_path, data)
        started = time.monotonic()
        with_gateway = AgentTerminalBridge(self.terminal, self.workdir)
        try:
            payload = self.call_agent('mvp1_search_node', load_prompt('search.node', workdir=self.workdir), self.workdir)
        finally:
            with_gateway.close()
        self.check_running()
        manifest = collect_files(self.terminal, node_root, self.approved['body'].get('budget', {}).get('output_bytes'))
        names = {item['path'] for item in manifest['files']}
        if not set(payload.output_files).issubset(names) or (payload.succeeded and manifest['command_count'] <= before_commands):
            raise ValueError('Search node result does not match verified SSH execution/files')
        node.plan, node.analysis = payload.plan, payload.summary
        node.is_buggy = not payload.succeeded
        node.is_buggy_plots = False  # No mandatory plotting contract for general work.
        node.exec_time = time.monotonic() - started
        node.exp_dir = str(node_root)
        node.vlm_feedback_summary = [payload.summary, *payload.limitations]
        node.datasets_successfully_tested = payload.datasets_tested
        node.metric = self.verified_metric(payload.metric, node_root, names)
        sources = []
        for item in manifest['files']:
            if item['path'].startswith('source/') and item['bytes'] <= 1_000_000:
                try:
                    sources.append('# File: ' + item['path'] + '\n' + (node_root / item['path']).read_text(encoding='utf-8'))
                except UnicodeDecodeError:
                    pass
        node.code = '\n\n'.join(sources)[:1_000_000]
        node._term_out = [payload.summary]
        write_json(node_root / 'manifest.json', manifest)
        write_json(node_root / 'result.json', payload.model_dump())
        self.nodes[node.id] = (node_root, manifest, payload)
        self.node_stages[node.id] = stage_name
        return node

    def verified_metric(self, metric, root, names):
        if metric is None:
            return MetricValue(None)
        if metric.evidence_file not in names or not math.isfinite(metric.value):
            raise ValueError('Metric requires a collected finite value')
        value = json.loads((root / metric.evidence_file).read_text(encoding='utf-8'))
        if not metric.evidence_pointer.startswith('/'):
            raise ValueError('Metric evidence requires a JSON pointer')
        for part in metric.evidence_pointer[1:].split('/'):
            key = part.replace('~1', '/').replace('~0', '~')
            value = value[int(key)] if isinstance(value, list) else value[key]
        if type(value) not in (int, float) or value != metric.value:
            raise ValueError('Metric value differs from collected evidence')
        approved_metric = self.approved['body'].get('metric')
        if isinstance(approved_metric, dict) and any(approved_metric.get(key) not in (None, getattr(metric, key)) for key in ('name', 'direction')):
            raise ValueError('Metric differs from the approved proposal')
        return MetricValue(metric.value, name=metric.name, maximize=metric.direction == 'maximize')

    def checkpoint(self, manager):
        state = {
            'status': self.status,
            'options': self.options.model_dump(), 'stages': [asdict(stage) for stage in manager.stages],
            'transitions': [asdict(item) for item in manager.stage_history],
            'journals': {name: journal_snapshot(journal) for name, journal in manager.journals.items()},
            'stage_results': self.stage_results,
            'selected_node_id': getattr(self, 'selected_node_id', None)}
        write_json(self.logs / 'search-state.json', state)
        from ai_scientist.treesearch.utils.run_tree import render_search_state
        html = render_search_state(state, self.root.name)
        target = self.logs / 'unified_tree_viz.html'
        temporary = target.with_suffix('.html.tmp')
        temporary.write_text(html, encoding='utf-8')
        temporary.replace(target)

    def save_stage(self, stage, journal):
        self.stage_results[stage.name] = [{'id': node.id, 'parent_id': node.parent.id if node.parent else None,
                                         'succeeded': node.is_buggy is False, 'summary': node.analysis,
                                         'metric': node.metric.to_dict() if node.metric else None}
                                        for node in journal.nodes]
        save_run(self.manager.cfg, journal, stage_name='stage_' + stage.name)
        self.checkpoint(self.manager)

    def run(self):
        cfg = OmegaConf.load(Path(__file__).resolve().parents[2] / 'bfts_config.yaml')
        cfg.log_dir, cfg.workspace_dir, cfg.exp_name = str(self.logs), str(self.root), '0-run'
        # save_run operates on Paths; allow these objects in the original config.
        cfg = OmegaConf.create(OmegaConf.to_container(cfg), flags={'allow_objects': True})
        cfg.log_dir, cfg.workspace_dir = self.logs, self.root
        cfg.agent.num_workers = 1
        cfg.agent.multi_seed_eval.num_seeds = 0
        cfg.agent.scale_experiments = False
        cfg.agent.stages.count_generated_nodes = True
        for index, maximum in enumerate(self.options.stage_iterations, 1):
            cfg.agent.stages[f'stage{index}_max_iters'] = maximum
        for key in ('num_drafts', 'debug_prob', 'max_debug_depth'):
            cfg.agent.search[key] = getattr(self.options, key)
        for key in ('code', 'feedback', 'select_node', 'summary'):
            cfg.agent[key] = {'model': self.service.config.codex_model, 'temp': 0.3}
        description = json.loads((self.root / 'idea.json').read_text(encoding='utf-8'))
        goals = json.loads(load_prompt('search.stage_goals'))
        with use_query_provider(self.query):
            self.manager = AgentManager(json.dumps(description, ensure_ascii=False), cfg, self.root,
                agent_factory=lambda **kwargs: RemoteSearchAgent(self, **kwargs),
                checkpoint_callback=self.checkpoint, stage_goals={int(key): value for key, value in goals.items()})
            self.checkpoint(self.manager)
            write_json(self.root / 'token_tracker.json', {'usage_status': 'unavailable', 'models': {}, 'calls': []})
            try:
                self.manager.run(exec_callback=None, step_callback=self.save_stage)
            finally:
                self.checkpoint(self.manager)
            # Keep original stage journals as evidence; the unified viewer combines
            # every node once using its original ID and parent relationship.
            cfg.unified_stage_paths = {}
            for number, main_name in self.manager.main_stage_dict.items():
                records = {}
                for name, stage_journal in self.manager.journals.items():
                    if self.manager.parse_stage_names(name)[0] == number:
                        for node in stage_journal.nodes:
                            records.setdefault(node.id, node.to_dict())
                if records:
                    combined = restore_journal({'nodes': list(records.values())})
                    directory = f'stage_{number}_{main_name}'
                    cfg.unified_stage_paths[f'Stage_{number}'] = directory
                    save_run(cfg, combined, stage_name=directory)
            final_stage = self.manager.stages[-1]
            journal = self.manager.journals[final_stage.name]
            best = journal.get_best_node(cfg=cfg)
            completed = {self.manager.parse_stage_names(stage.name)[0] for stage in self.manager.stages}
            if best is None or best.id not in self.nodes:
                raise ValueError('Tree search produced no verified working implementation')
            self.selected_node_id = best.id
            best_root, manifest, payload = self.nodes[best.id]
            # Publish the verified selected solution; all other nodes remain immutable.
            import shutil
            for item in manifest['files']:
                target = self.root / item['path']
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(best_root / item['path'], target)
            write_json(self.root / 'journal.json', journal_snapshot(journal))
            write_json(self.root / 'working-manifest.json', manifest)
            reviews = [f'{name}: ' + json.dumps(response, ensure_ascii=False)
                       for name, response in self.cache.items()]
            (self.root / 'review_text.txt').write_text('\n\n'.join(reviews), encoding='utf-8')
            successful_stages = {int(name.split('_')[0]) for name, results in self.stage_results.items()
                                 if any(item['succeeded'] and item['id'] in self.nodes
                                        and self.node_stages[item['id']] == name for item in results)}
            success = completed == successful_stages == {1, 2, 3, 4}
            limitations = payload.limitations + ([] if success else ['Chưa có bản thử thành công ở đủ bốn giai đoạn.'])
            evidence = ['Kết quả được chọn: ' + payload.summary]
            for name, results in self.stage_results.items():
                own = [item for item in results if item['id'] in self.nodes
                       and self.node_stages[item['id']] == name]
                if own:
                    evidence.append(name + ': ' + own[-1]['summary'])
            summary = WorkingPayload(succeeded=success, summary='\n\n'.join(evidence)[:20_000],
                                     limitations=limitations, output_files=payload.output_files)
            return summary, manifest, best

    async def execute(self):
        try:
            result = await asyncio.to_thread(self.run)
            self.status = 'completed' if result[0].succeeded else 'failed'
            self.checkpoint(self.manager)
            return result
        except SearchInterrupted as exc:
            self.status = 'interrupted'
            if self.manager:
                self.checkpoint(self.manager)
            if self.key in self.service.stop_requests or self.service.closed:
                raise asyncio.CancelledError() from exc
            raise TimeoutError(str(exc)) from exc
        except BaseException:
            self.status = 'interrupted' if self.key in self.service.stop_requests or self.service.closed else 'failed'
            if self.manager:
                self.checkpoint(self.manager)
            raise
