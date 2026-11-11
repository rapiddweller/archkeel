# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""A package shadows a module of the same name, as the import system resolves it (#797)."""

import json
from pathlib import Path

from test_architecture_demo import _prepare_repo
from test_python_source_evidence_lines import GUARD, RULE

from archkeel.analyzer.python.source import parse_sources
from archkeel.check.ports import ScanConfig
from archkeel.check.report import run_report
from archkeel.cli.observe import observe
from archkeel.ir.codec import decode_canonical_model, parse_observation
from archkeel.ir.decisions import rule_assessments


def _write(tmp_path: Path, *names: str) -> list[Path]:
    paths = []
    for name in names:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("import json\n", encoding="utf-8")
        paths.append(path)
    return paths


def test_package_wins_and_the_shadowed_module_is_a_named_gap(tmp_path: Path) -> None:
    paths = _write(tmp_path, "app/__init__.py", "app/fmt.py", "app/fmt/__init__.py")
    parsed = parse_sources(paths, root=tmp_path, namespace="app")
    by_path = {module.rel_path: module.module for module in parsed.modules}
    assert by_path == {"app/__init__.py": "app", "app/fmt/__init__.py": "app.fmt"}
    assert [failure["data"]["file"] for failure in parsed.failures] == ["app/fmt.py"]
    assert "app.fmt" in parsed.failures[0]["data"]["message"]
    assert "shadowed" in parsed.failures[0]["data"]["message"]


def test_the_result_does_not_depend_on_the_path_order(tmp_path: Path) -> None:
    paths = _write(tmp_path, "app/__init__.py", "app/fmt.py", "app/fmt/__init__.py")
    parsed = parse_sources(paths[::-1], root=tmp_path, namespace="app")
    assert sorted(module.rel_path for module in parsed.modules) == [
        "app/__init__.py",
        "app/fmt/__init__.py",
    ]
    assert [failure["data"]["file"] for failure in parsed.failures] == ["app/fmt.py"]


def test_a_violation_in_the_package_fails_and_the_shadowed_module_is_named(tmp_path: Path) -> None:
    source = "def _probe(value): return value == 'node16'\n"
    root = _prepare_repo(
        tmp_path,
        {
            "sample/__init__.py": "",
            "sample/fmt.py": source,
            "sample/fmt/__init__.py": source,
            "contract.json": json.dumps(GUARD),
        },
    )
    result, encoded = run_report(
        root,
        config=ScanConfig(("sample",), "sample", "contract.json", "0" * 64),
        analyzer=observe,
    )
    assert encoded is not None, result.diagnostics
    model = parse_observation(decode_canonical_model(json.loads(encoded)))
    rule = next(row for row in rule_assessments(model, undecided_by_rule={}) if row.id == RULE)
    assert rule.status == "FAIL"
    assert {row.file for row in model.evidence if row.excerpt} >= {"sample/fmt/__init__.py"}
    assert "sample/fmt.py" in json.dumps(model.records("unknowns"), default=str)
