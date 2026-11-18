# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The timings line of the core is read as a whole contract, and a run that was asked for its
timings but got none is an error, not a silent success (#659, review of PR #1834)."""

import json
from pathlib import Path
from typing import Any

import pytest
from core_support import HONEST, case_root, run

from archkeel.cli import core_only
from archkeel.cli.core_json import CoreError
from archkeel.cli.core_output import read_timings

PHASES = {
    "prepare": 0.1,
    "collect": 1.0,
    "validate": 0.1,
    "evaluate": 0.1,
    "render": 0.1,
    "join": 0.0,
}


def _line(**change: Any) -> bytes:
    document: dict[str, Any] = {
        "protocol": "archkeel-core-timings-1",
        "clock": "monotonic",
        "unit": "seconds",
        "phases": dict(PHASES),
        "core_seconds": 1.5,
    }
    document.update(change)
    return json.dumps(document).encode() + b"\n"


def test_a_complete_line_is_kept_as_it_is() -> None:
    line = _line()
    assert read_timings(line) == line


def test_the_line_of_a_refused_scan_has_no_seconds_and_gives_no_file() -> None:
    assert read_timings(b'{"protocol":"archkeel-core-timings-1","refused":true}\n') is None


@pytest.mark.parametrize(
    "stderr",
    [
        b"",
        b"\n",
        _line() + _line(),
        b"warning\n" + _line(),
        b"not json\n",
        b"[]\n",
        _line(protocol="archkeel-core-timings-2"),
        b'{"protocol":"archkeel-core-timings-1"}\n',
        b'{"protocol":"archkeel-core-timings-1","refused":false}\n',
        _line(clock="wall"),
        _line(unit="milliseconds"),
        _line(extra=1),
        _line(phases={name: value for name, value in PHASES.items() if name != "join"}),
        _line(phases=dict(reversed(PHASES.items()))),
        _line(phases={**PHASES, "collect": -0.5}),
        _line(phases={**PHASES, "collect": "1.0"}),
        _line(phases={**PHASES, "collect": True}),
        _line(phases={**PHASES, "collect": 5.0}),
        _line(core_seconds=-1),
        _line(core_seconds=None),
        b'{"protocol":"archkeel-core-timings-1","clock":"monotonic","unit":"seconds",'
        b'"phases":{"prepare":NaN,"collect":1,"validate":0,"evaluate":0,"render":0,"join":0},'
        b'"core_seconds":2}\n',
        b'{"protocol":"archkeel-core-timings-1","clock":"monotonic","unit":"seconds",'
        b'"phases":{"prepare":0,"collect":Infinity,"validate":0,"evaluate":0,"render":0,"join":0},'
        b'"core_seconds":Infinity}\n',
    ],
)
def test_a_line_that_breaks_the_protocol_is_an_error(stderr: bytes) -> None:
    with pytest.raises(CoreError):
        read_timings(stderr)


def test_a_run_that_was_asked_for_its_timings_and_got_none_is_an_error(
    tmp_path: Path, core_binary: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real = core_only.exchange

    def silent(binary: str, kind: str, request: bytes, stderr_sink: list[bytes]) -> Any:
        answer = real(binary, kind, request, stderr_sink)
        stderr_sink[:] = [b""]
        return answer

    target = tmp_path / "timings.json"
    monkeypatch.setattr(core_only, "locate_core", lambda: core_binary)
    monkeypatch.setattr(core_only, "exchange", silent)
    with case_root(HONEST) as root:
        code, result = run("validate", "--root", str(root), "--timings", str(target))
    assert code == 2, result
    assert "one timings line" in json.dumps(result)
    assert not target.exists()


def test_a_run_that_did_not_ask_for_timings_reads_no_standard_error(
    core_binary: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def noisy(binary: str, kind: str, request: bytes) -> Any:
        assert "timings" not in json.loads(request)
        return real(binary, kind, request)

    real = core_only.exchange
    monkeypatch.setattr(core_only, "locate_core", lambda: core_binary)
    monkeypatch.setattr(core_only, "exchange", noisy)
    with case_root(HONEST) as root:
        code, result = run("validate", "--root", str(root))
    assert code == 0, result
