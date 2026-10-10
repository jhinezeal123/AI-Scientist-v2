# MVP5 stage autonomy acceptance

Accepted 2026-10-11 (Asia/Saigon), under MVP5_STAGE_QA_SCOPE.md and the user's
authorization to run additional CPU sessions autonomously.

## Real workflow

- Project: `386e00c181a24954ad3ce5350c82155e`.
- Workflow: `acf745d77c674171ae479f9ebfade1ff` — **DONE**, one completed iteration.
- Run: `691be18f19ee4cd4b0ad811b99c455c7` — **COMPLETED**.
- Native seats: Codex `gpt-6.1-sol`; approval: DSH ACP `ds/deepseek-flash`.
- Approval receipt pins proposal version, context SHA256, finite grant and actor.
- One CPU session for this successful run, TTL 600s, execution 480s, output 5MB.
- Tree, four stage summaries and technical report all **completed**.

| Original stage | Node | Fixed intercept | Measured mse_test |
| --- | --- | ---: | ---: |
| Draft | `5d1a0782f80c4a1b9c979417fe3d5330` | 1 | 0.0013851734605946817 |
| Tuning | `c8f819c2ac1b482bb495bf25cd439996` | 1 | 0.0013851734605946817 |
| Research | `3077156be5344ba9a96c4462e1d39432` | 1 | 0.0013851734605946817 |
| Ablation | `3fda42b016354c7d84924710f4017f30` | 0 | 1.002662336883973 |

All four nodes contain `source/workload.py`, `output/predictions.csv`,
`output/metric.json` and `output/qa-report.json`. Metrics agree between those
files and the backend's measured node records. The four sources share SHA256
`0bf38d23cfa3d02e0b9b4515e46310d9fe04add99b2bb129f9470e760738d169`.
The workload verifies all three pinned public benchmark files before evaluation.
No training, new dataset, GPU or remote exposure was needed.

The experiment verifies orchestration and deterministic inference on 32 synthetic
test cases. Repeated results do not establish independent statistical uncertainty
or generalization. The selected best baseline originated in Draft; its historical
node limitations remain in the receipt. Aggregate future results explicitly label
these as limitations of the selected node at its execution time.

## Human controls and recovery

- Human ideation and human approval pause/resume kept the same proposal/input and
  call count. Human rejection admitted no Kaggle session.
- GUI exposes the configured stage actors, harness/model, current activity and run
  link. Saved attempts have distinct labels; active stages remain active between
  their remote action turns.
- Restart after completion retained DONE, exactly 55 total calls, identical task
  receipts and no pending/leased/unknown tasks. Starting the completed workflow
  returned conflict, with no replay.
- All **seven** admitted CPU runs have `stop_confirmed=true`. Successful workflow
  used 22 calls; total acceptance effort used **55/60** calls, including failures
  and pre-admission formatting/budget gates.

## Failures retained and repaired

| Attempt | Observed failure | Correction |
| --- | --- | --- |
| 1 | Windows file reader blocked atomic state replacement | Bounded atomic retry for transient Windows sharing errors |
| 2 | Redirected cp1252 console rejected Vietnamese | UTF-8 console and journal output |
| 3 | Native prompt rejected authorized mediated actions | Explicit action JSON contract, local tools still disabled |
| 4 | Generated workload had invalid syntax | Reuse the existing verified benchmark QA source via pinned Library |
| 5 | Extended Windows result path could not be made relative to cwd | Normalize path namespace and retain external workspace paths |
| 6 | Upstream idea objects were incorrectly treated as dataclasses | Preserve their explicit name/description contract |
| 7 | Completed full workflow | Measured nodes, summaries/report and confirmed stop retained |

Failed runs were never replayed or relabeled as successful. Two additional
workflows were stopped before admission by output-format/budget gates.

## Local and CI verification

- Workbench regression: 382 passed, one existing MLflow deprecation warning.
- Follow-up harness/workflow tests: 27 passed.
- Latest original manager/research finishing and Windows tests: 11 passed.
- Frontend production build passed; desktop/mobile fixture UI had no overflow.
- GitHub gateway tests and frontend build passed for PR #4.

Live raw receipts and artifacts stay in the ignored local QA workspace; credentials
are not part of the committed evidence.
