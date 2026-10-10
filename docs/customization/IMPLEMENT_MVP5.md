# MVP5 — Unified Multi-Agent Coding Platform

Scope được người dùng xác nhận ngày 2026-10-10: triển khai toàn bộ
[issue #2](https://github.com/jhinezeal123/AI-Scientist-v2/issues/2), QA rồi merge
[PR #3](https://github.com/jhinezeal123/AI-Scientist-v2/pull/3) vào
`codex/personal-implementation-agent`. Không đánh dấu MVP5 hoàn tất trước M5-9.

Implementation giữ module đóng gói trong `agent management/`; FastAPI hiện tại
là composition root duy nhất. Control DB quản lý agent; project DB vẫn quản lý
research. Nền MVP3 được ghép từ merge commit `b448faa`.

## Tasks và acceptance gates

| Gate | Tasks | Acceptance | State |
| --- | --- | --- | --- |
| M5-0 | Baseline, feature flag, migrations/backup, regression | MVP3 không hồi quy, tắt orchestration được | Doing |
| M5-1 | RigSpec/AgentSpec, pods/seats, templates, schema | Tạo/đọc rig qua restart | Todo |
| M5-2 | Registry, models/capabilities, native Codex/Claude, ACP v1/v2, CLI | Hai harness thật chạy task, không fallback | Todo |
| M5-3 | Queue/leases, scheduler, chatroom, handoff | Lead → Builder → QA → Reviewer, không double lease | Todo |
| M5-4 | Worktrees, supervisor, checkpoint/snapshot, resume/fork/adopt/grow/shrink/reconcile | UNKNOWN không replay, restart phục hồi topology | Todo |
| M5-5 | Teams workspace UI, threads/code/terminal/Git/topology/policy/provider | Một hành trình tạo team và nhận kết quả qua GUI | Todo |
| M5-6 | Pairing/scopes/revoke/HTTPS, event reconnect | Thiết bị cá nhân điều khiển an toàn, không double submit | Todo |
| M5-7 | MCP/CLI/TUI, context/skills/rosters, bundles, telemetry, SDLC, Slack opt-in | Feature matrix có test/demo cho mọi subsystem trong issue | Todo |
| M5-8 | Research bridge/outbox, approval/version/hash/budget/provenance | Idea → duyệt → code/review → Kaggle → report | Todo |
| M5-9 | Security/load/recovery/release QA | 4 seats + 2 harness thật + reboot/retry + remote + no duplicate run | Todo |

## Tiến độ kiểm chứng

- Baseline sau merge/sửa review: **317 tests pass**.
- Schema/workspaces/recovery + execution fixtures: **16 tests pass**; pipeline
  Lead → Builder → QA → Reviewer giữ checkout chính nguyên vẹn, trao checkpoint
  qua dependency và không replay task DONE khi khởi động lại.
- Probe thật: native Codex (`gpt-6-luna`, cấu hình hiện có) và **DSH ACP v1** đều
  trả JSON `ready`, có receipt chứng minh process tree đã dừng.
- Người dùng chọn DSH ACP làm harness thứ hai ngày 2026-10-10. Bản cài local
  `@deepseek-ai/dsh@0.2.0-rc.2` được chạy bằng Node entrypoint; không gọi npx/install.
  Provider/model từ profile Web được copy vào file cấu hình ignored của repo;
  chọn model qua ACP `session/set_config_option`, không thay global profile.
- Native Claude có adapter nhưng auth native cần đăng nhập riêng; proxy đang cấu
  hình trên máy không đạt probe. Gate hai harness sử dụng Codex + DSH theo yêu cầu.
- UI/remote/research bridge và release QA vẫn đang triển khai; chưa nghiệm thu MVP5.

## Review regressions

PR gốc `ba22421`: 31 tests gateway/bootstrap/planning/working pass nhưng probes
phát hiện blocking stdin không tuân deadline/cancel, hai lease cùng seat, late
finish của lease hết hạn, seat ngoài rig nhận task/broadcast, và hiểu nhầm
`authMethods` là trạng thái chưa login. Regression tests chạy provider fixture
local và DB tạm; không dùng Kaggle hay model trả phí.

## References

- [OpenRig README](https://github.com/mvschwarz/openrig/blob/main/README.md)
- [OpenRig architecture](https://github.com/mvschwarz/openrig/blob/main/ARCHITECTURE.md)
- [OpenRig RigSpec](https://github.com/mvschwarz/openrig/blob/main/docs/reference/rig-spec.md)
- [T3 ACP providers](https://github.com/pingdotgg/t3code/blob/main/docs/user/providers-acp.md)
- [ACP v1 authentication](https://agentclientprotocol.com/protocol/v1/authentication)

Không cài OpenRig daemon hay sửa provider trust/config toàn cục. Các cơ chế được
triển khai trong package Python hiện có; credentials nằm ngoài bundle/export.
