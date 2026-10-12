# Archived OpenRig Team implementation

This document describes the retired opt-in Team API, not the production Workbench interface.

# Agent Management — MVP5

The `agent_management` package is loaded by the existing Workbench FastAPI app.
Control SQLite owns coding coordination; existing project SQLite owns proposals,
approvals, runs and artifacts. Use **one Uvicorn worker per checkout**.
The default `AgentRuntime.run(request, progress, cancelled)` still delegates
to the existing Codex runtime. The default legacy path creates no control DB
and starts no team. Creating a team or coding task never authorizes research.

## GUI setup

Use **Python 3.12+**, matching the Workbench runtime documented since MVP0
(existing storage checks use pathlib's junction API). The upstream scientist CLI's
Python 3.11 instructions are a separate runtime guide.

1. Start Workbench on loopback with a randomly generated
   `AI_SCIENTIST_AGENT_CONTROL_TOKEN` in the backend's private environment.
2. Open **Settings → Config agent**, beside **Kaggle proxy**, **Slack** and
   **Remote**. Enter the local bootstrap token once. Workbench exchanges it
   for a revocable 30-day `HttpOnly` browser cookie; the token is never saved
   in browser storage or a URL. Signing out revokes that browser session.
3. Save named presets of installed agent/harness and model. These are shared
   Workbench configuration, retained across browser refresh and backend restart.
4. Open a Project's **Agent team** tab alongside **Library**, **Idea**, **Run**.
   Set up its default team and select presets for agent stages. Applying a preset
   copies the pair into the project; later preset edits do not rewrite existing grants.
5. The GUI exposes one default template, matching the earlier MVP flow: human
   ideation, human proposal approval, human approval before each run, agents for
   the remaining stages. Saving a workflow leaves it paused; starting it waits
   at each human step. Approving a proposal creates a run but does not start Working.

Project-owned teams, tasks, sessions, receipts, worktrees and live provider state
are stored under `.workbench/projects/<project name>/agents/`. Workflow grants
and human decisions remain in the same Project's `project.sqlite`; planner state
is in its `automation/` folder. Shared harness configuration, presets, Slack and
device authentication remain in `.workbench/agent-management.sqlite`.
Legacy project-bound teams move on first access with a recoverable database
backup. Active/uncertain sessions must be reconciled before moving. Worktrees
move through Git so their registrations stay valid. Deleting a stopped Project
unregisters its agent worktrees and removes its team state.

Set `AI_SCIENTIST_AGENT_ORCHESTRATION=0` to disable starting teams. Unset
`AI_SCIENTIST_AGENT_CONTROL_TOKEN` to disable management HTTP endpoints.
Stop/reconcile active work before changing flags. Existing research admission
and default legacy execution remain independent.

## Feature boundaries

| Feature | Backend policy / HTTP | UI / client | Owns |
| --- | --- | --- | --- |
| Slack | `slack.py`, `slack_api.py` | `SlackSettings`, `slackApi` | Opt-in configuration and explicit message delivery |
| Remote | `remote.py`, `remote_api.py` | `RemoteSettings`, `RemotePairing`, `remoteApi` | One-time pairing, scoped device references, revocation |
| Agent presets | `presets.py`, `preset_api.py` | `PresetSettings`, `agentPresets` | Reusable agent/model pairs and configured harness catalog |
| Project teams | `project_teams.py`, `project_team_api.py`, `team_api.py` | `ProjectAgentTeam`, `TeamWorkflowMonitor`, `ResearchWorkflowPanel`, `teamApi` | Project-owned team lifecycle, tasks and workflows |

`api.py` and `AgentSettingsPage` compose the features. Shared `auth`, `auth_api`,
`api_support`, `agentApi`, `agentAuth` and `AgentAccess` provide authentication,
transport and session lifecycle; they do not own Slack/preset/pairing policy.
The gateway exposes persistence and the harness catalog without constructing a
team scheduler, so reading/saving global settings does not recover/start teams.

The intentional integrations are narrow: Project setup receives a copied
agent/model pair through an injected lookup; Remote receives authorized team
references and a team-owned workflow view through callbacks. Team domain code
does not import preset/Slack/Remote policy. The remote workflow observer does
not load presets. Editing/deleting a preset, configuring Slack, or revoking a
device does not rewrite a Project's team topology or grants.
Device administration still loads if team lookup fails; an existing Project team
still loads if the preset catalog fails. Each result/error remains independent.

Global features share one SQLite file as infrastructure, with separate records
(`integration_config`, `pairings`/`devices`, `agent_presets`/`harnesses`). This
provides module isolation and independently testable policy, not independent
processes/databases. Project teams have their own Project database. Authentication
or storage outages can still affect the features using that infrastructure.

`tests/workbench/test_agent_feature_boundaries.py` covers forbidden domain/UI
imports, unavailable feature services, scheduler-free settings, copied preset
values, mutation isolation and read-only remote authority. It uses temporary
repositories and performs no external message/model calls.
The UI client boundary cases run with `npm run test:features` in `workbench-ui`;
they cover both partial failures and applying a copied pair to one team seat.

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

Each project seat owns a detached Git worktree under its `agents/worktrees/`.
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
Advanced coding topology, tasks, discovery/adoption and bundle operations use API/CLI.
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

The **Slack** tab is opt-in with backend-only `AI_SCIENTIST_SLACK_TOKEN`, explicit
channel configuration and explicit human sends. The **Remote** tab handles
pairing and device revocation. No actual Slack send was authorized or performed
during QA. Credentials are excluded from context and bundles.

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
T3 Code MIT provider setup components are imported under `workbench-ui/src/vendor/t3code`; its README and source manifest record the upstream commit and adaptations. OpenRig remains a reference only.


## Setup agent and model presets from the UI

Open Settings → Config agent. The T3 provider list/editor, setup wizard, runtime
fields, environment editor and Models section use upstream components and
styles. Add provider → Provider → Identity → Config creates a separate named
instance. Configuration commits on blur/Enter or selection. There is no limit
of three agents. Native Codex/Claude, ACP v1/v2 and CLI JSON adapters keep their
existing execution and permission policies.

Choose a configured provider and use Models to favorite, hide, reorder or add
an explicit custom model with display name and option descriptors. Add preset
selects an agent/model pair from that provider's model dropdown. Codex discovers
models from the configured app-server profile; ACP reads session metadata;
Claude uses the pinned T3 manifest filtered by installed CLI version. CLI JSON
uses its configured catalog. Metadata discovery sends no inference prompt and
never persists a draft. Model catalogs can be refreshed. A failed discovery
shows an error and keeps explicit custom models available.

Named instances, configuration, custom models and presets survive refresh and
backend restart in `.workbench/agent-management.sqlite`. Model visibility,
favorites and order are persisted in each provider's configuration. Sensitive
variables are masked after saving; untouched values are retained. Explicitly
non-sensitive variables are returned to the administrative editor. Native
Config directory selects CODEX_HOME or CLAUDE_CONFIG_DIR and is honored during
both discovery and execution. Provider processes do not inherit Workbench or
Slack secrets; process/control overrides are rejected.

Delete instance hides the provider from the configuration catalog. Delete its
presets first. The archived connection remains available to existing project
teams that copied its ID, avoiding changes to those projects. New presets
cannot use archived or disabled instances. Project teams retain their copied
agent/model pair until edited in that project. Connection changes apply to
all references to the same provider ID; independent credentials/endpoints
should use separate named instances.

### Antigravity and all ACP Registry agents

Antigravity is preconfigured. Select it, install the runtime if needed, then
click **Sign in → Open browser** and finish Google sign-in. Its ACP login is
separate from the installed IDE or agy CLI. Personal Google, Gemini Enterprise,
Gemini API key and Agent Platform / Vertex AI methods are available. Models
come from the authenticated ACP session; no inference prompt is sent.

For another agent, choose **Add provider → ACP Registry**, search/select an
agent and click Add. The runtime is prepared before the wizard creates the
named instance. The catalog is the official ACP Registry used by T3; the
bundled offline snapshot contains 41 agents, and the live catalog refreshes.
Examples include Codex ACP, Claude ACP, Gemini, Cursor, OpenCode, Copilot,
Kimi and Qwen. A catalog entry is not a guarantee that the agent's account,
external dependencies or subscription are ready; the UI reports runtime and
authentication state for the selected instance.

Managed releases are under `.workbench/tools/acp/<agent>/<version>`.
Registry refresh never updates a runtime silently. Prepare/update and removal
are explicit; removal requires disabling its instances and no active sessions.
Installation jobs and browser sign-in can be cancelled. Generic agents use
their advertised browser/terminal/API key methods, or link to their own setup
documentation. Node.js/npm is required for npm agents, uv for Python agents.

Antigravity account profiles are under
`.workbench/agents/providers/accounts/antigravity/<instance hash>`. They persist
across backend restarts; only per-process temporary folders are cleaned.
Active sign-in flows expire after five minutes and must restart after a backend
restart. Credentials/settings for Slack, Remote and project workflows are not
part of provider setup. Project execution shares runtime leases with setup,
so an in-use runtime cannot be removed or updated.

Upstream provenance and exact
adaptations: [vendor README](../workbench-ui/src/vendor/t3code/README.md).
Regression checks: `test_agent_preset_configuration.py`,
`test_agent_model_catalog.py`, `test_provider_setup.py`, `test_agent_feature_boundaries.py`, and
`npm run test:features`.
