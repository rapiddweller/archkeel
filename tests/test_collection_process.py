# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Replaceable argv collectors fail with bounded, named diagnostics."""

import json
import os
import sys
import time
from enum import Enum
from pathlib import Path
from threading import TIMEOUT_MAX
from types import SimpleNamespace
from typing import get_type_hints
from unittest.mock import patch

import pytest
from test_architecture_demo import _prepare_repo
from test_collection_protocol import _request, _response

from archkeel.analyzer import process as process_owner
from archkeel.check.ports import ScanConfig
from archkeel.ir.facts_codec import decode_request, decode_response
from archkeel.ir.protocol import CollectionError


def _collector(code: str, **limits):
    from archkeel.analyzer.process import ProcessCollector

    return ProcessCollector((sys.executable, "-B", "-c", code), **limits)


@pytest.mark.parametrize("timeout", [float("nan"), float("inf"), float("-inf"), TIMEOUT_MAX * 2])
def test_unsupported_collector_timeout_is_rejected_before_execution(timeout):
    with pytest.raises(ValueError, match="collector limits"):
        _collector("pass", timeout_seconds=timeout)


def _assert_process_exited(pid: int) -> None:
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        if os.name == "nt":
            import ctypes
            from ctypes import wintypes

            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
            kernel32.OpenProcess.restype = wintypes.HANDLE
            kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
            kernel32.WaitForSingleObject.restype = wintypes.DWORD
            kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
            handle = kernel32.OpenProcess(0x00100000, False, pid)
            if not handle:
                error = ctypes.get_last_error()
                if error == 87:
                    return
                raise OSError(error, "OpenProcess failed while checking collector descendant")
            try:
                if kernel32.WaitForSingleObject(handle, 0) == 0:
                    return
            finally:
                kernel32.CloseHandle(handle)
            time.sleep(0.02)
            continue
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return
        if sys.platform.startswith("linux"):
            try:
                stat = Path(f"/proc/{pid}/stat").read_text()
            except (FileNotFoundError, ProcessLookupError):
                return
            if stat.rsplit(")", 1)[1].split()[0] == "Z":
                return
        time.sleep(0.02)
    pytest.fail(f"collector descendant {pid} remained alive after cleanup")


@pytest.mark.skipif(os.name not in ("posix", "nt"), reason="requires process-tree cleanup support")
@pytest.mark.parametrize("failure", ["timeout", "parent_exits", "output_limit", "io_error"])
def test_failure_terminates_collector_descendants(tmp_path, monkeypatch, failure) -> None:
    from archkeel.analyzer.process import ProcessCollector

    pid_file = tmp_path / "child.pid"
    code = (
        "import os,subprocess,sys,time; from pathlib import Path; "
        "child=subprocess.Popen([sys.executable,'-c','import time; time.sleep(30)']); "
        f"Path({str(pid_file.with_suffix('.pending'))!r}).write_text(str(child.pid)); "
        f"os.replace({str(pid_file.with_suffix('.pending'))!r},{str(pid_file)!r}); "
    )
    if failure == "output_limit":
        code += "sys.stdout.write('x'*100000); sys.stdout.flush(); time.sleep(30)"
    elif failure == "parent_exits":
        code += "pass"
    else:
        code += "time.sleep(30)"

    limits = {"output_limit_bytes": 1000} if failure == "output_limit" else {}
    if failure in ("timeout", "parent_exits"):
        limits["timeout_seconds"] = 0.1
    collector = _collector(code, **limits)
    if failure in ("timeout", "parent_exits"):
        original_exchange = ProcessCollector._exchange

        def exchange_after_descendant_start(self, process, payload, workers):
            deadline = time.monotonic() + 2
            while not pid_file.is_file():
                if time.monotonic() >= deadline:
                    pytest.fail("collector fixture did not publish child.pid within 2 seconds")
                time.sleep(0.01)
            return original_exchange(self, process, payload, workers)

        monkeypatch.setattr(ProcessCollector, "_exchange", exchange_after_descendant_start)
    if failure == "io_error":

        def fail_exchange(self, process, payload, workers):
            deadline = time.monotonic() + 2
            while not pid_file.exists() and time.monotonic() < deadline:
                time.sleep(0.01)
            assert pid_file.exists()
            raise OSError("simulated pipe failure")

        monkeypatch.setattr(ProcessCollector, "_exchange", fail_exchange)

    from dataclasses import replace

    request = decode_request(_request())
    request = replace(request, snapshot=replace(request.snapshot, root=str(tmp_path)))
    result = collector.collect(request)

    assert isinstance(result, CollectionError)
    assert pid_file.is_file()
    _assert_process_exited(int(pid_file.read_text()))


