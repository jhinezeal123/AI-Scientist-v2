"""Human-readable folder names shared by projects and Library sources."""
from pathlib import Path
import os
import re
from threading import RLock
import unicodedata


PATH_LOCK = RLock()


def filesystem_path(path):
    """Use Windows' extended namespace for deep, project-packaged artifacts."""
    path = Path(path)
    if os.name != 'nt':
        return path
    value = str(path.resolve())
    if not value.startswith('\\\\?\\'):
        value = '\\\\?\\UNC\\' + value[2:] if value.startswith('\\\\') else '\\\\?\\' + value
    return Path(value)


def display_path(path):
    """Hide the filesystem namespace prefix in user-facing paths."""
    value = str(path)
    if value.startswith('\\\\?\\UNC\\'):
        return '\\\\' + value[8:]
    return value[4:] if value.startswith('\\\\?\\') else value


def folder_title(value):
    title = unicodedata.normalize('NFC', value)
    title = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', title)
    title = ' '.join(title.split()).strip(' .')[:120].rstrip(' .')
    if not title:
        raise ValueError('Tên thư mục phải có nội dung')
    if re.fullmatch(r'(?i)(CON|PRN|AUX|NUL|COM[1-9¹²³]|LPT[1-9¹²³])(?:\..*)?', title):
        title = '_' + title
    return title


def unique_title(title, occupied):
    occupied = {unicodedata.normalize('NFC', name).casefold() for name in occupied}
    candidate, suffix = title, 2
    while candidate.casefold() in occupied:
        candidate = f'{title[:110]} ({suffix})'
        suffix += 1
    return candidate


def checked_child(root, name):
    root = Path(root).resolve()
    if not name or name in {'.', '..'} or re.search(r'[<>:"/\\|?*\x00-\x1f]', name) or name.endswith((' ', '.')):
        raise ValueError('Invalid folder name')
    path = root / name
    if (path.is_symlink() or path.is_junction()
            or not path.resolve().is_relative_to(root)):
        raise ValueError('Linked folder path refused')
    return path


def rename_folder(source, destination):
    """Rename siblings, coordinating with Explorer if its directory handle blocks rename."""
    source, destination = Path(source), Path(destination)
    root = source.parent.resolve()
    if destination.parent.resolve() != root:
        raise ValueError('Folder rename must remain in its parent directory')
    source = checked_child(root, source.name)
    destination = checked_child(root, destination.name)
    if destination.exists() and not source.samefile(destination):
        raise FileExistsError('Folder name already exists')
    try:
        source.rename(destination)
    except PermissionError:
        if os.name != 'nt':
            raise
        import ctypes
        from ctypes import wintypes
        class Operation(ctypes.Structure):
            _fields_ = [('window', wintypes.HWND), ('function', wintypes.UINT),
                        ('source', wintypes.LPCWSTR), ('destination', wintypes.LPCWSTR),
                        ('flags', wintypes.WORD), ('aborted', wintypes.BOOL),
                        ('mappings', ctypes.c_void_p), ('title', wintypes.LPCWSTR)]
        old = ctypes.create_unicode_buffer(str(source) + '\0')
        new = ctypes.create_unicode_buffer(str(destination) + '\0')
        operation = Operation(None, 4, ctypes.cast(old, wintypes.LPCWSTR),
                              ctypes.cast(new, wintypes.LPCWSTR), 0x414, False, None, None)
        shell = ctypes.WinDLL('shell32')
        shell.SHFileOperationW.argtypes = [ctypes.POINTER(Operation)]
        result = shell.SHFileOperationW(ctypes.byref(operation))
        if result or operation.aborted or not destination.is_dir():
            raise PermissionError('Đóng thư mục đang mở trong File Explorer rồi thử lại')
