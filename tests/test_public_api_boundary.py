# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Public API closure includes resolved signature types and inherited public fields.

Unproven inheritance retains UNKNOWN with source evidence (AD-73, AD-131).
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from test_analyzer import _component
from test_html_report import _native_details

from archkeel.cli import main
from archkeel.ir.codec import decode_canonical_model, parse_observation


def _prepare(tmp_path: Path, public_api: list[str], facade_source: str) -> Path:
    (tmp_path / "pyproject.toml").write_text('[project]\nrequires-python = ">=3.11"\n')
    contract = {
        "schema_version": "2.1.0",
        "components": [],
        "rules": [],
        "declarations": {"public_api": public_api},
    }
    (tmp_path / "contract.json").write_text(json.dumps(contract))
    package = tmp_path / "sample"
    package.mkdir()
    (package / "__init__.py").write_text("")
    (package / "facade.py").write_text(facade_source)
    return tmp_path


def _commit_public_api_fixture(tmp_path: Path, public: tuple[str, ...] = ()) -> None:
    contract = json.loads((tmp_path / "contract.json").read_text())
    component = _component("sample", packages=["sample"], public=list(public))
    component["provenance"] = ["probe.md"]
    contract["components"] = [component]
    contract["declarations"]["public_api_provenance"] = ["probe.md"]
    (tmp_path / "contract.json").write_text(json.dumps(contract))
    (tmp_path / "probe.md").write_text(
        "<!-- archkeel-component-graph -->\n```mermaid\nflowchart TD\n    sample\n```\n"
    )
    (tmp_path / "archkeel.toml").write_text(
        '[scan]\nroots = ["sample"]\nnamespace = "sample"\ncontract = "contract.json"\n'
    )
    for args in (
        ["git", "init", "-q", "-b", "main"],
        ["git", "add", "."],
        [
            "git",
            "-c",
            "user.name=Demo",
            "-c",
            "user.email=demo@example.invalid",
            "-c",
            "commit.gpgsign=false",
            "commit",
            "-qm",
            "fixture",
        ],
    ):
        subprocess.run(args, cwd=tmp_path, check=True, capture_output=True)


@pytest.mark.parametrize(
    ("entries", "source", "exit_code", "status"),
    [
        (["sample:ChildPublic"], "class Child(Base): pass\n", 2, "PASS"),
        (["sample.facade:Child"], "class Child(Base): pass\n", 2, "PASS"),
        (["sample:Public"], "class Child(Base): pass\n", 2, "PASS"),
        (["sample:Public", "sample.facade:Nested"], "class Child(Base): pass\n", 0, "PASS"),
        (["sample:ChildPublic", "sample.facade:Nested"], "class Child(Base): pass\n", 0, "PASS"),
        (["sample:ChildPublic"], "class Child(Missing): pass\n", 0, "UNKNOWN"),
        (["sample.facade:Alias"], "class Child(Base): pass\nAlias = Child\n", 2, "PASS"),
        (
            ["sample.facade:Alias", "sample.facade:Nested"],
            "class Child(Base): pass\nAlias = Child\n",
            0,
            "PASS",
        ),
        (["sample.facade:Alias"], "class Child(Missing): pass\nAlias = Child\n", 0, "UNKNOWN"),
        (["sample:AliasPublic"], "class Child(Base): pass\nAlias = Child\n", 2, "PASS"),
        (
            ["sample:AliasPublic", "sample.facade:Nested"],
            "class Child(Base): pass\nAlias = Child\n",
            0,
            "PASS",
        ),
    ],
)
def test_public_api_inheritance_cli_and_report(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    entries: list[str],
    source: str,
    exit_code: int,
    status: str,
) -> None:
    _prepare(
        tmp_path,
        entries,
        "class Nested:\n    value: str\nclass Exported:\n    item: Nested\n"
        "class Base:\n    inherited: Nested\n" + source,
    )
    (tmp_path / "sample/__init__.py").write_text(
        "from .facade import Child as ChildPublic, Exported as Public\n"
        + (
            "from .facade import Alias as AliasPublic\n"
            "__all__ = ['ChildPublic', 'Public', 'AliasPublic']\n"
            if "sample:AliasPublic" in entries
            else "__all__ = ['ChildPublic', 'Public']\n"
        )
    )
    _commit_public_api_fixture(tmp_path)

    assert main(["validate", "--root", str(tmp_path), "--json"]) == exit_code
    validation = json.loads(capsys.readouterr().out)
    assert validation["declared_rules"] == status, validation
    assert validation["observation_complete"] == "PASS"
    assert validation["expectation_fulfilled"] == "n/a"
    assert [item["code"] for item in validation["diagnostics"]] == (
        ["api_surface.missing"] if exit_code == 2 else []
    )
    output = tmp_path / "report.json"
    assert main(["report", "--root", str(tmp_path), "--output", str(output), "--json"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["declared_rules"] == status, report
    observation = parse_observation(decode_canonical_model(json.loads(output.read_text())))
    api = next(
        item
        for item in observation.records("declarations") or ()
        if item.kind == "declared_public_api" and item.subjects == (entries[0],)
    )
    assert api.data.get("types") == (("sample.facade:Nested",) if exit_code == 2 else ())
    details = _native_details(output, observation)
    if "Missing" in source:
        unknown = next(
            item
            for item in observation.records("unknowns") or ()
            if "Public API fields cannot be fully resolved" in item.title
        )
        assert "unresolved_name" in unknown.title
        assert any(
            item.id == unknown.id and item.title == unknown.title and item.status == "UNKNOWN"
            for detail in details
            for item in detail.findings
        )