def test_windows_job_kills_on_close_and_bounds_process_memory() -> None:
    from archkeel.analyzer.windows_job import (
        _JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
        _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE,
        _JOB_OBJECT_LIMIT_PROCESS_MEMORY,
        _IoCounters,
        _job_limit_information,
    )

    limits = _job_limit_information(256 * 2**20)
    assert _JOB_OBJECT_EXTENDED_LIMIT_INFORMATION == 9
    assert _JOB_OBJECT_LIMIT_PROCESS_MEMORY == 0x100
    assert limits.basic_limit_information.limit_flags == (
        _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE | _JOB_OBJECT_LIMIT_PROCESS_MEMORY
    )
    assert limits.process_memory_limit == 256 * 2**20
    assert len(_IoCounters._fields_) == 6


@pytest.mark.parametrize(
    "arguments,parsed",
    [
        (["--memory-limit-bytes=1024", "--", "tool", "a"], (1024, ["tool", "a"])),
        (["--memory-limit-bytes=0", "--", "tool"], None),
        (["--memory-limit-bytes=-1", "--", "tool"], None),
        (["--memory-limit-bytes=abc", "--", "tool"], None),
        (["--memory-limit-bytes=1024", "--"], None),
        (["--", "tool"], None),
        (["--memory-limit-bytes=1024", "tool"], None),
    ],
)
def test_windows_job_reads_its_memory_limit_before_the_collector_argv(arguments, parsed) -> None:
    from archkeel.analyzer.windows_job import _parse

    assert _parse(arguments) == parsed


_LIMITED_PLATFORM = pytest.mark.skipif(
    sys.platform not in ("linux", "win32"),
    reason="Linux RLIMIT_AS and the Windows job bound memory; macOS has no reliable limit",
)


@_LIMITED_PLATFORM
def test_collector_over_the_memory_limit_is_a_named_execution_error(tmp_path) -> None:
    from dataclasses import replace

    from archkeel.ir.protocol import CollectionErrorKind

    # The allocation follows the request, as the work of a real collector does.
    code = "import sys; sys.stdin.buffer.read(); data = bytearray(1024 * 2**20)"
    request = decode_request(_request())
    request = replace(request, snapshot=replace(request.snapshot, root=str(tmp_path)))

    result = _collector(code, memory_limit_bytes=256 * 2**20).collect(request)

    assert isinstance(result, CollectionError)
    assert result.kind is CollectionErrorKind.EXECUTION_ERROR
    assert result.message.startswith(
        "Collector exceeded its memory limit of 268435456 bytes (256 MiB)."
    )
    assert "MemoryError" in result.message


@pytest.mark.skipif(sys.platform != "linux", reason="requires Linux RLIMIT_AS")
def test_linux_collector_receives_its_request_under_the_address_space_limit(tmp_path) -> None:
    from dataclasses import replace

    code = (
        "import resource, sys; sys.stdin.buffer.read(); "
        "sys.exit('limit=%d,%d' % resource.getrlimit(resource.RLIMIT_AS))"
    )
    request = decode_request(_request())
    request = replace(request, snapshot=replace(request.snapshot, root=str(tmp_path)))

    result = _collector(code, memory_limit_bytes=512 * 2**20).collect(request)

    assert isinstance(result, CollectionError)
    limit = 512 * 2**20
    assert result.message == f"Collector exited 1: limit={limit},{limit}"


def test_default_memory_limit_has_headroom_over_the_measured_collector_peak() -> None:
    from archkeel.analyzer.memory_limit import COLLECTOR_MEMORY_LIMIT_BYTES
    from archkeel.analyzer.process import ProcessCollector

    assert COLLECTOR_MEMORY_LIMIT_BYTES == 4 * 2**30
    assert ProcessCollector(("tool",)).memory_limit_bytes == COLLECTOR_MEMORY_LIMIT_BYTES
    with pytest.raises(ValueError, match="collector limits must be positive"):
        ProcessCollector(("tool",), memory_limit_bytes=0)


