"""Bundled account selection must pin identity without exposing credentials."""
import json
from types import SimpleNamespace

import pytest

from ai_scientist.workbench.accounts import AccountCatalog
from ai_scientist.workbench.ssh_terminal import DonorSession


def test_catalog_only_returns_public_metadata(tmp_path):
    profiles = tmp_path / 'profiles'
    (profiles / 'first').mkdir(parents=True)
    (profiles / 'first' / 'token.txt').write_text('KGAT_private_value', encoding='utf-8')
    (profiles / 'first' / 'web-session.json').write_text('{"cookie":"private"}', encoding='utf-8')
    (profiles / 'accounts.json').write_text(json.dumps({'accounts': {
        'first.txt': {'alias': 'first', 'username': 'alice', 'token_file': 'profiles/first/token.txt'},
        'escape.txt': {'alias': '..', 'username': 'mallory'}}}), encoding='utf-8')
    catalog = AccountCatalog(tmp_path, 'first.txt')
    items = catalog.list()
    assert len(items) == 1 and items[0]['configured'] is True
    assert items[0]['readiness'] == 'unverified'
    assert 'private' not in json.dumps(items)
    with pytest.raises(ValueError):
        catalog.record_idle('first.txt', {'account': 'first.txt', 'username': 'other',
                                          'idle': True, 'active_session_count': 0,
                                          'observed_at': 'now'})
    ready = catalog.record_idle('first.txt', {'account': 'first.txt', 'username': 'alice',
                                              'idle': True, 'active_session_count': 0,
                                              'observed_at': 'now'})
    assert ready['readiness'] == 'verified_idle'
    needs_login = catalog.record_observation('first.txt', {'account': 'first.txt', 'username': 'alice',
        'readiness': 'needs_login', 'active_session_count': None, 'observed_at': 'now'})
    assert needs_login['readiness'] == 'needs_login'
    assert 'private' not in json.dumps(needs_login)


def test_donor_for_account_pins_cli_commands(tmp_path):
    config = SimpleNamespace(donor_python=tmp_path/'python', donor_root=tmp_path,
                             kaggle_account_alias='first.txt')
    donor = DonorSession(config).for_account('second.txt')
    assert donor.command('status', 'run-id')[-2:] == ['--account', 'second.txt']
    assert donor.account == 'second.txt'
