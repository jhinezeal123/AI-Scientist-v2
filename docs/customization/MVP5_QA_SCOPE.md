# MVP5 live research acceptance scope

The local four-seat workflow and private remote QA use Codex + DSH ACP.
The following **new Kaggle execution** requires the user's approval before
approving the proposal or dispatching Working. Earlier benchmark QA approvals
covered different proposals and public dataset publication.

| Binding | Value |
| --- | --- |
| Project | `da98c2c2b5ea4b9f800db65632bbdcbf` |
| Proposal | `fb8e0d6da13e4c6d8a09e7ab4b14b5ab`, version `1` |
| Context SHA256 | `26b99f615edbd2c642bc3c5a9e850ecfa6e9250145d0a873b84ac216369c0f02` |
| Team | `mvp5-release`: Lead → Builder → QA → Reviewer |
| Account | `jhin_access_token.txt` / `huynhtrungcuong` |
| Accelerator | CPU |
| Sessions | At most **one**, TTL **600 seconds** |
| Workload budget | **480 seconds**, plus 120 seconds for collection |
| Output bound | 1 MB |

The team prepares a standard-library Python checksum function and three fixed
test cases. Existing Working runs the reviewed implementation on Kaggle,
asserts actual results, records elapsed time and team request/checkpoint
provenance, and collects `source/workload.py`, `output/qa-report.json` and the
existing Etc Output summary. No training, dataset upload or competition submission.

Acceptance: verified process/session stop receipts; authoritative project run
state and report; same request repeated and replayed after server restart
creates no second Working intent, notebook submission or session. A failed or
UNKNOWN execution is reconciled before any retry; an additional Kaggle session
requires a new approval.

## Accepted outcome (2026-10-10 UTC)

The user approved this scope. Run `665bd16698394126805d2119ed706cf9` completed
on CPU; `output/qa-report.json` contains four actual passing assertions and
request/checkpoint provenance. Working was called once and confirmed stopped.
Identical dispatch before and after backend restart returned the original receipt.
See [release evidence](IMPLEMENT_MVP5.md). No additional Kaggle session was consumed.
