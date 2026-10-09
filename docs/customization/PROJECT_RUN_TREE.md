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
