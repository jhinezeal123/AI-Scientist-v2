"""Backend-owned persistent SSH terminal and a run-scoped local command bridge."""
import base64
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import queue
import secrets
import shlex
import subprocess
import threading
import time
import uuid


class TerminalDisconnected(RuntimeError):
    pass


def transfer_library_file(terminal, name, data):
    """Respect the donor's 1 MB write limit while retaining exact original bytes."""
    if len(data) <= 1_000_000:
        receipt = terminal.request('write', path=name, data=base64.b64encode(data).decode('ascii'))
        if receipt.get('bytes') != len(data):
            raise ValueError('Selected Library file was not transferred completely')
        return
    import hashlib
    part = name.rsplit('/', 1)[0] + '/.transfer-' + uuid.uuid4().hex
    script = ('from pathlib import Path;import sys;'
              'part=Path(sys.argv[1]);destination=Path(sys.argv[2]);'
              'destination.parent.mkdir(parents=True,exist_ok=True);'
              'out=destination.open(sys.argv[3]);out.write(part.read_bytes());out.close();part.unlink()')
    for offset in range(0, len(data), 512_000):
        chunk = data[offset:offset + 512_000]
        receipt = terminal.request('write', path=part, data=base64.b64encode(chunk).decode('ascii'))
        if receipt.get('bytes') != len(chunk):
            raise ValueError('Incomplete Library chunk transfer')
        command = shlex.join(['python3', '-c', script, part, name, 'wb' if offset == 0 else 'ab'])
        if terminal.request('exec', command=command, timeout=30).get('returncode') != 0:
            raise ValueError('Library chunk assembly failed')
    verify = ('from pathlib import Path;import hashlib,sys;'
              'p=Path(sys.argv[1]);assert p.stat().st_size==int(sys.argv[2]);'
              'f=p.open("rb");assert hashlib.file_digest(f,"sha256").hexdigest()==sys.argv[3]')
    command = shlex.join(['python3', '-c', verify, name, str(len(data)), hashlib.sha256(data).hexdigest()])
    if terminal.request('exec', command=command, timeout=30).get('returncode') != 0:
        raise ValueError('Remote Library file hash mismatch')


class DonorSession:
    def __init__(self, config):
        self.config = config

    def command(self, action, session_id):
        return [str(self.config.donor_python), '-m', 'interface_ai_scientist', action, '--session', session_id,
                '--account', self.config.kaggle_account_alias]

    def call(self, action, session_id, timeout=40):
        result = subprocess.run(self.command(action, session_id), cwd=self.config.donor_root,
                                capture_output=True, timeout=timeout)
        if result.returncode:
            raise RuntimeError(f'Kaggle {action} failed; no new notebook was submitted')
        if action == 'status':
            return json.loads(result.stdout)
        return None

    def open(self, session_id, on_output):
        process = subprocess.Popen(self.command('bridge', session_id), cwd=self.config.donor_root,
                                   stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   start_new_session=os.name != 'nt')
        return SshTerminal(process, on_output)

    def inspect(self, kernel_ref):
        command = [str(self.config.donor_python), '-m', 'interface_ai_scientist', 'inspect',
                   '--account', self.config.kaggle_account_alias, '--kernel-ref', kernel_ref]
        result = subprocess.run(command, cwd=self.config.donor_root, capture_output=True, timeout=40)
        if result.returncode:
            raise RuntimeError('Cannot verify the old Kaggle notebook; no new run was submitted')
        return json.loads(result.stdout)


class SshTerminal:
    def __init__(self, process, on_output):
        self.process, self.on_output = process, on_output
        self.messages = queue.Queue()
        self.lock = threading.Lock()
        self.closed = False
        threading.Thread(target=self._read, daemon=True).start()
        threading.Thread(target=self._drain_errors, daemon=True).start()
        try:
            ready = self._next(time.monotonic() + 30)
            if ready.get('type') != 'ready' or ready.get('protocol') != 1:
                raise TerminalDisconnected('SSH terminal protocol did not become ready')
        except BaseException:
            self.close()
            raise

    def _read(self):
        try:
            for line in self.process.stdout:
                if len(line) > 2_000_000:
                    raise ValueError('Terminal response exceeds 2 MB')
                self.messages.put(json.loads(line))
        except (ValueError, OSError):
            pass
        finally:
            self.messages.put(None)

    def _drain_errors(self):
        # Native SSH errors can include the private Tailcat endpoint. Never publish them.
        for _ in self.process.stderr:
            pass

    def _next(self, deadline):
        try:
            message = self.messages.get(timeout=max(.01, deadline - time.monotonic()))
        except queue.Empty as exc:
            raise TerminalDisconnected('SSH command response timed out; it was not replayed') from exc
        if message is None:
            raise TerminalDisconnected('SSH disconnected; the command result is uncertain')
        return message

    def request(self, action, **arguments):
        with self.lock:
            if self.closed:
                raise TerminalDisconnected('SSH terminal is closed')
            request_id = uuid.uuid4().hex
            timeout = arguments.get('timeout', 30)
            deadline = time.monotonic() + timeout + 15
            request = {'id': request_id, 'action': action, **arguments}
            try:
                self.process.stdin.write((json.dumps(request) + '\n').encode())
                self.process.stdin.flush()
            except (BrokenPipeError, OSError) as exc:
                raise TerminalDisconnected('SSH could not receive the command') from exc
            text = ''
            truncated = False
            while True:
                message = self._next(deadline)
                if message.get('id') != request_id:
                    raise TerminalDisconnected('SSH response belongs to a different command')
                if message['type'] == 'output':
                    chunk = message['text']
                    self.on_output(chunk)
                    remaining = max(0, 600_000 - len(text))
                    text += chunk[:remaining]
                    truncated = truncated or len(chunk) > remaining
                    continue
                if message['type'] == 'error':
                    raise RuntimeError('Remote command failed (' + message['error'] + ')')
                if message['type'] != 'result':
                    raise TerminalDisconnected('Invalid SSH result')
                if action == 'exec':
                    message.update(output=text, output_truncated=truncated)
                return message

    def close(self):
        self.closed = True
        from .agents.codex import HeadlessCliRuntime
        HeadlessCliRuntime._kill_tree(self.process)
        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.kill()
        for stream in (self.process.stdin, self.process.stdout, self.process.stderr):
            try:
                stream.close()
            except (OSError, ValueError):
                pass


