"""Opt-in MLflow projection of approved Workbench runs.

Workbench remains authoritative for approval, execution, and metric validity.
MLflow stores an inspectable, idempotently synchronized metrics history.
"""
import hashlib
import math
import os
import re
import threading
import time

from .store import canonical

TRACKING_URI_ENV = "AI_SCIENTIST_MLFLOW_TRACKING_URI"
_BUDGET_KEYS = ("training_seconds", "execution_seconds", "output_bytes")
_SYNC_LOCK = threading.RLock()


def tracking_uri():
    return os.environ.get(TRACKING_URI_ENV, "").strip() or None


def _experiment(client, project_id):
    name = f"AI-Scientist/{project_id}"
    experiment = client.get_experiment_by_name(name)
    if experiment is not None:
        return experiment.experiment_id
    try:
        return client.create_experiment(name)
    except Exception:
        # Two simultaneous comparisons may create the same experiment.
        experiment = client.get_experiment_by_name(name)
        if experiment is None:
            raise
        return experiment.experiment_id


def _primary_points(row):
    spec = row["protocol"].get("metric")
    if not isinstance(spec, dict) or not isinstance(spec.get("name"), str):
        return None, []
    name = spec["name"]
    values = []
    for point in row["points"]:
        value = point.get("metrics", {}).get(name)
        step = point.get("step")
        if type(step) is int and step >= 0 and type(value) in (int, float) and math.isfinite(value):
            values.append((step, float(value)))
    result = row.get("metric")
    if row["state"] == "COMPLETED" and result is not None:
        final_value = result.get("final_value")
        if type(final_value) in (int, float) and math.isfinite(final_value):
            if values and values[-1][1] != float(final_value):
                raise ValueError("Final metric and Workbench telemetry disagree")
            if not values:
                values = [(0, float(final_value))]
    return name, values


def _sync_comparison(project_id, rows, *, client=None):
    """Sync selected runs and load curves/scores from MLflow into rows.

    No Workbench state is changed. On failure the caller can safely fall back
    to validated Workbench results. Mutations to rows happen only on success.
    """
    uri = tracking_uri()
    if client is None:
        if uri is None:
            return False
        from mlflow.tracking import MlflowClient
        client = MlflowClient(tracking_uri=uri)
    from mlflow.entities import Metric, Param, RunTag

    experiment_id = _experiment(client, project_id)
    updates = []
    for row in rows:
        workbench_id = row["run_id"]
        if not re.fullmatch(r"[a-zA-Z0-9_-]{1,80}", workbench_id):
            raise ValueError("Unsafe Workbench run ID for MLflow query")
        protocol_hash = hashlib.sha256(canonical(row["protocol"]).encode("utf-8")).hexdigest()
        found = client.search_runs(
            [experiment_id], filter_string=f"tags.workbench_run_id = '{workbench_id}'",
            max_results=2,
        )
        if len(found) > 1:
            raise ValueError("Multiple MLflow runs mapped to one Workbench run")
        if found:
            mlrun = found[0]
            mlrun_id = mlrun.info.run_id
            if (mlrun.data.tags.get("workbench_project_id") != project_id
                    or mlrun.data.tags.get("workbench_protocol_hash") != protocol_hash):
                raise ValueError("MLflow provenance mismatch")
        else:
            mlrun = client.create_run(
                experiment_id,
                tags={
                    "workbench_run_id": workbench_id,
                    "workbench_project_id": project_id,
                    "workbench_protocol_hash": protocol_hash,
                },
                run_name=row["title"][:250],
            )
            mlrun_id = mlrun.info.run_id

        name, desired = _primary_points(row)
        history = client.get_metric_history(mlrun_id, name) if name else []
        existing = {}
        for entry in history:
            if entry.step in existing and existing[entry.step] != entry.value:
                raise ValueError("Conflicting MLflow metric history")
            existing[entry.step] = entry.value
        fresh = []
        for step, value in desired:
            if step in existing:
                if existing[step] != value:
                    raise ValueError("MLflow metric differs from Workbench")
            else:
                fresh.append(Metric(name, value, int(time.time() * 1000), step))
                existing[step] = value

        params = []
        if not found:
            for key, value in (row.get("budget") or {}).items():
                if key in _BUDGET_KEYS and type(value) in (int, float) and math.isfinite(value):
                    params.append(Param(f"budget.{key}", str(value)))
            params.append(Param("evaluation.protocol_sha256", protocol_hash))
        tags = [
            RunTag("workbench_state", row["state"]),
            RunTag("workbench_metric_direction",
                   row["protocol"]["metric"].get("direction", "")
                   if isinstance(row["protocol"].get("metric"), dict) else ""),
        ]
        if row.get("parent_run_id"):
            tags.append(RunTag("workbench_parent_run_id", row["parent_run_id"]))
        if fresh or params or tags:
            client.log_batch(mlrun_id, metrics=fresh, params=params, tags=tags)

        # Fetch the persisted values rather than treating log_batch as proof.
        persisted = client.get_run(mlrun_id)
        history = client.get_metric_history(mlrun_id, name) if name else []
        history_by_step = {point.step: point.value for point in history}
        verified = row.get("metric")
        if row["state"] == "COMPLETED" and verified and name == verified.get("name"):
            actual = persisted.data.metrics.get(name)
            if actual is None or actual != float(verified["final_value"]):
                raise ValueError("MLflow final metric does not match verified Workbench result")
        mapped = {point["step"]: point for point in row["points"]}
        mlflow_points = [
            {
                "step": step,
                "total_steps": mapped.get(step, {}).get("total_steps", max(history_by_step)),
                "elapsed_seconds": mapped.get(step, {}).get("elapsed_seconds", 0),
                "metrics": {name: value},
            }
            for step, value in sorted(history_by_step.items())
        ] if name and history_by_step else []
        updates.append((row, mlrun_id, mlflow_points,
                        persisted.data.metrics.get(name) if name else None))

    for row, mlrun_id, points, final_value in updates:
        row["mlflow_run_id"] = mlrun_id
        if points:
            row["points"] = points
        if row.get("metric") is not None and final_value is not None:
            row["metric"] = {**row["metric"], "final_value": final_value}
    return True


def sync_comparison(project_id, rows, *, client=None):
    """Serialize first-time imports within one Workbench API process."""
    with _SYNC_LOCK:
        return _sync_comparison(project_id, rows, client=client)
