# MVP5 correction: configurable research stages

The product is a research pipeline whose stages each have one configured actor.
Human and Agent are interchangeable at ideation, proposal, approval, execution,
analysis and research finishing. Harness/model/instructions/context are chosen
per stage. This corrects the previous coding-team interpretation of issue #2.

## Acceptance

1. Ask mode: ideation/approval can remain human; automated stages stop at selected
   review points. The normal Idea/Run workflow remains available.
2. Full auto: an explicit operator grant permits the approval agent to approve
   exact proposal versions inside a project/benchmark/account/time/run budget.
   Approval records name the actor and the grant; they never pretend to be human.
3. One stage agent runs at a time in a workflow, using the existing harness
   registry, owned queue, supervisor, event journal and isolated seat workspace.
4. Existing Working performs Kaggle admission, cookie refresh, max-two/account,
   result collection and stopping. Existing AI Scientist research modules perform
   analysis/summary/report/plots/writeup/review; stage bindings route their calls.
5. GUI shows stage topology, actor/harness/model, waiting/running/stopped states,
   handoffs, human actions and linked run outputs. Personal remote scopes remain
   applicable to the same control endpoints.
6. Pause/takeover and restart preserve completed work. Unknown model/Working
   outcomes require reconciliation; no automatic uncertain replay.

Implementation was verified in the attached review worktree. PRs #4 and #5 are
merged into codex/personal-implementation-agent; the main checkout serves the
verified correction on port 8000. Live acceptance receipts remain in the QA workspace.
Refactor commit dc019d2 passed 30 affected baseline tests before behavior work.
Local fixtures do not establish real-provider/real-Kaggle acceptance. The approved
live scope and measured acceptance receipts are recorded in MVP5_STAGE_QA_RESULTS.md.

References: the supplied OpenRig activity recording and documentation,
T3 Code harness/remote architecture, and the existing AI Scientist experiment
manager and research finishing modules. No external daemon is required.

## Tasks to track

- [x] A1: expose stage runtime seams in a separate refactor (dc019d2).
- [x] A2: immutable workflow grant and Human/Agent bindings for every stage.
- [x] A3: delegated exact-version approval, source pinning and existing Working gates.
- [x] A4: route execution/actions/analysis/finishing through the existing team harnesses.
- [x] A5: enable original four-stage experiment manager for explicitly configured workflows.
- [x] A6: Settings UI, human idea/proposal forms, per-agent harness/model/instructions,
  activity map, human review controls and explicit remote research scope.
- [x] A7: local regression and fixture QA, including actual experiment-manager code.
- [x] A8: live human gate, native/ACP providers, all four Kaggle stages,
  summary/report, confirmed stop and restart without replay verified.
- [x] A9: reviewed release, merged PRs #4/#5, updated the main checkout and
  restarted backend 8000; health, latest frontend and 14-stage template verified.

## How to use

1. Settings → Multi-agent → create team → Research pipeline → choose project.
2. Configure each stage actor and its agent seat. Each seat has a harness, model,
   instructions and the existing per-seat context/policy controls.
3. Ask preset keeps ideation and approval human. Full auto selects agents and
   explicitly permits agent approval within the saved workflow grant.
4. Select benchmark, Library sources, account, maximum runs/calls and session/output
   limits. Enable the four-stage experiment manager when wanted; select finishing outputs.
5. Save the workflow, then start. Answer Human stages or review candidates at the
   selected gates. The activity observer offers a per-stage table and a connected
   graph. Select a stage to inspect its live output, saved result and sessions
   beside the overview. Run links open the normal run GUI.
6. Pause invalidates the old actor generation and stops an admitted Working session.
   Resume preserves pending human inputs/completed pre-execution candidates.
   A stopped/failed run is never submitted again by resuming; inspect it and create
   a new workflow for another attempt. UNKNOWN requires reconciliation first.
7. For remote use, grant the device the explicit research checkbox when generating
   its pairing code. Existing HTTPS, pairing, CSRF and scoped-team controls apply.

## Boundaries and QA evidence

