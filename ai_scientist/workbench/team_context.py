"""Stage reviewed team code as untrusted, approval-bound Working reference material."""
import hashlib
import json
from pathlib import PurePosixPath


def checksum(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def stage_team_context(root,workdir,approved):
    path=root/'team-provenance.json'
    if not path.exists():
        return None
    if path.is_symlink() or path.stat().st_size>1000000:
        raise ValueError('Invalid team provenance file')
    package=json.loads(path.read_text(encoding='utf-8'))
    manifest=package['manifest']
    if package['sha256']!=checksum(manifest) or manifest['version']!=1:
        raise ValueError('Team provenance integrity check failed')
    binding=manifest['binding']
    scope=checksum({'body':approved['body'],'snapshot':approved['snapshot']})
    if binding['context_sha256']!=approved['context_sha256'] or binding['scope_sha256']!=scope or binding['budget']!=(approved['body'].get('budget') or {}):
        raise ValueError('Team reference is outside the approved research scope')
    references=[]
    for file in manifest['files']:
        name=file['path']
        relative=PurePosixPath(name)
        if relative.as_posix()!=name or relative.is_absolute() or '\\' in name or ':' in name or any(p in {'..','profiles','secrets'} or p.startswith('.') for p in relative.parts):
            raise ValueError('Invalid reviewed code reference path')
        content=file['content'].encode('utf-8')
        if len(content)>1000000:
            raise ValueError('Reviewed code reference is too large')
        target=workdir/'team-source'/relative
        if not target.resolve().is_relative_to(workdir.resolve()) or any(p.is_symlink() or getattr(p,'is_junction',lambda:False)() for p in (target,*target.parents) if p.is_relative_to(workdir)):
            raise ValueError('Linked reviewed code reference refused')
        target.parent.mkdir(parents=True,exist_ok=True)
        target.write_bytes(content)
        references.append({'path':'team-source/'+name,'sha256':hashlib.sha256(content).hexdigest()})
    return {'rig_id':manifest['rig_id'],'request_id':binding['request_id'],'checkpoint':binding['checkpoint'],
        'task_ids':manifest['task_ids'],'files':references,'provenance_sha256':package['sha256']}
