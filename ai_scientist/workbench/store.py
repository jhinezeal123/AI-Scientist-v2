"""Project-scoped SQLite authority. Every operation owns a short connection."""
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import uuid


SCHEMA = """
CREATE TABLE IF NOT EXISTS project_meta(id TEXT PRIMARY KEY, name TEXT NOT NULL, created_at TEXT NOT NULL, schema_version INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS resources(id TEXT PRIMARY KEY, kind TEXT NOT NULL, title TEXT NOT NULL, url TEXT, content TEXT NOT NULL, status TEXT NOT NULL, version INTEGER NOT NULL, content_sha256 TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS ideas(id TEXT PRIMARY KEY, text TEXT NOT NULL, conversation_json TEXT NOT NULL, state TEXT NOT NULL, error TEXT, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS proposals(id TEXT PRIMARY KEY, idea_id TEXT NOT NULL REFERENCES ideas(id), version INTEGER NOT NULL, body_json TEXT NOT NULL, context_snapshot_json TEXT NOT NULL, context_sha256 TEXT NOT NULL, state TEXT NOT NULL, approved_at TEXT);
CREATE TABLE IF NOT EXISTS runs(id TEXT PRIMARY KEY, proposal_id TEXT NOT NULL REFERENCES proposals(id), node_id TEXT, node_json TEXT, state TEXT NOT NULL, intent_key TEXT UNIQUE NOT NULL, code_sha256 TEXT, identity_json TEXT, artifact_dir TEXT NOT NULL, error TEXT, report_path TEXT);
CREATE TABLE IF NOT EXISTS logs(run_id TEXT NOT NULL REFERENCES runs(id), generation INTEGER NOT NULL, seq INTEGER NOT NULL, text TEXT NOT NULL, stream TEXT NOT NULL, UNIQUE(run_id,generation,seq));
"""

IMPLEMENTATION_SCHEMA = """
CREATE TABLE IF NOT EXISTS implementation_attempts(
run_id TEXT NOT NULL REFERENCES runs(id), attempt INTEGER NOT NULL,
request_id TEXT NOT NULL UNIQUE, state TEXT NOT NULL, node_json TEXT,
session_id TEXT, checks_json TEXT, error TEXT, PRIMARY KEY(run_id,attempt));
"""


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class StoreConflict(ValueError):
    pass


