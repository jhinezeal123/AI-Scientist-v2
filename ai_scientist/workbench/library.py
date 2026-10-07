"""Versioned project source files and copies for an agent's request workspace."""
import hashlib
from pathlib import Path
import re


class LibraryFiles:
    def __init__(self, project_directory):
        self.project_directory = Path(project_directory).resolve()

    def path(self, name):
        if not re.fullmatch(r'library/[0-9a-f]{32}/v[1-9][0-9]*/source\.md', name):
            raise ValueError('Invalid Library file path')
        path = self.project_directory / name
        if not path.resolve().is_relative_to(self.project_directory) or any(
                parent.is_symlink() for parent in (path, *path.parents) if parent.is_relative_to(self.project_directory)):
            raise ValueError('Linked Library path refused')
        return path

    @staticmethod
    def document(source):
        return (f"# {source['title']}\n\n"
                f"Resource: {source['id']}\nVersion: {source['version']}\n"
                f"Kind: {source['kind']}\nStatus: {source['status']}\n"
                f"URL: {source.get('url') or '(none)'}\n\n"
                f"{source['content'] or 'Reference only. The URL has not been fetched.'}\n").encode('utf-8')

    def reference(self, source):
        name = f"library/{source['id']}/v{source['version']}/source.md"
        path = self.path(name)
        if 'content' in source:
            data = self.document(source)
            path.parent.mkdir(parents=True, exist_ok=True)
            if not path.exists():
                try:
                    with path.open('xb') as stream:
                        stream.write(data)
                except FileExistsError:
                    pass
            if path.read_bytes() != data:
                raise ValueError('Library file changed; save a new source version through the app')
        else:
            if source.get('file_path') != name:
                raise ValueError('Library reference does not match its resource/version')
            data = path.read_bytes()
            if hashlib.sha256(data).hexdigest() != source.get('file_sha256'):
                raise ValueError('Pinned Library file hash mismatch')
        return {key: value for key, value in source.items() if key != 'content'} | {
            'file_path': name, 'file_sha256': hashlib.sha256(data).hexdigest(), 'file_bytes': len(data)}

    def selected_files(self, snapshot):
        for source in snapshot['resources']:
            ref = self.reference(source)
            yield ref['file_path'], self.path(ref['file_path']).read_bytes()

    def stage(self, snapshot, workspace):
        workspace = Path(workspace).resolve()
        for name, data in self.selected_files(snapshot):
            target = workspace / name
            if not target.resolve().is_relative_to(workspace) or any(
                    parent.is_symlink() for parent in (target, *target.parents) if parent.is_relative_to(workspace)):
                raise ValueError('Linked agent Library path refused')
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)

    def agent_snapshot(self, snapshot):
        return {**snapshot, 'resources': [self.reference(source) for source in snapshot['resources']]}
