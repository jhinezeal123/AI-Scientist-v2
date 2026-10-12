# Workbench agent configuration

Production Workbench exposes separate Config agent, Slack and Remote settings.
Each project has a Workflow tab backed by local n8n. OpenRig Team creation,
templates, topology, seat tokens, task queues and supervisor controls have been
removed from the production routes and GUI.

See [n8n setup and usage](../n8n/README.md). Historical Team code is retained only
for reading existing records and explicit legacy tests. Its retired interface
is documented in [archived Team notes](docs/legacy-teams.md).

| Feature | Responsibility | Storage |
| --- | --- | --- |
| Config agent | Provider setup, model catalogs and agent/model presets | Global control DB and provider profiles |
| Slack | Optional Slack configuration and explicit sends | Global control DB; backend Slack token |
| Remote | Pairing, scoped human access and device revocation | Global control DB |
| Project Workflow | Frozen grants, human inputs, research events and runs | Project DB and project folders |
| n8n | Research phase order and provider/remote action loops | Local n8n profile |

Settings do not construct a Team scheduler. Project execution calls a saved
provider directly through the existing sandbox and process supervisor. Presets
are copied at grant creation. The n8n bridge has its own local credential and
cannot act as a human operator or administer settings.

Remote pairs to projects with read access and optional research control. A read
device cannot start/stop or answer gates. Slack sends remain explicit. Neither
Slack nor device management alters saved workflow grants or provider settings.

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
presets first. Its archived configuration remains stored for history. A saved
workflow requires an enabled, ready provider before starting. New presets
cannot use archived or disabled instances. Saved project workflows retain their frozen
agent/model pair; save a new grant to select a different preset. Connection changes apply to
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