- Ideation produces one structured hypothesis per iteration, driven by operator goal
  and selected context. This is not a port of upstream Semantic Scholar novelty search.
- Library excerpts for tool-free stage turns are capped at 20KB combined and include
  version/hash/truncation metadata. Full selected files are still staged for Kaggle.
- A saved workflow is immutable; create a new configuration to change the grant.
  Pause the team before changing its seat harness/model/instructions.
- Existing manual Idea/Run and optional coding templates remain available.
- Full Workbench regression after the Windows/context fixes: 382 passed in 383.97s
  (one existing MLflow deprecation warning). After the last proposal schema and
  native action prompt fixes, 27 affected harness/workflow tests passed in 28.59s.
  24 follow-up tests passed (17 stage/search cases and 7 planning cases), covering same-input pause/resume, agent candidate reuse, old-actor
  invalidation and selected-context freshness. The actual original experiment manager
  traversed Draft/Tuning/Research/Ablation with one simulated SSH session and file-verified
  metrics. These checks did not call a model or Kaggle.
- Frontend production build passed. Desktop/mobile GUI and both presets were verified; mobile had no horizontal overflow and the console had no errors. GUI fixture endpoints reject model/Kaggle execution.
- Live QA uses MVP5_STAGE_QA_SCOPE.md and the user's autonomous retry authorization.
  Human pause/resume/rejection caused no admission; delegated ACP approval records
  exact version/hash/grant. Workflow acf745d77c674171ae479f9ebfade1ff completed run
  691be18f19ee4cd4b0ad811b99c455c7 through all four original stages and summary/report.
  All seven CPU sessions have confirmed stop receipts; restart preserved DONE,
  calls and task receipts, and rejected replay. No new dataset or remote exposure
  was created. See MVP5_STAGE_QA_RESULTS.md for measured values and history.
- Follow-up QA fixed unrelated team inbox/source leakage into structured stage turns,
  atomic JSON publication under Windows readers and redirected Unicode console output.
  One same-actor schema-format repair is allowed per invocation; it uses the existing
  call budget/deadline and never retries UNKNOWN outcomes. 25 affected tests passed,
  followed by 18 workflow tests and 5 search/Windows tests after the last fixes.
- Delegated proposal schemas now require exact execution/output budget keys within
  the grant, before approval. Native harnesses permit returning structured action
  JSON for the backend-owned approved session while retaining disabled local tools.
  Two pre-admission workflow attempts stopped on invalid output/budget; neither
  consumed a Kaggle session. Total live usage: 55 agent calls, seven CPU sessions.
- The latest 11 search/Windows tests also enable the original ResearchPipeline,
  upstream tuning/ablation idea classes, stage summaries and report generation.
  Selected-node limitations are explicitly scoped to that node at execution time;
  a Draft baseline selected after later stages does not describe the aggregate
  experiment as Draft-only.

## Activity UI correction

The first stage release supplied configuration forms and status cards. The
operator clarified that the OpenRig reference also calls for an immediately
inspectable view of each actor's work. The follow-up adds:

- A stage/agent table with harness, model, workflow state, call count, queued tasks
  and session count, plus a connected graph with active handoff motion.
- An adjacent inspector with Activity, Result and Sessions views. Each action
  turn can be selected independently, including its saved response and handoff.
- Exact workflow-event task IDs and session IDs for history selection. A shared
  seat does not merge outputs from other stages or workflows.
- Explicit Human/waiting, paused, failed, unknown and disconnected observations.
  An enabled team means ready to accept work, not that an agent is executing.
- A two-column graph on narrow screens, keyboard stage selection, bounded output
  scrolling and reduced-motion support. The existing configuration and human
  gate controls remain in Settings alongside Kaggle proxy.

The interface uses the repository's own queue/session journal. It does not claim
to reproduce the OpenRig TUI or estimate provider context-window percentages.
Eight frontend selector cases and a production build passed. The actual saved
22-call workflow was inspected at 1280px and 520px without horizontal page overflow;
result/session selection and table/graph switching were verified without executing
another provider turn or Kaggle session.
