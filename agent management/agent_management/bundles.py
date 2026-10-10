"""Portable rig manifests with integrity checks; credentials/commands are never exported."""
from __future__ import annotations

import hashlib
import json

from .models import RigSpec


def canonical(value):
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'))


def checksum(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def export_bundle(control, rig_id):
    team=control.store.snapshot(rig_id)
    spec={**team['spec'],'base_ref':control.workspaces.revision(team['spec']['base_ref'])}
    for seat in spec['seats']:
        control.context.pack(RigSpec.model_validate(spec),seat['id'])
    from .resources import resource_limits
    payload={'format':'ai-scientist-team','version':1,'spec':spec,
        'resources':[r.model_dump() for r in resource_limits(control.store,rig_id)],
        'harnesses':[{'id':s.id,'kind':s.kind,'models':s.models} for s in control.store.harnesses() if s.id in {seat['harness'] for seat in spec['seats']}]}
    return {'payload':payload,'sha256':checksum(payload)}


def import_bundle(control, rig_id, bundle):
    if set(bundle)!={'payload','sha256'} or checksum(bundle['payload'])!=bundle['sha256']:
        raise ValueError('Bundle checksum mismatch')
    payload=bundle['payload']
    if not {'format','version','spec','harnesses'}<=set(payload) or set(payload)-{'format','version','spec','harnesses','resources'} or payload['format']!='ai-scientist-team' or payload['version']!=1:
        raise ValueError('Unsupported team bundle version')
    if len(canonical(payload).encode())>1000000:
        raise ValueError('Bundle exceeds 1MB')
    spec=RigSpec.model_validate(payload['spec'])
    from .resources import CodingResource, configure_resource
    resources=[CodingResource.model_validate(r) for r in payload.get('resources',[])]
    for resource in resources:
        if set(resource.seat_ids)-{s.id for s in spec.seats}:
            raise ValueError('Bundle resource references an unknown seat')
    for seat in spec.seats:
        existing=next((s for s in control.store.harnesses() if s.id==seat.harness),None)
        wanted=next((s for s in payload['harnesses'] if s['id']==seat.harness),None)
        if existing is None or wanted is None or existing.kind!=wanted['kind']:
            raise ValueError('Configure the bundle harness locally before importing')
        control.context.pack(spec,seat.id)
    # Import never executes a saved command, installs a harness or starts a team.
    result=control.create(rig_id,spec)
    for resource in resources:
        configure_resource(control.store,rig_id,resource)
    control.store.publish('bundle_imported',{'sha256':bundle['sha256']},rig_id=rig_id)
    return result
