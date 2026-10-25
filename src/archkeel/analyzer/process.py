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
from enum import Enum
from pathlib import Path, PurePosixPath
from queue import Empty, Queue
from threading import TIMEOUT_MAX, Thread
from typing import BinaryIO

from archkeel.ir.facts import (
    Language,
    ProviderBindingKind,
    ResolutionRole,
    SourceFacts,
    SourceProfile,
)
from archkeel.ir.facts_codec import (
    DEFAULT_RESPONSE_LIMIT_BYTES,
    ProtocolError,
    decode_response,
    encode_request,
)
from archkeel.ir.phases import Phase, PhaseClock, WorkCounter, measured
from archkeel.ir.protocol import (
    FEATURE_GATED_PROTOCOLS,
    PYTHON_IMPORT_SURVEY_SECTIONS,
    CollectionError,
    CollectionErrorKind,
    CollectionRequest,
    CollectionResponse,
    PythonCollectionPhase,
    PythonSettings,
    collected_resolution_features,
)


class _OutputLimitError(ValueError):
    pass


class _ProcessCleanupError(RuntimeError):
    pass


_CLEANUP_TIMEOUT_SECONDS = 2


class _ProcessPlatform(Enum):
    POSIX = "posix"
    WINDOWS = "nt"


def _process_platform(name: str) -> _ProcessPlatform | None:
    try:
        return _ProcessPlatform(name)
    except ValueError:
        return None


@dataclass(frozen=True, slots=True)
class ProcessCollector:
    argv: tuple[str, ...]
    timeout_seconds: float = 300
    output_limit_bytes: int = DEFAULT_RESPONSE_LIMIT_BYTES
    stderr_limit_bytes: int = 64 * 1024
    # Set only for a run with --timings; None measures nothing.
    clock: PhaseClock | None = None

    def __post_init__(self) -> None:
        if not self.argv or any(not value or "\x00" in value for value in self.argv):
            raise ValueError("collector argv must contain nonempty arguments")
        if (
            not 0 < self.timeout_seconds <= TIMEOUT_MAX
            or self.output_limit_bytes <= 0
            or self.stderr_limit_bytes <= 0
        ):
            raise ValueError(
                "collector limits must be positive; timeout must fit threading.TIMEOUT_MAX"
            )

    def collect(self, request: CollectionRequest) -> SourceFacts | CollectionError:
        response = self.collect_response(request)
        return response if isinstance(response, CollectionError) else response.facts

    def collect_response(self, request: CollectionRequest) -> CollectionResponse | CollectionError:
        subject = self.argv[0]
        try:
            payload = encode_request(request)
            command = self.argv
            environment = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
            platform = _process_platform(os.name)
            if platform is _ProcessPlatform.WINDOWS:
                search_path = os.pathsep.join((request.snapshot.root, environment.get("PATH", "")))
                executable = shutil.which(self.argv[0], path=search_path)
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
                command = (sys.executable, "-I", "-B", str(helper), "--", *self.argv)
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
                    stdout, stderr = self._exchange(process, payload, workers)
                finally:
                    cleanup_error = _cleanup_exchange(process, workers)
                    if cleanup_error is not None:
                        raise cleanup_error
                if process.returncode:
                    message = stderr.decode("utf-8", errors="replace").strip()
                    return CollectionError(
                        CollectionErrorKind.EXECUTION_ERROR,
                        subject,
                        f"Collector exited {process.returncode}: {message}",
                    )
            if self.clock is not None:
                self.clock.count(WorkCounter.COLLECTOR_WIRE_BYTES, len(stdout))
            with measured(self.clock, Phase.DECODE):
                response = decode_response(stdout, output_limit=self.output_limit_bytes)
                _requested_facts(response.facts, request)
                _requested_provider_sources(response, request)
            return response
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


def _requested_provider_sources(response: CollectionResponse, request: CollectionRequest) -> None:
    discovery = (
        isinstance(request.resolver, PythonSettings)
        and request.resolver.phase is PythonCollectionPhase.PROVIDERS
    )
    expected = {
        item.path: item.digest
        for item in response.facts.inputs
        if item.path.startswith(".archkeel-providers/")
    }
    captured = {item.path: item.digest for item in response.provider_sources}
    if (discovery and captured != expected) or (not discovery and captured):
        raise ProtocolError("collector captured provider sources disagree with discovery inputs")


def _requested_facts(facts: SourceFacts, request: CollectionRequest) -> None:
    profiles: dict[Language, SourceProfile] = {
        Language.PYTHON: SourceProfile.PYTHON,
        Language.DART: SourceProfile.DART,
        Language.TYPESCRIPT: SourceProfile.TYPESCRIPT,
    }
    if facts.profile != profiles[request.resolver.language]:
        raise ProtocolError("collector profile disagrees with requested language")
    if (
        isinstance(request.resolver, PythonSettings)
        and request.resolver.phase is not PythonCollectionPhase.COLLECT
        and frozenset(facts.capabilities.sections) != frozenset(PYTHON_IMPORT_SURVEY_SECTIONS)
    ):
        raise ProtocolError("collector sections disagree with requested import survey")
    if (
        request.protocol_version in FEATURE_GATED_PROTOCOLS
        and isinstance(request.resolver, PythonSettings)
        and request.resolver.phase is PythonCollectionPhase.COLLECT
        and frozenset(facts.capabilities.resolution_features)
        != frozenset(
            collected_resolution_features(request.protocol_version, request.resolver.features)
        )
    ):
        raise ProtocolError("collector resolution features disagree with requested features")
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
    providers = (
        request.resolver.provider_sources if isinstance(request.resolver, PythonSettings) else ()
    )
    discovery = (
        isinstance(request.resolver, PythonSettings)
        and request.resolver.phase is PythonCollectionPhase.PROVIDERS
    )
    expected = {item.path: item.digest for item in providers}
    actual: dict[str, str] = {}
    for item in facts.inputs:
        path: str = item.path
        if path.startswith(".archkeel-providers/") and item.role is ResolutionRole.RESOLUTION:
            actual[path] = item.digest
    if (not discovery and actual != expected) or set(actual) & set(facts.coverage.selected_files):
        raise ProtocolError("collector provider sources disagree with requested snapshot")
    providers_by_path = {item.path: item for item in providers}
    evidence = {item.id: item for item in facts.evidence}
    for binding in facts.provider_bindings:
        if discovery:
            continue
        source = providers_by_path.get(evidence[binding.evidence_id].file)
        qualified_name: str = binding.qualified_name
        source_matches = source is not None and (
            qualified_name == source.module
            if binding.kind is ProviderBindingKind.MODULE
            else qualified_name.rpartition(".")[0] == source.module
            if binding.kind is ProviderBindingKind.ALIAS
            else qualified_name.startswith(source.module + ".")
        )
        if not source_matches:
            raise ProtocolError("collector provider binding disagrees with requested source")


def _terminate_process_tree(process: subprocess.Popen[bytes]) -> None:
    platform = _process_platform(os.name)
    if platform is _ProcessPlatform.POSIX:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        except OSError as error:
            raise _ProcessCleanupError(
                "Could not terminate the collector process group."
            ) from error
    elif platform is _ProcessPlatform.WINDOWS:
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
