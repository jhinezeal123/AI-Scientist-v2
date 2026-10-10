# Agent Management — MVP5

The `agent_management` package is loaded by the existing Workbench FastAPI app.
Control SQLite owns coding coordination; existing project SQLite owns proposals,
approvals, runs and artifacts. Use **one Uvicorn worker per checkout**.
The default `AgentRuntime.run(request, progress, cancelled)` still delegates
to the existing Codex runtime. The default legacy path creates no control DB
and starts no team. Creating a team or coding task never authorizes research.

## GUI setup

1. Start Workbench on loopback with a randomly generated
   `AI_SCIENTIST_AGENT_CONTROL_TOKEN` in the backend's private environment.
2. Open **Settings → Multi-agent**, beside **Kaggle proxy**. Connect with the
   local bootstrap token; do not save it in browser storage or a URL.
3. Create a team template, optionally bind an existing project, then choose each
   seat's installed harness, model, instructions and permissions.
4. Pin source/skill/roster/knowledge or existing project Library references.
5. Queue a seat task or Lead → Builder → QA → Reviewer workflow, then start.
   Inspect topology, tasks, sessions, receipts, code, Git diff, terminal,
   snapshots, context and usage on the same page.

Set `AI_SCIENTIST_AGENT_ORCHESTRATION=0` to disable starting teams. Unset
`AI_SCIENTIST_AGENT_CONTROL_TOKEN` to disable management HTTP endpoints.
Stop/reconcile active work before changing flags. Existing research admission
and default legacy execution remain independent.

## Harnesses and policy

| Runtime | Behavior |
| --- | --- |
| Native Codex | Structured results, streams/usage, resume and installed-CLI fork; tools disabled, service applies validated edits |
| Native Claude | Structured results, streams/usage, resume/fork, strict empty MCP/tool settings; native authentication required |
| Generic ACP v1/v2 | Full-duplex stdio, negotiated models/capabilities, completion semantics, permission decisions, resume when supported |
| DSH ACP | Copy installed Web provider/model into ignored repo profiles; installed Node entrypoint with `--profile acp` |
| Raw CLI/JSON | Explicit installed argv, JSON contract, bounded process tree, production OS sandbox |

No implicit fallback, download or package installation. Probes check installed
commands/capabilities without model calls; they do not prove authenticated access.
Actual release QA used native Codex and DSH `@deepseek-ai/dsh@0.2.0-rc.2`.
Claude native authentication was unavailable and remains explicit.
ACP interactive auth/client filesystem/client terminal and unsupported fork are
rejected. DSH model-callable tools, global instructions, implicit skills, plugin
installs and subagent plugins are disabled. Structured edits are validated as a
whole before applying any file.

Each seat owns a detached Git worktree under `.workbench/agents/worktrees/`.
Traversal, hidden/configuration paths, secrets and redirected paths are refused.
Terminal commands require human workspace authority plus seat terminal policy,
bounded argv/output/duration and the installed Codex OS sandbox. Provider transport
networking is distinct from tool-network permission. Agent credentials cannot
authorize terminal, permission decisions or research. Their file/diff/event views
remain within their own seat; team metadata, summaries and intentionally shared
chat remain readable.

### Windows capacity

The elevated Codex sandbox retains `CodexSandboxUsers` deny ACLs. ACP, raw CLI
and human terminal therefore share **one Windows OS sandbox slot**, including
legacy research calls after management is enabled. Native tool-free Codex turns
can run concurrently. While holding the slot, only owned current worktree/runtime
DACLs are refreshed, then protected again after stop. Provider templates and
sibling private directories remain denied. Installed Codex sandbox and PowerShell
Core are required; no full-access fallback. Linux does not use this Windows slot.
Run one backend owner, not concurrent servers against the same checkout.

Coding queue/pod/resource pools and Kaggle account admission are separate.
Existing cookie refresh/quota/max-two-sessions/account gates remain in Working.
Unreported provider usage/cost is `null`, never zero.

## Continuity and API

The opt-in prefix `/api/agent-management` supports teams/templates/topology CAS,
tasks/leases/dependencies/idempotency, send/broadcast/chatroom, sessions/interrupt/
health/reconcile, snapshots/restore, worktree discovery/adoption, context,
resources, bundles, telemetry, devices, permissions and research.
Grow/shrink is available in the GUI RigSpec editor; discovery/adoption use API/CLI.
Topology/context/resource edits require a paused and reconciled team.

