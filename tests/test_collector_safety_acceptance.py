# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Independent acceptance tests for collector process and import safety."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from test_collection_protocol import _request, _response

from archkeel.analyzer.process import ProcessCollector
from archkeel.cli.config import load_config
from archkeel.ir.facts_codec import decode_request
from archkeel.ir.protocol import CollectionError, CollectionRequest, DartSettings, SourceScope


def _request_for(root: Path, language: str = "python") -> CollectionRequest:
    request = decode_request(_request())
    resolver = DartSettings() if language == "dart" else request.resolver
    if (root / "archkeel.toml").exists():
        config = load_config(root)
        scope = SourceScope(config.roots, config.namespace)
    else:
        scope = request.scope
    return replace(
        request,
        protocol_version="2.0.0" if language == "dart" else request.protocol_version,
        snapshot=replace(request.snapshot, root=str(root)),
        resolver=resolver,
        scope=scope,
    )


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    if sys.platform.startswith("linux"):
        try:
            stat = Path(f"/proc/{pid}/stat").read_text()
        except (FileNotFoundError, ProcessLookupError):
            return False
        if stat.rsplit(")", 1)[1].split()[0] == "Z":
            return False
    return True


def _wait_for_stop(pid: int) -> bool:
    deadline = time.monotonic() + 1
    while time.monotonic() < deadline:
        if not _alive(pid):
            return True
        time.sleep(0.01)
    return not _alive(pid)


@pytest.mark.skipif(os.name != "posix", reason="POSIX process-group proof only")
@pytest.mark.parametrize(
    ("case", "expected_kind"),
    [
        ("valid", None),
        ("malformed", "protocol_error"),
        ("nonzero", "execution_error"),
        ("timeout", "timeout"),
        ("output_limit", "protocol_error"),
        ("snapshot_mismatch", "protocol_error"),
    ],
)
def test_collection_stops_owned_descendant_for_every_completion(
    tmp_path: Path,
    case: str,
    expected_kind: str | None,
    monkeypatch: pytest.MonkeyPatch,
    child_start_delay: float = 0,
) -> None:
    pid_file = tmp_path / "child.pid"
    heartbeat = tmp_path / "heartbeat"
    child_code = (
        "import time\n"
        f"time.sleep({child_start_delay})\n"
        f"path = {str(heartbeat)!r}\n"
        "open(path, 'w').write('started')\n"
        "while True:\n"
        "    time.sleep(0.015)\n"
        "    with open(path, 'a') as stream: stream.write('x')\n"
    )
    command = (
        "import subprocess, sys, time\n"
        "child = subprocess.Popen([sys.executable, '-c', "
        f"{child_code!r}], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, "
        "stderr=subprocess.DEVNULL)\n"
        f"open({str(pid_file)!r}, 'w').write(str(child.pid))\n"
        f"from pathlib import Path; deadline = time.monotonic() + 2\n"
        # `open(path, 'w')` makes the file before `write` fills it: wait for the text.
        f"while 'started' not in (Path({str(heartbeat)!r}).read_text() "
        f"if Path({str(heartbeat)!r}).exists() else '') and time.monotonic() < deadline:\n"
        "    time.sleep(0.01)\n"
    )
    if case == "valid" or case == "snapshot_mismatch":
        response: dict[str, Any] = _response()
        if case == "snapshot_mismatch":
            response["facts"]["source"]["git_head"] = "b" * 40
        command += f"print({json.dumps(response)!r})\n"
    elif case == "malformed":
        command += "print('not json')\n"
    elif case == "nonzero":
        command += "sys.exit(7)\n"
    elif case == "timeout":
        command += "time.sleep(10)\n"
    else:
        command += "sys.stdout.write('x' * 100000); sys.stdout.flush(); time.sleep(10)\n"

    limits: dict[str, float | int] = {}
    if case == "timeout":
        limits["timeout_seconds"] = 0.12
        original_exchange = ProcessCollector._exchange

        def exchange_after_descendant_start(self, process, payload, workers):
            deadline = time.monotonic() + 2
            # Fixture startup must finish before the real collector timeout begins.
            while not heartbeat.is_file() or not heartbeat.read_text().startswith("started"):
                if time.monotonic() >= deadline:
                    pytest.fail("collector fixture did not publish heartbeat within 2 seconds")
                time.sleep(0.01)
            return original_exchange(self, process, payload, workers)

        monkeypatch.setattr(ProcessCollector, "_exchange", exchange_after_descendant_start)
    if case == "output_limit":
        limits["output_limit_bytes"] = 256

    pid: int | None = None
    try:
        result = ProcessCollector((sys.executable, "-B", "-c", command), **limits).collect(
            _request_for(tmp_path)
        )
        deadline = time.monotonic() + 1
        while not pid_file.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert pid_file.exists(), "fixture descendant did not start"
        pid = int(pid_file.read_text())
        assert heartbeat.read_text().startswith("started"), "child heartbeat did not start"
        if expected_kind is None:
            assert not isinstance(result, CollectionError)
            assert result.files
        else:
            assert isinstance(result, CollectionError)
            assert result.kind == expected_kind
        assert _wait_for_stop(pid), f"{case}: descendant {pid} remained alive after collection"
    finally:
        if pid is None and pid_file.exists():
            pid = int(pid_file.read_text())
        if pid is not None and _alive(pid):
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass


def _git_init(root: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.invalid",
            "commit",
            "-qm",
            "fixture",
        ],
        cwd=root,
        check=True,
    )
