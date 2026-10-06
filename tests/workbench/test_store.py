from copy import deepcopy
import json

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from ai_scientist.workbench.api import library_router
from ai_scientist.workbench.store import ProjectStore, StoreConflict


def source(content="original"):
    return {"kind": "url", "title": "Source", "url": "https://example.com/data", "content": content}


def test_persistence_isolation_and_resource_version(tmp_path):
    store = ProjectStore(tmp_path / "projects")
    a, b = store.create_project("A"), store.create_project("B")
    resource = store.save_resource(a["id"], source())
    idea = store.save_idea(a["id"], "Baseline idea")
    snapshot = store.context_snapshot(a["id"], idea["id"], [resource["id"]])
    untouched = deepcopy(snapshot)
    proposal_id = store.save_proposal(a["id"], idea["id"], {"objective": "baseline"}, snapshot)
    updated = store.save_resource(a["id"], source("updated"), resource["id"], 1)
    assert updated["version"] == 2 and updated["content_sha256"] != resource["content_sha256"]
    assert snapshot == untouched
    restarted = ProjectStore(tmp_path / "projects")
    assert restarted.resources(a["id"])[0] == updated
    assert restarted.ideas(a["id"])[0]["text"] == "Baseline idea"
    assert restarted.resources(b["id"]) == []
    assert restarted.ideas(b["id"]) == []
    with restarted.connection(a["id"]) as connection:
        record = connection.execute("SELECT * FROM proposals WHERE id=?", (proposal_id,)).fetchone()
        assert json.loads(record["context_snapshot_json"]) == untouched["snapshot"]
        assert record["state"] == "STALE"
        assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert connection.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    with pytest.raises(KeyError):
        restarted.context_snapshot(b["id"], idea["id"], [resource["id"]])
    with pytest.raises(KeyError):
        restarted.save_resource(b["id"], source("wrong project"), resource["id"], 2)
    with pytest.raises(StoreConflict):
        restarted.save_resource(a["id"], source("stale edit"), resource["id"], 1)


def test_reference_only_and_bounded_context(tmp_path):
    store = ProjectStore(tmp_path)
    project = store.create_project("A")["id"]
    ref = store.save_resource(project, source(""))
    assert ref["status"] == "reference_only"
    idea = store.save_idea(project, "idea")
    r1 = store.save_resource(project, source("a" * 60000))
    r2 = store.save_resource(project, source("b" * 60000))
    with pytest.raises(ValueError, match="100 KB"):
        store.context_snapshot(project, idea["id"], [r1["id"], r2["id"]])
    with pytest.raises(ValueError, match="distinct"):
        store.context_snapshot(project, idea["id"], [ref["id"], ref["id"]])
    with pytest.raises(KeyError):
        store.resources("../escape")


def test_library_api_status_and_readiness_import(tmp_path):
    store = ProjectStore(tmp_path / "projects")
    app = FastAPI()
    app.include_router(library_router(store, tmp_path))
    with TestClient(app) as client:
        project = client.post("/api/projects", json={"name": "Soil"}).json()["id"]
        base = f"/api/projects/{project}"
        resource = client.post(base + "/resources", json=source("")).json()
        assert resource["status"] == "reference_only"
        bad_url = source()
        bad_url["url"] = "file:///secret"
        assert client.post(base + "/resources", json=bad_url).status_code == 422
        assert client.put(base + f"/resources/{resource['id']}", json={**source(), "expected_version": 2}).status_code == 409
        assert client.get("/api/projects/" + "f" * 32 + "/resources").status_code == 404
        idea = client.post(base + "/ideas", json={"text": "My idea"}).json()
        response = client.post(base + "/context", json={"idea_id": idea["id"], "resource_ids": [resource["id"]]})
        assert response.status_code == 200
        assert response.json()["snapshot"]["resources"][0]["id"] == resource["id"]
        readiness = tmp_path / ".workbench/readiness"
        readiness.mkdir(parents=True)
        (readiness / "pages.json").write_text(json.dumps({"pages": [{"name": "Evaluation", "content": "Metric reference"}]}))
        assert client.post(base + "/import-readiness").status_code == 200
        assert client.post(base + "/import-readiness").status_code == 200
        assert len(client.get(base + "/resources").json()) == 3
        assert client.get(base + "/history").json() == {"proposals": [], "runs": []}
