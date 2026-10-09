This call implements one search node, not the entire four-stage pipeline. Follow
search.stage_task and search.action within the approved proposal and its budget.
For draft create a baseline; for debug fix the selected failed implementation;
for improve make a controlled change appropriate to the current stage. The
backend has restored the selected parent's source/output files remotely. Read
them through terminal.py; preserve useful baseline results and use separate
names for changed outputs if comparison needs them. Record what changed.

Implementation establishes correctness; tuning changes configuration while
preserving architecture/method; research tests a substantive improvement;
ablation removes/changes a component to measure its contribution. For general
tasks these principles apply to the implementation method. Do not add unrelated
datasets, larger models, extra epochs or paper generation outside the proposal.
If an action cannot meaningfully be performed within scope, report the limitation
and succeeded=false; do not invent successful experiments.

Run the relevant experiment in the foreground and inspect its actual outputs.
Environment checks already made in this session need not be repeated. The
backend owns tree selection, collecting artifacts and stopping Kaggle. Complete
this node and return; do not execute later stages or stop the session yourself.
Read only the baseline files and Library sections needed for this stage. Use
targeted searches and bounded excerpts; do not print all inherited source files,
outputs or every page of a paper. Reuse preceding stage results rather than
rerunning completed experiments unless the controlled comparison requires it.
After checking the required files and measured metric, return the final node
JSON promptly. Do not add unrelated inspections after successful execution.

search.stage_idea is the upstream tuning/ablation proposal for this node; apply it
only inside the user's approved method/data/budget. search.parent_execution holds
real SSH stdout and returncodes from the parent; use it for debugging. When
search.action=seed, perform one repeat of the selected parent with exactly
search.evaluation_seed for training randomness; preserve its method/hyperparameters
and the approved train/validation/test split. Do not search for a better seed,
change datasets or evaluate held-out test results to select an implementation.
Record the actual training seed in the metric evidence JSON at /training_seed.
When approved.body.research is present, do not generate paper/aggregate figures
during an individual tree node: approved research finishing steps are handled
after all four stages. Older approvals without that field keep their original
requested outputs and node workflow.

Return succeeded, summary in Vietnamese, limitations, output_files, plan,
metric and datasets_tested. plan explains the tested change. metric is null
when no comparable numerical metric exists. Otherwise provide name, value,
direction, evidence_file (a collected JSON file) and evidence_pointer (JSON
pointer to the measured numeric value, e.g. /validation/accuracy). Use only the
approved metric where specified, never test results to tune/select a model.
datasets_tested names only datasets actually tested. Summary must distinguish
verified results from hypotheses. Do not claim full pipeline completion.
