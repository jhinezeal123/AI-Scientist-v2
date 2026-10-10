"""MLflow comparison projection tests run without installing the optional SDK."""
import sys
from types import ModuleType, SimpleNamespace

import pytest

from ai_scientist.workbench import mlflow_tracking
from ai_scientist.workbench.compare import compare_runs


class _Entity:
    def __init__(self, *args):
        self.key, self.value = args[:2]
        if len(args) == 4:
            self.timestamp, self.step = args[2:]


class FakeClient:
    def __init__(self):
        self.experiments = {}
        self.runs = {}
        self.history = {}
        self.writes = 0

    def get_experiment_by_name(self, name):
        identifier = self.experiments.get(name)
        return SimpleNamespace(experiment_id=identifier) if identifier else None

    def create_experiment(self, name):
        self.experiments[name] = str(len(self.experiments) + 1)
        return self.experiments[name]

    def search_runs(self, ids, filter_string, max_results):
        key = filter_string.split("'")[1]
        return [self.get_run(mlrun_id) for mlrun_id, row in self.runs.items()
                if row["experiment"] in ids and row["tags"]["workbench_run_id"] == key][:max_results]

    def create_run(self, experiment_id, tags, run_name):
        identifier = f"mlflow-{len(self.runs) + 1}"
        self.runs[identifier] = {"experiment": experiment_id, "tags": dict(tags),
                                 "params": {}, "name": run_name}
        self.history[identifier] = {}
        return self.get_run(identifier)

    def get_metric_history(self, run_id, key):
        return self.history[run_id].get(key, []) if key else []

    def log_batch(self, run_id, metrics, params, tags):
        self.writes += 1
        run = self.runs[run_id]
        run["tags"].update({tag.key: tag.value for tag in tags})
        run["params"].update({param.key: param.value for param in params})
        for metric in metrics:
            self.history[run_id].setdefault(metric.key, []).append(metric)

    def get_run(self, run_id):
        run = self.runs[run_id]
        metrics = {key: max(history, key=lambda m: (m.step, m.timestamp)).value
                   for key, history in self.history[run_id].items() if history}
        return SimpleNamespace(info=SimpleNamespace(run_id=run_id),
                               data=SimpleNamespace(tags=dict(run["tags"]), metrics=metrics))


@pytest.fixture(autouse=True)
def fake_entities(monkeypatch):
    module = ModuleType("mlflow.entities")
    module.Metric = _Entity
    module.Param = _Entity
    module.RunTag = _Entity
    monkeypatch.setitem(sys.modules, "mlflow.entities", module)


def _row(run_id="a", final=0.8):
    return {"run_id": run_id, "title": run_id, "state": "COMPLETED",
            "parent_run_id": None, "budget": {"training_seconds": 60},
            "protocol": {"mode": "training_research",
                         "data": [("data", 1, "sha")], "split": {"seed": 42},
                         "metric": {"name": "accuracy", "direction": "maximize"}},
            "metric": {"name": "accuracy", "direction": "maximize", "final_value": final},
            "points": [{"step": 1, "total_steps": 2, "elapsed_seconds": 1,
                        "metrics": {"accuracy": 0.5}},
                       {"step": 2, "total_steps": 2, "elapsed_seconds": 2,
                        "metrics": {"accuracy": final}}]}


def test_sync_to_mlflow_is_idempotent():
    client = FakeClient()
    rows = [_row()]
    assert mlflow_tracking.sync_comparison("project", rows, client=client)
    assert rows[0]["mlflow_run_id"] == "mlflow-1"
    assert [p["step"] for p in rows[0]["points"]] == [1, 2]
    assert len(client.get_metric_history("mlflow-1", "accuracy")) == 2
    assert client.runs["mlflow-1"]["params"]["budget.training_seconds"] == "60"

    assert mlflow_tracking.sync_comparison("project", rows, client=client)
    assert len(client.runs) == 1
    assert len(client.get_metric_history("mlflow-1", "accuracy")) == 2


def test_reject_protocol_and_metric_provenance_changes():
    client = FakeClient()
    mlflow_tracking.sync_comparison("project", [_row()], client=client)
    changed = _row()
    changed["protocol"]["split"] = {"seed": 7}
    with pytest.raises(ValueError, match="provenance"):
        mlflow_tracking.sync_comparison("project", [changed], client=client)
    changed = _row()
    changed["points"][-1]["metrics"]["accuracy"] = 0.9
    with pytest.raises(ValueError, match="telemetry"):
        mlflow_tracking.sync_comparison("project", [changed], client=client)


def test_tracking_outage_preserves_workbench_comparison(monkeypatch):
    from ai_scientist.workbench import compare

    class Store:
        def approved_snapshot(self, project, run):
            return {"body": {"data_refs": ["data"], "split": {"seed": 42},
                             "metric": {"name": "accuracy", "direction": "maximize"}},
                    "snapshot": {"resources": [{"id": "data", "version": 1,
                                                "content_sha256": "sha"}]}}

    class Working:
        store = Store()

        def detail(self, project, run):
            return {"title": run, "purpose": run, "state": "COMPLETED",
                    "mode": "training_research", "account": None, "variant": None,
                    "result_metric": {"name": "accuracy", "direction": "maximize",
                                      "final_value": 0.8 if run == "a" else 0.9}}

    monkeypatch.setattr(compare, "tracking_uri", lambda: "sqlite:///temporary.db")

    def fail(*args):
        raise ConnectionError("offline")

    monkeypatch.setattr(compare, "sync_comparison", fail)
    result = compare_runs(Working(), "project", ["a", "b"])
    assert result["tracking_backend"] == "workbench"
    assert "ConnectionError" in result["tracking_warning"]
    assert result["ranked_run_ids"] == ["b", "a"]

    client = FakeClient()
    monkeypatch.setattr(
        compare, "sync_comparison",
        lambda project, rows: mlflow_tracking.sync_comparison(project, rows, client=client),
    )
    result = compare_runs(Working(), "project", ["a", "b"])
    assert result["tracking_backend"] == "mlflow"
    assert result["tracking_warning"] is None
    assert result["ranked_run_ids"] == ["b", "a"]
    assert len(client.runs) == 2
