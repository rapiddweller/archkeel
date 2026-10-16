# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Python AST source evidence follows physical newlines, not Unicode string data."""

import hashlib
import json

import pytest
from test_architecture_demo import _prepare_repo

from archkeel.analyzer.python.source import parse_sources
from archkeel.check.ports import ScanConfig
from archkeel.check.report import run_report
from archkeel.cli.observe import observe
from archkeel.ir.codec import decode_canonical_model, parse_observation
from archkeel.ir.decisions import rule_assessments
from archkeel.ir.trace import trace_valid_violations

RULE = "PYTHON-PHYSICAL-LINE-COMPARISON"
GUARD = {
    "schema_version": "2.2.0",
    "components": [
        {
            "id": "sample",
            "label": "sample",
            "role": "component",
            "packages": ["sample"],
            "responsibilities": ["Own the observed source."],
            "forbidden_responsibilities": [],
            "public": [],
            "provenance": ["contract.json"],
            "decided_by": "architect",
        }
    ],
    "rules": [
        {
            "id": RULE,
            "kind": "forbidden_construct",
            "source": "sample",
            "constructs": ["string_literal_compare"],
            "rationale": "Every reported comparison must cite its actual Python source line.",
            "provenance": ["contract.json"],
            "decided_by": "architect",
        }
    ],
}


def _source(newline, eof, alias):
    # Both characters are actual string data in the scanned Python program.
    lines = ['marker = "' + "\u2028\u2029" + '"', "", ""]
    if alias:
        lines += ["from typing import Final", 'TOKEN: Final[str] = "node16"']
    lines += ["def _probe(value):", "    return value == TOKEN" if alias else '    return value == "node16"']
    source = newline.join(lines) + (newline if eof else "")
    return source, len(lines), lines[-1]


@pytest.mark.parametrize("newline", ["\n", "\r\n", "\r"], ids=["lf", "crlf", "cr"])
@pytest.mark.parametrize("eof", [False, True], ids=["no-eof-newline", "eof-newline"])
@pytest.mark.parametrize("alias", [False, True], ids=["literal", "final-alias"])
def test_native_unicode_literal_preserves_exact_physical_source_trace(tmp_path, newline, eof, alias):
    source, expected_line, expected_excerpt = _source(newline, eof, alias)
    root = _prepare_repo(
        tmp_path,
        {"sample/__init__.py": "", "sample/api.py": source, "contract.json": json.dumps(GUARD)},
    )
    # _prepare_repo writes text without altering the requested source line endings.
    assert (root / "sample/api.py").read_bytes() == source.encode()
    result, encoded = run_report(
        root,
        config=ScanConfig(("sample",), "sample", "contract.json", "0" * 64),
        analyzer=observe,
    )
    assert result.exit_code == 0 and encoded is not None, result.diagnostics
    model = parse_observation(decode_canonical_model(json.loads(encoded)))
    rule = next(row for row in rule_assessments(model, undecided_by_rule={}) if row.id == RULE)
    assert rule.status == "FAIL" and rule.evaluation_proven
    violations = model.records("violations")
    assert len(violations) == 1
    assert trace_valid_violations(model) == violations
    records = {row.id: row for section in model.sections for row in section.records}
    evidence = {row.id: row for row in model.evidence}
    facts = [records[key] for key in violations[0].fact_ids]
    assert len(facts) == 1 and facts[0].kind == "string_literal_compare"
    cited = [evidence[key] for key in facts[0].evidence_ids]
    assert len(cited) == 1
    assert (cited[0].file, cited[0].line, cited[0].end_line, cited[0].excerpt) == (
        "sample/api.py",
        expected_line,
        expected_line,
        expected_excerpt,
    )


@pytest.mark.parametrize("newline", ["\n", "\r\n", "\r"], ids=["lf", "crlf", "cr"])
@pytest.mark.parametrize("eof", [False, True], ids=["no-eof-newline", "eof-newline"])
def test_physical_line_view_keeps_original_source_bytes_and_digest(tmp_path, newline, eof):
    source, expected_line, expected_excerpt = _source(newline, eof, False)
    path = tmp_path / "sample/api.py"
    path.parent.mkdir()
    raw = source.encode()
    path.write_bytes(raw)
    parsed = parse_sources([path], root=tmp_path, namespace="sample")
    assert not parsed.failures
    (module,) = parsed.modules
    assert module.source == source and module.source_bytes == raw
    assert parsed.source_digest == hashlib.sha256(b"sample/api.py\0" + raw + b"\0").hexdigest()
    assert module.lines[expected_line - 1] == expected_excerpt
