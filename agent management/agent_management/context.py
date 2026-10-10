"""Versioned, hashed context references; no implicit cross-project or secret copies."""
from __future__ import annotations

import hashlib
from pathlib import Path

from .models import ContextSource, RigSpec
from .workspaces import safe_path


class ContextRouter:
    def __init__(self, repository: Path, workspaces):
        self.repository = repository
        self.workspaces = workspaces
        self.projects = None

    def library_reference(self, rig, identifier, resource_id, seats):
        if not rig.project_id or self.projects is None:
            raise ValueError('Library context requires a bound project')
        resource = next((r for r in self.projects.resources(rig.project_id) if r['id']==resource_id), None)
        if resource is None or resource.get('deletion_pending'):
            raise ValueError('Library source is unavailable in this project')
        return ContextSource(id=identifier, kind='library', path=resource_id,
            sha256=resource['content_sha256'], seats=seats, version=resource['version'])

    def register(self, identifier, kind, path, seats, version=1):
        file = safe_path(self.repository, path, allow_missing=False)
        # Context is explicit AND tracked; ignored profiles cannot enter a context pack.
        tracked = self.workspaces.git(self.repository, "ls-files", "--", path)
        if tracked != path:
            raise ValueError("Only tracked project sources can be registered as context")
        if file.stat().st_size > 200_000:
            raise ValueError("Context source exceeds 200KB")
        body = file.read_bytes()
        body.decode("utf-8")
        return ContextSource(id=identifier, kind=kind, path=path,
                             sha256=hashlib.sha256(body).hexdigest(), seats=seats, version=version)

    def pack(self, rig: RigSpec, seat_id):
        chunks = []
        for source in rig.context:
            if source.seats and seat_id not in source.seats:
                continue
            if source.kind == 'library':
                pinned = self.library_reference(rig, source.id, source.path, source.seats)
                if (pinned.sha256,pinned.version) != (source.sha256,source.version):
                    raise ValueError('Library source version changed; explicitly update the context reference')
                resource = next(r for r in self.projects.resources(rig.project_id) if r['id']==source.path)
                files = list(self.projects.library(rig.project_id).selected_files({'resources':[resource]}))
                body = files[0][1]
            else:
                if self.workspaces.git(self.repository, 'ls-files', '--', source.path) != source.path:
                    raise ValueError('Context source is no longer tracked in this repository')
                file = safe_path(self.repository, source.path, allow_missing=False)
                body = file.read_bytes()
            if len(body) > 200_000 or (source.kind != 'library' and hashlib.sha256(body).hexdigest() != source.sha256):
                raise ValueError("Context source changed; update its version and hash explicitly")
            chunks.append({"id": source.id, "kind": source.kind, "version": source.version,
                           "sha256": source.sha256, "content": body.decode("utf-8")})
        if sum(len(x["content"].encode()) for x in chunks) > 500_000:
            raise ValueError("Combined context exceeds 500KB")
        return chunks
