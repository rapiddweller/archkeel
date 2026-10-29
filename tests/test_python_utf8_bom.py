# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""A Python source with a UTF-8 byte order mark parses as the interpreter parses it (#742).

Rule for positions: the mark is not a character of the source. Line 1 starts after it, so a
column on line 1 is the column the interpreter, `ast` and an editor report.
"""

import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest
from test_architecture_demo import _prepare_repo
from test_python_provider_sources import _captured_sources, _native_facts, _request
from test_python_source_evidence_lines import GUARD, RULE

from archkeel.analyzer.python.source import parse_sources
from archkeel.check.ports import ScanConfig
from archkeel.check.report import run_report
from archkeel.cli.observe import observe
from archkeel.ir.codec import decode_canonical_model, parse_observation
from archkeel.ir.decisions import rule_assessments
from archkeel.ir.protocol import PythonSettings

BOM = b"\xef\xbb\xbf"


def _parse(tmp_path: Path, raw: bytes):
    path = tmp_path / "sample/api.py"
    path.parent.mkdir(exist_ok=True)
    path.write_bytes(raw)
    return parse_sources([path], root=tmp_path, namespace="sample")


@pytest.mark.parametrize(
    "raw",
    [
        b"x = 1\n",
        BOM + b"x = 1\n",
        BOM + b"# coding: utf-8\nx = 1\n",
        BOM + b"#!/usr/bin/env python\n# -*- coding: utf-8 -*-\nx = 1\n",
        BOM + b"x = 1\r\n",
        BOM + b"x = 1\r",
        BOM + b"x = 1",
        BOM,
        BOM + b"\n",
    ],
    ids=[
        "no-bom",
        "bom-code",
        "bom-cookie-utf8",
        "bom-cookie-second-line",
        "bom-crlf",
        "bom-cr",
        "bom-no-eof-newline",
        "bom-only",
        "bom-newline",
    ],
)
def test_source_with_a_mark_parses_and_keeps_its_bytes(tmp_path: Path, raw: bytes) -> None:
    parsed = _parse(tmp_path, raw)
    assert not parsed.failures
    (module,) = parsed.modules
    assert "\ufeff" not in module.source
    assert module.source == raw.removeprefix(BOM).decode()
    # The digest and the stored bytes cover the file as it is on disk, mark included.
    assert module.source_bytes == raw
    assert parsed.source_digest == hashlib.sha256(b"sample/api.py\0" + raw + b"\0").hexdigest()


def test_first_line_column_ignores_the_mark(tmp_path: Path) -> None:
    (module,) = _parse(tmp_path, BOM + b"x = 1\n").modules
    assert (module.tree.body[0].col_offset, module.tree.body[0].end_col_offset) == (0, 5)
    assert module.lines[0] == "x = 1"


@pytest.mark.parametrize(
    ("raw", "line", "message"),
    [
        (BOM + b"# coding: latin-1\nx = 1\n", 1, "encoding problem"),
        (BOM + BOM + b"x = 1\n", 1, "invalid non-printable character U+FEFF"),
        (b"x = 1\n" + BOM + b"y = 2\n", 2, "invalid non-printable character U+FEFF"),
        (b"x = 1\ny = 2 " + BOM + b"\n", 2, "invalid non-printable character U+FEFF"),
    ],
    ids=["bom-cookie-latin1", "two-marks", "mark-in-file", "mark-in-line"],
)
def test_source_the_interpreter_rejects_stays_a_failure(
    tmp_path: Path, raw: bytes, line: int, message: str
) -> None:
    with pytest.raises(SyntaxError):
        compile(raw, "api.py", "exec")
    parsed = _parse(tmp_path, raw)
    assert not parsed.modules
    [failure] = parsed.failures
    assert failure["kind"] == "SyntaxError"
    assert (failure["data"]["file"], failure["data"]["line"]) == ("sample/api.py", line)
    assert message in failure["data"]["message"]


def test_cookie_without_a_mark_is_decoded_as_before(tmp_path: Path) -> None:
    parsed = _parse(tmp_path, b"# coding: latin-1\nx = 1\n")
    assert not parsed.failures and len(parsed.modules) == 1


def _model(tmp_path: Path, prefix: bytes):
    source = "def _probe(value): return value == 'node16'\n"
    files = {
        "sample/__init__.py": "",
        "sample/api.py": source,
        "contract.json": json.dumps(GUARD),
    }
    root = _prepare_repo(tmp_path, files)
    for name in ("sample/__init__.py", "sample/api.py"):
        path = root / name
        path.write_bytes(prefix + path.read_bytes())
    result, encoded = run_report(
        root,
        config=ScanConfig(("sample",), "sample", "contract.json", "0" * 64),
        analyzer=observe,
    )
    assert result.exit_code == 0 and encoded is not None, result.diagnostics
    return parse_observation(decode_canonical_model(json.loads(encoded)))


def _verdict(model):
    rule = next(row for row in rule_assessments(model, undecided_by_rule={}) if row.id == RULE)
    evidence = sorted(
        (row.file, row.line, row.column, row.end_line, row.excerpt) for row in model.evidence
    )
    return rule.status, rule.evaluation_proven, model.records("violations") != (), evidence


def test_whole_pipeline_gives_the_same_verdict_with_and_without_a_mark(tmp_path: Path) -> None:
    plain = _verdict(_model(tmp_path / "plain", b""))
    marked = _verdict(_model(tmp_path / "marked", BOM))
    assert plain[:3] == ("FAIL", True, True)
    assert any(item[:3] == ("sample/api.py", 1, 26) for item in plain[3])
    assert marked == plain


@pytest.mark.parametrize(
    ("raw", "text"),
    [
        (BOM + b"name = 1\r\n", "name = 1\r\n"),
        (BOM + b"# coding: utf-8\nname = 1\n", "# coding: utf-8\nname = 1\n"),
        (b"name = 1\n", "name = 1\n"),
        (BOM + b"# coding: latin-1\nname = 1\n", None),
    ],
    ids=["bom", "bom-cookie-utf8", "no-bom", "bom-cookie-latin1"],
)
def test_provider_source_is_captured_without_the_mark(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, raw: bytes, text: str | None
) -> None:
    library = tmp_path / "library"
    library.mkdir()
    (library / "bomprovider.py").write_bytes(raw)
    monkeypatch.syspath_prepend(str(library))
    request = _request(tmp_path / "project", imported="bomprovider", binding="name")
    captured = _captured_sources(request)
    if text is None:
        assert captured == ()
        return
    [provider] = captured
    assert provider.source == text
    # The protocol digest covers the transmitted text, which the request codec checks again.
    assert provider.digest == hashlib.sha256(text.encode()).hexdigest()
    facts = _native_facts(replace(request, resolver=PythonSettings(provider_sources=captured)))
    assert [
        (item.path, item.digest) for item in facts.inputs if item.role.name == "RESOLUTION"
    ] == [(provider.path, provider.digest)]
