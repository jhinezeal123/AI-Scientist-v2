# Project run tree

## User flow

Idea → proposal → approval creates exactly one draft run. Working opens one
Kaggle SSH session for that run. The agent fixes errors inside the same run.
There is no automatic implementation/tuning/research/ablation pipeline.

Select a run in the project tree → Improve or Etc → the normal Idea form →
proposal → approval creates one child run with its own SSH session. Training
children accept research/tuning/ablation labels as display metadata only.

Summary, report, plots, PDF and review are independent checkboxes in the Idea
form. New ideas default to none selected, including review. Approval pins the
choices. Technical intermediate evidence required by an output is not another
experiment or a hidden stage. Existing approved proposals keep their saved scope.
Plots/PDF use the existing node log as their interchange evidence when Summary
is unchecked; there is no extra summarizer call or user-facing summary output.

Children receive pinned code files, memory_journal.json and an artifact manifest
with short titles and artifact:// links. Artifact bytes are fetched on demand
through terminal.py into baseline/artifacts; they are not embedded in prompts.

## Acceptance checklist for manual QA

- [ ] All project runs appear in one tree, including Training/Research and Etc.
- [ ] Wheel zooms around the cursor; drag pans; node click opens run detail.
- [ ] A draft proposal creates one node. Working has no four-stage controls.
- [ ] Repairs stay inside that run, with one SSH session and one node.
- [ ] Improve/Etc open the corresponding Idea form with the selected parent.
- [ ] Improve tags do not change prompts, search policy or execution.
- [ ] Output checkboxes are pinned and can be selected independently.
- [ ] Unticked finishing steps are not performed as user outputs.
- [ ] Child can read parent code/journal and fetch an artifact by its link.
- [ ] New child uses its own session_id; it never resumes the parent session.
- [ ] Only stopped leaf nodes can be deleted; backend also rejects non-leaves.
- [ ] Deleting a leaf removes its files from disk and its run record. Copies
      previously imported into Library remain independent sources.
- [ ] Restart retains lineage and never replays a Working action.
- [ ] Legacy saved artifacts remain readable; no legacy experiments are rerun.

No new Kaggle session is needed to inspect this UI change. Actual SSH execution
and selected scientific outputs require a user-approved Working run.

## Delivery checks

- Frontend production build (TypeScript + Vite): passed.
- Python syntax compilation: passed.
- Diff whitespace check: passed.
- Backend restart on 8011: startup completed, health status ok.
- Browser workflow: exercised on 2026-10-09; results below.
- New Kaggle execution: not exercised; no new session launched.

## Browser QA — 2026-10-09

Browser-use drove the running app on `http://127.0.0.1:8011/`, using project
`QA M2-02 Etc Output`. No API fixtures or unit tests supplied the workflow.

Passed:

- Existing Etc roots and a retry child appeared in one tree. A new Improve
  was added under the correct parent, with a different mode accent.
- Wheel zoom changed scale from 0.6539 to 0.8278 without scrolling the page;
  dragging changed the translation by exactly the drag distance. Fit and
  node selection worked. The separate full-screen tree opened run detail.
- Improve opened Training/Research Idea with the pinned parent; Etc opened
  the Etc form with desired-output input and without Research checkboxes.
- All five optional outputs started unchecked. Plots, PDF and Review could
  be selected while Summary and Report remained off. These choices survived
  save/edit, planning, approval and page reload, becoming read-only in Run.
- Real Codex planning and approval created exactly one child, increasing
  the tree from 3 to 4 runs. Working exposed hardware/TTL and one start
  action, with no automatic stage-budget controls. The `tuning` tag appeared.
- The parent delete action was disabled; the new unstarted leaf was eligible.
  After user confirmation, deleting QA run
  `4180d513ab624ebbb9a4360ebd4c40c7` returned the tree to 3 runs. The node did
  not reappear after reload, and its owned `runs/<id>` directory was absent.
  This run had not executed: removing a populated artifact directory remains
  untested. The approved QA idea/proposal and planning diagnostics remain.
- Saved baseline showed code and memory_journal file references. Older run
  outputs and logs remained accessible. Browser console inspection showed
  no JavaScript errors before the deliberate backend reloads.

Planning initially failed with a generic ValueError. The first worker failed;
the second worker completed but the planning service rejected its result.
Earlier failures did not retain enough detail to prove their exact cause.
Adapter-authored error diagnostics and a validated `proposal-result.json` are
now saved. Planner prompts explicitly restrict `data_refs` to selected Library
IDs and keep parent artifact links in the separate baseline. The next browser
planning attempt succeeded as proposal `a76a0c553c12483893b7bfd7d26ad1b8`.

