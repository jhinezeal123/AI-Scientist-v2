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

Implementation is performed in the attached review worktree. Main checkout and
the user's backend keep the accepted release until the correction is verified.
Refactor commit dc019d2 passed 30 affected baseline tests before behavior work.
Local fixtures do not establish real-provider/real-Kaggle acceptance. A new live
scope will be proposed only after the implementation and local QA are reviewable.

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
- [ ] A8: real-provider/Kaggle acceptance under the new scope; not authorized yet.
- [ ] A9: review release, bring the verified correction to the main checkout.

## How to use

1. Settings → Multi-agent → create team → Research pipeline → choose project.
2. Configure each stage actor and its agent seat. Each seat has a harness, model,
   instructions and the existing per-seat context/policy controls.
3. Ask preset keeps ideation and approval human. Full auto selects agents and
   explicitly permits agent approval within the saved workflow grant.
4. Select benchmark, Library sources, account, maximum runs/calls and session/output
   limits. Enable the four-stage experiment manager when wanted; select finishing outputs.
5. Save the workflow, then start. Answer Human stages or review candidates at the
   selected gates. The activity cards select the current agent; Tasks & sessions and
   workspace show its actual records. Run links open the normal run GUI.
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
- Full Workbench regression: 366 passed (one existing MLflow deprecation warning).
  24 follow-up tests passed (17 stage/search cases and 7 planning cases), covering same-input pause/resume, agent candidate reuse, old-actor
  invalidation and selected-context freshness. The actual original experiment manager
  traversed Draft/Tuning/Research/Ablation with one simulated SSH session and file-verified
  metrics. These checks did not call a model or Kaggle.
- Frontend production build passed. Desktop/mobile GUI and both presets were verified; mobile had no horizontal overflow and the console had no errors. GUI fixture endpoints reject model/Kaggle execution.
- No new paid model call, Kaggle session, public dataset or remote exposure was created.
