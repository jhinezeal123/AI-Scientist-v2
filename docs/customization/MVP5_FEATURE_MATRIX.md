# MVP5 subsystem acceptance matrix

> Phạm vi lịch sử của PR #3 đã merge. User đã sửa mục tiêu MVP5 thành mỗi stage
> một actor Human/Agent, gồm cả ideation và approval. Trạng thái của hướng sửa:
> [MVP5_STAGE_AUTONOMY.md](MVP5_STAGE_AUTONOMY.md). Bằng chứng dưới đây không
> thay thế nghiệm thu pipeline mới.

Complete issue #2 scope mapped to shipped interfaces and evidence. Fixtures prove
protocol/error handling; actual providers/Kaggle are documented separately in
[release evidence](IMPLEMENT_MVP5.md).

| Subsystem | Shipped surface and evidence | Limits |
| --- | --- | --- |
| Rig/agent/pod/seat/template | Versioned models, GUI topology editor, restart/CAS/grow-shrink tests | Personal operator; paused/reconciled changes |
| Harness fabric/models | Native Codex/Claude, ACP v1/v2, DSH import, CLI/JSON; protocol fixtures + real Codex/DSH team | Probe ≠ auth; no install/fallback; native Claude auth unavailable |
| Coding edits/worktrees | Per-seat Git, bounded atomic validation/CAS; actual two-file checksum checkpoint | Native agents tool-free; no hidden/config/secret/link paths |
| Queue/dependency/scheduler | Owned leases/heartbeat/hash/global/pod/256 pending limits; parallel/load/recovery tests | UNKNOWN blocks seat; explicit retry |
| Messaging/chatroom | Send/broadcast/inbox/sender scope; real handoffs + cross-rig tests | Shared intentional team chat, no impersonation |
| Session supervisor | Process-tree containment/deadline/interrupt/receipt/birth identity tests | Unknown stop must reconcile |
| Continuity | Snapshot/restore/discover/adopt/grow/shrink; tests + actual Codex fork/DSH resume | Adopt owned worktrees only; ACP fork if supported |
| Settings GUI | Tasks/threads/topology/code/diff/terminal/events/model/policy/context; API journey + actual desktop/mobile browser | Discover/adopt API/CLI; grow/shrink RigSpec editor |
| Permissions | Default read-only, scoped writes, human terminal, one-use decisions; broker/path/agent privilege tests | ACP client FS/terminal disabled; unsupported operations refused |
| Windows sandbox | Private runtime homes/owned DACL/exclusive slot; actual no-model A→B→A isolation test | One ACP/CLI/terminal slot; native tool-free concurrency; no full-access fallback |
| Private devices | HTTPS/pair/scopes/hash/cookie/CSRF/Origin/revoke/logout; real TLS + stream revoke | Personal devices, not multi-human RBAC; no public Funnel |
| Reconnect/idempotency | SSE cursor, browser intent IDs, outbox; actual reconnect and restart Working replay | UNKNOWN dispatch reconciles first |
| CLI/TUI/MCP | Same backend, call/body-file, interactive TUI, MCP tools/resources; actual probes and lifecycle/redirect tests | Seat token cannot approve/start/research; operator token for human controls |
| Context/skills/rosters/knowledge | Version/hash-pinned tracked sources routed per seat; routing/integrity tests | Referenced text, not implicit executable skills |
| Project Library | Existing authority/version/hash; stale/project scope tests + real shared contract | No mirrored Library DB |
| Bundles | SHA256 versioned topology/models/context/pools import/export; tamper/kind/hash tests | No commands/credentials/local paths/install |
| Pools/telemetry | Scheduler pool admission, limits, reported usage/workspaces; overlap and null-field tests | Missing usage/cost is null; Kaggle quota separate |
| Review/SDLC | Workshop/four-role template; actual reviewed checkpoint and chain tests | Static review ≠ execution; actual terminal/Kaggle tests separate |
| Slack opt-in | Backend env secret/channel/config, explicit human send, scoped interface validation | No automatic send; actual Slack send not authorized/exercised |
| Research bridge | Exact approval/version/context/scope/budget/checkpoint/reviewer/receipts/outbox; tamper/UNKNOWN tests + live CPU | Agents cannot approve or enlarge scope |
| Working/report | Existing cookie/quota/max2 gates, provenance artifact; one COMPLETED CPU, 4/4 assertions, one call after restart | Existing project DB authority; Etc JSON/Output, no forced report.md |
| Migration/rollback/legacy | Isolated v2 backup/new-version refusal/flags/default forwarding; full Workbench regression | Stop/reconcile before rollback, retain current artifacts/project DB |

Actual QA used product runtime model calls. Implementation was done directly,
without delegating to a DSH subagent. See release evidence for scope/receipts.