class AgentTerminalBridge:
    """Give the agent terminal access without Kaggle MCP or account credentials."""
    def __init__(self, terminal, workdir):
        self.terminal, self.workdir = terminal, Path(workdir)
        self.token = secrets.token_urlsafe(32)
        bridge = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                if self.path != '/terminal' or not secrets.compare_digest(
                        self.headers.get('Authorization', ''), 'Bearer ' + bridge.token):
                    self.send_error(403)
                    return
                try:
                    size = int(self.headers.get('Content-Length', '0'))
                    if not 0 < size <= 2_000_000:
                        raise ValueError('Invalid request size')
                    body = json.loads(self.rfile.read(size))
                    action = body.pop('action')
                    if action not in {'exec', 'read', 'write'}:
                        raise ValueError('This action belongs to the backend')
                    allowed = {'exec': {'command', 'timeout'}, 'read': {'path', 'offset'},
                               'write': {'path', 'data'}}[action]
                    if not set(body).issubset(allowed):
                        raise ValueError('Invalid terminal arguments')
                    result = bridge.terminal.request(action, **body)
                    data = json.dumps(result).encode()
                    self.send_response(200)
                except (ValueError, KeyError, TypeError, RuntimeError, OSError) as exc:
                    data = json.dumps({'error': type(exc).__name__}).encode()
                    self.send_response(400)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                try:
                    self.wfile.write(data)
                except (BrokenPipeError, OSError):
                    pass

        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.server.daemon_threads = True
        self.workdir.mkdir(parents=True, exist_ok=True)
        self.access = self.workdir / 'terminal-access.json'
        self.access.write_text(json.dumps({'url': f'http://127.0.0.1:{self.server.server_port}/terminal',
                                          'token': self.token}), encoding='utf-8')
        self.access.chmod(0o600)
        helper = Path(__file__).with_name('terminal_client.py').read_bytes()
        (self.workdir / 'terminal.py').write_bytes(helper)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.access.unlink(missing_ok=True)


def collect_files(terminal, root, limit=None, on_progress=None):
    """Copy only source/output files over the existing SSH connection and verify hashes."""
    import hashlib
    if limit is not None and (type(limit) is not int or limit < 1):
        raise ValueError('Output budget must be a positive integer when supplied')
    root = Path(root).resolve()
    manifest = terminal.request('manifest', limit=limit)
    files = manifest['files']
    if not isinstance(files, list) or len(files) > 200:
        raise ValueError('Invalid SSH manifest')
    total = 0
    seen = set()
    collected = []
    if on_progress:
        on_progress({**manifest, 'files': [], 'complete': False})
    for item in files:
        name, size, sha256 = item['path'], item['bytes'], item['sha256']
        path = Path(name)
        if (not isinstance(name, str) or '\\' in name or path.is_absolute() or '..' in path.parts
                or not path.parts or path.parts[0] not in {'source', 'output'} or name in seen
                or type(size) is not int or size < 0):
            raise ValueError('Unsafe SSH artifact path or size')
        seen.add(name)
        total += size
        if limit is not None and total > limit:
            raise ValueError('SSH files exceed the approved output budget')
        target = root / path
        if target.is_symlink() or target.is_junction() or not target.resolve().is_relative_to(root):
            raise ValueError('Artifact destination escapes the run')
        target.parent.mkdir(parents=True, exist_ok=True)
        if any(parent.is_symlink() or parent.is_junction() for parent in target.parents if parent.is_relative_to(root)):
            raise ValueError('Linked artifact directory')
        temporary = target.with_name(target.name + '.collecting')
        if temporary.is_symlink():
            raise ValueError('Linked temporary artifact')
        digest = hashlib.sha256()
        offset = 0
        with temporary.open('wb') as destination:
            while offset < size:
                received = terminal.request('read', path=name, offset=offset)
                data = base64.b64decode(received['data'], validate=True)
                if not data or len(data) > size - offset:
                    raise ValueError('Artifact size changed during collection')
                destination.write(data)
                digest.update(data)
                offset += len(data)
        if digest.hexdigest() != sha256:
            raise ValueError('SSH artifact hash mismatch')
        temporary.replace(target)
        collected.append(item)
        if on_progress:
            on_progress({**manifest, 'files': list(collected), 'complete': False})
    return manifest
