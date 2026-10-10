"""Operator-selected actors and finite delegation for research stages."""
from typing import Literal
from pydantic import Field, model_validator
from .models import StrictModel, ResearchPlan, SearchOptions

STAGES = ('ideation', 'proposal', 'approval', 'execution', 'draft', 'tuning', 'research', 'ablation', 'analysis',
          'summary', 'report', 'plots', 'writeup', 'review')

class StageBinding(StrictModel):
    actor: Literal['human', 'agent'] = 'agent'
    seat: str = Field(min_length=1, max_length=64)
    ask: bool = False

class WorkflowSpec(StrictModel):
    goal: str = Field(min_length=1, max_length=10000)
    mode: Literal['training_research', 'etc'] = 'training_research'
    benchmark_id: str | None = None
    resource_ids: list[str] = Field(default_factory=list, max_length=30)
    desired_output: str = Field(default='', max_length=10000)
    stages: dict[str, StageBinding]
    allow_agent_approval: bool = False
    max_runs: int = Field(default=1, ge=1, le=100)
    ttl_seconds: int = Field(default=600, ge=180, le=43200)
    execution_seconds: int = Field(default=480, ge=60, le=43080)
    max_agent_calls: int = Field(default=40, ge=1, le=1000)
    output_bytes: int = Field(default=1000000, ge=1, le=10000000)
    accelerator: Literal['cpu', 'NvidiaT4', 'TpuV5E8', 'TpuV6E8'] = 'cpu'
    account: str = Field(min_length=1, max_length=128)
    research: ResearchPlan = Field(default_factory=ResearchPlan)
    search: SearchOptions = Field(default_factory=SearchOptions)

    def active_stages(self):
        stages = ['ideation','proposal','approval']
        stages += ['draft','tuning','research','ablation','analysis'] if self.search.enabled else ['execution']
        if self.mode=='training_research':
            stages += [s for s in ('summary','report','plots','review') if getattr(self.research,s)]
            if self.research.writeup!='none':
                stages.append('writeup')
        return stages

    @model_validator(mode='after')
    def valid(self):
        if set(self.stages) != set(STAGES):
            raise ValueError('Configure exactly one actor for each research stage')
        if self.stages['approval'].actor == 'agent' and not self.allow_agent_approval:
            raise ValueError('Agent approval requires an explicit operator delegation')
        if self.mode == 'training_research' and not self.benchmark_id:
            raise ValueError('Training/Research requires a completed benchmark')
        if self.mode == 'etc' and (not self.desired_output.strip() or self.search.enabled):
            raise ValueError('Etc requires desired output and cannot use research tree search')
        if self.execution_seconds > self.ttl_seconds - 120:
            raise ValueError('Reserve 120 seconds of the session for collection')
        if len(self.resource_ids) != len(set(self.resource_ids)):
            raise ValueError('Context IDs must be distinct')
        return self
