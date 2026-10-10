"""Strict declarative harness/seat configuration; no shell expressions or implicit installs."""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re

_ID = re.compile(r"^[a-zA-Z][a-zA-Z0-9_-]{0,63}$")
_ROLES = frozenset({
    "mvp0_plan", "mvp0_code", "mvp0_report", "mvp0_working",
    "mvp1_search_node", "mvp1_search_query",
})


def _id(value: object, label: str) -> str:
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise ValueError(f"Invalid {label}")
    return value


def _mapping(value: object, label: str) -> dict:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return value


@dataclass(frozen=True)
class Provider:
    name: str
    kind: str
    executable: str = ""
    args: tuple[str, ...] = ()
    model: str | None = None

    @classmethod
    def parse(cls, name: str, raw: object) -> "Provider":
        _id(name, "provider ID")
        obj = _mapping(raw, "provider")
        if set(obj) - {"kind", "executable", "args", "model"}:
            raise ValueError("Unknown provider configuration keys")
        kind = obj.get("kind")
        if kind not in {"native_codex", "acp"}:
            raise ValueError("Unsupported provider kind")
        executable = obj.get("executable", "")
        args = obj.get("args", [])
        model = obj.get("model")
        if not isinstance(executable, str) or "\x00" in executable or (kind == "acp" and not executable.strip()):
            raise ValueError("Invalid provider executable")
        if not isinstance(args, list) or any(not isinstance(x, str) or "\x00" in x for x in args):
            raise ValueError("Provider args must be a list of literal strings")
        if len(args) > 32 or any(len(x) > 2048 for x in args):
            raise ValueError("Provider arguments exceed safety limits")
        if model is not None and (not isinstance(model, str) or not model or len(model) > 256):
            raise ValueError("Invalid provider model")
        if kind == "native_codex" and (executable or args or model):
            raise ValueError("native_codex uses the existing Workbench Codex configuration")
        return cls(name, kind, executable, tuple(args), model)


@dataclass(frozen=True)
class Seat:
    name: str
    provider: str


@dataclass(frozen=True)
class GatewaySpec:
    providers: dict[str, Provider]
    seats: dict[str, Seat]
    role_seats: dict[str, str]
    default_seat: str

    @classmethod
    def from_dict(cls, raw: object) -> "GatewaySpec":
        data = _mapping(raw, "gateway configuration")
        if set(data) - {"version", "providers", "seats", "role_seats", "default_seat"}:
            raise ValueError("Unknown gateway configuration keys")
        if data.get("version", 1) != 1:
            raise ValueError("Unsupported gateway configuration version")
        providers = {"codex": Provider("codex", "native_codex")}
        custom = _mapping(data.get("providers", {}), "providers")
        for name, profile in custom.items():
            if name == "codex":
                raise ValueError("Reserved provider codex cannot be overridden")
            providers[name] = Provider.parse(name, profile)
        seats = {}
        for name, raw_seat in _mapping(data.get("seats", {"default": {"provider": "codex"}}), "seats").items():
            _id(name, "seat ID")
            obj = _mapping(raw_seat, "seat")
            if set(obj) != {"provider"}:
                raise ValueError("Seat requires only a provider")
            provider = _id(obj["provider"], "provider ID")
            if provider not in providers:
                raise ValueError("Seat references an unknown provider")
            seats[name] = Seat(name, provider)
        if not seats or len(seats) > 32:
            raise ValueError("Gateway requires 1–32 seats")
        default_seat = _id(data.get("default_seat", "default"), "default seat")
        if default_seat not in seats:
            raise ValueError("Default seat must exist")
        assignments = _mapping(data.get("role_seats", {}), "role_seats")
        for role, seat in assignments.items():
            if role not in _ROLES or seat not in seats:
                raise ValueError("Unknown Workbench role or seat assignment")
        return cls(providers, seats, dict(assignments), default_seat)

    def for_role(self, role: str) -> Provider:
        seat_name = self.role_seats.get(role, self.default_seat)
        return self.providers[self.seats[seat_name].provider]


def load_spec(path: Path) -> GatewaySpec:
    """No file means the exact historical single-Codex behavior (zero database writes)."""
    if path.is_symlink():
        raise ValueError("Refusing symlinked agent configuration")
    try:
        if path.stat().st_size > 128_000:
            raise ValueError("Agent configuration exceeds 128KB")
        body = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return GatewaySpec.from_dict({})
    return GatewaySpec.from_dict(json.loads(body))
