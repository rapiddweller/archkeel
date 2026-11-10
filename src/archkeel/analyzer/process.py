# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Bounded source collection and cross-platform process lifecycle helpers."""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import sys
import time
from dataclasses import dataclass, replace
from enum import Enum
from pathlib import Path
from queue import Empty, Queue
from threading import TIMEOUT_MAX, Thread
from typing import BinaryIO

from archkeel.analyzer.memory_limit import COLLECTOR_MEMORY_LIMIT_BYTES, exit_message, limit_memory
from archkeel.analyzer.pin import PinError, is_pin, pinned_path
from archkeel.analyzer.reply_checks import check_reply
from archkeel.analyzer.runtime import package_version
from archkeel.ir.facts import SourceFacts
from archkeel.ir.facts_codec import (
    DEFAULT_RESPONSE_LIMIT_BYTES,
    MAX_RESPONSE_LIMIT_BYTES,
    ProtocolError,
    decode_response,
    encode_request,
)
from archkeel.ir.phases import Phase, PhaseClock, WorkCounter, measured
from archkeel.ir.protocol import (
    CollectionError,
    CollectionErrorKind,
    CollectionRequest,
    CollectionResponse,
    ProtocolVersion,
)


class _OutputLimitError(ValueError):
    pass


class _ProcessCleanupError(RuntimeError):
    pass


_CLEANUP_TIMEOUT_SECONDS = 2
_EXIT_GRACE_SECONDS = 0.5
_DEFAULT_OUTPUT_LIMIT_REMEDY = "Raise collector_output_limit_bytes and retry."
_STDERR_LINES_REPORTED = 20
# Supported POSIX targets use signed 32-bit pid_t; Windows process IDs are DWORDs.
_POSIX_PID_MAX = (1 << 31) - 1
_WINDOWS_PID_MAX = (1 << 32) - 1


class _ProcessPlatform(Enum):
    POSIX = "posix"
    WINDOWS = "nt"


def _process_platform(name: str) -> _ProcessPlatform | None:
    try:
        return _ProcessPlatform(name)
    except ValueError:
        return None


def is_safe_process_id(pid: int) -> bool:
    """Whether a PID is safe for Studio process APIs on this platform (PID 0/1 are rejected)."""
    if type(pid) is not int or pid <= 1:
        return False
    platform = _process_platform(os.name)
    if platform is _ProcessPlatform.POSIX:
        return pid <= _POSIX_PID_MAX
    if platform is _ProcessPlatform.WINDOWS:
        return pid <= _WINDOWS_PID_MAX
    return False