@pytest.mark.parametrize(
    "platform,named",
    [("linux", True), ("win32", True), ("darwin", False), ("freebsd", False)],
)
@pytest.mark.parametrize(
    "stderr",
    [
        "Traceback (most recent call last):\nMemoryError",
        "memory allocation of 1073741824 bytes failed",
        "FATAL ERROR: Reached heap limit Allocation failed - JavaScript heap out of memory",
    ],
)
def test_only_a_limited_platform_names_the_memory_limit(monkeypatch, platform, named, stderr):
    from archkeel.analyzer import memory_limit

    monkeypatch.setattr(memory_limit.sys, "platform", platform)
    message = memory_limit.exit_message(-6, stderr, 2**30)

    assert message.endswith(f"Collector exited -6: {stderr}")
    assert message.startswith("Collector exceeded its memory limit") is named
    assert memory_limit.exit_message(1, "ValueError: bad input", 2**30) == (
        "Collector exited 1: ValueError: bad input"
    )


@pytest.mark.skipif(sys.platform == "linux", reason="Linux sets RLIMIT_AS on the collector")
def test_platform_without_an_address_space_limit_sets_nothing() -> None:
    from archkeel.analyzer.memory_limit import limit_memory

    # PID 1 is never our child; a call that tried to limit it would fail.
    assert limit_memory(1, 2**20) is None


@pytest.mark.skipif(sys.platform != "linux", reason="requires Linux prlimit")
def test_linux_memory_limit_ignores_a_collector_that_already_exited() -> None:
    import subprocess

    from archkeel.analyzer.memory_limit import limit_memory

    child = subprocess.Popen([sys.executable, "-c", "pass"])
    child.wait()

    assert limit_memory(child.pid, 2**30) is None


def test_refused_memory_limit_is_an_execution_error(monkeypatch, tmp_path) -> None:
    from dataclasses import replace

    from archkeel.ir.protocol import CollectionErrorKind

    monkeypatch.setattr(
        process_owner, "limit_memory", lambda pid, limit: "Could not set the limit."
    )
    request = decode_request(_request())
    request = replace(request, snapshot=replace(request.snapshot, root=str(tmp_path)))

    result = _collector("import time; time.sleep(30)").collect(request)

    assert isinstance(result, CollectionError)
    assert (result.kind, result.message) == (
        CollectionErrorKind.EXECUTION_ERROR,
        "Could not set the limit.",
    )


@pytest.mark.parametrize("reported,accepted", [("7.1.0", True), ("7.0.9", False)])
def test_host_collector_must_report_the_host_adapter_version(
    monkeypatch, tmp_path, reported, accepted
):
    from dataclasses import replace

    from archkeel.ir.protocol import CollectionErrorKind

    response = _response()
    response["facts"]["adapter"]["version"] = reported
    code = f"import sys; sys.stdin.buffer.read(); print({json.dumps(json.dumps(response))})"
    request = decode_request(_request())
    request = replace(request, snapshot=replace(request.snapshot, root=str(tmp_path)))

    monkeypatch.setattr(process_owner, "package_version", lambda: "7.1.0")

    result = _collector(code, pin_adapter_version=True).collect(request)

    if accepted:
        assert not isinstance(result, CollectionError), result
        assert result.adapter.version == "7.1.0"
    else:
        assert isinstance(result, CollectionError)
        assert result.kind is CollectionErrorKind.PROTOCOL_ERROR
        assert result.message == (
            "collector adapter version '7.0.9' does not match the host version '7.1.0'"
        )


def test_configured_executable_collects_facts_without_receiving_policy(tmp_path) -> None:
    response = _response()
    code = (
        "import json,sys; request=json.load(sys.stdin); "
        "assert set(request)=={'protocol_version','snapshot','scope','resolver'}; "
        "assert request['protocol_version']=='2.0.0'; "
        f"print({json.dumps(json.dumps(response))})"
    )
    request = decode_request(_request())
    from dataclasses import replace

    request = replace(
        request,
        protocol_version="2.0.0",
        snapshot=replace(request.snapshot, root=str(tmp_path)),
    )
    facts = _collector(code).collect(request)
    assert not isinstance(facts, CollectionError)
    assert facts.adapter.name == "alternate-parser"
    assert facts.files[0].module == "project.app"


