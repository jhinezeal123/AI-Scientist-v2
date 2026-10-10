"""Bounded argv-only subprocesses, with a stop receipt for the entire process group."""
from __future__ import annotations

import ctypes
import errno
import os
from pathlib import Path
import signal
import subprocess
from threading import Event, Lock, Thread
import time


class ProcessFailure(RuntimeError):
    def __init__(self, message, receipt, *, cancelled=False, diagnostic=None):
        super().__init__(message)
        self.receipt = receipt
        self.cancelled = cancelled
        self.diagnostic = diagnostic  # Never included in public error strings or event journals.


def private_environment():
    # Native CLI authentication remains in its own credential store. Project/control
    # secrets, dotenv and provider API tokens are not inherited by coding subprocesses.
    allowed = {"PATH", "PATHEXT", "SYSTEMROOT", "WINDIR", "COMSPEC", "TEMP", "TMP",
               "HOME", "USERPROFILE", "APPDATA", "LOCALAPPDATA", "PROGRAMFILES",
               "PROGRAMFILES(X86)", "PROGRAMDATA", "LANG", "LC_ALL", "TERM"}
    return {key: value for key, value in os.environ.items() if key.upper() in allowed}


def process_identity(pid):
    """Birth identity protects restart reconciliation from PID reuse."""
    if os.name == "nt":
        from ctypes import wintypes
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel.OpenProcess(0x1000, False, pid)
        if not handle:
            if ctypes.get_last_error() == 87:
                return None
            raise ValueError("Cannot verify process birth identity")
        values = [wintypes.FILETIME() for _ in range(4)]
        try:
            if not kernel.GetProcessTimes(handle, *[ctypes.byref(v) for v in values]):
                raise ValueError("Cannot verify process birth identity")
            return str((values[0].dwHighDateTime << 32) | values[0].dwLowDateTime)
        finally:
            kernel.CloseHandle(handle)
    try:
        # Field 22; command names may contain spaces or closing parentheses.
        return Path(f"/proc/{pid}/stat").read_text().rpartition(")")[2].split()[19]
    except FileNotFoundError:
        return None


