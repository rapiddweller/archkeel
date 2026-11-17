# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""One output mode for a command line and one JSON head for every result (AD-735).

Each JSON result starts with `command`, `outcome`, `status` and `exit_code`: a run, a refusal,
`init` and `skill`. The fields that a result had before keep their values.
"""

import json
from pathlib import Path

import pytest

from archkeel.cli import core_arguments, core_only
from archkeel.cli.core_arguments import OutputMode
from archkeel.cli.core_binary import CoreBinaryNotFound
from tests.test_cli_init import plant

HEAD = ["command", "outcome", "status", "exit_code"]


def _json(capsys: pytest.CaptureFixture[str], *argv: str) -> tuple[int, dict[str, object]]:
    code = core_only.run([*argv, "--json"])
    return code, json.loads(capsys.readouterr().out)


@pytest.mark.parametrize(
    ("argv", "tty", "mode"),
    [
        (["validate", "--summary"], False, OutputMode.SUMMARY),
        (["validate", "--json"], True, OutputMode.JSON),
        (["validate", "--text"], False, OutputMode.TEXT),
        (["validate"], False, OutputMode.JSON),
        (["validate"], True, OutputMode.TEXT),
        (["report", "--output", "r.html"], False, OutputMode.TEXT),
        (["report", "--output", "r.html", "--json"], False, OutputMode.JSON),
        (["init"], False, OutputMode.TEXT),
        (["init", "--json"], False, OutputMode.JSON),
        (["skill", "install", "claude"], False, OutputMode.JSON),
    ],
)
def test_one_output_mode_for_each_command_line(
    argv: list[str], tty: bool, mode: OutputMode, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(core_arguments.sys.stdout, "isatty", lambda: tty)
    assert core_arguments.output_mode(argv) is mode


def test_a_refusal_starts_with_the_head(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    def no_core() -> Path:
        raise CoreBinaryNotFound("the core binary is missing")

    monkeypatch.setattr(core_only, "locate_core", no_core)
    code, document = _json(capsys, "validate", "--root", str(tmp_path))
    assert list(document)[:4] == HEAD and code == 2
    assert document["command"] == "validate" and document["outcome"] == "command_refused"
    assert (document["status"], document["exit_code"]) == ("UNKNOWN", 2)
    assert document["refusal"] == {  # type: ignore[comparison-overlap]
        "kind": "core_binary_not_found",
        "message": "the core binary is missing",
    }


def test_an_unknown_command_has_no_command_in_the_head(
    capsys: pytest.CaptureFixture[str],
) -> None:
    code, document = _json(capsys, "nosuch")
    assert list(document)[:4] == HEAD and code == 2
    assert document["command"] is None and document["outcome"] == "command_refused"


def test_init_and_skill_complete_without_a_status(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = plant(tmp_path / "p")
    code, document = _json(capsys, "init", "--root", str(root))
    assert list(document)[:4] == HEAD and code == 0
    assert (document["command"], document["outcome"], document["status"]) == (
        "init",
        "completed",
        None,
    )
    assert document["files"] == [  # type: ignore[comparison-overlap]
        "archkeel.toml",
        "architecture-contract.json",
        "docs/architecture/architecture.md",
    ]
    code, document = _json(capsys, "skill", "install", "claude", "--root", str(root))
    assert list(document)[:4] == HEAD and code == 0
    assert (document["command"], document["outcome"], document["status"]) == (
        "skill",
        "completed",
        None,
    )
    assert str(document["path"]).startswith(str(root))


def test_a_run_starts_with_the_head_and_keeps_its_fields(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    release_core: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # #1609: a run needs the shared release core; without it the result is command_refused.
    monkeypatch.setattr(core_only, "locate_core", lambda: release_core)
    root = plant(tmp_path / "p")
    code, document = _json(capsys, "validate", "--root", str(root))
    assert list(document)[:4] == HEAD
    assert (document["command"], document["outcome"]) == ("validate", "verdict")
    assert (document["status"], document["exit_code"], code) == ("UNKNOWN", 2, 2)
    for key in ("frame", "core", "gaps", "init"):
        assert key in document, key
