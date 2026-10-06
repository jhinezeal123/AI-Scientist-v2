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


    def idea(self, project_id, idea_id):
        item = next((item for item in self.ideas(project_id) if item["id"] == idea_id), None)
        if item is None:
            raise KeyError("Idea not found in this project")
        return item


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


    def history(self, project_id):
        with self.connection(project_id) as connection:
            return {"proposals": [dict(row) for row in connection.execute(
                "SELECT id,idea_id,version,state,context_sha256,approved_at FROM proposals ORDER BY rowid DESC")],
                "runs": [dict(row) for row in connection.execute(
                "SELECT id,proposal_id,node_id,state,artifact_dir,error,report_path FROM runs ORDER BY rowid DESC")]}
