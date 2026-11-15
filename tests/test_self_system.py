# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-522: the system line is the weakest verdict of the parts and never trusts a bad result."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from tools import self_system
from tools.report_product import contract_of
from tools.system_parts import ROOT, SystemPart

COMMIT = "a" * 40
CORE = "archkeel-core " + "1" * 64


def envelope(
    status: object,
    rows: list[str] | None = None,
    exit_code: object = None,
    commit: str = COMMIT,
    core: str = CORE,
    **extra: Any,
) -> dict[str, Any]:
    document: dict[str, Any] = {
        "status": status,
        "frame": {
            "rules": {f"r{i}": ["kind", word] for i, word in enumerate(rows or [])},
            "engine": core,
            "self_test": {"collect": {"request": {"snapshot": {"git_head": commit}}}},
        },
        **extra,
    }
    if exit_code is not None:
        document["exit_code"] = exit_code
    return document


PASS = envelope("PASS", ["PASS", "PASS"], 0)


def document(tmp_path: Path, names: list[str]) -> Path:
    parts = [
        {"id": name, "title": name.upper(), "config": "native/archkeel.toml"} for name in names
    ]
    path = tmp_path / "system.json"
    path.write_text(json.dumps({"kind": "system", "title": "Demo", "parts": parts}))
    return path


def line(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    results: dict[str, object],
) -> list[str]:
    """The printed lines for a document with one part for each key of `results`."""

    def fake(cli: list[str], part: SystemPart) -> Any:
        value = results[part.id]
        if isinstance(value, Exception):
            return contract_of(None, part.title, f"no result: {type(value).__name__}")
        return contract_of(value, part.title)

    monkeypatch.setattr(self_system, "run_part", fake)
    system = document(tmp_path, list(results))
    assert self_system.main(["--system", str(system)]) == 0
    return capsys.readouterr().out.splitlines()


@pytest.mark.parametrize(
    ("second", "status", "counts"),
    [
        (PASS, "PASS", "4 PASS · 0 FAIL · 0 UNKNOWN"),
        (envelope("FAIL", ["FAIL"], 1), "FAIL", "2 PASS · 1 FAIL · 0 UNKNOWN"),
        (envelope("UNKNOWN", ["UNKNOWN"], 2), "UNKNOWN", "2 PASS · 0 FAIL · 1 UNKNOWN"),
        (OSError("missing"), "UNKNOWN", "2 PASS · 0 FAIL · 0 UNKNOWN"),
        ({}, "UNKNOWN", "2 PASS · 0 FAIL · 0 UNKNOWN"),
        ([], "UNKNOWN", "2 PASS · 0 FAIL · 0 UNKNOWN"),
        (None, "UNKNOWN", "2 PASS · 0 FAIL · 0 UNKNOWN"),
        ({"status": None, "frame": {}}, "UNKNOWN", "2 PASS · 0 FAIL · 0 UNKNOWN"),
        (envelope("fail", ["FAIL"], 1), "FAIL", "2 PASS · 1 FAIL · 0 UNKNOWN"),
        (envelope("PASS", ["PASS"], 0, refusal={"message": "x"}), "UNKNOWN", "2 PASS"),
    ],
    ids=[
        "pass",
        "fail",
        "unknown",
        "missing",
        "empty-object",
        "list",
        "null",
        "null-status",
        "lowercase",
        "refusal",
    ],
)
def test_the_system_is_the_weakest_part_and_a_bad_result_is_never_a_pass(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    second: object,
    status: str,
    counts: str,
) -> None:
    out = line(capsys, monkeypatch, tmp_path, {"one": PASS, "two": second})
    assert out[0].startswith(f"Demo (ONE + TWO): {status}: {counts}"), out
    assert len(out) == 3


def test_a_status_that_the_rows_or_the_exit_code_contradict_is_the_weaker_of_both(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    for second, status in [
        (envelope("PASS", ["FAIL", "PASS"], 0), "FAIL"),
        (envelope("PASS", ["UNKNOWN", "PASS"], 0), "UNKNOWN"),
        (envelope("PASS", ["PASS"], 2), "UNKNOWN"),
        (envelope("PASS", ["PASS"], 1), "FAIL"),
        (envelope("PASS", ["PASS"], 7), "UNKNOWN"),
        (envelope("PASS", ["PASS"], "0"), "UNKNOWN"),
        (envelope("FAIL", ["PASS"], 0), "FAIL"),
    ]:
        out = line(capsys, monkeypatch, tmp_path, {"one": PASS, "two": second})
        assert f": {status}: " in out[0], (second, out)
        assert f"  TWO: {status}: " in out[2], out


def test_parts_from_different_commits_or_cores_are_unknown_with_the_cause(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    other = envelope("PASS", ["PASS"], 0, commit="b" * 40)
    out = line(capsys, monkeypatch, tmp_path, {"one": PASS, "two": other})
    assert ": UNKNOWN: " in out[0] and "(parts are from different commits)" in out[0]
    other = envelope("PASS", ["PASS"], 0, core="archkeel-core " + "2" * 64)
    out = line(capsys, monkeypatch, tmp_path, {"one": PASS, "two": other})
    assert ": UNKNOWN: " in out[0] and "(parts ran with different cores)" in out[0]
    # A FAIL stays a FAIL; the cause is still named.
    fail = envelope("FAIL", ["FAIL"], 1, commit="b" * 40)
    out = line(capsys, monkeypatch, tmp_path, {"one": PASS, "two": fail})
    assert ": FAIL: " in out[0] and "different commits" in out[0]


def test_a_third_part_of_the_document_is_a_third_line_and_the_weakest_verdict_wins(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    results = {"one": PASS, "two": PASS, "three": envelope("UNKNOWN", ["UNKNOWN"], 2)}
    out = line(capsys, monkeypatch, tmp_path, results)
    assert out[0] == "Demo (ONE + TWO + THREE): UNKNOWN: 4 PASS · 0 FAIL · 1 UNKNOWN"
    assert [row.split(":")[0].strip() for row in out[1:]] == ["ONE", "TWO", "THREE"]


def test_the_runner_asks_the_cli_to_validate_the_config_of_the_part(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[list[str]] = []

    def fake(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        seen.append(command)
        return subprocess.CompletedProcess(command, 1, json.dumps(PASS), "")

    monkeypatch.setattr(subprocess, "run", fake)
    part = SystemPart("x", "X", "native/archkeel.toml", "RUST", "X")
    result = self_system.run_part(["uv", "run", "archkeel"], part)
    assert seen == [
        ["uv", "run", "archkeel", "validate", "--config", "native/archkeel.toml", "--json"]
    ]
    assert result.status == "PASS" and (ROOT / part.config).is_file()
    monkeypatch.setattr(
        subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, 2, "", "")
    )
    assert not self_system.run_part(["x"], part).decided