def test_configured_executable_response_may_use_a_different_valid_version(tmp_path) -> None:
    response = _response()
    encoded = json.dumps(response)
    code = f"import sys; sys.stdin.buffer.read(); sys.stdout.buffer.write({encoded!r}.encode())"
    request = decode_request(_request())
    from dataclasses import replace

    request = replace(
        request,
        protocol_version="2.0.0",
        snapshot=replace(request.snapshot, root=str(tmp_path)),
    )

    result = _collector(code).collect_response(request)

    assert not isinstance(result, CollectionError)
    assert result.protocol_version.value == "1.0.0"


def test_selected_protocol_version_rejects_a_mismatched_response(tmp_path) -> None:
    from dataclasses import replace

    from archkeel.ir.facts_codec import decode_request
    from archkeel.ir.protocol import CollectionError, CollectionErrorKind, ProtocolVersion

    legacy = json.dumps(_response(), sort_keys=True, separators=(",", ":")).encode()
    code = f"import sys; sys.stdin.buffer.read(); sys.stdout.buffer.write({legacy!r})"
    request = decode_request(_request())
    request = replace(request, snapshot=replace(request.snapshot, root=str(tmp_path)))

    result = _collector(code, protocol_version=ProtocolVersion.V8).collect_response(request)

    assert isinstance(result, CollectionError)
    assert result.kind is CollectionErrorKind.PROTOCOL_ERROR
    assert "does not match its request" in result.message


def test_nonzero_process_exit_cannot_be_a_complete_collection(tmp_path) -> None:
    from dataclasses import replace

    request = decode_request(_request())
    request = replace(request, snapshot=replace(request.snapshot, root=str(tmp_path)))
    result = _collector("import sys; sys.stderr.write('collector failed'); sys.exit(2)").collect(
        request
    )
    assert isinstance(result, CollectionError)
    assert result.kind == "execution_error"
    assert "collector failed" in result.message


def test_long_stderr_does_not_fail_a_valid_collection(tmp_path) -> None:
    from dataclasses import replace

    request = decode_request(_request())
    request = replace(
        request,
        protocol_version="2.0.0",
        snapshot=replace(request.snapshot, root=str(tmp_path)),
    )
    code = (
        "import sys; sys.stdin.read(); sys.stderr.write('w' * 200000); sys.stderr.flush(); "
        f"print({json.dumps(json.dumps(_response()))})"
    )
    facts = _collector(code).collect(request)
    assert not isinstance(facts, CollectionError)


def test_failed_collector_reports_the_exit_code_and_the_end_of_a_long_stderr(tmp_path) -> None:
    from dataclasses import replace

    request = decode_request(_request())
    request = replace(request, snapshot=replace(request.snapshot, root=str(tmp_path)))
    code = (
        "import sys; sys.stdin.read(); "
        "sys.stderr.write('noise\\n' * 50000 + 'Traceback\\nRealError: boom'); sys.exit(3)"
    )
    result = _collector(code).collect(request)
    assert isinstance(result, CollectionError)
    assert result.kind == "execution_error"
    assert result.message.startswith("Collector exited 3:")
    assert result.message.endswith("Traceback\nRealError: boom")
    assert result.message.count("\n") <= 20


def test_output_limit_stops_collector_while_it_is_running(tmp_path) -> None:
    from dataclasses import replace

    request = decode_request(_request())
    request = replace(request, snapshot=replace(request.snapshot, root=str(tmp_path)))
    result = _collector(
        "import sys; sys.stdout.write('x'*1000000); sys.stdout.flush()", output_limit_bytes=1000
    ).collect(request)
    assert isinstance(result, CollectionError)
    assert result.kind == "protocol_error"
    assert "limit" in result.message


