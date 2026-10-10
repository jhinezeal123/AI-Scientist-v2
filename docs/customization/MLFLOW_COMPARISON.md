# MLflow comparison for Workbench runs

The Workbench run/proposal SQLite database remains authoritative for approvals,
Kaggle accounts, queue, stop receipts, and validated results. This integration
projects selected runs into MLflow **when a comparison is requested**; it does
not instrument remote Kaggle notebooks or change their lifecycle.

## Enable locally

Install the optional dependency in the Workbench Python environment:

    pip install -r requirements-mlflow.txt

Set the AI_SCIENTIST_MLFLOW_TRACKING_URI environment variable in the Workbench
backend process before starting it. Example local database URI (use a private
absolute path outside the git checkout):

    sqlite:////absolute/path/mlflow.db

On Windows, a typical form is sqlite:///D:/private/mlflow.db. An authenticated
Tracking Server URI is also supported. When the variable is unset, comparison
uses the verified Workbench metrics and requires no MLflow installation.

To browse the tracked experiments, start MLflow with the same URI:

    mlflow server --host 127.0.0.1 --port 5000 --backend-store-uri sqlite:////absolute/path/mlflow.db

Open http://127.0.0.1:5000. Do not expose the server publicly without
authentication. Back up the database before MLflow schema upgrades.

## Behavior and provenance

- Comparison API: POST /api/projects/{project_id}/runs/compare (2–8 IDs).
- The approved dataset IDs/versions/SHA256, split, metric definition and mode
  still gate ranking in Workbench. MLflow alone does not decide comparability.
- Each Workbench project gets an AI-Scientist/{project_id} MLflow experiment.
  Runs are mapped with workbench_run_id / workbench_project_id tags, and an
  immutable workbench_protocol_hash.
- Primary metric curves are synced by step using MLflow metric history.
  Existing steps are checked before writing, so repeated compares do not
  duplicate metrics. Scores and curves are read back from MLflow; completed
  results must match verified Workbench scores.
- Approved time budget is logged as MLflow parameters when present. Budget
  discrepancies produce advisory fairness warnings, not automatic exclusion.
- The UI displays tracking_backend and tracking_warning. If MLflow is
  unreachable or inconsistent, comparison falls back to locally verified
  Workbench metrics; no Kaggle run is retried and no Workbench data is changed.
- Only identifiers, protocol hash, limited budget metadata and primary metric
  values are projected; not source documents, credentials, cookies or artifacts.
- Older runs are synced lazily when selected for comparison, not at execution.

## Limitations and follow-up

- MLflow is not an evaluator: it cannot prove that SSH AILAB_METRIC lines were
  computed on the approved validation split.
- Multi-worker concurrent first imports need a durable unique mapping to
  guarantee exactly one MLflow run per Workbench run across processes.
- Generated-code hyperparameters (e.g. learning rate) require a structured
  execution contract before they can be reliably logged as parameters.
- Statistical confidence, multi-seed aggregation, and tied results remain
  future evaluation-layer work.
