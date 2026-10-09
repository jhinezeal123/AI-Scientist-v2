"""One experiment per Working session, with reusable upstream finishing modules."""
import asyncio
from types import SimpleNamespace

from .journal import Journal, Node, journal_snapshot
from .models import ResearchPlan, SearchOptions, WorkingPayload
from .run_graph import memory_document, write_run_json


def save_node(root, approved, payload, commands, run_id):
    chunks = []
    for path in sorted((root / 'source').rglob('*')):
        if path.is_file() and not path.is_symlink() and not path.is_junction() and path.stat().st_size <= 1_048_576:
            try:
                chunks.append('# ' + path.relative_to(root).as_posix() + '\n' + path.read_text(encoding='utf-8'))
            except UnicodeDecodeError:
                pass
    node = Node(plan=approved['body']['objective'], code='\n\n'.join(chunks))
    node.id = run_id
    node.overall_plan = '\n'.join(approved['body']['implementation_steps'])
    node.analysis = payload.summary
    node.is_buggy = not payload.succeeded
    node._term_out = [str(item.get('output', '')) for item in commands]
    node.exec_time = sum(item.get('elapsed_seconds', 0) or 0 for item in commands)
    node.exp_results_dir = str(root / 'output')
    journal = Journal()
    journal.append(node)
    write_run_json(root / 'journal.json', {**journal_snapshot(journal), 'run_id': run_id,
        'parent_run_id': (approved['snapshot'].get('variant') or {}).get('parent_run_id'),
        'kind': 'improve' if approved['snapshot'].get('variant') else 'draft'})
    write_run_json(root / 'execution.json', {'run_id': run_id, 'commands': commands, 'result': payload.model_dump()})
    return node, journal


async def finish_research(service, key, approved, descriptor, terminal, payload, manifest, node, journal, deadline):
    """Use existing Codex/query adapter and original report/plot/PDF/review code."""
    plan = ResearchPlan.model_validate(approved['body'].get('research') or {})
    if not any((plan.summary, plan.report, plan.plots, plan.writeup != 'none', plan.review)):
        return payload, manifest
    from .tree_search import TreeSearchRun, SearchInterrupted
    from ai_scientist.treesearch.backend import use_query_provider
    support = TreeSearchRun(service, key, approved, descriptor, terminal, SearchOptions(enabled=False), single_run=True)
    support.deadline = deadline
    support.manager = SimpleNamespace(journals={'1_run': journal}, main_stage_dict={1: 'Single run'},
        cfg=SimpleNamespace(report=SimpleNamespace(model=service.config.codex_model, temp=0.3)))
    support.nodes[node.id] = (support.root, manifest, payload)
    support.stage_results = {'run': [payload.model_dump()]}
    write_run_json(support.root / 'memory_journal.json', memory_document(
        service.store.run(*key), approved, {'summary': payload.model_dump(), 'manifest': manifest}))
    def finish():
        with use_query_provider(support.query):
            try:
                return support.pipeline.run_single(payload.succeeded)
            except BaseException:
                support.pipeline.interrupted()
                raise
    try:
        success, limitations = await asyncio.to_thread(finish)
    except SearchInterrupted as exc:
        if key in service.stop_requests or service.closed:
            raise asyncio.CancelledError() from exc
        raise TimeoutError(str(exc)) from exc
    return WorkingPayload(succeeded=payload.succeeded and success, summary=payload.summary,
                          limitations=payload.limitations + limitations, output_files=payload.output_files), manifest
