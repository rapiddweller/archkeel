# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Replaceable argv collectors fail with bounded, named diagnostics."""

import json
import os
import sys
import time
from pathlib import Path

import pytest
from test_collection_protocol import _request, _response

from archkeel.ir.facts_codec import decode_request
from archkeel.ir.protocol import CollectionError


def _collector(code: str, **limits):
    from archkeel.analyzer.process import ProcessCollector

    return ProcessCollector((sys.executable, "-B", "-c", code), **limits)


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
        "import subprocess,sys,time; "
        "child=subprocess.Popen([sys.executable,'-c','import time; time.sleep(30)']); "
        f"open({str(pid_file)!r},'w').write(str(child.pid)); "
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
        f"print({json.dumps(json.dumps(response))})"
    )
    request = decode_request(_request())
    from dataclasses import replace

    request = replace(request, snapshot=replace(request.snapshot, root=str(tmp_path)))
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
