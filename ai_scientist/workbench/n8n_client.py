"""Local n8n transport and a separate bridge credential, without agent authority."""
import json
import secrets
import subprocess
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlsplit, parse_qs
from urllib.request import Request, urlopen, build_opener, HTTPRedirectHandler


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class N8nClient:
    def __init__(self, workspace, *, base_url='http://127.0.0.1:5678'):
        self.base_url = base_url
        root = Path(workspace) / '.workbench/n8n'
        if root.is_symlink() or getattr(root, 'is_junction', lambda: False)():
            raise ValueError('Refusing redirected n8n data')
        root.mkdir(parents=True, exist_ok=True)
        path = root / 'bridge-token.txt'
        if path.is_symlink():
            raise ValueError('Refusing redirected n8n credential')
        if not path.exists():
            with path.open('x', encoding='utf-8') as stream:
                stream.write(secrets.token_urlsafe(48))
        self.token = path.read_text(encoding='utf-8').strip()

    def status(self):
        try:
            with urlopen(self.base_url + '/healthz/readiness', timeout=2) as response:
                ready = response.status == 200
        except (OSError, HTTPError):
            ready = False
        return {'ready': ready, 'editor_url': self.base_url,
                'workflow_url': self.base_url + '/workflow/workbenchResearch',
                'agent_workflow_url': self.base_url + '/workflow/workbenchAgent'}

    def dispatch(self, name, body):
        request = Request(self.base_url + '/webhook/workbench-' + name,
                          data=json.dumps(body).encode(), method='POST',
                          headers={'Content-Type': 'application/json', 'X-Workbench-N8n': self.token})
        with urlopen(request, timeout=10) as response:
            if response.status != 200:
                raise ValueError('n8n did not accept the workflow')

    def validate_resume_url(self, url, execution, generation, iteration, step, proposal_round=0):
        base, target = urlsplit(self.base_url), urlsplit(url)
        expected = f'/webhook-waiting/{execution}/{step}'
        query = parse_qs(target.query)
        if (not execution.isascii() or not execution.isdecimal() or any(ord(c) < 32 for c in url)
                or target.scheme != base.scheme or target.netloc != base.netloc
                or base.hostname not in {'127.0.0.1', 'localhost', '::1'}
                or target.username or target.password or target.fragment or target.path != expected
                or query.get('wb_generation') != [str(generation)] or query.get('wb_iteration') != [str(iteration)]
                or query.get('wb_round', ['0']) != [str(proposal_round)]):
            raise ValueError('Callback must target this local n8n execution and research step')
        return url

    def resume(self, url, body):
        # Only registered, validated URLs reach this method. Never forward the
        # bridge credential through a redirect, even on the local server.
        request = Request(url, data=json.dumps(body).encode(), method='POST',
                          headers={'Content-Type': 'application/json', 'X-Workbench-N8n': self.token})
        with build_opener(_NoRedirect).open(request, timeout=5) as response:
            if response.status != 200:
                raise OSError('n8n did not accept the completion notification')

    def start(self, workspace):
        script = Path(workspace) / 'scripts/n8n.ps1'
        result = subprocess.run(['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass',
                                 '-File', str(script), 'start'], capture_output=True, timeout=30,
                                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        if result.returncode:
            raise ValueError('n8n could not start; check .workbench/n8n/server.err.log')
        return self.status()
