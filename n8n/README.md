# Local n8n research workflows

Workbench uses n8n 2.42.6 on `http://127.0.0.1:5678`. The project Workflow tab
replaces OpenRig Team setup. Config agent, Slack and Remote remain independent.

## Start and use

From the repository in PowerShell:

```powershell
./scripts/n8n.ps1 start
```

On a fresh checkout the script installs the pinned version locally (Node.js 24
required), imports the bridge credential and publishes the two workflows.
Create your local owner account in the browser once. No cloud account is needed.
Start Workbench using its existing local run configuration.

1. Open a project → **Workflow**, beside Library and Idea.
2. Enter a goal, select its benchmark (or Etc output), Kaggle account and preset.
3. Optionally choose different presets per agent stage, Library inputs and limits.
4. **Lưu cấu hình workflow** freezes the agent/model selection and grant in that
   project. It does not start research. Provider connection settings still belong
   to Config agent; separate instances provide separate credentials/profiles.
5. **Bắt đầu / Tiếp tục** dispatches the saved grant to n8n.
6. In Hybrid mode, enter the idea, approve the exact proposal and run. Full agent
   delegates those decisions within the saved limits. Per-stage actors and
   human review can also be configured individually.
7. Open n8n from the project to inspect/edit the canvas and execution history.

`workbenchResearch` orders the human gates, planning, admission and result
collection. `workbenchAgent` orders each provider call, remote action and next
turn for all research stages. The existing experiment manager/tree policy,
Kaggle session lifecycle, result verification and research output algorithms
remain Python domain operations; they use the n8n agent loop. This is not a
reimplementation of AI-Scientist's research algorithms as generic n8n nodes.

The research canvas has five Canvas Groups: Ideathon/Novelty, proposal design
(preparation and approval), run configuration, execution, and collection/repetition. Each operation starts once,
waits for an authenticated completion webhook, then validates its result. There is no research status polling loop. Expand a group to inspect
its nodes; use **Collapse all groups** for the overview. The agent canvas keeps
the provider/remote-action nodes separate. The agent canvas retains its existing provider polling loop.

Research callback URLs use the execution and operation path, with generation and
iteration in the query. The canvas validates both the query and saved result before advancing;
an unexpected or stale notification stops the execution for review.
Proposal design includes **Bạn nhắn lại? → Lập proposal**. A human message invalidates
the current candidate, saves the conversation in the project and authorizes one new
planning round. No message means no replanning. An agent clarification request disables
approval on both the UI and backend until the user replies and a ready candidate is produced.
This clarification gate also applies when proposal approval is assigned to an agent.
The canvas exposes **Agent yêu cầu làm rõ?** directly. Its true branch calls
**Khóa duyệt · Yêu cầu bạn làm rõ**; its false branch opens normal proposal review.
Both wait for the saved decision, and only a human message takes **Bạn nhắn lại?**
back to planning. The backend includes the clarification flag, questions and approval
availability in the completion result and enforces the candidate's own state.
Completion delivery is saved with the project job; retries send the saved result only.
If delivery fails, Project → Workflow offers **Gửi lại thông báo cho n8n**.
Backend recovery retries saved notifications and fails interrupted executions; it never
replays unfinished work. A stopped generation cannot advance a later one.

The default is human ideathon/proposal/run approval, agents for the rest. No
additional Team templates are supplied. n8n cannot answer human gates or modify
Slack, Remote or presets. Changing canvas order does not bypass backend grant
validation, call/run budgets or exact run approvals.

## Literature, citations and VLM

Project → Workflow exposes three independent scientific options:

- **Literature / novelty** searches Semantic Scholar and reflects on the idea
  before planning. At least one retrieved paper is required for a positive
  novelty decision. A negative or unfinished decision stops the workflow.
- **Citation gathering** uses upstream `get_citation_addition`, including its
  query → paper selection loop. The bibliography uses retrieved API BibTeX;
  PDF compilation rejects citation keys outside that bibliography.
- **VLM** sends actual collected images to the selected vision preset. It uses
  upstream plot analysis, PDF figure/caption/reference review, figure selection
  during writeup reflections and duplicate-image checks. Missing images or an
  unsupported provider are reported as failures.

Set the maximum literature/citation rounds and stage presets in the project.
These operations consume the same model-call and execution budgets as the run.
Choose PDF to enable its visual reflection/final paper checks; plot evaluation
also works without a PDF. The new options are off in existing saved grants.

Public Semantic Scholar access can return 429. An admin can save its API key once
in **Project → Workflow → Semantic Scholar**. It is stored locally in the ignored
`.workbench/credentials/semantic-scholar.key`; `S2_API_KEY` is also supported.
The key is never returned to the UI, sent to an agent or included in n8n payloads.

Literature evidence is saved at `automation/<workflow>/literature/<iteration>/`.
Run outputs include `research/references.bib`, `citations_progress.json`,
node `vlm-review.json`, writeup `vlm-reflection-*.json` and
`research/vlm-paper-review.json`. A finite search is an agent's novelty assessment,
not a guarantee that no prior work exists.

## Persistence and restarts

- Project grants, inputs, events and run references: each project's SQLite DB.
- Grant snapshot: `.workbench/projects/<name>/automation/<workflow>/grant.json`.
- Provider working folders: `.workbench/projects/<name>/agents/worktrees/`.
- n8n workflows, encrypted credentials and executions:
  `.workbench/n8n/profile/.n8n/`. Retain the generated encryption key when backing
  up this folder. The bridge token is `.workbench/n8n/bridge-token.txt`.
- Old Team workflows remain readable as archived history; create a fresh n8n
  grant to continue. Existing project Team device identities are remapped to
  the same project without changing their tokens or expanding scopes.

Refresh preserves saved grants. Backend restart pauses active workflows and
marks unresolved provider outcomes for reconciliation; it never resubmits a run
automatically. Dừng cancels owned work and requests stop of its Kaggle session.

```powershell
./scripts/n8n.ps1 status
./scripts/n8n.ps1 stop
```

Edit workflows in n8n and Publish to apply changes. Normal startup preserves
those edits. To deliberately replace them with repository templates, stop n8n
then run `./scripts/n8n.ps1 setup -ResetTemplates` and start it again.

## Verification

`test_n8n_workflows.py` checks grants, copied presets, human gates, duplicate
delivery, stale execution rejection, archived history and device scope migration.
`test_n8n_live.py` runs against an isolated real n8n profile whose workflows point
to fixture backend port 8001. Set `N8N_QA_ROOT` to that profile's parent folder.
It exercises both actual canvases, all three human gates on two iterations,
exec/write/read/finish and persisted n8n execution success. Providers, SSH and
Kaggle are fixtures; it does not establish a real training result.

Official operational references: [CLI import/publish](https://docs.n8n.io/hosting/cli-commands/)
and [self-hosted deployment](https://docs.n8n.io/hosting/).