@pytest.mark.skipif(os.name != "posix", reason="requires POSIX process groups")
def test_output_limit_with_an_exited_unreaped_collector_is_a_protocol_error(
    tmp_path, monkeypatch
) -> None:
    import subprocess
    from dataclasses import replace

    terminate = process_owner._terminate_process_tree

    def terminate_after_exit(process):
        # Cleanup must see a collector that exited but is not reaped yet (a zombie).
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            state = subprocess.run(
                ["ps", "-o", "stat=", "-p", str(process.pid)], capture_output=True, text=True
            ).stdout.strip()
            if state.startswith("Z"):
                break
            time.sleep(0.01)
        else:
            pytest.fail("collector did not exit within 5 seconds")
        terminate(process)

    monkeypatch.setattr(process_owner, "_terminate_process_tree", terminate_after_exit)
    request = decode_request(_request())
    request = replace(request, snapshot=replace(request.snapshot, root=str(tmp_path)))
    result = _collector(
        "import sys; sys.stdout.write('x'*100000); sys.stdout.flush()", output_limit_bytes=1000
    ).collect(request)
    assert isinstance(result, CollectionError)
    assert result.kind == "protocol_error"
    assert "limit" in result.message


def test_timeout_also_bounds_a_process_that_never_reads_stdin(tmp_path) -> None:
    from dataclasses import replace

    request = decode_request(_request())
    request = replace(request, snapshot=replace(request.snapshot, root=str(tmp_path)))
    result = _collector("import time; time.sleep(30)", timeout_seconds=0.05).collect(request)
    assert isinstance(result, CollectionError)
    assert result.kind == "timeout"


def test_unavailable_executable_is_a_named_missing_tool(tmp_path) -> None:
    from dataclasses import replace

    from archkeel.analyzer.process import ProcessCollector

    request = decode_request(_request())
    request = replace(request, snapshot=replace(request.snapshot, root=str(tmp_path)))
    result = ProcessCollector((str(tmp_path / "missing-tool"),)).collect(request)
    assert isinstance(result, CollectionError)
    assert result.kind == "missing_tool"


def test_response_revision_must_match_requested_snapshot(tmp_path) -> None:
    from dataclasses import replace

    response = _response()
    response["facts"]["source"]["git_head"] = "b" * 40
    request = decode_request(_request())
    request = replace(request, snapshot=replace(request.snapshot, root=str(tmp_path)))
    result = _collector(f"print({json.dumps(json.dumps(response))})").collect(request)
    assert isinstance(result, CollectionError)
    assert result.kind == "protocol_error"
    assert "snapshot" in result.message


@pytest.mark.parametrize(
    "sections,accepted",
    [
        (("imports",), False),
        (("imports", "unknowns"), True),
        (("imports", "unknowns", "symbols"), False),
    ],
)
def test_python_survey_response_matches_requested_phase(sections, accepted):
    from dataclasses import replace

    from archkeel.analyzer.reply_checks import check_requested_facts
    from archkeel.ir.facts import FactSection, SourceSectionName
    from archkeel.ir.facts_codec import ProtocolError
    from archkeel.ir.protocol import ProtocolVersion, PythonCollectionPhase, PythonSettings

    facts = decode_response(json.dumps(_response()).encode()).facts
    names = tuple(SourceSectionName(name) for name in sections)
    records = {section.name: section.records for section in facts.sections}
    facts = replace(
        facts,
        capabilities=replace(facts.capabilities, sections=names),
        sections=tuple(FactSection(name, records.get(name, ())) for name in names),
    )
    request = replace(
        decode_request(_request()),
        protocol_version=ProtocolVersion.V4,
        resolver=PythonSettings(phase=PythonCollectionPhase.IMPORTS),
    )
    if accepted:
        check_requested_facts(facts, request)
    else:
        with pytest.raises(ProtocolError, match="survey"):
            check_requested_facts(facts, request)


# Other OS names remain outside the recognized process platform vocabulary.
_PROCESS_ROOT = Path(__file__).parents[1]
_PLATFORM_GUARD = "PROCESS-PLATFORM-DECODE-CONTROL"
_CLEANUP_GUARD = "PROCESS-PLATFORM-CLEANUP-CONTROL"
_COLLECT_PROBE = "PROCESS-PLATFORM-COLLECT-PROBE"


