"""n8n owns the provider → remote action → next turn loop for each request."""
import asyncio
from dataclasses import dataclass, field
import json
from pathlib import Path
import threading
import time
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
import uuid

from .agents.contracts import RuntimeCancelled, RuntimeUncertain


@dataclass
class Ticket:
    runtime: object
    stage: str
    prompt: dict
    schema: dict
    deadline: float
    cancelled: object
    terminal: dict | None = None
    status: str = 'PENDING'
    turn: int = 0
    result: dict | None = None
    error: str = ''
    task: object = None
    history: list = field(default_factory=list)
    actions: dict = field(default_factory=dict)
    images: tuple = ()


class N8nAgentTurns:
    def __init__(self, client, executor):
        self.client, self.executor = client, executor
        self.tickets = {}
        self.lock = threading.RLock()

    def invoke(self, runtime, stage, prompt, schema, deadline, cancelled, *, images=()):
        return self.wait(Ticket(runtime, stage, prompt, schema, deadline, cancelled, images=tuple(images)))

    def remote(self, runtime, request, stage, inputs, schema, deadline, cancelled):
        path = Path(request.workdir) / 'terminal-access.json'
        if path.is_symlink() or not path.is_file():
            raise ValueError('Backend-owned terminal bridge is unavailable')
        terminal = json.loads(path.read_text(encoding='utf-8'))
        url = urlsplit(terminal['url'])
        if url.scheme != 'http' or url.hostname != '127.0.0.1' or url.path != '/terminal' or url.username:
            raise ValueError('Invalid backend terminal bridge')
        action_schema = {'type': 'object', 'required': ['action'], 'properties': {
            'action': {'enum': ['exec', 'read', 'write', 'fetch', 'finish']},
            'command': {'type': 'string'}, 'timeout': {'type': 'integer', 'minimum': 1, 'maximum': 120},
            'path': {'type': 'string'}, 'data': {'type': 'string'}, 'offset': {'type': 'integer'},
            'link': {'type': 'string'}, 'result': schema}, 'additionalProperties': False}
        if '$defs' in schema:
            action_schema['$defs'] = schema['$defs']
        return self.wait(Ticket(runtime, stage, {**inputs, 'selected_library': runtime.context(),
            'instructions': 'Choose one remote action for the approved Kaggle SSH session. write.data is base64 bytes. Returning a structured action is not a local tool call; the backend mediates it. Finish with result matching final_schema after actual execution.',
            'final_schema': schema}, action_schema, deadline, cancelled, terminal=terminal))

    def wait(self, ticket):
        identity = uuid.uuid4().hex
        with self.lock:
            self.tickets[identity] = ticket
        ticket.runtime.owner.store.event(ticket.runtime.project, ticket.runtime.workflow, ticket.stage,
                                         'n8n_agent_dispatched', ticket_id=identity, image_count=len(ticket.images))
        try:
            self.client.dispatch('agent', {'ticket_id': identity, 'stage': ticket.stage})
            while time.monotonic() < ticket.deadline:
                ticket.runtime.check(ticket.cancelled)
                if ticket.status == 'DONE':
                    return ticket.result
                if ticket.status == 'UNKNOWN':
                    raise RuntimeUncertain(ticket.error)
                if ticket.status == 'FAILED':
                    raise ValueError(ticket.error)
                time.sleep(.2)
            raise TimeoutError('n8n agent request exceeded the delegated deadline')
        except BaseException:
            self.executor.interrupt(ticket.runtime.workflow)
            raise
        finally:
            # Keep completed receipts for duplicate n8n deliveries; bounded by the grant.
            if ticket.status not in {'DONE', 'FAILED', 'UNKNOWN'}:
                ticket.status, ticket.error = 'FAILED', 'Request stopped; review before continuing'

    def ticket(self, identity):
        with self.lock:
            return self.tickets[identity]

    @staticmethod
    def view(identity, ticket):
        return {'ticket_id': identity, 'turn': ticket.turn, 'status': ticket.status,
                'pending': ticket.status in {'PENDING', 'RUNNING'},
                'failed': ticket.status in {'FAILED', 'UNKNOWN'}, 'finished': ticket.status == 'DONE',
                'result': ticket.result, 'error': ticket.error, 'remote': ticket.terminal is not None}

    async def turn(self, identity, execution_id=''):
        ticket = self.ticket(identity)
        if ticket.status in {'DONE', 'FAILED', 'UNKNOWN'}:
            return self.view(identity, ticket)
        ticket.runtime.check(ticket.cancelled)
        if time.monotonic() >= ticket.deadline:
            raise TimeoutError('Agent deadline reached')
        if ticket.status == 'PENDING':
            ticket.status = 'RUNNING'
            ticket.runtime.owner.store.event(ticket.runtime.project, ticket.runtime.workflow, ticket.stage,
                'n8n_agent_execution', execution_id=execution_id, ticket_id=identity)
            ticket.task = asyncio.create_task(self._turn(ticket))
        return self.view(identity, ticket)

    async def _turn(self, ticket):
        try:
            prompt = {**ticket.prompt, 'remote_history': ticket.history[-6:]} if ticket.terminal else ticket.prompt
            result = await asyncio.to_thread(self.executor.invoke, ticket.runtime, ticket.stage, prompt,
                                            ticket.schema, ticket.deadline, ticket.cancelled,
                                            **({'images':ticket.images} if ticket.images else {}))
            ticket.result = result
            ticket.status = 'ACTION' if ticket.terminal else 'DONE'
        except RuntimeUncertain as exc:
            ticket.status, ticket.error = 'UNKNOWN', str(exc)[:1000]
        except BaseException as exc:
            ticket.status, ticket.error = 'FAILED', str(exc)[:1000]

    async def action(self, identity, turn):
        ticket = self.ticket(identity)
        ticket.runtime.check(ticket.cancelled)
        if turn in ticket.actions:
            receipt = ticket.actions[turn]
            if receipt['status'] == 'RUNNING':
                raise RuntimeUncertain('Remote action outcome is pending; it cannot be replayed')
            return receipt['view']
        if turn != ticket.turn or ticket.status != 'ACTION':
            raise ValueError('Remote action does not match the completed provider turn')
        ticket.actions[turn] = {'status': 'RUNNING'}
        action = dict(ticket.result)
        try:
            if action['action'] == 'finish':
                import jsonschema
                result = action.get('result')
                jsonschema.validate(result, ticket.prompt['final_schema'])
                ticket.status, ticket.result = 'DONE', result
            else:
                if action['action'] == 'exec':
                    action['timeout'] = min(action.get('timeout', 30), max(1, int(ticket.deadline-time.monotonic())))
                result = await asyncio.to_thread(self._terminal, ticket.terminal, action)
                ticket.runtime.check(ticket.cancelled)
                ticket.history.append({'action': action, 'result': result})
                ticket.history = ticket.history[-6:]
                ticket.turn += 1
                ticket.status, ticket.result = 'PENDING', None
            value = self.view(identity, ticket)
            ticket.actions[turn] = {'status': 'DONE', 'view': value}
            return value
        except BaseException as exc:
            ticket.status, ticket.error = 'UNKNOWN', 'Remote action outcome requires review: ' + str(exc)[:500]
            ticket.actions[turn] = {'status': 'UNKNOWN', 'view': self.view(identity, ticket)}
            raise

    @staticmethod
    def _terminal(terminal, action):
        body = {k: v for k, v in action.items() if k != 'result'}
        request = Request(terminal['url'], data=json.dumps(body).encode(), method='POST', headers={
            'Content-Type': 'application/json', 'Authorization': 'Bearer ' + terminal['token']})
        with urlopen(request, timeout=body.get('timeout', 30)+10) as response:
            result = json.load(response)
        if len(json.dumps(result).encode()) > 24000:
            result = {'truncated': True, 'excerpt': json.dumps(result)[:22000]}
        return result

    async def close(self):
        for ticket in list(self.tickets.values()):
            self.executor.interrupt(ticket.runtime.workflow)
        tasks = [t.task for t in self.tickets.values() if t.task and not t.task.done()]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
