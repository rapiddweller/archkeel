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
from test_uml_evaluation import _model

from archkeel.analyzer import process as process_owner
from archkeel.check.ports import ScanConfig
from archkeel.ir.decisions import rule_assessments
from archkeel.ir.facts_codec import decode_request, decode_response
from archkeel.ir.protocol import CollectionError
from archkeel.ir.report_graph import architecture_report
from archkeel.ir.trace import trace_valid_violations


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


def test_windows_kill_on_close_uses_extended_job_limits() -> None:
    from archkeel.analyzer.windows_job import (
        _JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
        _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE,
        _IoCounters,
        _kill_on_close_limit_information,
    )

    limits = _kill_on_close_limit_information()
    assert _JOB_OBJECT_EXTENDED_LIMIT_INFORMATION == 9
    assert limits.basic_limit_information.limit_flags == _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    assert len(_IoCounters._fields_) == 6


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

    from archkeel.analyzer.process import _requested_facts
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
        _requested_facts(facts, request)
    else:
        with pytest.raises(ProtocolError, match="survey"):
            _requested_facts(facts, request)


@pytest.mark.parametrize("language", ["python", "dart"])
def test_bundled_collector_never_imports_snapshot_modules(tmp_path: Path, language: str) -> None:
    from archkeel.cli.observe import observer_for

    marker = tmp_path / "executed"
    shadow = f"from pathlib import Path\nPath({str(marker)!r}).write_text('executed')\n"
    for name in ("typing", "dataclasses"):
        (tmp_path / f"{name}.py").write_text(shadow)
    source = tmp_path / "src"
    source.mkdir()
    if language == "python":
        source /= "sample"
        source.mkdir()
    (source / ("app.py" if language == "python" else "app.dart")).write_text("")
    if language == "dart":
        (tmp_path / "pubspec.yaml").write_text("name: sample\n")
    else:
        (tmp_path / "pyproject.toml").write_text('[project]\nrequires-python = ">=3.11"\n')
    (tmp_path / "contract.json").write_text(
        '{"schema_version":"2.1.0","components":[],"rules":[]}\n'
    )

    result = observer_for(language)(
        tmp_path,
        roots=("src",),
        namespace="sample",
        contract="contract.json",
        git_head="a" * 40,
        dirty=False,
        contract_root=tmp_path,
        language=language,
    )
    assert result.exit_code == 0, result.diagnostics
    assert result.observation is not None
    assert not marker.exists()


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
        if self.failure == "wait":
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
    if failure in ("kill", "killpg"):
        assert not any(event[0] == "wait" for event in events)


