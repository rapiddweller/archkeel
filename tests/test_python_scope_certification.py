# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Python scope receipts must reflect parsed content and physical file paths."""

import json
import subprocess
from pathlib import Path

import pytest
from test_analyzer import _component
from test_cycle_levels import _component as _cycle_component
from test_inside_rule_coverage import _inside_rule_report

from archkeel.analyzer import observe
from archkeel.cli import main
from archkeel.ir.codec import decode_canonical_model, parse_observation
from archkeel.ir.decisions import rule_assessments
from archkeel.ir.model import Observation


@pytest.mark.parametrize(
    ("initializer", "expected", "exit_code"),
    [
        ("# package notice\n", ("PASS", True), 0),
        (" \n\t", ("PASS", True), 0),
        ('"""package docs"""\n', ("UNKNOWN", False), 0),
        ("from . import api\n", ("UNKNOWN", False), 0),
        ("if True\n    pass\n", ("UNKNOWN", False), 2),
    ],
    ids=["comments-only", "whitespace-only", "docstring", "import", "parse-error"],
)
def test_unowned_package_initializer_is_exempt_only_when_it_has_no_statements(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    initializer: str,
    expected: tuple[str, bool],
    exit_code: int,
) -> None:
    code, payload, observation, html = _inside_rule_report(
        tmp_path,
        [_component("app", packages=["sample.api"], public=[])],
        capsys,
        modules={"__init__.py": initializer, "api.py": "VALUE = 1\n"},
    )

    assert code == exit_code, json.dumps(payload, indent=2)
    assert payload["declared_rules"] == expected[0]
    assert {
        item["id"]: (item["status"], item["evaluation_proven"])
        for item in payload["rule_assessments"]
    } == {
        "app:INTERFACE": expected,
        "app:REQUIRES": expected,
    }
    if exit_code == 2:
        assert payload["diagnostics"][0]["kind"] == "parse_error"
        assert payload["coverage"]["status"] == "FAIL"
        return
    initializer_record = next(
        item
        for item in observation.records("modules") or ()
        if item.data.get("file") == "sample/__init__.py"
    )
    assert initializer_record.data.get("file") == "sample/__init__.py"
    row = html[html.index('data-search="app:INTERFACE ') :]
    row = row[: row.index("</tr>")]
    assert f'data-status="{expected[0].lower()}"' in row