@dataclass(frozen=True, slots=True)
class ProcessCollector:
    argv: tuple[str, ...]
    timeout_seconds: float = 300
    output_limit_bytes: int = DEFAULT_RESPONSE_LIMIT_BYTES
    stderr_limit_bytes: int = 64 * 1024
    # Set only for a run with --timings; None measures nothing.
    clock: PhaseClock | None = None
    output_limit_remedy: str = _DEFAULT_OUTPUT_LIMIT_REMEDY
    # Collectors without a pinned version accept any valid response version.
    protocol_version: ProtocolVersion | None = None
    memory_limit_bytes: int = COLLECTOR_MEMORY_LIMIT_BYTES
    # Set for a collector of this package: its reply must carry the host version (AD-319).
    pin_adapter_version: bool = False
    # Set for a configured collector that the user pins: its file must have this digest (AD-344).
    pinned_digest: str | None = None

    def __post_init__(self) -> None:
        if self.pinned_digest is not None and not is_pin(self.pinned_digest):
            raise ValueError("collector digest must be sha256: and 64 lowercase hexadecimal digits")
        if not self.argv or any(not value or "\x00" in value for value in self.argv):
            raise ValueError("collector argv must contain nonempty arguments")
        if not 0 < self.timeout_seconds <= TIMEOUT_MAX:
            raise ValueError(
                "collector limits must be positive; timeout must fit threading.TIMEOUT_MAX"
            )
        if (
            not isinstance(self.output_limit_bytes, int)
            or isinstance(self.output_limit_bytes, bool)
            or not 0 < self.output_limit_bytes <= MAX_RESPONSE_LIMIT_BYTES
        ):
            raise ValueError(
                "collector output limit must be a positive integer no greater than "
                f"{MAX_RESPONSE_LIMIT_BYTES} bytes"
            )
        if self.stderr_limit_bytes <= 0 or self.memory_limit_bytes <= 0:
            raise ValueError("collector limits must be positive")

    def collect(self, request: CollectionRequest) -> SourceFacts | CollectionError:
        response = self.collect_response(request)
        return response if isinstance(response, CollectionError) else response.facts

    def collect_response(self, request: CollectionRequest) -> CollectionResponse | CollectionError:
        subject = self.argv[0]
        try:
            wire_request = (
                replace(request, protocol_version=self.protocol_version)
                if self.protocol_version is not None and not request.scope.exclude_test_sources
                else request
            )
            payload = encode_request(wire_request)
            environment = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "LC_ALL": "C"}  # AD-325
            platform = _process_platform(os.name)
            command = self._launch_argv(request, environment)
            if isinstance(command, CollectionError):
                return command
            if platform is _ProcessPlatform.WINDOWS:
                search_path = os.pathsep.join((request.snapshot.root, environment.get("PATH", "")))
                executable = shutil.which(command[0], path=search_path)
                if executable is None:
                    return CollectionError(
                        CollectionErrorKind.MISSING_TOOL,
                        subject,
                        f"Collector could not execute: {subject}",
                    )
                if Path(executable).suffix.lower() in {".bat", ".cmd"}:
                    return CollectionError(
                        CollectionErrorKind.EXECUTION_ERROR,
                        subject,
                        "Windows .bat/.cmd collector shims cannot run without a shell; "
                        "configure an explicit executable and script argv.",
                    )
                helper = Path(__file__).with_name("windows_job.py")
                limit = f"--memory-limit-bytes={self.memory_limit_bytes}"
                command = (sys.executable, "-I", "-B", str(helper), limit, "--", *command)
            with (
                measured(self.clock, Phase.COLLECT),
                subprocess.Popen(
                    command,
                    cwd=request.snapshot.root,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    bufsize=0,
                    env=environment,
                    start_new_session=platform is _ProcessPlatform.POSIX,
                ) as process,
            ):
                workers: list[Thread] = []
                try:
                    if refused := limit_memory(process.pid, self.memory_limit_bytes):
                        error_kind = CollectionErrorKind.EXECUTION_ERROR
                        return CollectionError(error_kind, subject, refused)
                    stdout, stderr = self._exchange(process, payload, workers)
                finally:
                    cleanup_error = _cleanup_exchange(process, workers)
                    if cleanup_error is not None:
                        raise cleanup_error
                if process.returncode:
                    lines = stderr.decode("utf-8", errors="replace").strip().splitlines()
                    message = "\n".join(lines[-_STDERR_LINES_REPORTED:])
                    return CollectionError(
                        CollectionErrorKind.EXECUTION_ERROR,
                        subject,
                        exit_message(process.returncode, message, self.memory_limit_bytes),
                    )
            if self.clock is not None:
                self.clock.count(WorkCounter.COLLECTOR_WIRE_BYTES, len(stdout))
            return self._decode_response(stdout, wire_request)
        except subprocess.TimeoutExpired:
            return CollectionError(
                CollectionErrorKind.TIMEOUT,
                subject,
                f"Collector exceeded {self.timeout_seconds:g} seconds. "
                "Raise collector_timeout_seconds in [scan].",
            )
        except OSError as error:
            return CollectionError(
                CollectionErrorKind.MISSING_TOOL, subject, f"Collector could not execute: {error}"
            )
        except (ProtocolError, _OutputLimitError) as error:
            return CollectionError(CollectionErrorKind.PROTOCOL_ERROR, subject, str(error))

    def _launch_argv(
        self, request: CollectionRequest, environment: dict[str, str]
    ) -> tuple[str, ...] | CollectionError:
        """The argv to start: for a pinned collector, its checked absolute path and the rest."""
        if self.pinned_digest is None:
            return self.argv
        try:
            path = pinned_path(
                self.argv[0], request.snapshot.root, environment.get("PATH", ""), self.pinned_digest
            )
        except PinError as error:
            return CollectionError(CollectionErrorKind.EXECUTION_ERROR, self.argv[0], str(error))
        return (path, *self.argv[1:])

    def _decode_response(self, stdout: bytes, request: CollectionRequest) -> CollectionResponse:
        with measured(self.clock, Phase.DECODE):
            response = decode_response(stdout, output_limit=self.output_limit_bytes)
            check_reply(
                response,
                request,
                protocol_version=self.protocol_version,
                adapter_version=package_version() if self.pin_adapter_version else None,
            )
        return response

    def _exchange(
        self, process: subprocess.Popen[bytes], payload: bytes, workers: list[Thread]
    ) -> tuple[bytes, bytes]:
        if process.stdin is None or process.stdout is None or process.stderr is None:
            raise OSError("collector pipes were not created")
        deadline = time.monotonic() + self.timeout_seconds
        completed: Queue[tuple[str, bytes | OSError | _OutputLimitError]] = Queue()

        def read_output(
            name: str, stream: BinaryIO, limit: int, remedy: str, keep_tail: bool
        ) -> None:
            output = bytearray()
            try:
                while chunk := stream.read(64 * 1024):
                    if not keep_tail and len(output) + len(chunk) > limit:
                        raise _OutputLimitError(
                            f"Collector output exceeded its {limit} byte limit.{remedy}"
                        )
                    output.extend(chunk)
                    if keep_tail:
                        # Only the end of stderr explains a crash, so a long trace must not fail.
                        del output[:-limit]
                completed.put((name, bytes(output)))
            except (OSError, _OutputLimitError) as error:
                completed.put((name, error))

        def write_input(stream: BinaryIO) -> None:
            try:
                sent = 0
                while sent < len(payload):
                    written = stream.write(payload[sent:])
                    if written is None or written == 0:
                        raise OSError("collector stdin could not accept the request")
                    sent += written
                stream.close()
            except BrokenPipeError:
                pass
            except OSError as error:
                completed.put(("stdin", error))
                return
            completed.put(("stdin", b""))

        # Pipe selectors are unavailable on Windows. Separate readers also drain
        # stderr while a collector writes stdout or waits for its request.
        readers_and_writer = (
            Thread(target=write_input, args=(process.stdin,), daemon=True),
            Thread(
                target=read_output,
                args=(
                    "stdout",
                    process.stdout,
                    self.output_limit_bytes,
                    f" {self.output_limit_remedy}",
                    False,
                ),
                daemon=True,
            ),
            Thread(
                target=read_output,
                args=("stderr", process.stderr, self.stderr_limit_bytes, "", True),
                daemon=True,
            ),
        )
        workers.extend(readers_and_writer)
        for worker in workers:
            worker.start()
        results: dict[str, bytes] = {}
        while len(results) < len(workers):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise subprocess.TimeoutExpired(self.argv, self.timeout_seconds)
            try:
                name, result = completed.get(timeout=remaining)
            except Empty as error:
                raise subprocess.TimeoutExpired(self.argv, self.timeout_seconds) from error
            if isinstance(result, (OSError, _OutputLimitError)):
                raise result
            results[name] = result
        process.wait(timeout=max(0, deadline - time.monotonic()))
        return results["stdout"], results["stderr"]


