# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The timings line of the core is read as a whole contract, and a run that was asked for its
timings but got none is an error, not a silent success (#659, review of PR #1834)."""

import json
import os
import stat
from pathlib import Path
from typing import Any

import pytest
from core_support import HONEST, case_root, run

from archkeel.cli import core_only
from archkeel.cli.core_json import CoreError
from archkeel.cli.core_output import read_timings, write_new

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


REFUSED = b'{"protocol":"archkeel-core-timings-1","refused":true}\n'


def test_a_complete_line_of_a_decided_frame_is_kept_as_it_is() -> None:
    line = _line()
    assert read_timings(line, refused=False) == line


def test_the_line_of_a_refused_frame_has_no_seconds_and_gives_no_file() -> None:
    assert read_timings(REFUSED, refused=True) is None


@pytest.mark.parametrize(("stderr", "refused"), [(REFUSED, False), (_line(), True)])
def test_a_line_that_disagrees_with_its_frame_is_an_error(stderr: bytes, refused: bool) -> None:
    with pytest.raises(CoreError, match="its frame says"):
        read_timings(stderr, refused=refused)


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
        _line(phases={**PHASES, "prepare": 10**400}, core_seconds=10**400),
        _line(phases={**PHASES, "prepare": 10**400}),
        b"[" * 100000 + b"\n",
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
        read_timings(stderr, refused=False)


@pytest.mark.parametrize(
    ("stderr", "broken_config", "cause"),
    [
        (b"", False, "one timings line"),
        (REFUSED, False, "its frame says"),
        (_line(), True, "its frame says"),
        (_line(phases={**PHASES, "prepare": 10**400}), False, "too large"),
    ],
)
def test_a_line_that_does_not_fit_the_run_is_an_error_and_writes_no_file(
    tmp_path: Path,
    core_binary: Path,
    monkeypatch: pytest.MonkeyPatch,
    stderr: bytes,
    broken_config: bool,
    cause: str,
) -> None:
    real = core_only.exchange

    def other(binary: str, kind: str, request: bytes, stderr_sink: list[bytes]) -> Any:
        answer = real(binary, kind, request, stderr_sink)
        stderr_sink[:] = [stderr]
        return answer

    target = tmp_path / "timings.json"
    monkeypatch.setattr(core_only, "locate_core", lambda: core_binary)
    monkeypatch.setattr(core_only, "exchange", other)
    with case_root(HONEST) as root:
        if broken_config:
            (root / "archkeel.toml").write_text("[scan\n", encoding="utf-8")
        code, result = run("validate", "--root", str(root), "--timings", str(target))
    assert code == 2, result
    assert cause in json.dumps(result)
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


def test_write_new_creates_a_complete_file_and_leaves_no_temporary_file(tmp_path: Path) -> None:
    target = tmp_path / "timings.json"
    write_new(target, b"complete\n")
    assert target.read_bytes() == b"complete\n"
    assert stat.S_IMODE(target.stat().st_mode) == 0o600
    assert [path.name for path in tmp_path.iterdir()] == ["timings.json"]


def test_write_new_never_replaces_a_file_a_link_or_a_second_name(tmp_path: Path) -> None:
    kept = tmp_path / "kept.txt"
    kept.write_bytes(b"keep\n")
    names = {
        "regular": kept,
        "symlink": tmp_path / "symlink.txt",
        "dangling": tmp_path / "dangling.txt",
        "hardlink": tmp_path / "hardlink.txt",
    }
    names["symlink"].symlink_to(kept)
    names["dangling"].symlink_to(tmp_path / "missing.txt")
    os.link(kept, names["hardlink"])
    for name, path in names.items():
        with pytest.raises(OSError):
            write_new(path, b"new\n")
        assert kept.read_bytes() == b"keep\n", name
    assert not (tmp_path / "missing.txt").exists()
    assert sorted(path.name for path in tmp_path.iterdir()) == sorted(
        path.name for path in names.values()
    ), "no temporary file"


def test_write_new_needs_the_folder_to_exist(tmp_path: Path) -> None:
    with pytest.raises(OSError):
        write_new(tmp_path / "missing" / "timings.json", b"x")
