"""Versioned control-plane contracts. Research approval is deliberately absent."""
from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

Identifier = str
ID = r"^[a-zA-Z][a-zA-Z0-9_-]{0,63}$"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class PermissionPolicy(StrictModel):
    sandbox: Literal["read-only"] = "read-only"
    file_edits: bool = False
    terminal: bool = False
    network: bool = False
    allowed_paths: list[str] = Field(default_factory=lambda: ["src/", "tests/", "docs/"])
    max_files: int = Field(default=20, ge=1, le=100)
    max_file_bytes: int = Field(default=200_000, ge=1, le=1_000_000)

    @model_validator(mode="after")
    def valid_paths(self):
        from pathlib import PurePosixPath
        for value in self.allowed_paths:
            path = PurePosixPath(value)
            if not value or "\\" in value or ":" in value or path.is_absolute() or ".." in path.parts:
                raise ValueError("Allowed paths must be relative POSIX paths")
            if any(p.startswith(".") for p in path.parts):
                raise ValueError("Hidden/configuration paths are not editable by agents")
        return self


class HarnessSpec(StrictModel):
    id: str = Field(pattern=ID)
    kind: Literal["native_codex", "native_claude", "acp", "cli_json"]
    executable: str = Field(default="", max_length=2048)
    args: list[str] = Field(default_factory=list, max_length=32)
    protocol_version: Literal[1, 2] = 1
    models: list[str] = Field(default_factory=list, max_length=100)
    # A local command is an explicit administrator configuration, never an installer.
    enabled: bool = True

    @model_validator(mode="after")
    def valid_command(self):
        if self.kind in {"acp", "cli_json"} and not self.executable:
            raise ValueError("Local harness needs an explicit installed executable")
        if "\x00" in self.executable or any("\x00" in x or len(x) > 2048 for x in self.args):
            raise ValueError("Invalid literal harness arguments")
        if any(not model or len(model) > 256 for model in self.models):
            raise ValueError("Invalid model catalog")
        return self


class AgentSpec(StrictModel):
    id: str = Field(pattern=ID)
    role: Literal["lead", "builder", "qa", "reviewer", "specialist"] = "specialist"
    harness: str = Field(default="codex", pattern=ID)
    model: str | None = Field(default=None, min_length=1, max_length=256)
    pod: str = Field(default="team", pattern=ID)
    instructions: str = Field(default="", max_length=20_000)
    policy: PermissionPolicy = Field(default_factory=PermissionPolicy)


class PodSpec(StrictModel):
    id: str = Field(pattern=ID)
    max_parallel: int = Field(default=4, ge=1, le=32)


class ContextSource(StrictModel):
    id: str = Field(pattern=ID)
    kind: Literal["source", "skill", "knowledge", "roster"]
    path: str = Field(min_length=1, max_length=512)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    seats: list[str] = Field(default_factory=list, max_length=32)
    version: int = Field(default=1, ge=1)


class RigSpec(StrictModel):
    version: Literal[2] = 2
    name: str = Field(min_length=1, max_length=120)
    project_id: str | None = Field(default=None, pattern=r"^[a-zA-Z0-9_-]{1,64}$")
    base_ref: str = Field(default="HEAD", min_length=1, max_length=256)
    pods: list[PodSpec] = Field(default_factory=lambda: [PodSpec(id="team")], min_length=1, max_length=32)
    seats: list[AgentSpec] = Field(min_length=1, max_length=32)
    context: list[ContextSource] = Field(default_factory=list, max_length=100)
    max_parallel: int = Field(default=4, ge=1, le=32)
    timeout_seconds: int = Field(default=300, ge=5, le=3600)
    template: str | None = Field(default=None, pattern=ID)

    @model_validator(mode="after")
    def topology(self):
        names = [s.id for s in self.seats]
        pods = [p.id for p in self.pods]
        if len(names) != len(set(names)) or len(pods) != len(set(pods)):
            raise ValueError("Duplicate seat or pod")
        if any(s.pod not in pods for s in self.seats):
            raise ValueError("Seat references an unknown pod")
        if any(set(c.seats) - set(names) for c in self.context):
            raise ValueError("Context references an unknown seat")
        if self.base_ref.startswith("-") or any(c in self.base_ref for c in "\x00\r\n"):
            raise ValueError("Invalid base Git reference")
        return self


class TaskRequest(StrictModel):
    instruction: str = Field(min_length=1, max_length=80_000)
    kind: Literal["coding", "review", "research"] = "coding"
    input_checkpoint: str | None = Field(default=None, pattern=r"^[0-9a-f]{40,64}$")
    resume_session: str | None = Field(default=None, max_length=128)


class FileEdit(StrictModel):
    path: str = Field(min_length=1, max_length=512)
    content: str = Field(max_length=1_000_000)


class TaskResult(StrictModel):
    summary: str = Field(max_length=40_000)
    files: list[FileEdit] = Field(default_factory=list, max_length=100)
    checks: list[str] = Field(default_factory=list, max_length=100)
    handoff: str = Field(default="", max_length=20_000)


def templates() -> list[dict]:
    result = []
    for name, parallel in (("starter", 2), ("workshop", 4), ("factory", 8)):
        seats = [AgentSpec(id=role, role=role,
                          policy=PermissionPolicy(file_edits=role == "builder"))
                 for role in ("lead", "builder", "qa", "reviewer")]
        result.append(RigSpec(name=name.title(), seats=seats,
                              max_parallel=parallel, template=name).model_dump())
    return result