def _terminate_process_tree(process: subprocess.Popen[bytes]) -> None:
    platform = _process_platform(os.name)
    if platform is _ProcessPlatform.POSIX:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except OSError as error:
            # macOS fails with EPERM while it tears down an exiting group.
            try:
                process.wait(timeout=_EXIT_GRACE_SECONDS)
            except subprocess.TimeoutExpired:
                raise _ProcessCleanupError(
                    "Could not terminate the collector process group."
                ) from error
    else:
        message = (
            "Could not terminate the Windows job launcher."
            if platform is _ProcessPlatform.WINDOWS
            else "Could not terminate the collector process."
        )
        if process.poll() is None:
            try:
                process.kill()
            except OSError as error:
                raise _ProcessCleanupError(message) from error

    try:
        process.wait(timeout=_CLEANUP_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired as error:
        raise _ProcessCleanupError(
            "Collector did not stop after process-tree termination."
        ) from error


def _close_pipes(process: subprocess.Popen[bytes]) -> None:
    errors: list[OSError] = []
    for stream in (process.stdin, process.stdout, process.stderr):
        if stream is not None:
            try:
                stream.close()
            except OSError as error:
                errors.append(error)
    if errors:
        raise _ProcessCleanupError(
            "Could not close collector pipes: " + "; ".join(str(error) for error in errors)
        )


def _cleanup_exchange(
    process: subprocess.Popen[bytes], workers: list[Thread]
) -> _ProcessCleanupError | None:
    failures: list[str] = []
    try:
        _terminate_process_tree(process)
    except _ProcessCleanupError as error:
        failures.append(_cleanup_failure(error))
    try:
        _close_pipes(process)
    except _ProcessCleanupError as error:
        failures.append(_cleanup_failure(error))
    join_deadline = time.monotonic() + _CLEANUP_TIMEOUT_SECONDS
    for worker in workers:
        worker.join(max(0, join_deadline - time.monotonic()))
    alive_workers = [worker.name for worker in workers if worker.is_alive()]
    if alive_workers:
        failures.append("Collector pipe workers did not stop: " + ", ".join(alive_workers))
    if failures:
        return _ProcessCleanupError("; ".join(failures))
    return None


def _cleanup_failure(error: _ProcessCleanupError) -> str:
    if error.__cause__ is not None:
        return f"{error}: {error.__cause__}"
    return str(error)


def is_process_alive(pid: int) -> bool:
    """Check liveness without signaling a Windows PID; unknown results preserve state."""
    if type(pid) is not int or pid <= 1:
        return False
    platform = _process_platform(os.name)
    if platform is None or not is_safe_process_id(pid):
        return True
    if platform is _ProcessPlatform.POSIX:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except OSError:
            return True
        return True
    if platform is not _ProcessPlatform.WINDOWS:
        return True

    import ctypes
    from ctypes import wintypes

    try:
        # POSIX mypy stubs omit this Windows-only API.
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)  # type: ignore[attr-defined]
        kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.WaitForSingleObject.argtypes = (wintypes.HANDLE, wintypes.DWORD)
        kernel32.WaitForSingleObject.restype = wintypes.DWORD
        kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
        kernel32.CloseHandle.restype = wintypes.BOOL

        # SYNCHRONIZE permits a zero-time wait; PROCESS_TERMINATE is never requested.
        handle = kernel32.OpenProcess(0x00100000, False, pid)
        if not handle:
            # ERROR_INVALID_PARAMETER means the PID is gone; other errors are UNKNOWN.
            error: int = ctypes.get_last_error()  # type: ignore[attr-defined]
            return error != 87

        try:
            result = kernel32.WaitForSingleObject(handle, 0)
        finally:
            closed = kernel32.CloseHandle(handle)
        if not closed:
            return True
        if result == 0:  # WAIT_OBJECT_0: process exited.
            return False
        if result == 258:  # WAIT_TIMEOUT: process remains live.
            return True
        return True  # WAIT_FAILED and unexpected values are UNKNOWN.
    except (AttributeError, OSError, TypeError, ValueError, ctypes.ArgumentError):
        return True