class ProcessGroup:
    def __init__(self, proc):
        self.proc = proc
        self.job = None
        if os.name == "nt":
            from ctypes import wintypes
            class Basic(ctypes.Structure):
                _fields_ = [("PerProcessUserTimeLimit", ctypes.c_longlong), ("PerJobUserTimeLimit", ctypes.c_longlong),
                            ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                            ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
                            ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD), ("SchedulingClass", wintypes.DWORD)]
            class IO(ctypes.Structure):
                _fields_ = [(name, ctypes.c_ulonglong) for name in ("ReadOperationCount", "WriteOperationCount", "OtherOperationCount", "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]
            class Extended(ctypes.Structure):
                _fields_ = [("BasicLimitInformation", Basic), ("IoInfo", IO), ("ProcessMemoryLimit", ctypes.c_size_t),
                            ("JobMemoryLimit", ctypes.c_size_t), ("PeakProcessMemoryUsed", ctypes.c_size_t), ("PeakJobMemoryUsed", ctypes.c_size_t)]
            self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
            self.kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
            self.kernel.CreateJobObjectW.restype = wintypes.HANDLE
            self.kernel.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
            self.kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
            self.kernel.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
            self.kernel.QueryInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD, ctypes.c_void_p]
            self.kernel.CloseHandle.argtypes = [wintypes.HANDLE]
            self.job = self.kernel.CreateJobObjectW(None, None)
            limits = Extended()
            limits.BasicLimitInformation.LimitFlags = 0x2000  # KILL_ON_JOB_CLOSE
            if not self.job or not self.kernel.SetInformationJobObject(self.job, 9, ctypes.byref(limits), ctypes.sizeof(limits)) or not self.kernel.AssignProcessToJobObject(self.job, int(proc._handle)):
                if self.job:
                    self.kernel.CloseHandle(self.job)
                    self.job = None
                proc.kill()
                proc.wait(timeout=5)
                raise ValueError("Cannot create the required supervised process job")

    def stop(self):
        if self.job:
            self.kernel.TerminateJobObject(self.job, 1)
        else:
            try:
                os.killpg(self.proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        try:
            self.proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            return False
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            if self.job:
                class Accounting(ctypes.Structure):
                    _fields_ = [("times", ctypes.c_longlong * 4), ("faults", ctypes.c_uint32),
                                ("total", ctypes.c_uint32), ("active", ctypes.c_uint32), ("terminated", ctypes.c_uint32)]
                info = Accounting()
                if not self.kernel.QueryInformationJobObject(self.job, 1, ctypes.byref(info), ctypes.sizeof(info), None):
                    return False
                if info.active == 0:
                    return True
            else:
                try:
                    os.killpg(self.proc.pid, 0)
                except ProcessLookupError:
                    return True
            time.sleep(.05)
        return False

    def close(self):
        if self.job:
            self.kernel.CloseHandle(self.job)
            self.job = None


def run_process(argv, cwd, body: bytes, *, timeout, cancelled, emit,
                started=lambda proc: None, limit=3_000_000, env=None):
    if cancelled():
        raise ProcessFailure("Cancelled before start", {"process_exited": True, "tree_stopped": True}, cancelled=True)
    if not argv or any(not isinstance(x, str) or "\x00" in x for x in argv):
        raise ValueError("Invalid subprocess argument vector")
    if Path(argv[0]).suffix.lower() in {".cmd", ".bat", ".ps1"}:
        raise ValueError("Configure the native executable/Node entrypoint, not a shell shim")
    proc = subprocess.Popen(argv, cwd=cwd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            shell=False, env=private_environment() if env is None else env,
                            start_new_session=os.name != "nt",
                            creationflags=(subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP) if os.name == "nt" else 0)
    group = ProcessGroup(proc)
    output = {"stdout": bytearray(), "stderr": bytearray()}
    lock, overflow = Lock(), Event()
    count = [0]
    readers = []
    def drain(name, stream):
        while True:
            chunk = stream.read1(8192)
            if not chunk:
                break
            with lock:
                count[0] += len(chunk)
                remaining = max(0, limit - sum(len(v) for v in output.values()))
                output[name].extend(chunk[:remaining])
                if count[0] > limit:
                    overflow.set()
            if name == "stdout" and remaining:
                emit(chunk[:remaining].decode("utf-8", errors="replace"))
    def write():
        try:
            proc.stdin.write(body)
            proc.stdin.flush()
        except (OSError, BrokenPipeError):
            pass
        finally:
            try:
                proc.stdin.close()
            except OSError:
                pass
    try:
        started(proc)
        for name in output:
            thread = Thread(target=drain, args=(name, getattr(proc, name)), daemon=True)
            thread.start()
            readers.append(thread)
        writer = Thread(target=write, daemon=True)
        writer.start()
        deadline = time.monotonic() + timeout
        reason = None
        while proc.poll() is None:
            if cancelled():
                reason = "cancelled"
                break
            if overflow.is_set():
                reason = "output limit exceeded"
                break
            if time.monotonic() >= deadline:
                reason = "time limit exceeded"
                break
            time.sleep(.05)
        stopped = group.stop()
        writer.join(timeout=1)
        for reader in readers:
            reader.join(timeout=1)
        receipt = {"pid": proc.pid, "process_exited": proc.poll() is not None,
                   "tree_stopped": stopped, "exit_code": proc.returncode}
        if not stopped:
            raise ProcessFailure("Process tree could not be confirmed stopped", receipt)
        if reason or overflow.is_set() or proc.returncode:
            raise ProcessFailure("Harness " + (reason or f"exited with status {proc.returncode}"), receipt,
                                 cancelled=reason == "cancelled", diagnostic={key: bytes(value) for key, value in output.items()})
        return bytes(output["stdout"]), receipt
    finally:
        group.stop()
        group.close()
        for stream in (proc.stdin, proc.stdout, proc.stderr):
            try:
                stream.close()
            except OSError:
                pass
