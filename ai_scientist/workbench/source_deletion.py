"""Permanently remove one source and its project-owned agent workspace copies."""
import json
import re
import shutil

from .named_paths import checked_child


def checked_directory(project, name):
    if not re.fullmatch(r'(?:library|planning/[0-9a-f]{32}/library|runs/[0-9a-f]{32}/working-agent/library)/[^/\\]+', name):
        raise ValueError('Invalid source deletion path')
    directory = project
    for part in name.split('/'):
        directory = checked_child(directory, part)
    if not directory.resolve().is_relative_to(project.resolve()):
        raise ValueError('Source deletion must stay inside this project')
    return directory


def checked_files(directory):
    for path in directory.rglob('*'):
        if path.is_symlink() or path.is_junction() or not path.resolve().is_relative_to(directory.resolve()):
            raise ValueError('Linked source file refused during deletion')
        if path.is_file():
            yield path


def checked_experiment_directory(roots, run_id, name):
    if run_id not in roots or not re.fullmatch(r'(?:working-agent|query-agent)/library/[^/\\]+', name):
        raise ValueError('Invalid experiment source deletion path')
    directory = roots[run_id]
    for part in name.split('/'):
        directory = checked_child(directory, part)
    return directory


def deletion_plan(library, resource_id, experiment_roots=None):
    original, identity = library._source_folder(resource_id)
    project = library.project_directory
    aliases = set([original.name, *identity['aliases']])
    copies = []
    for kind in ('planning', 'runs'):
        root = checked_child(project, kind)
        if not root.exists():
            continue
        for job in root.iterdir():
            if not re.fullmatch(r'[0-9a-f]{32}', job.name):
                continue
            job = checked_child(root, job.name)
            for alias in aliases:
                relative = f'{kind}/{job.name}/' + ('working-agent/' if kind == 'runs' else '') + f'library/{alias}'
                directory = checked_directory(project, relative)
                if not directory.is_dir():
                    continue
                list(checked_files(directory))
                versions = list(directory.glob('v*/source.md'))
                if not versions or any(f'\nResource: {resource_id}\n' not in file.read_text(encoding='utf-8') for file in versions):
                    raise ValueError('Agent source copy does not match its resource identity')
                copies.append(relative)
    paths = [*dict.fromkeys(copies), original.relative_to(project).as_posix()]
    files = [file for name in paths for file in checked_files(checked_directory(project, name))]
    experiment_paths = []
    for run_id in experiment_roots or {}:
        for workspace in ('working-agent', 'query-agent'):
            for alias in aliases:
                name = f'{workspace}/library/{alias}'
                directory = checked_experiment_directory(experiment_roots, run_id, name)
                if not directory.is_dir():
                    continue
                source_files = list(checked_files(directory))
                versions = list(directory.glob('v*/source.md'))
                if not versions or any(f'\nResource: {resource_id}\n' not in file.read_text(encoding='utf-8') for file in versions):
                    raise ValueError('Experiment source copy identity mismatch')
                files.extend(source_files)
                experiment_paths.append({'run_id': run_id, 'path': name})
    return {'paths':paths, 'experiment_paths':experiment_paths,
            'files':len(files), 'bytes':sum(file.stat().st_size for file in files)}


def remove_source_files(library, resource_id, plan, experiment_roots=None):
    project = library.project_directory
    directories = [checked_directory(project, name) for name in plan['paths']]
    directories.extend(checked_experiment_directory(experiment_roots or {}, item['run_id'], item['path'])
                       for item in plan.get('experiment_paths', []))
    # Check the whole plan before removing the first byte. A partial deletion can be retried.
    for directory in directories:
        if not directory.exists():
            continue
        files = list(checked_files(directory))
        marker = directory/'.resource.json'
        if marker.exists():
            if json.loads(marker.read_text(encoding='utf-8')).get('id') != resource_id:
                raise ValueError('Source deletion path belongs to another resource')
        for file in files:
            if file.name == 'source.md' and f'\nResource: {resource_id}\n' not in file.read_text(encoding='utf-8'):
                raise ValueError('Source deletion identity mismatch')
    for directory in directories:
        if directory.exists():
            shutil.rmtree(directory)