def test_missing_posix_process_group_still_waits_without_error():
    assert _cleanup_observation(process_owner, "posix", failure="gone") == (
        [("killpg", 17, 9), ("wait", 2)],
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
    command = [sys.executable, "-I", "-B", "windows_job.py", "--", "collector-tool", "script.py"]
    assert launches == [
        (
            "launch",
            command if name == "nt" else ["collector-tool", "script.py"],
            name == "posix",
            request.snapshot.root,
        )
    ]
    assert bool([event for event in events if event[0] == "which"]) is (name == "nt")


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


def _platform_repository(tmp_path, *, changed=None, relocate=False, collect_probe=False):
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
        assert source.count(old) == 1
        source = source.replace(old, new, 1)
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


def test_native_actual_process_target_and_os_control_sites(tmp_path):
    root, config = _platform_repository(tmp_path)
    model = _model(root, config)
    sites = [
        (row.data.get("owner"), excerpt)
        for owner in (
            "archkeel.analyzer.process.ProcessCollector.collect_response",
            "archkeel.analyzer.process._terminate_process_tree",
            "archkeel.analyzer.process._process_platform",
        )
        for row, excerpt in _comparison_sites(model, owner)
    ]
    print("ACTUAL_PROCESS_CONTROL_SITES=" + json.dumps(sites))
    comparison = architecture_report(model).comparison
    assert comparison is not None and comparison.status == "PASS", comparison
    assessments = {row.id: row for row in rule_assessments(model, undecided_by_rule={})}
    for rule_id in (_PLATFORM_GUARD, _CLEANUP_GUARD, "TYPES-ENUM-IN-MODEL"):
        assert assessments[rule_id].status == "PASS" and assessments[rule_id].evaluation_proven
    assert not trace_valid_violations(model)
    # This filename identity is real remaining grammar, not an OS selector or a blanket exception.
    assert [
        excerpt
        for _, excerpt in _comparison_sites(
            model, "archkeel.analyzer.process.ProcessCollector.collect_response"
        )
    ] == ['if Path(executable).suffix.lower() in {".bat", ".cmd"}:']


@pytest.mark.parametrize(
    "changed,missing,expected",
    [
        (None, None, "PASS"),
        (
            (
                "response = self.collect_response(request)",
                "response = self._exchange(request, b'', [])",
            ),
            "PORT-REL-9",
            "FAIL",
        ),
        (
            (
                "stdout, stderr = self._exchange(process, payload, workers)",
                "stdout, stderr = self.collect_response(request)",
            ),
            "PORT-REL-PROVIDER-EXCHANGE",
            "UNKNOWN",
        ),
    ],
    ids=["shared-runner", "missing-response-delegation", "missing-bounded-exchange"],
)
def test_required_process_call_path_keeps_both_direct_edges(tmp_path, changed, missing, expected):
    root, config = _platform_repository(tmp_path, changed=changed)
    authored = json.loads(
        (_PROCESS_ROOT / "docs/architecture/contracts/analyzer.json").read_text()
    )["declarations"]["uml"]["relationships"]
    required = {
        "PORT-REL-9": ("process.collect", "process.collect_response"),
        "PORT-REL-PROVIDER-EXCHANGE": ("process.collect_response", "process._exchange"),
    }
    relationships = [row for row in authored if row["id"] in required]
    assert {row["id"]: (row["source_id"], row["target_id"]) for row in relationships} == required
    target_path = root / "contract.json"
    target = json.loads(target_path.read_text())
    target["declarations"]["uml"]["relationships"] = relationships
    target_path.write_text(json.dumps(target))
    intent = target_path.read_bytes()
    model = _model(root, config)
    comparison = architecture_report(model).comparison
    assert comparison is not None and comparison.status == expected
    violations = trace_valid_violations(model)
    if missing:
        [assessment] = [row for row in comparison.assessments if row.subject_id == missing]
        assert assessment.status == expected
        if expected == "FAIL":
            assert any(row.data.get("subject_id") == missing for row in violations)
        else:
            assert assessment.reason == "Unresolved source sites may refer to this endpoint."
            assert assessment.fact_ids and assessment.evidence_ids
            calls_by_id = {row.id: row for row in model.records("calls")}
            assert all(
                calls_by_id[identifier].data.get("status") in {"unresolved", "partially_resolved"}
                for identifier in assessment.fact_ids
            )
            assert not any(
                row.data.get("source_scope")
                == "archkeel.analyzer.process.ProcessCollector.collect_response"
                and row.data.get("targets")
                == ("archkeel.analyzer.process.ProcessCollector._exchange",)
                for row in model.records("calls")
            )
    else:
        assert not violations
        calls = {
            (row.data.get("source_scope"), row.data.get("targets"))
            for row in model.records("calls")
            if row.data.get("expression") in {"self.collect_response", "self._exchange"}
            and row.data.get("status") == "resolved"
        }
        prefix = "archkeel.analyzer.process.ProcessCollector."
        assert calls == {
            (prefix + "collect", (prefix + "collect_response",)),
            (prefix + "collect_response", (prefix + "_exchange",)),
        }
    assert target_path.read_bytes() == intent


@pytest.mark.parametrize(
    "old,new",
    [
        (
            "def _process_platform(name: str) -> _ProcessPlatform | None:",
            "def _process_platform(name: object) -> _ProcessPlatform | None:",
        ),
        (
            "def _process_platform(name: str) -> _ProcessPlatform | None:",
            "def _process_platform(name: str) -> str | None:",
        ),
        ("class _ProcessPlatform(Enum):", "class _ProcessPlatform:"),
    ],
    ids=["raw-domain", "nominal-result", "enum-kind"],
)
def test_fixed_process_platform_target_rejects_port_weakening(tmp_path, old, new):
    root, config = _platform_repository(tmp_path, changed=(old, new))
    intent = (root / "contract.json").read_bytes()
    model = _model(root, config)
    comparison = architecture_report(model).comparison
    assert comparison is not None and comparison.status == "FAIL", comparison
    assert trace_valid_violations(model)
    assert (root / "contract.json").read_bytes() == intent


def test_actual_root_placement_rejects_process_enum_relocation(tmp_path):
    root, config = _platform_repository(tmp_path, relocate=True)
    model = _model(root, config)
    assert any("TYPES-ENUM-IN-MODEL" in row.rule_ids for row in trace_valid_violations(model))


@pytest.mark.parametrize(
    "old,new,rule_id",
    [
        (
            "    try:\n        return _ProcessPlatform(name)",
            '    if name == "posix":\n        return _ProcessPlatform.POSIX\n'
            "    try:\n        return _ProcessPlatform(name)",
            _PLATFORM_GUARD,
        ),
        (
            "    if platform is _ProcessPlatform.POSIX:",
            '    if os.name == "posix":',
            _CLEANUP_GUARD,
        ),
        (
            "    if platform is _ProcessPlatform.POSIX:",
            "    if platform.value == _ProcessPlatform.POSIX.value:",
            _CLEANUP_GUARD,
        ),
        (
            "            if platform is _ProcessPlatform.WINDOWS:",
            '            if os.name == "nt":',
            _COLLECT_PROBE,
        ),
    ],
    ids=[
        "converter-raw-control",
        "cleanup-raw-control",
        "cleanup-value-evasion",
        "collect-os-control",
    ],
)
def test_actual_os_comparison_mutations_keep_native_control_trace(tmp_path, old, new, rule_id):
    root, config = _platform_repository(
        tmp_path, changed=(old, new), collect_probe=rule_id == _COLLECT_PROBE
    )
    model = _model(root, config)
    violations = [row for row in trace_valid_violations(model) if rule_id in row.rule_ids]
    assert violations
    if rule_id == _COLLECT_PROBE:
        facts = [
            row
            for row, excerpt in _comparison_sites(
                model, "archkeel.analyzer.process.ProcessCollector.collect_response"
            )
            if excerpt == 'if os.name == "nt":'
        ]
        assert len(facts) == 1
        assert any(facts[0].id in row.fact_ids for row in violations)
