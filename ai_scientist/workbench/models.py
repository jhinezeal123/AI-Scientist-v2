"""Configuration and the three workbench role payloads."""
import json
from pathlib import Path
from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator
from typing import Literal


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class WorkbenchConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    donor_root: Path
    donor_python: Path
    codex_executable: Path
    codex_model: str = Field(min_length=1)
    codex_reasoning_effort: str = Field(min_length=1)
    kaggle_account_alias: str = Field(min_length=1)
    kaggle_username: str | None = Field(default=None, pattern=r"^[a-zA-Z0-9_-]+$")
    workspace_root: Path
    allow_new_run_after_idle_check: bool = False
    shutdown_seconds: float = Field(default=15, ge=1, le=60)
    working_seconds: int = Field(default=900, ge=60)
    kaggle_session_seconds: int = Field(default=1800, ge=60)
    kaggle_accelerator: str = 'cpu'

    @classmethod
    def load(cls, path: Path):
        config = cls.model_validate_json(path.read_text(encoding="utf-8"))
        from .codex_executable import resolve_codex_executable
        config.codex_executable = resolve_codex_executable(config.codex_executable)
        for name in ("donor_root", "workspace_root"):
            value = getattr(config, name)
            if not value.is_absolute() or not value.is_dir():
                raise ValueError(f"{name} must be an existing absolute directory")
        for name in ("donor_python", "codex_executable"):
            value = getattr(config, name)
            if not value.is_absolute() or not value.is_file():
                raise ValueError(f"{name} must be an existing absolute executable")
        return config


class PlanPayload(StrictModel):
    needs_clarification: bool
    questions: list[str] = Field(default_factory=list)
    paraphrase: str
    objective: str | None = None
    data_refs: list[str] | None = None
    split: str | dict[str, JsonValue] | None = None
    metric: str | dict[str, JsonValue] | None = None
    implementation_steps: list[str] | None = None
    budget: dict[str, JsonValue] | None = None
    expected_outputs: list[str] | None = None

    @model_validator(mode="after")
    def check_clarification(self):
        if self.needs_clarification:
            if not self.questions or any(not question.strip() for question in self.questions):
                raise ValueError("Clarification must contain concrete questions")
        elif self.questions or any(getattr(self, name) is None for name in (
                "objective", "data_refs", "split", "metric", "implementation_steps", "budget", "expected_outputs")):
            raise ValueError("A ready proposal must provide all fields and no pending questions")
        return self


class ProposalBudget(StrictModel):
    # Retain legacy proposal fields for stored approvals; user actions have no quota.
    coder_calls: int | None = Field(default=None, ge=1, description='Legacy metadata; omit. User controls each code request.')
    training_attempts: int | None = Field(default=None, ge=1, description='Legacy metadata; omit. User controls each execution.')
    training_seconds: int = Field(ge=1, le=600)
    output_bytes: int = Field(ge=1, le=10_000_000)


class ProposalSplit(StrictModel):
    method: str = Field(min_length=1)
    group_key: str = Field(min_length=1)
    subset: str = Field(min_length=1)
    seed: int = Field(ge=0, le=2_147_483_647)


class ProposalMetric(StrictModel):
    name: str = Field(min_length=1)
    direction: Literal["minimize", "maximize"]
    definition: str = Field(min_length=1)


class ReadyProposal(StrictModel):
    needs_clarification: Literal[False]
    questions: list[str] = Field(max_length=0)
    paraphrase: str = Field(min_length=1)
    objective: str = Field(min_length=1)
    data_refs: list[str] = Field(min_length=1)
    split: ProposalSplit
    metric: ProposalMetric
    implementation_steps: list[str] = Field(min_length=1)
    budget: ProposalBudget
    expected_outputs: list[str] = Field(min_length=1)


class CodePayload(StrictModel):
    source: str = Field(min_length=1)
    config: dict[str, JsonValue]
    implementation_summary: str
    checks_explained: list[str]


class WorkloadConfig(StrictModel):
    seed: int = Field(ge=0, le=2_147_483_647)
    max_epochs: int = Field(ge=1, le=100)
    training_seconds: int = Field(ge=1, le=600)
    output_bytes: int = Field(ge=1, le=10_000_000)
    parameters: dict[str, JsonValue] = Field(default_factory=dict)


class ReportPayload(StrictModel):
    summary: str
    interpretation: str
    limitations: list[str]
    suggested_next: list[str]
    evidence_refs: list[str]


class WorkingPayload(StrictModel):
    succeeded: bool
    summary: str = Field(min_length=1, max_length=20_000)
    limitations: list[str] = Field(max_length=30)
    output_files: list[str] = Field(max_length=200)


ROLE_PAYLOADS = {"mvp0_plan": PlanPayload, "mvp0_code": CodePayload, "mvp0_report": ReportPayload,
                 "mvp0_working": WorkingPayload}


def validate_result(role, result):
    if role not in ROLE_PAYLOADS:
        raise ValueError(f"Unsupported workbench role: {role}")
    if result.files:
        raise ValueError("Workbench results must have an empty files envelope")
    try:
        payload = json.loads(result.text)
    except json.JSONDecodeError as exc:
        raise ValueError("Role result text must contain one JSON object") from exc
    return ROLE_PAYLOADS[role].model_validate(payload)