class ProjectStore:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        for project in self.list_projects():
            with self.connection(project['id']) as connection:
                connection.executescript(IMPLEMENTATION_SCHEMA)

    def _path(self, project_id):
        if not re.fullmatch(r"[0-9a-f]{32}", project_id):
            raise KeyError("Project not found")
        directory = self.root / project_id
        if directory.is_symlink() or not directory.resolve().is_relative_to(self.root):
            raise KeyError("Project not found")
        database = directory / "project.sqlite"
        if database.is_symlink():
            raise KeyError("Project not found")
        return database

    @contextmanager
    def connection(self, project_id):
        path = self._path(project_id)
        if not path.is_file():
            raise KeyError("Project not found")
        connection = sqlite3.connect(path, timeout=5)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=5000")
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def create_project(self, name):
        project_id = uuid.uuid4().hex
        database = self._path(project_id)
        database.parent.mkdir()
        connection = sqlite3.connect(database)
        try:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.executescript(SCHEMA)
            connection.executescript(IMPLEMENTATION_SCHEMA)
            connection.execute("INSERT INTO project_meta VALUES(?,?,?,1)",
                               (project_id, name.strip(), datetime.now(timezone.utc).isoformat()))
            connection.commit()
        finally:
            connection.close()
        return self.project(project_id)

    def project(self, project_id):
        with self.connection(project_id) as connection:
            row = connection.execute("SELECT * FROM project_meta WHERE id=?", (project_id,)).fetchone()
            if row is None:
                raise KeyError("Project not found")
            return dict(row)

    def list_projects(self):
        projects = []
        for directory in self.root.iterdir():
            if re.fullmatch(r"[0-9a-f]{32}", directory.name) and (directory / "project.sqlite").is_file():
                projects.append(self.project(directory.name))
        return sorted(projects, key=lambda project: project["created_at"], reverse=True)

    def resources(self, project_id):
        with self.connection(project_id) as connection:
            return [dict(row) for row in connection.execute("SELECT * FROM resources ORDER BY rowid")]

    def save_resource(self, project_id, body, resource_id=None, expected_version=None):
        title, content = body["title"].strip(), body["content"]
        url = body.get("url") or None
        status = "provided_text" if content.strip() else "reference_only"
        if not title or (not content.strip() and not url):
            raise ValueError("A title and text or URL are required")
        with self.connection(project_id) as connection:
            if resource_id is None:
                resource_id, version = uuid.uuid4().hex, 1
            else:
                existing = connection.execute("SELECT version FROM resources WHERE id=?", (resource_id,)).fetchone()
                if existing is None:
                    raise KeyError("Resource not found in this project")
                if existing["version"] != expected_version:
                    raise StoreConflict("Resource changed; reload before saving")
                version = existing["version"] + 1
            row = {"id": resource_id, "kind": body["kind"], "title": title, "url": url,
                   "content": content, "status": status, "version": version,
                   "content_sha256": digest(canonical({"kind": body["kind"], "title": title,
                                                       "url": url, "content": content, "status": status}))}
            connection.execute("INSERT INTO resources VALUES(:id,:kind,:title,:url,:content,:status,:version,:content_sha256) "
                               "ON CONFLICT(id) DO UPDATE SET kind=excluded.kind,title=excluded.title,url=excluded.url,content=excluded.content,status=excluded.status,version=excluded.version,content_sha256=excluded.content_sha256", row)
            connection.execute("UPDATE proposals SET state='STALE' WHERE state IN ('AWAITING_APPROVAL','NEEDS_CLARIFICATION')")
            return row

    def ideas(self, project_id):
        with self.connection(project_id) as connection:
            result = []
            for row in connection.execute("SELECT * FROM ideas ORDER BY rowid DESC"):
                item = dict(row)
                item["conversation"] = json.loads(item.pop("conversation_json"))
                result.append(item)
            return result

    def save_idea(self, project_id, text):
        if not text.strip():
            raise ValueError("Idea must contain text")
        idea_id = uuid.uuid4().hex
        with self.connection(project_id) as connection:
            connection.execute("INSERT INTO ideas VALUES(?,?,?,'DRAFT',NULL,?)",
                               (idea_id, text, "[]", datetime.now(timezone.utc).isoformat()))
        return next(item for item in self.ideas(project_id) if item["id"] == idea_id)

    def context_snapshot(self, project_id, idea_id, resource_ids):
        if not resource_ids or len(resource_ids) != len(set(resource_ids)):
            raise ValueError("Select at least one distinct source")
        with self.connection(project_id) as connection:
            idea = connection.execute("SELECT id,text,conversation_json FROM ideas WHERE id=?", (idea_id,)).fetchone()
            if idea is None:
                raise KeyError("Idea not found in this project")
            resources = []
            for resource_id in resource_ids:
                row = connection.execute("SELECT * FROM resources WHERE id=?", (resource_id,)).fetchone()
                if row is None:
                    raise KeyError("Source not found in this project")
                resources.append(dict(row))
            context = {"project_id": project_id, "idea": {"id": idea["id"], "text": idea["text"],
                        "conversation": json.loads(idea["conversation_json"])},
                       "resources": sorted(resources, key=lambda item: item["id"])}
            serialized = canonical(context)
            if len(serialized.encode("utf-8")) > 100_000:
                raise ValueError("Selected context exceeds 100 KB; select fewer or shorter sources")
            return {"snapshot": context, "context_sha256": digest(serialized)}

    def save_proposal(self, project_id, idea_id, body, context):
        snapshot = context["snapshot"]
        if snapshot["project_id"] != project_id or snapshot["idea"]["id"] != idea_id:
            raise ValueError("Context does not belong to this project/idea")
        serialized = canonical(snapshot)
        if digest(serialized) != context["context_sha256"]:
            raise ValueError("Context hash mismatch")
        proposal_id = uuid.uuid4().hex
        with self.connection(project_id) as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._check_context(connection, snapshot)
            version = connection.execute("SELECT COALESCE(MAX(version),0)+1 FROM proposals WHERE idea_id=?",
                                         (idea_id,)).fetchone()[0]
            state = "NEEDS_CLARIFICATION" if body.get("needs_clarification") else "AWAITING_APPROVAL"
            connection.execute("UPDATE proposals SET state='STALE' WHERE idea_id=? AND state IN ('AWAITING_APPROVAL','NEEDS_CLARIFICATION')", (idea_id,))
            connection.execute("INSERT INTO proposals VALUES(?,?,?,?,?,?,?,NULL)",
                               (proposal_id, idea_id, version, canonical(body), serialized, context["context_sha256"], state))
            row = connection.execute("SELECT conversation_json FROM ideas WHERE id=?", (idea_id,)).fetchone()
            conversation = json.loads(row[0])
            conversation.append({"role": "assistant", "proposal_id": proposal_id, "version": version, "body": body})
            connection.execute("UPDATE ideas SET state=?,error=NULL,conversation_json=? WHERE id=?",
                               (state, canonical(conversation), idea_id))
        return proposal_id

    @staticmethod
    def _check_context(connection, snapshot):
        idea = connection.execute("SELECT text,conversation_json FROM ideas WHERE id=?", (snapshot["idea"]["id"],)).fetchone()
        # Assistant proposal messages do not change the human request context.
        human = lambda messages: [message for message in messages if message.get("role") == "user"]
        if idea is None or idea["text"] != snapshot["idea"]["text"] or human(json.loads(idea["conversation_json"])) != human(snapshot["idea"]["conversation"]):
            raise StoreConflict("Idea or answers changed; create a new proposal")
        for source in snapshot["resources"]:
            current = connection.execute("SELECT version,content_sha256 FROM resources WHERE id=?", (source["id"],)).fetchone()
            if current is None or current["version"] != source["version"] or current["content_sha256"] != source["content_sha256"]:
                raise StoreConflict("Source changed; create a new proposal")

    def idea(self, project_id, idea_id):
        item = next((item for item in self.ideas(project_id) if item["id"] == idea_id), None)
        if item is None:
            raise KeyError("Idea not found in this project")
        return item

    def reserve_plan(self, project_id, idea_id):
        with self.connection(project_id) as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT state FROM ideas WHERE id=?", (idea_id,)).fetchone()
            if row is None:
                raise KeyError("Idea not found in this project")
            if row["state"] in {"PLANNING", "APPROVED"}:
                raise StoreConflict("Idea is planning or already approved; create a new idea for changed scope")
            connection.execute("UPDATE ideas SET state='PLANNING',error=NULL WHERE id=?", (idea_id,))

    def plan_failed(self, project_id, idea_id, error):
        with self.connection(project_id) as connection:
            connection.execute("UPDATE ideas SET state='FAILED',error=? WHERE id=? AND state='PLANNING'", (error[:1000], idea_id))

    def recover_planning(self):
        for project in self.list_projects():
            with self.connection(project["id"]) as connection:
                connection.execute("UPDATE ideas SET state='FAILED',error='Planning interrupted by restart; retry explicitly' WHERE state='PLANNING'")

    def answer(self, project_id, idea_id, proposal_id, version, text):
        if not text.strip():
            raise ValueError("Answer must contain text")
        with self.connection(project_id) as connection:
            connection.execute("BEGIN IMMEDIATE")
            proposal = connection.execute("SELECT * FROM proposals WHERE id=? AND idea_id=?", (proposal_id, idea_id)).fetchone()
            if proposal is None:
                raise KeyError("Proposal not found in this project/idea")
            latest = connection.execute("SELECT MAX(version) FROM proposals WHERE idea_id=?", (idea_id,)).fetchone()[0]
            if proposal["version"] != version or version != latest or proposal["state"] != "NEEDS_CLARIFICATION":
                raise StoreConflict("Clarification is stale or not waiting for an answer")
            idea = connection.execute("SELECT state,conversation_json FROM ideas WHERE id=?", (idea_id,)).fetchone()
            if idea["state"] == "PLANNING":
                raise StoreConflict("Wait for the current planner")
            conversation = json.loads(idea["conversation_json"])
            conversation.append({"role": "user", "text": text, "reply_to": proposal_id})
            connection.execute("UPDATE ideas SET conversation_json=?,state='DRAFT',error=NULL WHERE id=?", (canonical(conversation), idea_id))
            connection.execute("UPDATE proposals SET state='STALE' WHERE idea_id=? AND state IN ('AWAITING_APPROVAL','NEEDS_CLARIFICATION')", (idea_id,))
        return self.idea(project_id, idea_id)

    def update_idea(self, project_id, idea_id, text, expected_text):
        if not text.strip():
            raise ValueError("Idea must contain text")
        with self.connection(project_id) as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT text,state FROM ideas WHERE id=?", (idea_id,)).fetchone()
            if row is None:
                raise KeyError("Idea not found in this project")
            if row["text"] != expected_text or row["state"] in {"PLANNING", "APPROVED"}:
                raise StoreConflict("Idea changed, is planning, or was approved; reload or create a new idea")
            connection.execute("UPDATE ideas SET text=?,conversation_json='[]',state='DRAFT',error=NULL WHERE id=?", (text, idea_id))
            connection.execute("UPDATE proposals SET state='STALE' WHERE idea_id=? AND state IN ('AWAITING_APPROVAL','NEEDS_CLARIFICATION')", (idea_id,))
        return self.idea(project_id, idea_id)

    def proposals(self, project_id, idea_id=None):
        with self.connection(project_id) as connection:
            rows = connection.execute("SELECT * FROM proposals" + (" WHERE idea_id=?" if idea_id else "") + " ORDER BY rowid DESC", (idea_id,) if idea_id else ())
            result = []
            for row in rows:
                item = dict(row)
                item["body"] = json.loads(item.pop("body_json"))
                item["context_snapshot"] = json.loads(item.pop("context_snapshot_json"))
                result.append(item)
            return result

    def approve_proposal(self, project_id, proposal_id, version, context_sha256, idle_unknown_ids=()):
        from .models import ReadyProposal
        with self.connection(project_id) as connection:
            connection.execute("BEGIN IMMEDIATE")
            proposal = connection.execute("SELECT * FROM proposals WHERE id=?", (proposal_id,)).fetchone()
            if proposal is None:
                raise KeyError("Proposal not found in this project")
            if proposal["version"] != version or proposal["context_sha256"] != context_sha256:
                raise StoreConflict("Approval version/hash is stale")
            intent_key = proposal_id + ":" + str(version)
            existing = connection.execute("SELECT * FROM runs WHERE intent_key=?", (intent_key,)).fetchone()
            if existing is not None and proposal["state"] == "APPROVED":
                return dict(existing)
            latest = connection.execute("SELECT MAX(version) FROM proposals WHERE idea_id=?", (proposal["idea_id"],)).fetchone()[0]
            idea_state = connection.execute("SELECT state FROM ideas WHERE id=?", (proposal["idea_id"],)).fetchone()[0]
            if proposal["state"] != "AWAITING_APPROVAL" or latest != version or idea_state == "PLANNING":
                raise StoreConflict("Proposal is not current and awaiting approval")
            self._check_context(connection, json.loads(proposal["context_snapshot_json"]))
            body = ReadyProposal.model_validate_json(proposal["body_json"])
            snapshot = json.loads(proposal["context_snapshot_json"])
            sources = {source["id"]: source for source in snapshot["resources"]}
            if any(ref not in sources or sources[ref]["status"] == "reference_only" for ref in body.data_refs):
                raise StoreConflict("Proposal cites unread or unselected source IDs; clarify before approval")
            candidates = connection.execute("SELECT id,state FROM runs WHERE state NOT IN ('COMPLETED','FAILED','REMOTE_SUCCEEDED','REMOTE_FAILED','COLLECTING')").fetchall()
            blocking = next((row for row in candidates if not (row['state'] == 'UNKNOWN' and row['id'] in idle_unknown_ids)), None)
            if blocking:
                raise StoreConflict(f"Run {blocking['id'][:8]} ({blocking['state']}) đang chặn lượt mới. Run đã kết thúc trên Kaggle không chặn duyệt proposal.")
            run_id = uuid.uuid4().hex
            artifact_dir = "runs/" + run_id
            connection.execute("INSERT INTO runs(id,proposal_id,state,intent_key,artifact_dir) VALUES(?,?,'APPROVED',?,?)",
                               (run_id, proposal_id, intent_key, artifact_dir))
            connection.execute("UPDATE proposals SET state='APPROVED',approved_at=? WHERE id=?", (datetime.now(timezone.utc).isoformat(), proposal_id))
            connection.execute("UPDATE ideas SET state='APPROVED' WHERE id=?", (proposal["idea_id"],))
            return dict(connection.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone())

    def approved_context(self, project_id, run_id):
        # The future coder must use this gate, never a client-supplied proposal body.
        with self.connection(project_id) as connection:
            row = connection.execute("SELECT runs.state,proposals.state AS proposal_state,proposals.body_json,proposals.context_snapshot_json,proposals.context_sha256 FROM runs JOIN proposals ON proposals.id=runs.proposal_id WHERE runs.id=?", (run_id,)).fetchone()
            if row is None:
                raise KeyError("Run not found in this project")
            if row["proposal_state"] != "APPROVED" or row["state"] != "APPROVED":
                raise StoreConflict("Implementation requires an approved run")
            return {"body": json.loads(row["body_json"]), "snapshot": json.loads(row["context_snapshot_json"]), "context_sha256": row["context_sha256"]}

    def history(self, project_id):
        with self.connection(project_id) as connection:
            return {"proposals": [dict(row) for row in connection.execute(
                "SELECT id,idea_id,version,state,context_sha256,approved_at FROM proposals ORDER BY rowid DESC")],
                "runs": [dict(row) for row in connection.execute(
                "SELECT id,proposal_id,node_id,state,artifact_dir,error,report_path FROM runs ORDER BY rowid DESC")]}
