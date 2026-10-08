# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Actual committed source is compared through the configured process boundary."""

import json
from functools import partial
from pathlib import Path

import pytest

from archkeel.cli import main
from archkeel.cli.config import parse_config
from archkeel.cli.observe import observer_for
from fixtures import demo_catalog_check


@pytest.mark.parametrize("language", ["python", "dart"])
@pytest.mark.parametrize("change", ["comment", "selected_edge", "undeclared_edge"])
def test_committed_profile_check_ignores_working_tree_and_keeps_scope(
    tmp_path: Path, monkeypatch, capsys, language, change
):
    fixture = tmp_path / "fixture"
    suffix = "py" if language == "python" else "dart"
    value = "VALUE = 1\n" if language == "python" else "const value = 1;\n"
    source = f"shop/core/a.{suffix}"
    for relative, content in {
        source: value,
        f"shop/data/b.{suffix}": value,
        ("pubspec.yaml" if language == "dart" else "pyproject.toml"): (
            "name: fixture\nenvironment:\n  sdk: '>=2.19.0 <4.0.0'\n"
            if language == "dart"
            else '[project]\nname="fixture"\nversion="0.0.0"\nrequires-python=">=3.11"\n'
        ),
        "architecture-contract.json": '{"schema_version":"2.1.0","components":[],"rules":[]}\n',
    }.items():
        path = fixture / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    config_bytes = (
        '[scan]\nroots=["shop"]\nnamespace="shop"\ncontract="architecture-contract.json"\n'
        f'language="{language}"\n'
    ).encode()
    (fixture / "archkeel.toml").write_bytes(config_bytes)
    monkeypatch.setattr(demo_catalog_check, "FIXTURE_DIR", fixture)
    monkeypatch.setattr(demo_catalog_check, "CONFIG", parse_config(config_bytes))
    comment = "# changed source\n" if language == "python" else "// changed source\n"
    imported = "from shop.data import b\n" if language == "python" else "import '../data/b.dart';\n"
    prepared = demo_catalog_check.build_and_run_check(
        tmp_path / "protocol",
        {source: value + comment if change == "comment" else imported + value},
        "ordered" if change == "selected_edge" else "empty_declaration",
        analyzer=partial(observer_for(language), language=language),
    )
    expected = 1 if change == "undeclared_edge" else 0
    assert prepared.exit_code == expected, prepared.diagnostics
    assert prepared.delta.coverage.status == "PASS"
    assert prepared.delta.baseline.source_digest != prepared.delta.head.source_digest
    if language == "dart":
        assert set(prepared.delta.coverage.unknown_dimensions) == {
            "private_crossings",
            "typing_signals",
            "api_crossings",
        }
        assert prepared.delta.ratchets.head.scalars.private_crossings is None
    provenance = prepared.provenance
    root = tmp_path / "protocol/root"
    (root / source).write_text("unparseable worktree !\n")
    args = [
        "check",
        "--root",
        str(root),
        "--baseline",
        provenance.baseline,
        "--expectation-commit",
        provenance.expectation,
        "--head",
        provenance.head,
        "--expected",
        "expectation.json",
        "--expected-digest",
        provenance.expected_digest,
        "--branch",
        "candidate",
        "--accepted-branch",
        "main",
        "--host-records",
        str(tmp_path / "protocol/host-records.json"),
        "--json",
    ]
    assert main(args) == expected
    first = json.loads(capsys.readouterr().out)
    assert first["delta"]["schema_version"] == "2.0.0"
    assert main(args) == expected
    assert json.loads(capsys.readouterr().out) == first