def _cycle_report(
    root: Path,
    capsys: pytest.CaptureFixture[str],
    *,
    roots: tuple[str, ...],
    cycle: bool = False,
) -> tuple[dict[str, object], Observation, str]:
    (root / "pyproject.toml").write_text('[project]\nrequires-python = ">=3.11"\n')
    (root / "archkeel.toml").write_text(
        f'[scan]\nroots = {json.dumps(roots)}\nnamespace = "sample"\ncontract = "contract.json"\n'
    )
    (root / "contract.json").write_text(
        json.dumps(
            {
                "schema_version": "2.1.0",
                "components": [],
                "rules": [
                    {
                        "id": "MODULE-CYCLES",
                        "kind": "no_component_cycles",
                        "level": "module",
                        "rationale": "Check scanned module cycles.",
                        "provenance": ["contract.json"],
                        "decided_by": "architect",
                    }
                ],
            }
        )
    )
    sources = {
        "__init__.py": "",
        "resources/demos/demo/script/generator.scr.py": "class Generator: pass\n",
    }
    if cycle:
        sources.update({"a.py": "import sample.b\n", "b.py": "import sample.a\n"})
    for relative, source in sources.items():
        path = root / "sample" / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source)
    for args in (
        ["git", "init", "-q", "-b", "main"],
        ["git", "config", "user.email", "qa@example.invalid"],
        ["git", "config", "user.name", "QA"],
        ["git", "add", "-A"],
        ["git", "-c", "commit.gpgsign=false", "commit", "-q", "-m", "fixture"],
    ):
        subprocess.run(args, cwd=root, check=True, capture_output=True)

    output = root / "architecture.json"
    code = main(["report", "--root", str(root), "--output", str(output), "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 0, json.dumps(payload, indent=2)
    observation = parse_observation(decode_canonical_model(json.loads(output.read_bytes())))
    return payload, observation, (root / "architecture.report.html").read_text()


def test_dotted_python_stem_does_not_make_a_complete_module_cycle_scan_unknown(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    payload, observation, html = _cycle_report(tmp_path, capsys, roots=("sample",))

    assert payload["declared_rules"] == "PASS"
    assert payload["rule_assessments"][0]["status"] == "PASS"
    assert payload["rule_assessments"][0]["evaluation_proven"] is True
    assert any(
        item.data.get("file") == "sample/resources/demos/demo/script/generator.scr.py"
        for item in observation.records("modules") or ()
    )
    row = html[html.index('data-search="MODULE-CYCLES ') :]
    row = row[: row.index("</tr>")]
    assert 'data-status="pass"' in row and ">PASS</strong>" in row


def test_partial_nested_scan_with_dotted_python_stem_stays_unknown(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    payload, _, html = _cycle_report(
        tmp_path,
        capsys,
        roots=("sample/resources/demos/demo/script",),
    )

    assert payload["declared_rules"] == "UNKNOWN"
    assert payload["rule_assessments"][0]["status"] == "UNKNOWN"
    row = html[html.index('data-search="MODULE-CYCLES ') :]
    row = row[: row.index("</tr>")]
    assert 'data-status="unknown"' in row and ">UNKNOWN</strong>" in row


def test_real_module_cycle_remains_fail_with_a_dotted_python_stem(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    payload, observation, html = _cycle_report(tmp_path, capsys, roots=("sample",), cycle=True)

    assert payload["declared_rules"] == "FAIL"
    assert any(item.kind == "module_cycle" for item in observation.records("violations") or ())
    row = html[html.index('data-search="MODULE-CYCLES ') :]
    row = row[: row.index("</tr>")]
    assert 'data-status="fail"' in row and ">FAIL</strong>" in row


def test_partial_scan_cannot_prove_cycle_scope_across_a_dotted_directory(
    tmp_path: Path,
) -> None:
    """A second physical domain can share the owned module prefix without a `core` path part."""
    (tmp_path / "pyproject.toml").write_text('[project]\nrequires-python = ">=3.11"\n')
    (tmp_path / "contract.json").write_text(
        json.dumps(
            {
                "schema_version": "2.1.0",
                "components": [_cycle_component("core")],
                "rules": [
                    {
                        "id": "RULE",
                        "kind": "no_component_cycles",
                        "rationale": "Check the complete cycle domain.",
                        "provenance": ["docs/architecture/sample.md"],
                        "decided_by": "architect",
                    }
                ],
            }
        )
    )
    sources = {
        "first/sample/core/api.py": "VALUE = 1\n",
        "second/sample/core.extra/visible/api.py": "VALUE = 1\n",
        "second/sample/core.extra/hidden.py": "VALUE = 1\n",
    }
    for relative, source in sources.items():
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source)

    result = observe(
        tmp_path,
        roots=("first/sample/core", "second/sample/core.extra/visible"),
        namespace="sample",
        contract="contract.json",
        git_head="a" * 40,
        dirty=False,
        contract_root=tmp_path,
    )
    assert result.observation is not None, result.diagnostics
    observation = result.observation
    modules = observation.records("modules") or ()

    assert any(item.data.get("file") == "first/sample/core/api.py" for item in modules)
    assert any(
        item.data.get("file") == "second/sample/core.extra/visible/api.py" for item in modules
    )
    assert not any(
        item.data.get("file") == "second/sample/core.extra/hidden.py" for item in modules
    )
    full_scan = observe(
        tmp_path,
        roots=("first/sample/core", "second/sample"),
        namespace="sample",
        contract="contract.json",
        git_head="a" * 40,
        dirty=False,
        contract_root=tmp_path,
    )
    assert full_scan.observation is not None, full_scan.diagnostics
    full_modules = full_scan.observation.records("modules") or ()
    assert any(
        item.data.get("file") == "second/sample/core.extra/hidden.py" for item in full_modules
    )
    assert {
        item.id: item.status
        for item in rule_assessments(full_scan.observation, undecided_by_rule={})
    }["RULE"] in {"PASS", "UNKNOWN"}
    assert {
        item.id: (item.status, item.evaluation_proven)
        for item in rule_assessments(observation, undecided_by_rule={})
    }["RULE"] == ("UNKNOWN", False)


def test_namespace_nested_under_dotted_source_root_can_prove_owned_package_scope(
    tmp_path: Path,
) -> None:
    (tmp_path / "pyproject.toml").write_text('[project]\nrequires-python = ">=3.11"\n')
    (tmp_path / "contract.json").write_text(
        json.dumps(
            {
                "schema_version": "2.1.0",
                "components": [_cycle_component("core")],
                "rules": [
                    {
                        "id": "RULE",
                        "kind": "no_component_cycles",
                        "rationale": "Check the complete cycle domain.",
                        "provenance": ["docs/architecture/sample.md"],
                        "decided_by": "architect",
                    }
                ],
            }
        )
    )
    source = tmp_path / "sample.core/src/sample/core/api.py"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("VALUE = 1\n")

    result = observe(
        tmp_path,
        roots=("sample.core/src/sample",),
        namespace="sample",
        contract="contract.json",
        git_head="a" * 40,
        dirty=False,
        contract_root=tmp_path,
    )

    assert result.observation is not None, result.diagnostics
    modules = result.observation.records("modules") or ()
    assert any(
        item.data.get("file") == "sample.core/src/sample/core/api.py"
        and item.data.get("qualified_name") == "sample.core.api"
        for item in modules
    )
    assert {
        item.id: (item.status, item.evaluation_proven)
        for item in rule_assessments(result.observation, undecided_by_rule={})
    }["RULE"] == ("PASS", True)
