"""Purge only a validated project folder, preserving its database until last."""
import shutil

from .named_paths import checked_child, filesystem_path


def project_files(root, directory):
    expected = checked_child(root, directory.name)
    if directory.resolve() != expected or directory.parent.resolve() != root.resolve():
        raise ValueError('Project deletion must stay in its own folder')
    directory = filesystem_path(expected)
    files = []
    # Validate every descendant before removing the first byte; never follow links.
    for path in directory.rglob('*'):
        if path.is_symlink() or path.is_junction() or not path.resolve().is_relative_to(directory):
            raise ValueError('Project chứa liên kết thư mục/file; gỡ liên kết trước khi xóa')
        if path.is_file():
            files.append(path)
    return directory, {'removed_files': len(files), 'freed_bytes': sum(path.stat().st_size for path in files)}


def remove_project_files(directory):
    # A locked artifact leaves project.sqlite available so the user can retry.
    database_files = {'project.sqlite', 'project.sqlite-wal', 'project.sqlite-shm'}
    for child in directory.iterdir():
        if child.name in database_files:
            continue
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()
    shutil.rmtree(directory)
