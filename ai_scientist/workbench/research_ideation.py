"""Prepare one research idea using the configured phase actor."""
import asyncio
import uuid

IDEA_SCHEMA = {'type': 'object', 'required': ['title', 'text'], 'properties': {
    'title': {'type': 'string', 'minLength': 1, 'maxLength': 80},
    'text': {'type': 'string', 'minLength': 1, 'maxLength': 20000}}, 'additionalProperties': False}
async def prepare_idea(runtime):
    owner = runtime.owner
    project, identity, spec = runtime.project, runtime.workflow, runtime.spec
    state = owner.store.get(project, identity)['state']
    if not state.get('idea_id'):
        topic = {'goal': spec.goal, 'benchmark_id': spec.benchmark_id,
                 'research_outputs': spec.research.model_dump(), 'previous_runs': state['runs'],
                 'instruction': 'Produce one concrete hypothesis to test within the operator goal. Reuse the selected benchmark; do not change its metric or split.'}
        if state['runs']:
            previous = owner.working.detail(project, state['runs'][-1])
            topic['previous_result'] = {'run_id':state['runs'][-1],'state':previous['state'],
                'summary':(previous.get('working') or {}).get('summary'),
                'result_metric':previous.get('result_metric'),'output':previous.get('output'),
                'artifacts':previous.get('artifacts',[])}
        idea = await asyncio.to_thread(runtime.invoke, 'ideation', topic, IDEA_SCHEMA, timeout=86400)
        import jsonschema
        jsonschema.validate(idea, IDEA_SCHEMA)
        if spec.mode == 'training_research' and spec.research.literature:
            from .research_literature import review_idea
            idea = await asyncio.to_thread(review_idea, runtime, idea)
            jsonschema.validate(idea, IDEA_SCHEMA)
        if state['runs']:
            created = await owner.planner.create_variant(project, state['runs'][-1], uuid.uuid4().hex,
                idea['title'], idea['text'], idea['text'], spec.mode, spec.desired_output,
                spec.research.model_dump(), ['research'], spec.benchmark_id)
        else:
            created = owner.projects.save_idea(project, idea['text'], idea['title'], spec.mode,
                spec.desired_output, spec.research.model_dump(), ['research'], spec.benchmark_id)
        owner.store.change(project, identity, lambda s: s.update(idea_id=created['id']))

