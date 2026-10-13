"""Scientific scope inherited by new ideas and delegated ideation."""
from typing import Literal
from pydantic import Field
from .models import StrictModel, ResearchPlan


class IdeaConfiguration(StrictModel):
    goal: str = Field(default='', max_length=10000)
    mode: Literal['training_research', 'etc'] = 'training_research'
    benchmark_id: str | None = Field(default=None, pattern=r'^[a-f0-9]{32}$')
    desired_output: str = Field(default='', max_length=20000)
    research: ResearchPlan = Field(default_factory=lambda: ResearchPlan(literature=True))

    @classmethod
    def from_legacy(cls, value):
        body = {k: v for k, v in (value or {}).items() if k in cls.model_fields}
        if body.get('research', True) is None:
            body['research'] = {}
        return cls.model_validate(body)
