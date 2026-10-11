"""Cancellable background setup jobs. State outlives a browser refresh."""
from copy import deepcopy
from threading import Event, RLock, Thread
import time
import uuid


class SetupOperation:
    def __init__(self, instance, owner, *, phase='starting'):
        self.cancelled=Event()
        self.lock=RLock()
        self.owner=owner
        self.channel=None
        self.thread=None
        self.responses={}
        self.changed=Event()
        self.value={'instanceId':instance,'operationId':uuid.uuid4().hex,'flowId':uuid.uuid4().hex,
                    'phase':phase,'message':None,'authorizationUrl':None,'interaction':None,
                    'expiresAt':None,'methods':[]}

    def update(self, **values):
        with self.lock: self.value.update(values)

    def public(self, owner=None):
        with self.lock: value=deepcopy(self.value)
        if owner is not None and owner!=self.owner:
            value.update(authorizationUrl=None,interaction=None,flowId=None)
        return value

    def guard(self):
        if self.cancelled.is_set(): raise InterruptedError('Provider setup cancelled')

    def response(self, ident, timeout=300):
        deadline=time.monotonic()+timeout
        while time.monotonic()<deadline:
            self.guard()
            with self.lock:
                if ident in self.responses: return self.responses.pop(ident)
            self.changed.wait(.1)
            self.changed.clear()
        raise TimeoutError('Provider sign-in expired')

    def stop(self):
        self.cancelled.set()
        self.changed.set()

    def start(self, task):
        def run():
            try: task(self)
            except InterruptedError: self.update(phase='cancelled',message='Setup cancelled.',interaction=None,authorizationUrl=None)
            except BaseException as error:
                if self.cancelled.is_set():
                    self.update(phase='cancelled',message='Setup cancelled.',interaction=None,authorizationUrl=None)
                    return
                # Never return raw agent stderr or credential-bearing protocol messages.
                message=getattr(error,'public_message',None) or 'Could not complete provider setup. Check the configuration and retry.'
                self.update(phase='failed',message=message,interaction=None,authorizationUrl=None)
        self.thread=Thread(target=run,daemon=True,name='provider-setup')
        self.thread.start()
        return self


class SetupError(ValueError):
    def __init__(self, message):
        super().__init__(message)
        self.public_message=message
