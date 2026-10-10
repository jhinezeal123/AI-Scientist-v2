# Agent Management (MVP5 foundation)

This root-level folder intentionally isolates agent execution and coordination
from AI-Scientist's science workflow. The nested agent_management Python package
is loaded at the existing Workbench composition root. No additional PYTHONPATH,
server, Git submodule, or TypeScript daemon is introduced.

## Unchanged integration boundary

PlanningService -> RuntimeWorker -> RuntimeBindings.runtime.run(request, progress, cancelled)

The sole runtime alias is now AgentGateway, which by default delegates to the
exact existing CodexCliRuntime. The Workbench request, progress/cancellation,
result schema validation, single-job concurrency, human-approved research
workflow, Kaggle idempotency, and session uncertainty are unchanged.

The package supplies a durable coordination store and configurable provider
and seat mapping, but **does not automatically run queued tasks or Kaggle
experiments**. These are independent domains. No control database is created
during the default legacy path.

## Enable provider selection explicitly

Create a JSON file at WORKSPACE_ROOT/.workbench/agent-management.json:

{
  "version": 1,
  "providers": {
    "deepseek": {
      "kind": "acp",
      "executable": "dsh",
      "args": ["--profile", "acp"]
    }
  },
  "seats": {
    "lead": {"provider": "codex"},
    "builder": {"provider": "deepseek"}
  },
  "default_seat": "lead",
  "role_seats": {"mvp0_working": "builder"}
}

This routes one existing Workbench role through the builder's ACP provider.
It does NOT launch multiple agents automatically. The agent's output still
must match the corresponding existing Workbench JSON schema or RuntimeWorker
will reject the response. The command must be installed and authenticated
before use. Shell expansion, implicit fallback and automatic installation
are forbidden.

The ACP bridge is an initial **v1** noninteractive stdio implementation. It
does not claim to support ACP v2, interactive authentication, model switching,
client filesystem/terminal capabilities or native session resume. Permission
requests are denied instead of being silently granted.

## Explicit team-coordination API

AgentGateway exposes create_rig, enqueue, claim, finish, send, inbox and
snapshot. Tasks have request IDs, per-rig dependencies, single active leases,
and UNKNOWN state on timeout with NO automatic retry.

Optional HTTP control paths are installed on the EXISTING FastAPI app at
/api/agent-management. They are disabled (404) unless the server process has
AI_SCIENTIST_AGENT_CONTROL_TOKEN set. Authenticated requests require a Bearer
token. Endpoints only manage metadata, messages and queued tasks; they do not
execute an agent or submit any experiment.

Do not expose the existing loopback server on an unauthenticated public
interface. Remote control still requires a separate secured HTTPS tunnel.

## Why this is a draft / what remains

See https://github.com/jhinezeal123/AI-Scientist-v2/issues/2 .

The PR starts M5-0/M5-1 and a limited M5-2/M5-3 implementation. Missing
before MVP5 is complete: true multi-seat execution loop with worktree
isolation, ACP Registry/v2, native Claude profiles, real full-agent
lifecycle/snapshot/resume, permissions/approval routing, MCP/CLI/TUI
feature parity, rich IDE/React topology UI, remote device pairing,
research bridge command admission, telemetry dashboards, and end-to-end
multi-provider testing with real credentials.

Run local tests with:
    python -m pytest tests/workbench/test_agent_management.py -q

No source code is copied from T3 Code or OpenRig.
