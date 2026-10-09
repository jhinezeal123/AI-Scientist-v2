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
- Browser workflow and new Kaggle run: left for user QA; no new session launched.
