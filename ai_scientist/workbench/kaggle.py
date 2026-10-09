"""Backend-owned Kaggle proxy lifecycle and the retired response decoder."""
from contextlib import asynccontextmanager
import asyncio
import importlib.util
import json
from .ssh_terminal import DonorSession


@asynccontextmanager
async def connect_kaggle(config):
    # Load just the bundle's stdlib-only proxy manager, without modifying sys.path
    # or importing its SDK/account modules into the backend process.
    spec = importlib.util.spec_from_file_location('workbench_kaggle_proxy', config.donor_root / 'proxy_control.py')
    manager = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(manager)
    proxy = await asyncio.to_thread(manager.ensure_proxy)
    try:
        yield DonorSession(config)
    finally:
        if proxy and proxy.poll() is None:
            proxy.terminate()
            await asyncio.to_thread(proxy.wait, 5)


def decode_result(result):
    if getattr(result, 'isError', False):
        # MCP errors may include provider details; keep credentials/raw errors out of app evidence.
        raise RuntimeError('MCP operation failed; outcome must be reconciled')
    structured = getattr(result, 'structuredContent', None)
    if isinstance(structured, dict):
        # FastMCP wraps primitive string returns; legacy tools return JSON strings.
        if set(structured) == {'result'} and isinstance(structured['result'], str):
            structured = json.loads(structured['result'])
        if isinstance(structured, dict):
            return structured
    content = getattr(result, 'content', [])
    texts = [item.text for item in content if getattr(item, 'type', None) == 'text']
    if len(texts) != 1:
        raise ValueError('Expected one structured MCP response')
    value = json.loads(texts[0])
    if isinstance(value, str):
        value = json.loads(value)
    if not isinstance(value, dict):
        raise ValueError('Expected MCP object response')
    return value
