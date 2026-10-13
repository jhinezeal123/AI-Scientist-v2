"""Project-owned candidate history, including rejected and unselected ideas."""
import hashlib
import json
import re
import uuid
from datetime import datetime, timezone


def fingerprint(idea):
    text = re.sub(r'\s+', ' ', idea['text']).strip().casefold()
    return hashlib.sha256(text.encode()).hexdigest()


class IdeaArchive:
    def __init__(self, projects):
        self.projects = projects

    @staticmethod
    def setup(con):
        con.execute('''CREATE TABLE IF NOT EXISTS research_idea_archive(
            id TEXT PRIMARY KEY, workflow_id TEXT NOT NULL, iteration INTEGER NOT NULL,
            ordinal INTEGER NOT NULL, body_json TEXT NOT NULL,
            UNIQUE(workflow_id,iteration,ordinal))''')

    def list(self, project, workflow=None, iteration=None):
        with self.projects.connection(project) as con:
            self.setup(con)
            rows = con.execute('''SELECT body_json FROM research_idea_archive
                WHERE (? IS NULL OR workflow_id=?) AND (? IS NULL OR iteration=?) ORDER BY rowid''',
                (workflow, workflow, iteration, iteration)).fetchall()
        return [json.loads(row[0]) for row in rows]

    def reserve(self, project, workflow, iteration, ordinal, prompt):
        with self.projects.connection(project) as con:
            self.setup(con)
            con.execute('BEGIN IMMEDIATE')
            row = con.execute('SELECT body_json FROM research_idea_archive WHERE workflow_id=? AND iteration=? AND ordinal=?',
                              (workflow, iteration, ordinal)).fetchone()
            if row:
                return json.loads(row[0])
            body = {'id': uuid.uuid4().hex, 'workflow_id': workflow, 'iteration': iteration,
                    'ordinal': ordinal, 'status': 'pending', 'input': prompt, 'idea': None,
                    'created_at': datetime.now(timezone.utc).isoformat()}
            con.execute('INSERT INTO research_idea_archive VALUES(?,?,?,?,?)',
                        (body['id'], workflow, iteration, ordinal, json.dumps(body)))
        return body

    def update(self, project, identity, **fields):
        with self.projects.connection(project) as con:
            self.setup(con)
            con.execute('BEGIN IMMEDIATE')
            row = con.execute('SELECT body_json FROM research_idea_archive WHERE id=?', (identity,)).fetchone()
            if row is None:
                raise KeyError('Idea candidate not found')
            body = {**json.loads(row[0]), **fields}
            con.execute('UPDATE research_idea_archive SET body_json=? WHERE id=?', (json.dumps(body), identity))
        folder = self.projects.directory(project) / 'automation' / body['workflow_id'] / 'ideation' / str(body['iteration'])
        from .json_files import write_json
        write_json(folder / 'archive.json', self.list(project, body['workflow_id'], body['iteration']))
        return body

    def context(self, project, exclude=None):
        return [{'id': r['id'], 'title': r['idea']['title'], 'text': r['idea']['text'][:500],
                 'status': r['status'], 'reason': r.get('reason', '')[:200]}
                for r in self.list(project) if r['idea'] and r['id'] != exclude][-40:]
