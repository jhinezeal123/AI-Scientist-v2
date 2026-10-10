# Required MLflow comparison for Workbench benchmarks

MLflow is the required comparison backend. Workbench retains approval, Kaggle
account, execution, stop and verified result records. A Training/Research run
must select a completed benchmark; MLflow readiness is checked before opening
its Kaggle session. Tracking failures never select a local comparison fallback.

## Setup

Install the standard Workbench environment with `requirements-mvp0.txt`, which
includes MLflow. `requirements-mlflow.txt` is also available to install the
tracking dependency alone in an existing Workbench environment.

Without `AI_SCIENTIST_MLFLOW_TRACKING_URI`, Workbench uses the local SQLite
store `.workbench/mlflow/mlflow.db`. Set that variable to use a separate SQLite
store or an authenticated MLflow Tracking Server. The variable configures the
store; it does not enable or disable tracking.

To browse the local store separately, run MLflow with its absolute SQLite URI:

    mlflow server --host 127.0.0.1 --port 5000 --backend-store-uri sqlite:///D:/Documents/AI-Scientist-v2/.workbench/mlflow/mlflow.db

## Immutable comparison groups

- Create a Benchmark idea with a required metric name, direction, definition
  and test split. The train split is optional; training without a specified
  train source requires planner clarification.
- The benchmark runs on Kaggle and publishes a public, versioned dataset with
  its manifest, test data and evaluator. Training/Research approvals pin that
  complete benchmark reference and dataset version.
- Runs with the same immutable reference share one MLflow experiment:
  `AI-Scientist/{project_id}/benchmarks/{benchmark_id}`. Independent roots and
  runs with different budgets or step counts can share a chart and ranking.
- Different benchmark definitions or dataset versions cannot be ranked
  together. MLflow run tags record project, run, benchmark hash, dataset handle
  and dataset version; inconsistent provenance blocks synchronization.

## Synchronization and failure behavior

`ai_scientist/workbench/benchmark_tracking.py` is the tracking implementation.
The optional adapter from the original PR has been superseded.

Measured telemetry is synchronized after research completion and when reading
comparison data. Imports are idempotent by measured step. Existing history,
immutable parameters and the final metric are verified after persistence;
unverified extra steps, conflicting values or missing final measurements fail.
An interrupted import can resume without creating a second mapping.

The chart reads persisted MLflow measurements. If tracking is unavailable,
preflight blocks a new research session; a completed Kaggle result remains
available, while comparison reports an error and can be retried. No tracking
failure triggers another Kaggle run.

The explicit comparison API accepts 2-8 run IDs. The benchmark chart includes
all runs using the selected reference, without that selection limit. Credentials,
cookies and private source documents are not logged to MLflow.

See [benchmark tasks and usage](BENCHMARK_TASKS.md) and
[local, GUI and live Kaggle QA](BENCHMARK_QA.md) for acceptance evidence.
