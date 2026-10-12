"""Retain personal-device grants when replacing team identities with projects."""
import json
import sqlite3


def migrate_remote_scopes(projects, control):
    known = {p['id'] for p in projects.list_projects()}
    mapping = {'project-'+p: p for p in known}
    with control.connect() as con:
        for row in con.execute('SELECT id,spec_json FROM rigs'):
            project = json.loads(row['spec_json']).get('project_id')
            if project in known:
                mapping[row['id']] = project
    for project in known:
        path = projects.directory(project)/'agents/agent-management.sqlite'
        if not path.exists():
            continue
        if path.is_symlink() or path.parent.is_symlink() or getattr(path.parent, 'is_junction', lambda: False)():
            raise ValueError('Refusing redirected legacy agent database')
        with sqlite3.connect(path.as_uri()+'?mode=ro', uri=True) as con:
            for identity, raw in con.execute('SELECT id,spec_json FROM rigs'):
                if json.loads(raw).get('project_id') == project:
                    mapping[identity] = project
    with control.connect(True) as con:
        for row in con.execute('SELECT id,rig_ids_json FROM devices WHERE revoked=0').fetchall():
            old = json.loads(row['rig_ids_json'])
            new = list(dict.fromkeys(mapping.get(identity, identity) for identity in old))
            if new != old:
                con.execute('UPDATE devices SET rig_ids_json=? WHERE id=?', (json.dumps(new), row['id']))
                control.event(con, 'device_scope_migrated_to_project', {'device_id': row['id'], 'projects': new})
