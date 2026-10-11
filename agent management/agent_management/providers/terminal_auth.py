"""A provider-advertised login command, shown in the setup UI."""
import os
import ctypes
import subprocess
from threading import Thread
import time

from .operations import SetupError
from ..processes import ProcessGroup


class TerminalProcess:
    """Expose the ConPTY child to the existing process-tree supervisor."""
    def __init__(self,pty):
        from ctypes import wintypes
        self.pty=pty
        self.pid=pty.pid
        self.kernel=ctypes.WinDLL('kernel32',use_last_error=True)
        self.kernel.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD]
        self.kernel.OpenProcess.restype=wintypes.HANDLE
        self.kernel.CloseHandle.argtypes=[wintypes.HANDLE]
        self._handle=self.kernel.OpenProcess(0x001F0FFF,False,self.pid)
        if not self._handle:
            pty.terminate(force=True)
            raise SetupError('Could not supervise the provider sign-in process.')

    def poll(self):return None if self.pty.isalive() else (self.pty.exitstatus or 0)
    def kill(self):self.pty.terminate(force=True)
    def wait(self,timeout):
        deadline=time.monotonic()+timeout
        while self.pty.isalive():
            if time.monotonic()>=deadline:raise subprocess.TimeoutExpired('provider login',timeout)
            time.sleep(.05)
        return self.poll()
    def close(self):self.kernel.CloseHandle(self._handle)


def terminal_login(argv,cwd,environment,operation):
    if os.name!='nt':
        raise SetupError('Interactive login requires the Windows terminal runtime on this installation.')
    try: from winpty import PtyProcess
    except ImportError: raise SetupError('Install the Workbench terminal dependency to sign in to this provider.') from None
    process=PtyProcess.spawn(argv,cwd=str(cwd),env=environment,dimensions=(24,80))
    supervised=TerminalProcess(process)
    try: group=ProcessGroup(supervised)
    except BaseException:
        supervised.close()
        raise
    operation.terminal=process
    operation.update(phase='waiting',interaction={'type':'terminal','id':'terminal','output':'','outputOffset':0})
    def read():
        while process.isalive():
            try: chunk=process.read(4096)
            except (EOFError,OSError): break
            if chunk:
                with operation.lock:
                    old=operation.value.get('interaction')
                    if old and old['type']=='terminal':
                        operation.value['interaction']=old|{'output':(old['output']+chunk)[-16384:],'outputOffset':old['outputOffset']+len(chunk)}
    reader=Thread(target=read,daemon=True)
    reader.start()
    try:
        deadline=time.monotonic()+300
        while process.isalive():
            operation.guard()
            if time.monotonic()>deadline: raise SetupError('Provider login expired. Retry sign-in.')
            time.sleep(.1)
        if process.exitstatus not in {0,None}: raise SetupError('The provider login command did not finish successfully.')
    finally:
        group.stop()
        group.close()
        supervised.close()
        reader.join(timeout=1)
        operation.terminal=None
