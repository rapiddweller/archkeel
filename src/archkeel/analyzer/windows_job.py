# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Run one collector inside a kill-on-close Windows job that bounds process memory."""

from __future__ import annotations

import ctypes
import subprocess
import sys
from ctypes import wintypes

_JOB_OBJECT_LIMIT_PROCESS_MEMORY = 0x00000100
_JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
_JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9
_MEMORY_LIMIT_OPTION = "--memory-limit-bytes"


class _BasicLimitInformation(ctypes.Structure):
    _fields_ = [
        ("per_process_user_time_limit", ctypes.c_longlong),
        ("per_job_user_time_limit", ctypes.c_longlong),
        ("limit_flags", wintypes.DWORD),
        ("minimum_working_set_size", ctypes.c_size_t),
        ("maximum_working_set_size", ctypes.c_size_t),
        ("active_process_limit", wintypes.DWORD),
        ("affinity", ctypes.c_size_t),
        ("priority_class", wintypes.DWORD),
        ("scheduling_class", wintypes.DWORD),
    ]


class _IoCounters(ctypes.Structure):
    _fields_ = [
        ("read_operation_count", ctypes.c_ulonglong),
        ("write_operation_count", ctypes.c_ulonglong),
        ("other_operation_count", ctypes.c_ulonglong),
        ("read_transfer_count", ctypes.c_ulonglong),
        ("write_transfer_count", ctypes.c_ulonglong),
        ("other_transfer_count", ctypes.c_ulonglong),
    ]


class _ExtendedLimitInformation(ctypes.Structure):
    _fields_ = [
        ("basic_limit_information", _BasicLimitInformation),
        ("io_info", _IoCounters),
        ("process_memory_limit", ctypes.c_size_t),
        ("job_memory_limit", ctypes.c_size_t),
        ("peak_process_memory_used", ctypes.c_size_t),
        ("peak_job_memory_used", ctypes.c_size_t),
    ]


def _job_limit_information(memory_limit_bytes: int) -> _ExtendedLimitInformation:
    limits = _ExtendedLimitInformation()
    limits.basic_limit_information.limit_flags = (
        _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE | _JOB_OBJECT_LIMIT_PROCESS_MEMORY
    )
    # The limit is on the committed memory of each process in the job (AD-319).
    limits.process_memory_limit = memory_limit_bytes
    return limits


def _create_owned_job(memory_limit_bytes: int) -> wintypes.HANDLE:
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)  # type: ignore[attr-defined]
    kernel32.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    kernel32.CreateJobObjectW.restype = wintypes.HANDLE
    kernel32.SetInformationJobObject.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        ctypes.c_void_p,
        wintypes.DWORD,
    ]
    kernel32.SetInformationJobObject.restype = wintypes.BOOL
    kernel32.GetCurrentProcess.argtypes = []
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    kernel32.AssignProcessToJobObject.restype = wintypes.BOOL

    job: wintypes.HANDLE = kernel32.CreateJobObjectW(None, None)
    if not job:
        raise OSError("CreateJobObjectW failed")
    limits = _job_limit_information(memory_limit_bytes)
    if not kernel32.SetInformationJobObject(
        job,
        _JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
        ctypes.byref(limits),
        ctypes.sizeof(limits),
    ):
        raise OSError("SetInformationJobObject failed")
    if not kernel32.AssignProcessToJobObject(job, kernel32.GetCurrentProcess()):
        raise OSError("AssignProcessToJobObject failed")
    return job


def _memory_limit(option: str) -> int | None:
    name, _, value = option.partition("=")
    try:
        limit = int(value)
    except ValueError:
        return None
    return limit if name == _MEMORY_LIMIT_OPTION and limit > 0 else None


def _parse(arguments: list[str]) -> tuple[int, list[str]] | None:
    """Read `--memory-limit-bytes=<bytes> -- <collector argv>`."""
    if len(arguments) < 3 or arguments[1] != "--":
        return None
    limit = _memory_limit(arguments[0])
    return None if limit is None else (limit, arguments[2:])


def main(arguments: list[str] | None = None) -> int:
    if sys.platform != "win32":
        print("The Windows job launcher only runs on Windows.", file=sys.stderr)
        return 2
    parsed = _parse(sys.argv[1:] if arguments is None else arguments)
    if parsed is None:
        print(
            f"Expected {_MEMORY_LIMIT_OPTION}=<bytes> -- followed by the collector argv.",
            file=sys.stderr,
        )
        return 2
    memory_limit_bytes, command = parsed
    try:
        _job = _create_owned_job(memory_limit_bytes)
    except OSError as error:
        print(f"Could not create the collector process job: {error}", file=sys.stderr)
        return 125
    # Process exit closes this non-inheritable handle and kills any surviving job members.
    try:
        return subprocess.run(command, check=False).returncode
    except OSError as error:
        print(f"Could not execute the collector: {error}", file=sys.stderr)
        return 126


if __name__ == "__main__":
    raise SystemExit(main())
