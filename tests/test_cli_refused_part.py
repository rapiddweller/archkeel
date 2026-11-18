# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The words of a refusal of the core and of its collector, read in one place (AD-735).

`_RefusedPart` is the closed set of parts that the Rust collector refuses by name; a test reads the
Rust sources, so a new part cannot reach the user without a word and a fix. `CoreExit` names the
exit codes of the core in one module. The typed refusal `parse_work_limit` has its own kind.
"""

import json
import re
from pathlib import Path

import pytest

from archkeel.cli import core_only
from archkeel.cli.core_frame import CoreError, Gap, GapKind
from archkeel.cli.core_json import CoreExit
from archkeel.cli.core_words import _refused_part, _RefusedPart, fix_for

ROOT = Path(__file__).resolve().parents[1]
COLLECTOR = ROOT / "native" / "collect" / "src"
# `refused("part", ...)`, `Refused::Unsupported("part", ...)` and `part: "part"` of a `Refusal`.
PART = re.compile(r'(?:\brefused|Refused::Unsupported)\(\s*"([^"]+)"|\bpart:\s*"([^"]+)"')


def _collector_parts() -> set[str]:
    found: set[str] = set()
    for path in COLLECTOR.rglob("*.rs"):
        if path.name.endswith("_tests.rs"):
            continue
        for match in PART.finditer(path.read_text(encoding="utf-8")):
            found.add((match[1] or match[2]).lower())
    return found


def test_every_part_that_the_collector_refuses_is_a_refused_part() -> None:
    # Older collectors can still return the retired Dart scan refusal.
    assert _collector_parts() | {_RefusedPart.SCAN.value} == {part.value for part in _RefusedPart}


@pytest.mark.parametrize(
    ("message", "part"),
    [
        ("config: cannot read archkeel.toml", _RefusedPart.CONFIG),
        ("Root: not a Git work tree", _RefusedPart.ROOT),
        ("git head: the shell names the commit a, and HEAD is b", _RefusedPart.GIT_HEAD),
        ("scan: test exclusion is not supported", _RefusedPart.SCAN),
        ("work budget: more than 5 files", _RefusedPart.WORK_BUDGET),
        ("a message without a part", None),
        ("unknownpart: why", None),
    ],
)
def test_the_part_of_a_refusal_is_read_in_one_place(
    message: str, part: _RefusedPart | None
) -> None:
    assert _refused_part(message) is part


@pytest.mark.parametrize(
    ("message", "start"),
    [
        ("config: cannot read archkeel.toml", "create archkeel.toml"),
        ("root: not a Git work tree", "run inside a Git work tree"),
        ("contract: missing", "check `contract` under [scan]"),
        ("system: bad part", "check the system document"),
        ("git head: moved", "read the problem above"),
        ("collector: file or folder not found", "check the path and run again."),
        ("dirty: permission denied", "check the permissions"),
        ("Rust worker: permission denied", "check that the installed Rust worker"),
    ],
)
def test_each_refused_part_keeps_its_fix(message: str, start: str) -> None:
    fix = fix_for("collection_refused", message)
    assert fix is not None and fix.startswith(start), fix


def test_the_exit_codes_of_the_core_are_named_once() -> None:
    assert (CoreExit.DECIDED, CoreExit.REFUSED, CoreExit.NAMES_A_GAP) == (0, 2, 3)


def test_a_parse_work_refusal_of_the_core_has_its_own_kind_and_fix(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    def refused(*_: object) -> tuple[bytes, int]:
        gap = Gap(GapKind.PARSE_WORK_LIMIT, "src/deep.ts", "too deep")
        raise CoreError("the core refused the request (exit 2): too deep", gap=gap)

    monkeypatch.setattr(core_only, "locate_core", lambda: tmp_path / "archkeel-core")
    monkeypatch.setattr(core_only, "exchange", refused)
    code = core_only.run(["validate", "--root", str(tmp_path), "--json"])
    document = json.loads(capsys.readouterr().out)
    assert code == 2 and document["refusal"]["kind"] == "parse_work_limit"
    assert "src/deep.ts: too deep" in document["refusal"]["message"]
    core_only.run(["validate", "--root", str(tmp_path), "--text"])
    assert capsys.readouterr().out.splitlines()[-1] == (
        "Fix: the file is larger or deeper than the scan reads; split it, or leave it out of "
        "the scan roots."
    )


def test_a_refusal_prints_the_paths_that_the_core_gives(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A refusal that names two files shows both (pydantic scan: the duplicate record id)."""
    message = (
        "collect: unsupported: collector: the store refuses the reply of the collector: "
        "duplicate source record id: a/vendor/httpx2/x.py, b/vendor/httpx2/x.py"
    )

    def refused(*_: object) -> tuple[bytes, int]:
        raise CoreError(message)

    monkeypatch.setattr(core_only, "locate_core", lambda: tmp_path / "archkeel-core")
    monkeypatch.setattr(core_only, "exchange", refused)
    core_only.run(["validate", "--root", str(tmp_path), "--text"])
    shown = capsys.readouterr().out
    assert "a/vendor/httpx2/x.py" in shown and "b/vendor/httpx2/x.py" in shown, shown
    core_only.run(["validate", "--root", str(tmp_path), "--json"])
    assert "b/vendor/httpx2/x.py" in capsys.readouterr().out


def test_a_repository_without_a_commit_has_a_fix_that_says_what_to_do() -> None:
    message = (
        "git head: this Git repository has no commit yet (HEAD names refs/heads/main, which no "
        "commit made); commit once, or run with --root on a folder"
    )
    assert _refused_part(message) is _RefusedPart.GIT_HEAD


@pytest.mark.parametrize(
    ("message", "start"),
    [
        ("config: cannot read archkeel.toml", "create archkeel.toml"),
        ("config: scan TypeScript config is not a file: tsconfig.json", "create that file"),
        ("config: scan contract is not a file: c.json", "create that file"),
        ("config: scan root is not a directory or file: lib", "create that folder"),
        ("config: scan.roots must be a non-empty list", "correct that key"),
    ],
)
def test_a_config_refusal_names_the_fix_of_its_cause(message: str, start: str) -> None:
    """#1708: an existing configuration that names a missing tsconfig was told to create
    archkeel.toml."""
    fix = fix_for("collection_refused", message)
    assert fix is not None and fix.startswith(start), fix