def _platform_type():
    kind = getattr(process_owner, "_ProcessPlatform", None)
    assert kind is not None, "the existing process owner needs its nominal OS platform port"
    return kind


def test_process_platform_port_owns_only_known_os_names():
    kind = _platform_type()
    assert issubclass(kind, Enum)
    assert [(member.name, member.value) for member in kind] == [
        ("POSIX", "posix"),
        ("WINDOWS", "nt"),
    ]
    hints = get_type_hints(process_owner._process_platform)
    assert hints == {"name": str, "return": kind | None}
    assert process_owner._process_platform("posix") is kind.POSIX
    assert process_owner._process_platform("nt") is kind.WINDOWS
    for name in ("other", "future-platform", "POSIX", "nt ", ""):
        assert process_owner._process_platform(name) is None


class _LifecycleProcess:
    pid = 17
    returncode = 0

    def __init__(self, events, running=True, failure=None):
        self.events, self.running, self.failure = events, running, failure

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def poll(self):
        self.events.append(("poll",))
        return None if self.running else 0

    def kill(self):
        self.events.append(("kill",))
        if self.failure == "kill":
            raise OSError("denied")
        self.running = False

    def wait(self, timeout):
        self.events.append(("wait", timeout))
        if self.failure in ("wait", "killpg"):
            import subprocess

            raise subprocess.TimeoutExpired("collector", timeout)
        self.running = False
        return 0


def _cleanup_observation(owner, name, running=True, failure=None):
    events = []
    process = _LifecycleProcess(events, running, failure)

    def killpg(pid, signum):
        events.append(("killpg", pid, signum))
        if failure == "gone":
            raise ProcessLookupError("gone")
        if failure == "killpg":
            raise OSError("denied")

    with (
        patch.object(owner, "os", SimpleNamespace(name=name, killpg=killpg)),
        patch.object(owner, "signal", SimpleNamespace(SIGKILL=9)),
    ):
        try:
            owner._terminate_process_tree(process)
        except owner._ProcessCleanupError as error:
            cause = error.__cause__
            return events, str(error), None if cause is None else (type(cause).__name__, str(cause))
    return events, None, None


@pytest.mark.parametrize("name", ["posix", "nt", "future-platform"])
@pytest.mark.parametrize("running", [False, True])
def test_actual_cleanup_keeps_existing_platform_lifecycle(name, running):
    events, error, cause = _cleanup_observation(process_owner, name, running)
    if name == "posix":
        expected = [("killpg", 17, 9), ("wait", 2)]
    else:
        expected = [("poll",)] + ([("kill",)] if running else []) + [("wait", 2)]
    assert (events, error, cause) == (expected, None, None)


@pytest.mark.parametrize(
    "name,failure,message",
    [
        ("posix", "killpg", "Could not terminate the collector process group."),
        ("nt", "kill", "Could not terminate the Windows job launcher."),
        ("future-platform", "kill", "Could not terminate the collector process."),
        ("posix", "wait", "Collector did not stop after process-tree termination."),
        ("nt", "wait", "Collector did not stop after process-tree termination."),
        ("future-platform", "wait", "Collector did not stop after process-tree termination."),
    ],
)
def test_platform_cleanup_keeps_exact_error_text_and_cause(name, failure, message):
    events, error, cause = _cleanup_observation(process_owner, name, failure=failure)
    assert error == message and cause is not None
    assert cause[0] == ("TimeoutExpired" if failure == "wait" else "OSError")
    if failure == "kill":
        assert not any(event[0] == "wait" for event in events)
    if failure == "killpg":
        assert [event for event in events if event[0] == "wait"] == [("wait", 0.5)]


def _permission_denied_cleanup(process, events):
    def killpg(pid, signum):
        events.append(("killpg", pid, signum))
        raise PermissionError("macOS refuses a group while it tears down an exiting collector")

    with (
        patch.object(process_owner, "os", SimpleNamespace(name="posix", killpg=killpg)),
        patch.object(process_owner, "signal", SimpleNamespace(SIGKILL=9)),
    ):
        process_owner._terminate_process_tree(process)


def test_posix_group_refusal_waits_briefly_for_an_exiting_collector():
    events = []
    _permission_denied_cleanup(_LifecycleProcess(events, running=True), events)
    assert events == [("killpg", 17, 9), ("wait", 0.5), ("wait", 2)]


