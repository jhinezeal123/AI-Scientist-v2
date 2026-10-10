import importlib
import json
import sqlite3
import subprocess

import pytest

from ai_scientist.workbench.runtime import _agent_gateway_class

PACKAGE = _agent_gateway_class().__module__.rsplit(".", 1)[0]
models = importlib.import_module(PACKAGE + ".models")
ControlStore = importlib.import_module(PACKAGE + ".control_store").ControlStore
AgentStore = importlib.import_module(PACKAGE + ".store").AgentStore
Workspaces = importlib.import_module(PACKAGE + ".workspaces").Workspaces
safe_path = importlib.import_module(PACKAGE + ".workspaces").safe_path


@pytest.fixture
def repository(tmp_path):
    subprocess.run(["git", "init", str(tmp_path)], check=True, capture_output=True)
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "demo.py").write_text("original\n")
    subprocess.run(["git", "-C", str(tmp_path), "add", "src"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(tmp_path), "-c", "user.name=Test", "-c", "user.email=test@localhost", "commit", "-m", "baseline"], check=True, capture_output=True)
    return tmp_path


def rig():
    return models.RigSpec.model_validate(models.templates()[1])


def test_versioned_rig_restart_and_backup(tmp_path):
    path = tmp_path / "control.sqlite"
    store = ControlStore(AgentStore(path))
    store.create("test", rig())
    task = store.queue.enqueue("test", "lead", "request", {"instruction": "hello"})
    reopened = ControlStore(AgentStore(path))
    snapshot = reopened.snapshot("test")
    assert len(snapshot["seats"]) == 4 and snapshot["tasks"][0]["id"] == task["id"]
    assert path.with_name("control.sqlite.before-v2.bak").exists()
    with sqlite3.connect(path) as con:
        assert con.execute("PRAGMA user_version").fetchone()[0] == 2
    with sqlite3.connect(path.with_name("control.sqlite.before-v2.bak")) as con:
        assert con.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def test_restart_fences_active_session_and_explicit_reconcile(tmp_path):
    store = ControlStore(AgentStore(tmp_path / "control.sqlite"))
    store.create("test", rig())
    store.queue.enqueue("test", "lead", "request", {"instruction": "hello"})
    task = store.queue.claim("test", "lead")
    session = store.begin_session(task, "codex")
    store.process_started(session, 123)
    reopened = ControlStore(AgentStore(store.path))
    reopened.recover()
    assert reopened.queue.claim("test", "lead") is None
    assert reopened.snapshot("test")["tasks"][0]["state"] == "UNKNOWN"
    with pytest.raises(ValueError, match="verified stop receipt"):
        reopened.reconcile(session, {}, retry=True)
    reopened.reconcile(session, {"process_exited": True, "tree_stopped": True}, retry=True)
    assert reopened.queue.claim("test", "lead")["id"] == task["id"]


def test_worktrees_separate_edits_checkpoint_and_peer_review(repository):
    workspaces = Workspaces(repository)
    builder, base = workspaces.ensure("test", "builder", "HEAD")
    reviewer, _ = workspaces.ensure("test", "reviewer", base)
    result = models.TaskResult(summary="edit", files=[{"path": "src/demo.py", "content": "changed\n"}])
    workspaces.apply(builder, result, models.PermissionPolicy(file_edits=True))
    checkpoint = workspaces.checkpoint(builder, task_id="test-task")
    assert (repository / "src/demo.py").read_text() == "original\n"
    assert (reviewer / "src/demo.py").read_text() == "original\n"
    workspaces.restore_checkpoint(reviewer, checkpoint)
    assert (reviewer / "src/demo.py").read_text() == "changed\n"
    assert "+changed" in workspaces.review(reviewer, base)["diff"]
    assert len(workspaces.discover()) == 2


@pytest.mark.parametrize("path", ["../credentials.json", "D:/secrets", "src/../x", ".git/config", "profiles/kaggle.json", "src\\x"])
def test_file_scope_rejects_traversal_and_secrets(repository, path):
    with pytest.raises(ValueError):
        safe_path(repository, path)


def test_edits_validate_all_before_writing(repository):
    workspaces = Workspaces(repository)
    result = models.TaskResult(summary="edit", files=[
        {"path": "src/demo.py", "content": "changed"},
        {"path": "outside.py", "content": "bad"},
    ])
    with pytest.raises(ValueError, match="outside"):
        workspaces.apply(repository, result, models.PermissionPolicy(file_edits=True))
    assert (repository / "src/demo.py").read_text() == "original\n"


def test_topology_revision_fences_live_edits(tmp_path):
    store = ControlStore(AgentStore(tmp_path / "control.sqlite"))
    store.create("test", rig())
    changed = rig().model_copy(update={"name": "New name"})
    store.update_spec("test", changed, 1)
    with pytest.raises(ValueError, match="revision"):
        store.update_spec("test", changed, 1)
    store.queue.enqueue("test", "lead", "request", {"instruction": "hello"})
    with pytest.raises(ValueError, match="queued/active"):
        store.update_spec("test", changed, 2)
