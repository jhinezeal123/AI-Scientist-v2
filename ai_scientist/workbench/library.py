"""Versioned project source files and copies for an agent's request workspace."""
import hashlib
import json
from pathlib import Path
import re
import shutil
import tempfile

from .named_paths import PATH_LOCK, checked_child, folder_title, rename_folder, unique_title


class LibraryFiles:
    def __init__(self, project_directory, ingestion_lookup=None, source_available=None):
        self.project_directory = Path(project_directory).resolve()
        self.ingestion_lookup = ingestion_lookup
        self.source_available = source_available

    def _folders(self):
        library = checked_child(self.project_directory, 'library')
        if not library.exists():
            return
        for directory in library.iterdir():
            if not directory.is_dir():
                continue
            directory = checked_child(library, directory.name)
            marker = directory / '.resource.json'
            if marker.is_symlink():
                raise ValueError('Linked Library identity refused')
            if marker.is_file():
                identity = json.loads(marker.read_text(encoding='utf-8'))
                if (not isinstance(identity, dict) or not isinstance(identity.get('id'), str)
                        or not re.fullmatch(r'[0-9a-f]{32}', identity['id'])
                        or not isinstance(identity.get('aliases'), list)
                        or any(not isinstance(alias, str) for alias in identity['aliases'])):
                    raise ValueError('Invalid Library folder identity')
                yield directory, identity

    def _source_folder(self, resource_id):
        if not isinstance(resource_id, str) or not re.fullmatch(r'[0-9a-f]{32}', resource_id):
            raise ValueError('Invalid Library resource identity')
        found = [(directory, identity) for directory, identity in self._folders() if identity['id'] == resource_id]
        if len(found) > 1:
            raise ValueError('Duplicate Library folder identity')
        if found:
            return found[0]
        legacy = checked_child(checked_child(self.project_directory, 'library'), resource_id)
        if legacy.is_dir():
            if (legacy / '.resource.json').exists():
                raise ValueError('Library folder belongs to another resource')
            return legacy, {'id':resource_id, 'aliases':[resource_id]}
        raise FileNotFoundError('Source folder not found in this project')

    def register(self, source):
        """Name the current source folder; keep old names resolvable for pinned snapshots."""
        resource_id = source['id']
        if not re.fullmatch(r'[0-9a-f]{32}', resource_id):
            raise ValueError('Invalid Library resource identity')
        with PATH_LOCK:
            library = checked_child(self.project_directory, 'library')
            library.mkdir(exist_ok=True)
            try:
                old, identity = self._source_folder(resource_id)
            except FileNotFoundError:
                old, identity = None, {'id':resource_id, 'aliases':[resource_id]}
            occupied = [item.name for item in library.iterdir() if item != old]
            occupied.extend(alias for _, item in self._folders() if item['id'] != resource_id for alias in item['aliases'])
            title = unique_title(folder_title(source['title']), occupied)
            destination = checked_child(library, title)
            identity['aliases'] = sorted(set([*identity['aliases'], title, *([old.name] if old else [])]))
            # Persist identity before moving: an interrupted rename can be resumed at startup.
            directory = old or destination
            directory.mkdir(exist_ok=True)
            marker = directory / '.resource.json'
            temporary = directory / '.resource.json.tmp'
            if marker.is_symlink() or temporary.is_symlink():
                raise ValueError('Linked Library identity refused')
            temporary.write_text(json.dumps(identity, ensure_ascii=False), encoding='utf-8')
            temporary.replace(marker)
            if old is not None and old.name != title:
                rename_folder(old, destination)
            return title

    def path(self, name):
        match = re.fullmatch(r'library/([^/\\]+)/v([1-9][0-9]*)/(source\.md|ingestion\.json|text\.md|original(?:\.[a-z0-9]{1,16})?|pages/page-[0-9]{4}\.md)', name)
        if not match:
            raise ValueError('Invalid Library file path')
        library = checked_child(self.project_directory, 'library')
        directory = checked_child(library, match[1])
        if not directory.exists():
            aliases = [folder for folder, identity in self._folders() if match[1] in identity['aliases']]
            if len(aliases) > 1:
                raise ValueError('Ambiguous Library folder alias')
            if aliases:
                directory = aliases[0]
        path = directory / f'v{match[2]}' / match[3]
        if not path.resolve().is_relative_to(self.project_directory) or any(
                parent.is_symlink() or parent.is_junction() for parent in (path, *path.parents) if parent.is_relative_to(self.project_directory)):
            raise ValueError('Linked Library path refused')
        return path

    def source_name(self, resource_id, version):
        if type(version) is not int or version < 1:
            raise ValueError('Invalid Library source version')
        directory, _ = self._source_folder(resource_id)
        return f'library/{directory.name}/v{version}/source.md'

    def source_path(self, resource_id, version):
        return self.path(self.source_name(resource_id, version))

    @staticmethod
    def document(source):
        return (f"# {source['title']}\n\n"
                f"Resource: {source['id']}\nVersion: {source['version']}\n"
                f"Kind: {source['kind']}\nStatus: {source['status']}\n"
                f"URL: {source.get('url') or '(none)'}\n\n"
                f"{source['content'] or 'Reference only. The URL has not been fetched.'}\n").encode('utf-8')

    def reference(self, source, *, saving=False):
        if not saving and self.source_available and not self.source_available(source['id']):
            raise FileNotFoundError('Nguồn đã bị xóa; nhập nguồn và lập proposal mới trước khi chạy lại')
        try:
            self._source_folder(source['id'])
        except FileNotFoundError:
            if 'content' not in source:
                raise
            self.register(source)
        name = self.source_name(source['id'], source['version'])
        path = self.path(name)
        if 'content' in source:
            data = self.document(source)
            self._write_version_file(path, data)
        else:
            directory, identity = self._source_folder(source['id'])
            accepted = {f"library/{alias}/v{source['version']}/source.md" for alias in (*identity['aliases'], directory.name)}
            if source.get('file_path') not in accepted:
                raise ValueError('Library reference does not match its resource/version')
            data = path.read_bytes()
            if hashlib.sha256(data).hexdigest() != source.get('file_sha256'):
                raise ValueError('Pinned Library file hash mismatch')
        result = {key: value for key, value in source.items() if key not in {'content','_ingestion','attachment'}} | {
            'file_path': name, 'file_sha256': hashlib.sha256(data).hexdigest(), 'file_bytes': len(data)}
        from .resources import source_urls
        result['urls'] = source_urls({'url':source.get('url'), 'content':data.decode('utf-8')})
        metadata = self._metadata(source)
        if metadata:
            prefix = name.rsplit('/', 1)[0] + '/'
            manifest = self.path(prefix + 'ingestion.json').read_bytes()
            attachment = {'filename':metadata['filename'], 'original_file_path':prefix + metadata['original']['path'],
                          'original_sha256':metadata['original']['sha256'], 'original_bytes':metadata['original']['bytes'],
                          'manifest_file_path':prefix + 'ingestion.json', 'manifest_sha256':hashlib.sha256(manifest).hexdigest(),
                          'page_count':metadata['page_count'], 'processed_pages':len(metadata['pages']),
                          'text_pages':metadata['text_pages'], 'issues':metadata['issues']}
            if source.get('attachment') and source['attachment'].get('manifest_sha256') != attachment['manifest_sha256']:
                raise ValueError('Pinned ingestion manifest hash mismatch')
            result['attachment'] = attachment
        return result

    def _metadata(self, source):
        metadata = source.get('_ingestion')
        if metadata is None and self.ingestion_lookup:
            metadata = self.ingestion_lookup(source['id'], source['version'])
        if metadata:
            name = self.source_name(source['id'], source['version']).rsplit('/', 1)[0] + '/ingestion.json'
            expected = json.dumps(metadata, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')
            if self.path(name).read_bytes() != expected:
                raise ValueError('Ingestion manifest differs from saved provenance')
        return metadata

    def write_import(self, resource_id, version, files):
        prefix = self.source_name(resource_id, version).rsplit('/', 1)[0] + '/'
        destination = self.path(prefix + 'source.md').parent
        if destination.exists():
            raise ValueError('Imported source version already exists; restore the saved version')
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = Path(tempfile.mkdtemp(prefix=f'.v{version}-import-', dir=destination.parent))
        try:
            for name, data in files.items():
                self.path(prefix + name)  # Validate every imported relative path before publishing it.
                self._write_version_file(temporary / name, data)
            temporary.rename(destination)
        finally:
            if temporary.exists():
                self.discard_import(temporary)
        return destination

    def discard_import(self, directory):
        directory = Path(directory)
        library = self.project_directory / 'library'
        if (directory.parent.parent != library
                or not re.fullmatch(r'v[1-9][0-9]*|\.v[1-9][0-9]*-import-[a-z0-9_]+', directory.name)
                or not directory.resolve().is_relative_to(library) or directory.resolve() == library or any(
                parent.is_symlink() or parent.is_junction() for parent in (directory, *directory.parents)
                if parent.is_relative_to(self.project_directory))):
            raise ValueError('Unsafe import cleanup path')
        shutil.rmtree(directory)

    @staticmethod
    def _write_version_file(path, data):
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            try:
                with path.open('xb') as stream:
                    stream.write(data)
            except FileExistsError:
                pass
        if path.read_bytes() != data:
            raise ValueError('Library file changed; save a new source version through the app')

    def selected_files(self, snapshot):
        for source in snapshot['resources']:
            ref = self.reference(source)
            yield ref['file_path'], self.path(ref['file_path']).read_bytes()
            metadata = self._metadata(source)
            if metadata:
                prefix = ref['file_path'].rsplit('/', 1)[0] + '/'
                yield prefix + 'ingestion.json', self.path(prefix + 'ingestion.json').read_bytes()
                for file in [metadata['original'], *metadata['pages'], *([metadata['text']] if metadata.get('text') else [])]:
                    name = prefix + file['path']
                    data = self.path(name).read_bytes()
                    if len(data) != file['bytes'] or hashlib.sha256(data).hexdigest() != file['sha256']:
                        raise ValueError('Imported Library file hash mismatch')
                    yield name, data

    def stage(self, snapshot, workspace):
        workspace = Path(workspace).resolve()
        for name, data in self.selected_files(snapshot):
            target = workspace / name
            if not target.resolve().is_relative_to(workspace) or any(
                    parent.is_symlink() or parent.is_junction() for parent in (target, *target.parents) if parent.is_relative_to(workspace)):
                raise ValueError('Linked agent Library path refused')
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)

    def agent_snapshot(self, snapshot):
        return {**snapshot, 'resources': [self.reference(source) for source in snapshot['resources']]}