@pytest.mark.skipif(os.name != "posix", reason="requires POSIX process groups")
def test_posix_group_refusal_accepts_a_real_collector_that_exits_soon():
    import subprocess

    events = []
    process = subprocess.Popen([sys.executable, "-B", "-c", "import time; time.sleep(0.1)"])
    try:
        # The fake killpg does not signal, so the collector exits on its own after the refusal.
        _permission_denied_cleanup(process, events)
        assert process.poll() == 0
    finally:
        process.kill()
        process.wait()


def test_missing_posix_process_group_still_waits_without_error():
    assert _cleanup_observation(process_owner, "posix", failure="gone") == (
        [("killpg", 17, 9), ("wait", 0.5), ("wait", 2)],
        None,
        None,
    )


def _launch_observation(owner, request, name, executable="tool.exe", popen_error=False):
    import subprocess

    events = []
    child = _LifecycleProcess(events)
    response = json.dumps(_response()).encode()

    def which(command, *, path):
        events.append(("which", command, path))
        return executable

    def popen(command, **options):
        normalized = list(command)
        if len(normalized) > 3 and normalized[1:3] == ["-I", "-B"]:
            normalized[3] = Path(normalized[3]).name
        events.append(("launch", normalized, options["start_new_session"], options["cwd"]))
        if popen_error:
            raise OSError("unavailable")
        return child

    runtime = SimpleNamespace(
        Popen=popen, PIPE=subprocess.PIPE, TimeoutExpired=subprocess.TimeoutExpired
    )
    external_os = SimpleNamespace(name=name, environ={"PATH": "bin"}, pathsep=os.pathsep)
    with (
        patch.object(owner, "os", external_os),
        patch.object(owner, "subprocess", runtime),
        patch.object(owner.shutil, "which", which),
        patch.object(owner.ProcessCollector, "_exchange", lambda *args: (response, b"")),
        patch.object(owner, "_cleanup_exchange", lambda *args: None),
        patch.object(owner, "limit_memory", lambda pid, limit: events.append(("limit", pid))),
    ):
        result = owner.ProcessCollector(("collector-tool", "script.py")).collect(request)
    if isinstance(result, CollectionError):
        return events, (result.kind, result.subject, result.message)
    return events, result


@pytest.mark.parametrize("name", ["posix", "nt", "future-platform"])
def test_actual_collect_keeps_launcher_session_and_unknown_fallback(name):
    request = decode_request(_request())
    events, result = _launch_observation(process_owner, request, name)
    expected = decode_response(json.dumps(_response()).encode()).facts
    assert result == expected
    launches = [event for event in events if event[0] == "launch"]
    assert len(launches) == 1
    command = [
        *(sys.executable, "-I", "-B", "windows_job.py", f"--memory-limit-bytes={4 * 2**30}"),
        *("--", "collector-tool", "script.py"),
    ]
    assert launches == [
        (
            "launch",
            command if name == "nt" else ["collector-tool", "script.py"],
            name == "posix",
            request.snapshot.root,
        )
    ]
    assert bool([event for event in events if event[0] == "which"]) is (name == "nt")
    assert [event for event in events if event[0] == "limit"] == [("limit", 17)]


@pytest.mark.parametrize(
    "executable,kind,message",
    [
        (None, "missing_tool", "Collector could not execute: collector-tool"),
        (
            "tool.CMD",
            "execution_error",
            "Windows .bat/.cmd collector shims cannot run without a shell; "
            "configure an explicit executable and script argv.",
        ),
        (
            "tool.bat",
            "execution_error",
            "Windows .bat/.cmd collector shims cannot run without a shell; "
            "configure an explicit executable and script argv.",
        ),
    ],
)
def test_windows_launcher_rejections_keep_existing_error_order(executable, kind, message):
    events, result = _launch_observation(
        process_owner, decode_request(_request()), "nt", executable=executable
    )
    assert result == (kind, "collector-tool", message)
    assert not any(event[0] == "launch" for event in events)