Immutable request IDs and payload hashes fence duplicates. Task/session completion
and seat release commit atomically. Startup marks interrupted sessions UNKNOWN,
preserves completed results and never autoreplays uncertain work. Reconcile checks
PID birth identity and process-tree receipts. Failed-task retry is an explicit
human operation on a paused team. Resume/fork require a stopped session belonging
to the same seat/harness and advertised support.

Bundles use a canonical SHA256 manifest and contain topology, models, pinned context
and resource pools. They exclude commands, credentials and local provider homes.
Import requires installed matching harnesses and valid local context; imported
teams are paused.

## Private remote devices

Keep Uvicorn on `127.0.0.1`. Configure private HTTPS (for example Tailscale Serve,
**not Funnel**), set `AI_SCIENTIST_AGENT_PUBLIC_ORIGIN` to that exact HTTPS origin,
and trust forwarded headers only from the loopback proxy. The legacy project API
is blocked on that route; `/health` remains read-only.

The local operator creates a one-use, five-minute pairing code scoped to teams
and actions. The exchanged personal-device cookie is HttpOnly, Secure on HTTPS
and SameSite Strict; mutations require CSRF and matching Origin. Stored tokens
are hashes; expiry is 30 days. Revoke/logout also terminates active SSE streams.
The bootstrap token is local Bearer only. This is personal-device access;
MVP7 multi-human identity/RBAC is separate.

SSE uses Last-Event-ID; polling uses durable cursors. Browser coding/terminal
commands retain request IDs after lost replies. Unknown research submissions
must reconcile existing Working state before retry.

## CLI / TUI / MCP

Create a one-hour seat credential via local operator API/GUI, put it in a private
`AI_SCIENTIST_AGENT_DEVICE_TOKEN` environment, and run:

```powershell
python tools/agent_management.py --url http://127.0.0.1:8000 teams
python tools/agent_management.py --url http://127.0.0.1:8000 tui
python tools/agent_management.py --url http://127.0.0.1:8000 call GET /teams/TEAM_ID
python tools/agent_management.py --url http://127.0.0.1:8000 mcp
```

`call` accepts JSON `--body-file` for mutations. TUI supports listing, inspection,
start/pause, messages and tasks subject to credential scope. Use a suitably
scoped paired human token for operator actions; seat tokens cannot start teams,
approve or run research. MCP is newline JSON-RPC stdio with initialize/initialized,
tools and resources; it never uses the bootstrap environment token or starts an
owner daemon. Remote URLs require HTTPS; redirects are refused.

Slack is opt-in with backend-only `AI_SCIENTIST_SLACK_TOKEN`, explicit channel
configuration and explicit human sends. No actual Slack send was authorized or
performed during QA. Credentials are excluded from context and bundles.

## Approved research → Working

Approve the existing proposal in Idea/Run first. Read that run's approval in the
team GUI and select a completed Reviewer checkpoint. The bridge verifies exact
project/run/proposal/version/context SHA/scope SHA/budget, Builder → QA → Reviewer
dependencies and stop receipts. Finite positive workload/session budgets are
checked before admission. Agents cannot authorize research or enlarge scope.

The durable outbox records intent before **existing Working**; project SQLite
remains authority. Reviewed source is staged as untrusted reference material with
immutable `team-provenance.json`. Repeated commands return existing receipts;
lost replies become UNKNOWN until reconciliation. Reports trace request,
checkpoint, tasks and file hashes. Etc returns its existing Output summary and
collected JSON/files; it does not require a training-style report.md.

## Verification and rollback

See [release evidence](../docs/customization/IMPLEMENT_MVP5.md),
[feature matrix](../docs/customization/MVP5_FEATURE_MATRIX.md) and
[approved live scope](../docs/customization/MVP5_QA_SCOPE.md).

Schema v2 uses SQLite backup to create
`.workbench/agent-management.sqlite.before-v2.bak`; newer unsupported DBs are
refused. Stop/reconcile all sessions before backing up control DB, owned runtime/
worktree directories and existing project storage. For rollback, stop backend,
retain current DB/artifacts, disable management/orchestration, and restore
compatible control state only into a separate closed checkout. Never overwrite
project SQLite with a control backup or downgrade a live/newer control DB.
Legacy Workbench can run with management disabled.
No source code was copied from T3 Code or OpenRig.
