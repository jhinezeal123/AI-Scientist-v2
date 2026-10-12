import asyncio
import json
from types import SimpleNamespace
import uuid

from ai_scientist.workbench.idea_archive import IdeaArchive
from ai_scientist.workbench.research_candidates import generate_candidates, assess_candidates, select_candidate
from ai_scientist.workbench.stage_runtime import StageRuntime
from tests.workbench.test_n8n_workflows import setup, repository


def test_archive_survives_service_recreation_feeds_next_candidates_and_rejects_duplicates(repository):
    async def check():
        owner, project, _, spec, _ = setup(repository)
        spec = spec.model_copy(deep=True)
        spec.stages['ideation'].actor = 'agent'
        spec.stages['ideation'].preset_id = 'default'
        spec.ideation.candidates = 3
        identity = uuid.uuid4().hex
        owner.create(project, identity, spec)
        owner.store.change(project, identity, lambda s: s.update(status='RUNNING'))
        prompts = []
        class Adapter:
            def start(self, agent, workspace):
                return SimpleNamespace(stop_receipt=None)
            def close(self, handle): pass
            def interrupt(self, handle): pass
            def send(self, handle, message, **kwargs):
                data = json.loads(message)
                prompts.append(data['input'])
                schema = data['result_schema']
                if 'candidate_id' in schema['properties']:
                    result = {'candidate_id': schema['properties']['candidate_id']['enum'][1], 'reason': 'Distinct feasible hypothesis'}
                else:
                    number = data['input']['candidate_number']
                    result = {'title': f'Candidate {number}', 'text': f'Distinct checksum hypothesis {number}'}
                handle.stop_receipt = {'tree_stopped': True}
                return SimpleNamespace(result=SimpleNamespace(summary=json.dumps(result), files=[]), receipt=handle.stop_receipt)
        owner.gateway._harness_catalog.resolve = lambda _: Adapter()
        owner.agent_turns.invoke = owner.executor.invoke
        runtime = StageRuntime(owner, project, identity)
        try:
            await generate_candidates(runtime)
            assert len(prompts) == 3 and prompts[1]['previous_ideas'][0]['title'] == 'Candidate 1'
            assert len(IdeaArchive(owner.projects).list(project)) == 3
            await generate_candidates(StageRuntime(owner, project, identity))
            assert len(prompts) == 3
            await assess_candidates(runtime)
            await select_candidate(runtime)
            chosen = owner.store.get(project, identity)['state']['idea_id']
            assert owner.projects.idea(project, chosen)['title'] == 'Candidate 2'
            assert [r['status'] for r in IdeaArchive(owner.projects).list(project)] == ['unselected','selected','unselected']
            await select_candidate(runtime)
            assert len(prompts) == 4 and owner.store.get(project, identity)['state']['idea_id'] == chosen
            owner.store.change(project, identity, lambda s: s.update(idea_id=None))
            await select_candidate(runtime)
            assert owner.store.get(project, identity)['state']['idea_id'] == chosen
            assert len(owner.projects.ideas(project)) == 1
            second = uuid.uuid4().hex
            owner.create(project, second, spec)
            owner.store.change(project, second, lambda s: s.update(status='RUNNING'))
            await generate_candidates(StageRuntime(owner, project, second))
            assert any(r['status'] == 'selected' for r in prompts[4]['previous_ideas'])
            assert all(r['status'] == 'duplicate' for r in IdeaArchive(owner.projects).list(project, second))
            assert (owner.projects.directory(project)/'automation'/identity/'ideation/0/archive.json').is_file()
        finally:
            await owner.close()
    asyncio.run(check())
