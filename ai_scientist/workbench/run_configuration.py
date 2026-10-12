"""Run-owned project defaults; independent of orchestration actors and loops."""
from typing import Literal
from pydantic import Field, model_validator
from .models import StrictModel, ResearchPlan, SearchOptions


class RunConfiguration(StrictModel):
    mode: Literal['training_research','etc'] = 'training_research'
    benchmark_id: str | None = Field(default=None,pattern=r'^[a-f0-9]{32}$')
    desired_output: str = Field(default='',max_length=10000)
    account: str = Field(default='',max_length=128)
    accelerator: Literal['cpu','NvidiaT4','TpuV5E8','TpuV6E8'] = 'cpu'
    ttl_seconds: int = Field(default=600,ge=180,le=43200)
    execution_seconds: int = Field(default=480,ge=60,le=43080)
    output_bytes: int = Field(default=1000000,ge=1,le=10000000)
    research: ResearchPlan = Field(default_factory=lambda:ResearchPlan(literature=True))
    search: SearchOptions = Field(default_factory=lambda:SearchOptions(enabled=False,num_drafts=3))

    @model_validator(mode='after')
    def valid_limits(self):
        if self.execution_seconds > self.ttl_seconds-120:
            raise ValueError('Chừa 120 giây cuối phiên để thu kết quả')
        if self.mode=='etc' and self.search.enabled:
            raise ValueError('Experiment manager chỉ dùng cho Training/Research')
        return self

    @classmethod
    def from_workflow(cls, workflow):
        return cls.model_validate({k:v for k,v in (workflow or {}).items() if k in cls.model_fields})