@pytest.mark.parametrize("name", ["posix", "nt", "future-platform"])
def test_launch_oserror_keeps_existing_missing_tool_text(name):
    _, result = _launch_observation(
        process_owner, decode_request(_request()), name, popen_error=True
    )
    assert result == ("missing_tool", "collector-tool", "Collector could not execute: unavailable")


def _platform_repository(
    tmp_path, *, changed=None, changed_in=None, relocate=False, collect_probe=False
):
    target = json.loads((_PROCESS_ROOT / "docs/architecture/contracts/analyzer.json").read_text())
    target.pop("$schema", None)
    target["components"] = [target["components"][0]]
    ids = {
        "archkeel.analyzer.process",
        "process",
        "process.argv",
        "process.timeout_seconds",
        "process.output_limit_bytes",
        "process.stderr_limit_bytes",
        "process.collect",
        "process.collect_response",
        "process.__post_init__",
        "process._exchange",
        "PROCESS-PLATFORM",
        "PROCESS-PLATFORM-DECODE",
    }
    uml = target["declarations"]["uml"]
    uml["entities"] = [row for row in uml["entities"] if row["id"] in ids]
    assert {row["id"] for row in uml["entities"]} == ids
    uml["relationships"], uml["scopes"] = [], []
    rules = json.loads((_PROCESS_ROOT / "architecture-contract.json").read_text())["rules"]
    placement = next(row for row in rules if row["id"] == "TYPES-ENUM-IN-MODEL")
    rule_ids = {"TYPES-ENUM-IN-MODEL", _PLATFORM_GUARD, _CLEANUP_GUARD}
    target["rules"] = [row for row in rules if row["id"] in rule_ids]
    assert {row["id"] for row in target["rules"]} == rule_ids
    if collect_probe:
        target["rules"].append(
            {
                "id": _COLLECT_PROBE,
                "kind": "forbidden_construct",
                "source": "archkeel.analyzer.process.ProcessCollector.collect_response",
                "constructs": ["string_literal_compare"],
                "rationale": "Trace an OS mutation while retaining the real filename grammar.",
                "provenance": ["docs/architecture/language-adapter-target.md"],
                "decided_by": "architect",
            }
        )
    source = (_PROCESS_ROOT / "src/archkeel/analyzer/process.py").read_text()
    if changed is not None:
        old, new = changed
        if changed_in is None:
            assert source.count(old) == 1
            source = source.replace(old, new, 1)
        else:
            lines = source.splitlines(keepends=True)
            start = next(
                index
                for index, line in enumerate(lines)
                if line.lstrip().startswith(f"def {changed_in}(")
            )
            indent = len(lines[start]) - len(lines[start].lstrip())
            end = next(
                (
                    index
                    for index in range(start + 1, len(lines))
                    if len(lines[index]) - len(lines[index].lstrip()) == indent
                    and lines[index].lstrip().startswith("def ")
                ),
                len(lines),
            )
            body = "".join(lines[start:end])
            assert body.count(old) == 1
            lines[start:end] = [body.replace(old, new, 1)]
            source = "".join(lines)
    extra = {}
    if relocate:
        block = 'class _ProcessPlatform(Enum):\n    POSIX = "posix"\n    WINDOWS = "nt"\n\n\n'
        assert source.count(block) == 1
        source = source.replace(block, "")
        extra["archkeel/analyzer/misplaced.py"] = "from enum import Enum\n\n" + block
    root = _prepare_repo(
        tmp_path,
        {
            "archkeel/__init__.py": "",
            "archkeel/analyzer/__init__.py": "",
            "archkeel/analyzer/process.py": source,
            "contract.json": json.dumps(target),
            **{name: (_PROCESS_ROOT / name).read_text() for name in placement["provenance"]},
            "docs/architecture/language-adapter-target.md": (
                _PROCESS_ROOT / "docs/architecture/language-adapter-target.md"
            ).read_text(),
            **extra,
        },
    )
    return root, ScanConfig(("archkeel",), "archkeel", "contract.json", "0" * 64)


def _comparison_sites(model, owner):
    evidence = {row.id: row for row in model.evidence}
    return [
        (row, evidence[row.evidence_ids[0]].excerpt.strip())
        for row in model.records("constructs")
        if row.kind == "string_literal_compare" and row.data.get("owner") == owner
    ]
