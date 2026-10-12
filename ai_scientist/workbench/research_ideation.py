"""Prepare one research idea using the configured phase actor."""
import asyncio
import uuid

IDEA_SCHEMA = {'type': 'object', 'required': ['title', 'text'], 'properties': {
    'title': {'type': 'string', 'minLength': 1, 'maxLength': 80},
    'text': {'type': 'string', 'minLength': 1, 'maxLength': 20000}}, 'additionalProperties': False}
async def prepare_idea(runtime):
    from .research_candidates import generate_candidates, assess_candidates, select_candidate
    await generate_candidates(runtime)
    await assess_candidates(runtime)
    await select_candidate(runtime)
