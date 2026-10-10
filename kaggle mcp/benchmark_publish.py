"""Publish only a collected benchmark package with the selected account token."""
import hashlib
import json
import os
from pathlib import Path
import re
import time


def dataset_name(arguments):
    """Generate a stable slug and validate Kaggle's dataset naming limits."""
    run_id = arguments.get('run_id')
    if not isinstance(run_id, str) or not re.fullmatch(r'[a-f0-9]{32}', run_id):
        raise ValueError('Dataset cần run ID hợp lệ.')
    slug = arguments.get('dataset_slug')
    if slug is None:
        slug = 'ais-benchmark-' + run_id
    title = arguments.get('dataset_title')
    if title is None:
        title = ('Benchmark: ' + ' '.join(arguments.get('title', '').split()))[:50].rstrip()
    if (not isinstance(slug, str) or not 6 <= len(slug) <= 50
            or not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', slug)):
        raise ValueError('Slug dataset phải dài 6–50 ký tự, chỉ chữ thường, số và dấu gạch ngang giữa các từ.')
    if (not isinstance(title, str) or not 6 <= len(title) <= 50 or title != title.strip()
            or any(ord(char) < 32 for char in title)):
        raise ValueError('Title dataset phải dài 6–50 ký tự, không chứa ký tự điều khiển hoặc khoảng trắng ở hai đầu.')
    return slug, title


def _name_status(client, owner, slug):
    from requests import HTTPError
    from kagglesdk.datasets.types.dataset_api_service import ApiGetDatasetRequest
    request = ApiGetDatasetRequest()
    request.owner_slug, request.dataset_slug = owner, slug
    try:
        client.datasets.dataset_api_client.get_dataset(request)
    except HTTPError as exc:
        if exc.response is not None and exc.response.status_code == 404:
            return 'available'
        if exc.response is not None and exc.response.status_code == 403:
            # Kaggle may deny datasets.get for an absent slug. A 403 alone
            # proves nothing; exhaust the authenticated owner's full listing.
            return _owned_name_status(client, owner, slug)
        return 'unavailable'
    except Exception:
        return 'unavailable'
    return 'exists'


def _owned_name_status(client, owner, slug):
    from kagglesdk.datasets.types.dataset_api_service import ApiListDatasetsRequest
    from kagglesdk.datasets.types.dataset_enums import DatasetSelectionGroup
    request = ApiListDatasetsRequest()
    request.group = DatasetSelectionGroup.DATASET_SELECTION_GROUP_MY
    request.user = owner
    request.page = 1
    seen, tokens = set(), set()
    try:
        for _ in range(100):
            result = client.datasets.dataset_api_client.list_datasets(request)
            rows = result.datasets
            if not isinstance(rows, list):
                return 'unavailable'
            refs = [item.ref for item in rows]
            if any(not isinstance(ref, str) or not ref.startswith(owner + '/') for ref in refs):
                return 'unavailable'
            if owner + '/' + slug in refs:
                return 'exists'
            token = result.next_page_token
            if not rows and not token:
                return 'available'
            if not refs or len(set(refs)) != len(refs) or seen.intersection(refs):
                return 'unavailable'
            seen.update(refs)
            if token:
                if token in tokens:
                    return 'unavailable'
                tokens.add(token)
                request.page_token = token
            elif request.page_token:
                # Cursor API explicitly signals its final nonempty page.
                return 'available'
            else:
                # Legacy endpoint omits cursor/page-size; require an empty
                # numbered page rather than assuming a short page is final.
                request.page += 1
    except Exception:
        return 'unavailable'
    return 'unavailable'


def check_name(account, arguments):
    from account_store import read_token, resolve
    from sdk_version import _assert_pinned_sdk
    _assert_pinned_sdk()
    try:
        slug, title = dataset_name(arguments)
    except ValueError as exc:
        return {'status': 'invalid', 'error': str(exc)}
    from kagglehub.clients import build_kaggle_client
    owner = resolve(account)[1]['username']
    os.environ['KAGGLE_API_TOKEN'] = read_token(account)
    with build_kaggle_client() as client:
        status = _name_status(client, owner, slug)
    result = {'status': status, 'handle': owner + '/' + slug, 'slug': slug, 'title': title}
    if status != 'available':
        result['error'] = ('Tên dataset đã tồn tại trên account Kaggle; không ghi đè hoặc tạo version mới.'
                           if status == 'exists' else 'Chưa xác minh được tên dataset trên Kaggle; chưa mở phiên chạy.')
    return result


def publish(account, arguments):
    from account_store import read_token, resolve
    from sdk_version import _assert_pinned_sdk
    _assert_pinned_sdk()
    from kagglehub.gcs_upload import upload_files_and_directories
    from kagglehub.clients import build_kaggle_client
    from kagglesdk.blobs.types.blob_api_service import ApiBlobType
    from kagglesdk.datasets.types.dataset_api_service import ApiCreateDatasetRequest, ApiGetDatasetRequest, ApiGetDatasetStatusRequest

    directory = Path(arguments['directory']).resolve(strict=True)
    slug, title = dataset_name(arguments)
    if not directory.is_dir():
        raise ValueError('Invalid benchmark publication request')
    entries = arguments['files']
    serialized = json.dumps(sorted(entries, key=lambda item: item['path']), ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)
    if hashlib.sha256(serialized.encode()).hexdigest() != arguments['manifest_sha256']:
        raise ValueError('Publication manifest hash mismatch')
    expected = {item['path'].removeprefix('output/benchmark/'): item for item in entries}
    actual = {path.relative_to(directory).as_posix() for path in directory.rglob('*') if path.is_file()}
    if actual != set(expected) or not {'benchmark.json', 'evaluate.py'}.issubset(actual):
        raise ValueError('Benchmark directory differs from collected manifest')
    for name, item in expected.items():
        path = directory / name
        if (path.is_symlink() or path.is_junction() or not path.resolve().is_relative_to(directory)
                or any(parent.is_symlink() or parent.is_junction() for parent in path.parents if parent.is_relative_to(directory))
                or path.stat().st_size != item['bytes']):
            raise ValueError('Unsafe or changed benchmark file')
        with path.open('rb') as stream:
            if hashlib.file_digest(stream, 'sha256').hexdigest() != item['sha256']:
                raise ValueError('Benchmark file hash mismatch')
    owner = resolve(account)[1]['username']
    # This subprocess owns its environment. Token is never in stdout, argv,
    # agent context, SSH commands, artifacts, or the publication receipt.
    os.environ['KAGGLE_API_TOKEN'] = read_token(account)
    with build_kaggle_client() as client:
        status = _name_status(client, owner, slug)
        if status != 'available':
            raise ValueError('Dataset name gate: tên đã tồn tại hoặc chưa xác minh được; chưa upload file.')
        request = ApiGetDatasetRequest()
        request.owner_slug, request.dataset_slug = owner, slug
        tokens = upload_files_and_directories(str(directory), item_type=ApiBlobType.DATASET, ignore_patterns=[], quiet=True)
        upload = tokens.to_proto()
        create = ApiCreateDatasetRequest()
        create.owner_slug, create.slug = owner, slug
        create.title = title
        create.files, create.directories = upload.files, upload.directories
        create.is_private = False
        create.license_name = 'unknown'
        # Deliberately no create-or-version behavior: a benchmark is immutable.
        response = client.datasets.dataset_api_client.create_dataset(create)
        if getattr(response, 'error', None):
            raise RuntimeError('Kaggle rejected benchmark publication')
        deadline = time.monotonic() + 120
        dataset = None
        status_request = ApiGetDatasetStatusRequest()
        status_request.owner_slug, status_request.dataset_slug = owner, slug
        ready = False
        while time.monotonic() < deadline:
            try:
                dataset = client.datasets.dataset_api_client.get_dataset(request)
                state = client.datasets.dataset_api_client.get_dataset_status(status_request)
                ready = state.status.name == 'READY'
            except Exception:
                dataset = None
                ready = False
            if dataset and ready and dataset.current_version_number >= 1:
                break
            time.sleep(2)
        if not dataset or not ready or dataset.is_private is not False or dataset.ref != owner + '/' + slug:
            raise RuntimeError('Public benchmark dataset has not been verified')
        return {'handle': dataset.ref, 'url': 'https://www.kaggle.com/datasets/' + dataset.ref,
                'version': dataset.current_version_number, 'visibility': 'public',
                'manifest_sha256': arguments['manifest_sha256'], 'files': entries}
