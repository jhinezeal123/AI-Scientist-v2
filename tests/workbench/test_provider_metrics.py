"""Measure provider attempts without storing authorization headers or response bodies."""
import importlib.util
from pathlib import Path
import time
from types import SimpleNamespace

import pytest

from ai_scientist.workbench.accounts import AccountCatalog


def test_provider_totals_are_account_isolated_and_secret_free(tmp_path):
    source = Path(__file__).resolve().parents[2] / 'kaggle mcp' / 'provider_metrics.py'
    spec = importlib.util.spec_from_file_location('test_bundled_metrics', source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    (tmp_path / '.runtime').mkdir()
    module.PATH = tmp_path / '.runtime' / 'provider-metrics.sqlite3'
    module.record('alice.txt', 10, 20, time.perf_counter())
    module.record('bob.txt', 30, 40, time.perf_counter(), failed=True)
    catalog = AccountCatalog(tmp_path, 'alice.txt')
    alice, bob = catalog.provider_stats('alice.txt'), catalog.provider_stats('bob.txt')
    assert alice['requests'] == bob['requests'] == 1
    assert alice['request_bytes'] == 10 and alice['response_bytes'] == 20 and alice['errors'] == 0
    assert bob['request_bytes'] == 30 and bob['response_bytes'] == 40 and bob['errors'] == 1
    assert alice['epoch'] == bob['epoch']


def test_status_measurement_does_not_change_identity_or_retry(tmp_path, monkeypatch):
    root = Path(__file__).resolve().parents[2] / 'kaggle mcp'
    monkeypatch.syspath_prepend(str(root))
    from interface_ai_scientist import session
    import requests
    calls, measured = [], []
    monkeypatch.setattr(session.account_store, 'resolve', lambda key: ('alice.txt', {'username':'alice'}))
    monkeypatch.setattr(session.account_store, 'read_token', lambda key: 'KGAT_fixture_only')
    monkeypatch.setattr('provider_metrics.record', lambda *args: measured.append(args))
    response = SimpleNamespace(content=b'{"status":"complete"}',status_code=200,
        raise_for_status=lambda:None,json=lambda:{'status':'complete'})
    def get(url, **kwargs):
        calls.append(kwargs)
        return response
    monkeypatch.setattr(requests,'get',get)
    result = session.notebook_status('alice.txt','alice/unique-run','run')
    assert result['stopped'] is True and len(calls) == len(measured) == 1
    assert calls[0]['headers']['Authorization'] == 'Bearer KGAT_fixture_only'
    assert measured[0][0:3] == ('alice.txt',0,len(response.content))
    assert measured[0][-1] is False
    monkeypatch.setattr(requests,'get',lambda *args,**kwargs: (_ for _ in ()).throw(requests.Timeout()))
    with pytest.raises(requests.Timeout):
        session.notebook_status('alice.txt','alice/unique-run','run')
    assert len(measured) == 2 and measured[-1][-1] is True
