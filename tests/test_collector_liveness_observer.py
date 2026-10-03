# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Deterministic acceptance tests for collector process liveness observations."""

from __future__ import annotations

import os
import signal
from pathlib import Path

import pytest
import test_collection_process as process_tests
import test_collector_safety_acceptance as acceptance

from archkeel.ir.protocol import CollectionError


class _ProcStat:
    def __init__(self, content: str | None, read_error: type[OSError]) -> None:
        self.content = content
        self.read_error = read_error

    def exists(self) -> bool:
        return True

    def read_text(self) -> str:
        if self.content is None:
            raise self.read_error("process exited before stat read")
        return self.content


def _linux_stat(
    monkeypatch: pytest.MonkeyPatch,
    content: str | None,
    read_error: type[OSError] = FileNotFoundError,
) -> None:
    original_path: type[Path] = acceptance.Path

    def path(value: str) -> Path | _ProcStat:
        if str(value) == "/proc/424242/stat":
            return _ProcStat(content, read_error)
        return original_path(value)

    monkeypatch.setattr(acceptance, "Path", path)
    monkeypatch.setattr(acceptance.sys, "platform", "linux")
    monkeypatch.setattr(acceptance.os, "kill", lambda pid, sig: None)


def test_proc_entry_disappearing_after_exists_is_stopped(monkeypatch: pytest.MonkeyPatch) -> None:
    _linux_stat(monkeypatch, None)

    assert acceptance._alive(424242) is False


@pytest.mark.parametrize("state", ["R", "S"])
def test_live_linux_process_states_remain_live(monkeypatch: pytest.MonkeyPatch, state: str) -> None:
    _linux_stat(monkeypatch, f"424242 (command name with (parens)) {state} 1 2 3")

    assert acceptance._alive(424242) is True


def test_proc_read_process_lookup_error_after_kill_zero_is_stopped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _linux_stat(monkeypatch, None, ProcessLookupError)

    assert acceptance._alive(424242) is False


def test_linux_zombie_with_spaces_and_parentheses_is_stopped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _linux_stat(monkeypatch, "424242 (command name with (parens)) Z 1 2 3")

    assert acceptance._alive(424242) is False


def test_vanished_kill_zero_pid_is_stopped(monkeypatch: pytest.MonkeyPatch) -> None:
    def kill(pid: int, sig: int) -> None:
        raise ProcessLookupError(pid, "No such process")

    monkeypatch.setattr(acceptance.os, "kill", kill)

    assert acceptance._alive(424242) is False


def test_unexpected_permission_error_is_not_reported_as_stopped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def kill(pid: int, sig: int) -> None:
        raise PermissionError(pid, "Operation not permitted")

    monkeypatch.setattr(acceptance.os, "kill", kill)

    with pytest.raises(PermissionError):
        acceptance._alive(424242)


@pytest.mark.skipif(os.name != "posix", reason="POSIX process-group proof only")
def test_acceptance_fixture_cleanup_tolerates_exit_before_sigkill(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pid_file = tmp_path / "child.pid"
    heartbeat = tmp_path / "heartbeat"

    class FinishedCollector:
        def __init__(self, command: tuple[str, ...], **limits: float | int) -> None:
            pass

        def collect(self, request: object) -> CollectionError:
            pid_file.write_text("424242")
            heartbeat.write_text("started")
            return CollectionError("protocol_error", "fixture", "expected test result")

    def kill(pid: int, sig: int) -> None:
        if sig == 0:
            return None
        if sig == signal.SIGKILL:
            raise ProcessLookupError(pid, "No such process")
        raise AssertionError(f"unexpected signal {sig}")

    monkeypatch.setattr(acceptance, "ProcessCollector", FinishedCollector)
    monkeypatch.setattr(acceptance, "_wait_for_stop", lambda pid: True)
    monkeypatch.setattr(acceptance, "_alive", lambda pid: True)
    monkeypatch.setattr(acceptance.os, "kill", kill)

    acceptance.test_collection_stops_owned_descendant_for_every_completion(
        tmp_path, "malformed", "protocol_error"
    )


def test_timeout_stops_descendant_started_after_100ms(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original_factory = process_tests._collector

    def delayed_collector(code: str, **limits: float | int):
        return original_factory("import time; time.sleep(0.15)\n" + code, **limits)

    monkeypatch.setattr(process_tests, "_collector", delayed_collector)

    results: list[object] = []
    original_collect = acceptance.ProcessCollector.collect

    def record_result(self, request):
        result = original_collect(self, request)
        results.append(result)
        return result

    monkeypatch.setattr(acceptance.ProcessCollector, "collect", record_result)
    process_tests.test_failure_terminates_collector_descendants(tmp_path, monkeypatch, "timeout")

    assert len(results) == 1
    assert isinstance(results[0], CollectionError)
    assert results[0].kind == "timeout"
