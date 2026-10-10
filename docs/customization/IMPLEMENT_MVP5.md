# MVP5 — Unified Multi-Agent Coding Platform

Full scope: [issue #2](https://github.com/jhinezeal123/AI-Scientist-v2/issues/2).
Delivery: [PR #3](https://github.com/jhinezeal123/AI-Scientist-v2/pull/3), target
`codex/personal-implementation-agent`. User expanded the foundation draft to
the full issue, authorized QA then merge, selected DSH ACP as second harness and
Settings → Multi-agent beside Kaggle proxy. Implementation was performed directly,
without delegating to a DSH subagent.

The root `agent management/` package uses existing FastAPI as composition root.
Control SQLite owns coordination; project SQLite owns research. Accepted MVP3
(`b448faa`) is included. MLflow, immutable benchmark/public dataset protocol,
multi-account admission, cookie refresh and max-two-sessions/account remain covered.

## Tasks and acceptance gates

| Gate | Delivered/evidence | State |
| --- | --- | --- |
| M5-0 | Legacy compatibility, flags, v2 backup/migration, bootstrap/shutdown/MVP3 regressions | Done |
| M5-1 | RigSpec/AgentSpec, pods/seats/templates, durable topology; restart/CAS tests | Done |
| M5-2 | Native Codex/Claude, ACP v1/v2, DSH, CLI/models; actual Codex + DSH model tasks | Done |
| M5-3 | Owned queue/dependencies/leases/heartbeat/chat; real four-seat handoff, atomic/load tests | Done |
| M5-4 | Worktrees/supervisor/snapshot/restore/discover/adopt/grow/shrink/reconcile; actual fork/resume | Done |
| M5-5 | Settings GUI topology/tasks/threads/code/diff/terminal/provider/policy/context; browser/build QA | Done |
| M5-6 | Private HTTPS/pairing/scopes/revoke/CSRF/Origin/cursors; actual stream reconnect/revoke | Done |
| M5-7 | MCP/CLI/TUI/context/Library/bundles/pools/telemetry/templates/Slack opt-in; feature matrix | Done |
| M5-8 | Exact approval bridge/outbox/provenance/existing Working; actual CPU 4/4 result/report | Done |
| M5-9 | Security/load/migration/recovery/docs; 358 tests + build + actual provider/Kaggle/remote acceptance passed | Done |

## Actual four-seat acceptance

- Team `mvp5-release`: Lead/QA native Codex `gpt-6-luna`, configured reasoning
  `max`; Builder/Reviewer DSH ACP `api-box` / `ds/deepseek-flash`.
- Installed DSH `@deepseek-ai/dsh@0.2.0-rc.2`; provider/model/credential references
  copied to ignored repo-owned profiles. No runtime install/global-profile change.
- Pinned project Library contract reached all four seats. Builder created only
  `src/mvp5_qa/checksum.py` and `src/mvp5_qa/test_checksum.py`. QA/Reviewer reported
  static-review limitations explicitly. Human terminal later passed 4/4 unittest cases.
- Reviewed checkpoint `7cd397a66cc5edc10546b38f4b4397985b253362` passed through
  Builder → QA → Reviewer. All seven final tasks are DONE, including terminal
  and separate continuity tasks.
- Initial DSH startup and terminal attempts exposed persistent Windows sandbox ACL
  interference. Both stopped with receipts, were fixed and their existing tasks
  explicitly retried. Failed attempts remain in history; no automatic replay.
- Actual Codex fork returned `fork-ready`; actual DSH resume returned `resume-ready`.
  Those two seats overlapped. DSH fork is unsupported explicitly.
- Windows ACP/CLI/terminal use one exclusive OS sandbox slot; native tool-free turns
  can run alongside it. A real no-model-call A→B→A regression proves own source is
  readable and peer source/synthetic project secrets are denied.

## Approved Kaggle acceptance

User approved [the exact new scope](MVP5_QA_SCOPE.md): one CPU session,
`huynhtrungcuong`, TTL 600s, workload 480s plus collection, output 1MB.
No training, dataset publication or competition submission.

| Receipt | Verified value |
| --- | --- |
| Run | `665bd16698394126805d2119ed706cf9` |
| Request | `mvp5-kaggle-release-1` |
| Notebook | `huynhtrungcuong/ai-scientist-ssh-665bd1669839` |
| State | Project COMPLETED; Working stopped; agent_called=1; stop confirmed |
| Start/stop UTC | `2026-10-10T14:58:51.662309+00:00` / `2026-10-10T15:03:34.328060+00:00` |
| Actual assertions | []→0, [1,2,3]→14, [-2,3]→13, [2,2]→8: **4/4 passed** |
| Report | `output/qa-report.json`, collected source and existing Etc Output summary |
| Provenance SHA256 | `f45aac81a3f33d1dc3e2198ed098ee46482a801666bc75f5bee2e5a3062ae0d7` |

Repeating the exact dispatch before/after backend restart returned the same stored
admission receipt. The run remained COMPLETED with one Working call and notebook/
session. Historic receipt state STARTING describes admission, not current run state.
Etc deliberately has no report.md; accepted evidence is collected JSON plus Output.

## Remote, interfaces and browser evidence

Actual private Tailscale Serve HTTPS reached the isolated QA backend, without
touching the main backend. TLS certificate validation remained enabled.
Secure/HttpOnly/SameSite cookies, team scope, local-only bootstrap, legacy remote
API block, Origin and CSRF passed. SSE reconnected with event IDs 80→84→85, then
returned access_revoked on revocation; subsequent HTTP returned 401.
Actual CLI teams, TUI --once, MCP initialization/tools/read reached the same
backend; MCP research access was denied. No additional owner daemon.
Temporary QA credentials were revoked. No actual Slack send.

Browser checks: desktop 1280×900 and mobile 390×844 via private HTTPS. Mobile
document width 375 versus viewport 390, without horizontal document overflow.
Settings displayed reviewed source and Git diff. This is mobile browser layout
QA, not a physical phone test. Screenshots/private logs remain ignored under
.workbench/qa; credentials are not committed.

The operator GUI also created a new paused team from Starter, saved DSH as the
Builder harness, queued one coding task and cancelled it while still pending.
No additional model call or Kaggle session was started by this UI check.

## Automated verification

- Accepted MVP3 + initial review-fix baseline: **317 passed**.
- Broad regression before final scope tightening: **357 passed**, one existing
  MLflow/SQLAlchemy deprecation warning.
- Final API/execution/research scope regressions: **21 passed**.
- Production TypeScript/Vite build: passed, 44 modules.
- Final full Workbench release suite: **358 passed**, one existing MLflow/SQLAlchemy
  deprecation warning, 321.60 seconds. This includes the real Windows sandbox test.
- Pushed-head CI remains the final merge gate.

Review fixes cover blocking stdin/deadline/cancel, same-seat lease races, expired
lease completion, cross-rig sends/tasks, ACP auth-capability interpretation,
atomic completion/chat failure, health regression, and peer file/diff/snapshot/
event read scope. Event filtering precedes LIMIT to prevent cursor starvation;
predecessor source follows the receiving seat policy.

See [subsystem matrix](MVP5_FEATURE_MATRIX.md) and
[setup/limits/backup/rollback](../../agent%20management/README.md).
No source code copied from T3 Code/OpenRig. Reference design remains in issue #2.
