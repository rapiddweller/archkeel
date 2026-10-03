# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Bounded argv execution of a source-only collection protocol."""

from __future__ import annotations

import os
import selectors
import subprocess
import time
from dataclasses import dataclass
from pathlib import PurePosixPath

from archkeel.ir.facts import SourceFacts, SourceProfile
from archkeel.ir.facts_codec import ProtocolError, decode_response, encode_request
from archkeel.ir.protocol import CollectionError, CollectionRequest


class _OutputLimitError(ValueError):
    pass


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
            with subprocess.Popen(
                self.argv,
                cwd=request.snapshot.root,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
            ) as process:
                try:
                    stdout, stderr = self._exchange(process, payload)
                except (subprocess.TimeoutExpired, _OutputLimitError, OSError):
                    process.kill()
                    process.wait()
                    raise
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

    def _exchange(self, process: subprocess.Popen[bytes], payload: bytes) -> tuple[bytes, bytes]:
        assert (
            process.stdin is not None and process.stdout is not None and process.stderr is not None
        )
        streams = (process.stdin, process.stdout, process.stderr)
        input_fd, output_fd, error_fd = (stream.fileno() for stream in streams)
        for stream in streams:
            os.set_blocking(stream.fileno(), False)
        deadline = time.monotonic() + self.timeout_seconds
        sent = 0
        output = bytearray()
        errors = bytearray()
        with selectors.DefaultSelector() as selector:
            selector.register(input_fd, selectors.EVENT_WRITE)
            selector.register(output_fd, selectors.EVENT_READ)
            selector.register(error_fd, selectors.EVENT_READ)
            while selector.get_map():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise subprocess.TimeoutExpired(self.argv, self.timeout_seconds)
                for key, _ in selector.select(remaining):
                    if key.fd == input_fd:
                        try:
                            sent += os.write(input_fd, payload[sent:])
                        except BrokenPipeError:
                            sent = len(payload)
                        if sent == len(payload):
                            selector.unregister(input_fd)
                            process.stdin.close()
                        continue
                    data = os.read(key.fd, 64 * 1024)
                    if not data:
                        selector.unregister(key.fd)
                        continue
                    target = output if key.fd == output_fd else errors
                    limit = (
                        self.output_limit_bytes if key.fd == output_fd else self.stderr_limit_bytes
                    )
                    if len(target) + len(data) > limit:
                        raise _OutputLimitError(
                            f"Collector output exceeded its {limit} byte limit."
                        )
                    target.extend(data)
            process.wait(timeout=max(0, deadline - time.monotonic()))
        return bytes(output), bytes(errors)


def _requested_facts(facts: SourceFacts, request: CollectionRequest) -> None:
    profiles: dict[str, SourceProfile] = {
        "python": "archkeel-python-analyzer",
        "dart": "archkeel-dart-directives",
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