Not verified by this browser session: remote artifact fetching, execution-time
self-repair, distinct SSH sessions for actual child execution, omitted finishing
steps, generation of selected scientific outputs, and deletion of a populated
run folder. These require a separately approved live Working run. A browser
reload proves persisted UI state, not process-restart recovery of a live session.

Screenshots (local, ignored QA artifacts):

- `.workbench/acceptance/project-tree-2026-10-09/browser-tree.jpg`
- `.workbench/acceptance/project-tree-2026-10-09/browser-scope.jpg`

## Live Codex / Kaggle QA — 2026-10-09

The user authorized actual Codex CLI calls and Kaggle SSH sessions. Browser-use
created proposals and started CPU runs in `QA Project Tree — live 09-10 (2)`
(`ae58ccc219304c68913d35400fab62f4`). The normal backend configuration was not
edited; a separate QA config allows 25 minutes Working with a 30-minute CPU TTL.

Verified live workflows:

- Draft `faffeb33caff4d6c839fe39db3d4cd49` generated real synthetic data,
  source, 31 loss points, 96 predictions and metrics. A read-only local
  recalculation confirmed the 64/16/16 split and all three MSEs. Its workload
  succeeded, but journal serialization failed before scientific finishing.
- Improve `e287a095b04b4a4fa49814084947e26b` read pinned parent code and
  memory_journal and lazily fetched `output/metrics.json`. SHA256 matched the
  approved reference, and all current-minus-parent MSE differences were zero.
  The new SSH session was distinct from its parent. A missing local dependency
  stopped research finishing, while source and outputs remained available.
- Improve `c3ea17bb7a314f429e24467a63b45723` completed execution, original
  Summary and original journal2report. Plots, PDF, Review and seed evaluation
  were `not_requested`. The saved summary/report use the measured MSEs and
  explicitly limit claims to a small, single-seed reproducibility check.
- Each of the three runs has its own `working-stop.json` confirming Kaggle
  status `complete` and `stopped: true`; failures did not leave sessions active.
- Execution command records show real failed shell/check commands followed by
  successful commands in the same run, without creating a debug child.
- A backend process restart retained the three-node lineage and the approved
  unstarted node; no old node was automatically replayed. This verifies idle
  restart persistence, not recovery from an abrupt interruption during work.
- In the narrow browser viewport, all three SVG node rectangles fit inside
  the tree after reload, without pressing Fit. Direct node selection worked.

Live QA exposed and fixed:

1. New-project SQLite migration used tuple rows where it needed named columns:
   new connections now use the same `sqlite3.Row` factory as existing projects.
2. Windows extended paths (`\\?\D:\...`) disagreed with upstream `Node.to_dict`
   when calculating a relative experiment path. Normalize the display path at
   the Workbench-to-upstream Node boundary, leaving filesystem long-path access.
3. The backend environment lacked upstream data-preview and PDF/review import
   dependencies. Added them to runtime requirements and the resolved lock;
   all finishing-module imports and `pip check` passed after installation.
4. Late backend errors could leave Training/Research memory summary success
   true despite overall failure. The error path now marks success false in both
   modes, retaining produced files and the original agent explanation.
5. The tree fitted only once, so a responsive size change could clip nodes.
   Refit on viewport/tree geometry changes, preserving user pan/zoom during
   ordinary status polling. The production frontend build passed.

Additional live evidence:

- Improve `77183b3964cf44c9960586f43ff8791c` completed execution and original
  plot aggregation with Summary/Report off. Its two PNGs show the 31-step loss
  and the 16 held-out predictions, with MSE matching metrics. Both were viewed.
  Direct journal evidence supplied the upstream interchange file without a
  Summary or Report LLM call. The three selected tags remained informational;
  exactly one child node and one new CPU session were created.
- PDF compilation in that run exposed missing `pdflatex` and `bibtex` in the
  Kaggle image. The run reported failed PDF/Review, retained the LaTeX draft,
  compiler diagnostics, figures and measured outputs, and stopped Kaggle.
  Backend now provisions the compiler/template packages in the same terminal
  only when PDF is selected, before invoking the original writeup/compiler.
- Shared Working instructions now recommend file-based scripts for nested
  quoting and Python timing instead of assuming `/usr/bin/time` exists.
- Responsive QA at the default narrow viewport and at 1280x900 confirmed all
  node rectangles remained within the SVG frame; the viewport override was reset.
