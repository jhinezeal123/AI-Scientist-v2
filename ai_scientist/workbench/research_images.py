"""Validated image attachments for upstream multimodal requests."""
import base64
import copy
import hashlib
from pathlib import Path

from PIL import Image


def validate_images(paths):
    paths = tuple(Path(p) for p in paths)
    if len(paths) > 32:
        raise ValueError('VLM accepts at most 32 images per request')
    total = 0
    for path in paths:
        if not path.is_file() or path.is_symlink() or path.is_junction():
            raise ValueError('VLM image must be a regular collected file')
        total += path.stat().st_size
        if path.stat().st_size > 8_000_000 or total > 20_000_000:
            raise ValueError('VLM image attachments exceed 20MB total / 8MB each')
        with Image.open(path) as image:
            if image.format not in {'PNG','JPEG','WEBP'}:
                raise ValueError('Unsupported VLM image format')
            image.verify()
    return paths


def image_blocks(paths):
    blocks = []
    for path in validate_images(paths):
        with Image.open(path) as image:
            mime = Image.MIME[image.format]
        blocks.append({'type':'image', 'mimeType':mime, 'data':base64.b64encode(path.read_bytes()).decode()})
    return blocks


def detach_images(messages, root):
    """Replace upstream data URLs with labels; send bytes through image inputs only."""
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    if root.is_symlink() or root.is_junction():
        raise ValueError('Refusing redirected VLM image directory')
    paths = []
    def visit(value):
        if isinstance(value, dict):
            if value.get('type') == 'image_url':
                url = value['image_url']['url']
                if not url.startswith(('data:image/png;base64,','data:image/jpeg;base64,','data:image/webp;base64,')) or len(url) > 11_000_000:
                    raise ValueError('VLM accepts bounded inline images only')
                raw = base64.b64decode(url.split(',',1)[1], validate=True)
                path = root / (hashlib.sha256(raw).hexdigest() + '.png')
                if path.is_symlink():
                    raise ValueError('Refusing redirected image attachment')
                path.write_bytes(raw)
                paths.append(path)
                return {'type':'text','text':f'Attached image {len(paths)}: {path.name}'}
            return {key:visit(item) for key,item in value.items()}
        if isinstance(value,list):
            return [visit(item) for item in value]
        return copy.deepcopy(value)
    result = visit(messages)
    return result, validate_images(paths)
