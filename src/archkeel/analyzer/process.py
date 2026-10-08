# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Bounded argv execution of a source-only collection protocol."""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from queue import Empty, Queue
from threading import Thread
from typing import BinaryIO

from archkeel.ir.facts import SourceFacts, SourceProfile
from archkeel.ir.facts_codec import ProtocolError, decode_response, encode_request
from archkeel.ir.protocol import CollectionError, CollectionRequest


class _OutputLimitError(ValueError):
    pass


class _ProcessCleanupError(RuntimeError):
    pass


_CLEANUP_TIMEOUT_SECONDS = 2


@dataclass(frozen=True, slots=True)
class ProcessCollector:
    argv: tuple[str, ...]
    timeout_seconds: float = 300
    output_limit_bytes: int = 64 * 1024 * 1024
    stderr_limit_bytes: int = 64 * 1024

    def __post_init__(self) -> None:
        if not self.argv or any(not value or "\x00" in value for value in self.argv):
            raise ValueError("collector argv must contain nonempty arguments")
        if (
            self.timeout_seconds <= 0
            or self.output_limit_bytes <= 0
            or self.stderr_limit_bytes <= 0
        ):
            raise ValueError("collector limits must be positive")

    def collect(self, request: CollectionRequest) -> SourceFacts | CollectionError:
        subject = self.argv[0]
        try:
            payload = encode_request(request)
            command = self.argv
            environment = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
            if os.name == "nt":
                search_path = os.pathsep.join((request.snapshot.root, environment.get("PATH", "")))
                executable = shutil.which(self.argv[0], path=search_path)
                if executable is None:
                    return CollectionError(
                        "missing_tool", subject, f"Collector could not execute: {subject}"
                    )
                if Path(executable).suffix.lower() in {".bat", ".cmd"}:
                    return CollectionError(
                        "execution_error",
                        subject,
                        "Windows .bat/.cmd collector shims cannot run without a shell; "
                        "configure an explicit executable and script argv.",
                    )
                helper = Path(__file__).with_name("windows_job.py")
                command = (sys.executable, "-I", "-B", str(helper), "--", *self.argv)
            with subprocess.Popen(
                command,
                cwd=request.snapshot.root,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                bufsize=0,
                env=environment,
                start_new_session=os.name == "posix",
            ) as process:
                workers: list[Thread] = []
                try:
                    stdout, stderr = self._exchange(process, payload, workers)
                finally:
                    cleanup_error = _cleanup_exchange(process, workers)
                    if cleanup_error is not None:
                        raise cleanup_error
                if process.returncode:
                    message = stderr.decode("utf-8", errors="replace").strip()
                    return CollectionError(
                        "execution_error",
                        subject,
                        f"Collector exited {process.returncode}: {message}",
                    )
            facts = decode_response(stdout).facts
            _requested_facts(facts, request)
            return facts
        except subprocess.TimeoutExpired:
            return CollectionError(
                "timeout", subject, f"Collector exceeded {self.timeout_seconds:g} seconds."
            )
        except OSError as error:
            return CollectionError("missing_tool", subject, f"Collector could not execute: {error}")
        except (ProtocolError, _OutputLimitError) as error:
            return CollectionError("protocol_error", subject, str(error))

    def _exchange(
        self, process: subprocess.Popen[bytes], payload: bytes, workers: list[Thread]
    ) -> tuple[bytes, bytes]:
        if process.stdin is None or process.stdout is None or process.stderr is None:
            raise OSError("collector pipes were not created")
        deadline = time.monotonic() + self.timeout_seconds
        completed: Queue[tuple[str, bytes | OSError | _OutputLimitError]] = Queue()

        def read_output(name: str, stream: BinaryIO, limit: int) -> None:
            output = bytearray()
            try:
                while chunk := stream.read(64 * 1024):
                    if len(output) + len(chunk) > limit:
                        raise _OutputLimitError(
                            f"Collector output exceeded its {limit} byte limit."
                        )
                    output.extend(chunk)
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

        # Pipe selectors are unavailable on Windows. Separate bounded readers also drain
        # stderr while a collector writes stdout or waits for its request.
        readers_and_writer = (
            Thread(target=write_input, args=(process.stdin,), daemon=True),
            Thread(
                target=read_output,
                args=("stdout", process.stdout, self.output_limit_bytes),
                daemon=True,
            ),
            Thread(
                target=read_output,
                args=("stderr", process.stderr, self.stderr_limit_bytes),
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


def _requested_facts(facts: SourceFacts, request: CollectionRequest) -> None:
    profiles: dict[str, SourceProfile] = {
        "python": "archkeel-python-analyzer",
        "dart": "archkeel-dart-analyzer",
        "typescript": "archkeel-typescript-imports",
    }
    if facts.profile != profiles[request.resolver.language]:
        raise ProtocolError("collector profile disagrees with requested language")
    if (
        facts.source.git_head != request.snapshot.git_head
        or facts.source.dirty != request.snapshot.dirty
    ):
        raise ProtocolError("collector facts disagree with requested snapshot")
    roots = tuple(PurePosixPath(root) for root in request.scope.roots)
    if any(
        not any(PurePosixPath(path).is_relative_to(root) for root in roots)
        for path in facts.coverage.selected_files
    ):
        raise ProtocolError("collector selected files escape requested scope")


def _terminate_process_tree(process: subprocess.Popen[bytes]) -> None:
    if os.name == "posix":
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        except OSError as error:
            raise _ProcessCleanupError(
                "Could not terminate the collector process group."
            ) from error
    elif os.name == "nt":
        if process.poll() is None:
            try:
                process.kill()
            except OSError as error:
                raise _ProcessCleanupError(
                    "Could not terminate the Windows job launcher."
                ) from error
    else:
        if process.poll() is None:
            try:
                process.kill()
            except OSError as error:
                raise _ProcessCleanupError("Could not terminate the collector process.") from error

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