- One PDF/Review planning attempt exceeded the existing 300-second CLI deadline
  before producing a proposal. No run/session was created. Browser "Continue"
  initiated a separate planning attempt with the saved idea/scope; that attempt
  succeeded as proposal `0c5c150a973d45d89ddb9db69fbd1403`. There is insufficient
  diagnostic evidence to attribute the first timeout to a particular provider.

- Improve `918083a4b85a4dc3bf95e47e527fe56b` completed PDF and Review with
  Summary, Report and Plots off. TeX provisioning succeeded in its own SSH
  session. Original writeup/reflection/compiler produced a two-page, 82,332-byte
  PDF (SHA256 `76e9a5798df4dbfa587ffe1fb1da6ffb949ce7ad7119b470752793448b2c1494`).
  Both pages of the final revision were rendered and visually inspected: readable,
  no clipping or overlap, truthful parent MSEs, no new-training/improvement claim.
  Original Review returned valid structured feedback and `Reject`, appropriately
  identifying the synthetic artifact audit's limited research contribution.
  The run is COMPLETED and its stop receipt confirms Kaggle stopped.
- Etc child `3f100a63170e45f7812a307d8f2b693e` of `c3ea17bb...` completed
  through a distinct SSH session without Research stages. It fetched the parent
  metrics on demand and verified the metrics/code/journal SHA256s. Its three
  requested source/output files total 10,847 bytes; no training occurred.
- Browser copied its `output/metrics-note.md` into Library as
  `QA metrics note — bản copy Etc` (`5bfadacebb0343e283a74b58f4a47133`).
  The 754-byte original/text copies match SHA256
  `e7b99dd49611ae77473e8b1fb1e06eb661ea2682966876454ce6de183cfdf6b4`.
  Library `source.md` additionally wraps the source title and provenance.
- With action-time user confirmation, browser deleted the populated Etc leaf.
  The tree count fell from six to five. Read-only disk inspection confirmed
  both its output directory and `runs/3f100a63...` directory are absent.
  The Library copy retained its exact hash and remained available in the GUI.
  The parent with an existing child still had its Delete action disabled.

- Training/Research `46be710474d244fb83973d26611aff5a` completed a
  standard-library foreground wait with all five finishing options off. It
  created no Research pipeline or generated Summary/Report/Plots/PDF/Review;
  journal and memory still saved and Kaggle stopped. This was not a successful
  cancellation test: `QA_STOP_READY` appeared together with completion after
  180 seconds because the donor transport retained a fixed 128-byte tail.
- Fixed that transport in the donor repository's
  `interface_ai_scientist/terminal_remote.py`: retain only bytes that could be
  a partial command-result marker, emitting other progress immediately.
  Syntax and every split boundary of a short-log/result-marker sequence passed.
  The fix is used when a new persistent terminal starts; existing terminals
  are not restarted or replayed.

- Follow-up `79b735bb15f0484d9eaea281e3901b1b` reused the pinned wait.py
  unchanged in another CPU session. Browser observed the standalone
  `QA_STOP_READY` line while no standalone `QA_WAIT_COMPLETED` line existed,
  then clicked Stop. The run transitioned to CANCELLED; saved memory has
  `succeeded: false`, `stop_confirmed: true`, and its stop receipt confirms
  Kaggle status `complete`. Final log ends with RuntimeCancelled and confirmed
  shutdown, with no script completion line or newly collected done.json.
  Cancellation does not claim uncollected remote files were absent.
- Restored the backend to the normal config on port 8011 after all QA sessions
  stopped. Health returned `ok`. Browser reload retained the seven remaining
  nodes and their states; no active QA run or automatic replay was observed.
  Runtime's last CLI job remains `failed` because it was cancelled, while the
  backend itself is healthy. The separate 25-minute QA config is retained as
  evidence, not used by the restarted backend.

Coverage limits: these actual sessions used CPU and the ICBINB PDF template.
GPU/TPU execution, ICML writeup, every checkbox combination, and abrupt process
termination during live work were not exercised by this session. This verifies
normal cancellation and idle restart, not arbitrary crash recovery. Three
failed historical QA nodes remain visible to document the bugs, followed by
successful verification nodes; failures were not silently relabelled.

Additional screenshots under the ignored acceptance directory:

- `live-tree-final.jpg` — final lineage and CANCELLED verification node.
- `library-after-leaf-deletion.jpg` — independent copied source after deletion.
- `pdf-review-page-1.png`, `pdf-review-page-2.png` — rendered final PDF.
- `stop-confirmed.jpg` — cancellation workflow evidence.
