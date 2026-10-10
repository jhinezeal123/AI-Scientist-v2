"""Public account metadata for the bundled Kaggle profiles; never return tokens."""
import json
from pathlib import Path
import re
import sqlite3


class AccountCatalog:
    def __init__(self, bundle_root: Path, default_account: str):
        self.root = bundle_root.resolve()
        self.profiles = self.root / 'profiles'
        self.default_account = default_account
        self.observations = {}

    def list(self):
        path = self.profiles / 'accounts.json'
        if not path.is_file() or path.is_symlink():
            return []
        document = json.loads(path.read_text(encoding='utf-8-sig'))
        if not isinstance(document, dict) or not isinstance(document.get('accounts'), dict):
            raise ValueError('Invalid bundled Kaggle account registry')
        accounts = []
        for key, entry in document['accounts'].items():
            if not isinstance(entry, dict):
                continue
            alias, username = entry.get('alias'), entry.get('username')
            if (not isinstance(key, str) or not re.fullmatch(r'[A-Za-z0-9_-]+\.txt', key)
                    or not isinstance(alias, str) or not re.fullmatch(r'[A-Za-z0-9_-]+', alias)
                    or not isinstance(username, str) or not re.fullmatch(r'[A-Za-z0-9_-]+', username)):
                continue
            token = self.profiles / alias / 'token.txt'
            try:
                valid_path = (token.name == 'token.txt' and not token.is_symlink()
                              and token.resolve().is_relative_to(self.profiles.resolve())
                              and entry.get('token_file') == f'profiles/{alias}/token.txt'
                              and token.is_file() and token.stat().st_size <= 1024)
                configured = valid_path and token.read_text(encoding='utf-8-sig').strip().startswith('KGAT_')
            except OSError:
                configured = False
            observed = self.observations.get(key)
            accounts.append({'account': key, 'alias': alias, 'username': username,
                             'configured': bool(configured), 'default': key == self.default_account,
                             'readiness': observed.get('readiness', 'unverified') if observed else 'unverified',
                             'active_session_count': observed.get('active_session_count') if observed else None,
                             'observed_at': observed.get('observed_at') if observed else None})
        return accounts

    def require(self, account: str):
        selected = next((entry for entry in self.list() if entry['account'] == account), None)
        if not selected or not selected['configured']:
            raise ValueError('Kaggle account is not configured in the bundle')
        return selected

    def record_idle(self, account: str, observation: dict):
        selected = self.require(account)
        if (observation.get('account') != account or observation.get('username') != selected['username']
                or observation.get('idle') is not True or type(observation.get('active_session_count')) is not int
                or observation.get('active_session_count') != 0
                or not observation.get('observed_at')):
            raise ValueError('Kaggle account idle observation does not match the selected profile')
        self.observations[account] = {**observation, 'readiness': 'verified_idle'}
        return next(item for item in self.list() if item['account'] == account)

    def record_observation(self, account, observation):
        selected = self.require(account)
        if observation.get('account') != account or observation.get('username') != selected['username']:
            raise ValueError('Kaggle readiness identity differs from selected profile')
        if observation.get('readiness') == 'verified_idle':
            return self.record_idle(account, observation)
        if observation.get('readiness') not in {'needs_login', 'busy', 'unavailable'}:
            raise ValueError('Unknown Kaggle readiness state')
        self.observations[account] = observation
        return next(item for item in self.list() if item['account'] == account)

    def unavailable(self, account):
        self.observations[account] = {'readiness': 'unavailable'}

    def provider_stats(self, account):
        path = self.root / '.runtime' / 'provider-metrics.sqlite3'
        if not path.is_file():
            return None
        try:
            with sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=.2) as db:
                db.row_factory = sqlite3.Row
                epoch = db.execute('SELECT epoch FROM metadata').fetchone()[0]
                row = db.execute('SELECT requests,request_bytes,response_bytes,latency_ms,errors FROM totals WHERE account=?', (account,)).fetchone()
                fields = ('requests', 'request_bytes', 'response_bytes', 'latency_ms', 'errors')
                return {'epoch': epoch, **(dict(row) if row else dict.fromkeys(fields, 0))}
        except (OSError, sqlite3.Error, TypeError):
            return None
