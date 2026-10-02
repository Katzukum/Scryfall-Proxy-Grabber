"""Keep native worker descendants inside a process owner that dies with the app."""

from __future__ import annotations

import ctypes
import os
import signal
import subprocess


class _BasicLimitInformation(ctypes.Structure):
    _fields_ = [
        ("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64),
        ("LimitFlags", ctypes.c_uint32), ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", ctypes.c_uint32),
        ("Affinity", ctypes.c_size_t), ("PriorityClass", ctypes.c_uint32), ("SchedulingClass", ctypes.c_uint32),
    ]


class _IoCounters(ctypes.Structure):
    _fields_ = [(name, ctypes.c_uint64) for name in (
        "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
        "ReadTransferCount", "WriteTransferCount", "OtherTransferCount",
    )]


class _ExtendedLimitInformation(ctypes.Structure):
    _fields_ = [
        ("BasicLimitInformation", _BasicLimitInformation), ("IoInfo", _IoCounters),
        ("ProcessMemoryLimit", ctypes.c_size_t), ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t), ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]


class _ThreadEntry(ctypes.Structure):
    _fields_ = [
        ("dwSize", ctypes.c_uint32), ("cntUsage", ctypes.c_uint32),
        ("th32ThreadID", ctypes.c_uint32), ("th32OwnerProcessID", ctypes.c_uint32),
        ("tpBasePri", ctypes.c_int32), ("tpDeltaPri", ctypes.c_int32), ("dwFlags", ctypes.c_uint32),
    ]


def _windows_api():
    api = ctypes.WinDLL("kernel32", use_last_error=True)
    handle, uint, boolean = ctypes.c_void_p, ctypes.c_uint32, ctypes.c_int
    signatures = {
        "CreateJobObjectW": ([handle, ctypes.c_wchar_p], handle),
        "SetInformationJobObject": ([handle, ctypes.c_int, handle, uint], boolean),
        "AssignProcessToJobObject": ([handle, handle], boolean),
        "TerminateJobObject": ([handle, uint], boolean),
        "CloseHandle": ([handle], boolean),
        "CreateToolhelp32Snapshot": ([uint, uint], handle),
        "Thread32First": ([handle, ctypes.POINTER(_ThreadEntry)], boolean),
        "Thread32Next": ([handle, ctypes.POINTER(_ThreadEntry)], boolean),
        "OpenThread": ([uint, boolean, uint], handle),
        "ResumeThread": ([handle], uint),
    }
    for name, (arguments, result) in signatures.items():
        function = getattr(api, name)
        function.argtypes, function.restype = arguments, result
    return api


class WorkerProcessTree:
    """Attach before resuming the child, so launchers cannot escape ownership."""

    def __init__(self):
        self._job = None
        self._pid = None
        self._api = None
        if os.name == "nt":
            self._api = _windows_api()
            self._job = self._api.CreateJobObjectW(None, None)
            if not self._job:
                raise ctypes.WinError(ctypes.get_last_error())
            limits = _ExtendedLimitInformation()
            limits.BasicLimitInformation.LimitFlags = 0x00002000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            if not self._api.SetInformationJobObject(self._job, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
                error = ctypes.WinError(ctypes.get_last_error())
                self.close()
                raise error

    def popen_options(self) -> dict:
        if os.name == "nt":
            return {"creationflags": subprocess.CREATE_NO_WINDOW | 0x00000004}  # CREATE_SUSPENDED
        return {"start_new_session": True}

    def attach(self, process) -> None:
        self._pid = process.pid
        if self._api is None:
            return
        if not self._api.AssignProcessToJobObject(self._job, int(process._handle)):
            raise ctypes.WinError(ctypes.get_last_error())
        # Popen closes the initial thread handle. Find the still-suspended
        # primary thread with documented Toolhelp APIs and resume it only now.
        snapshot = self._api.CreateToolhelp32Snapshot(0x00000004, 0)  # TH32CS_SNAPTHREAD
        if snapshot == ctypes.c_void_p(-1).value:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            entry = _ThreadEntry()
            entry.dwSize = ctypes.sizeof(entry)
            found = self._api.Thread32First(snapshot, ctypes.byref(entry))
            while found:
                if entry.th32OwnerProcessID == process.pid:
                    thread = self._api.OpenThread(0x0002, False, entry.th32ThreadID)  # THREAD_SUSPEND_RESUME
                    if not thread:
                        raise ctypes.WinError(ctypes.get_last_error())
                    try:
                        if self._api.ResumeThread(thread) == 0xFFFFFFFF:
                            raise ctypes.WinError(ctypes.get_last_error())
                        return
                    finally:
                        self._api.CloseHandle(thread)
                found = self._api.Thread32Next(snapshot, ctypes.byref(entry))
            raise OSError("The suspended image worker's primary thread could not be found.")
        finally:
            self._api.CloseHandle(snapshot)

    def close(self) -> None:
        if self._job is not None:
            job, self._job = self._job, None
            # Terminate immediately and close our non-inherited handle. The
            # configured limit also covers unexpected parent process exit.
            self._api.TerminateJobObject(job, 1)
            self._api.CloseHandle(job)
        elif self._api is None and self._pid is not None:
            pid, self._pid = self._pid, None
            try:
                os.killpg(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
