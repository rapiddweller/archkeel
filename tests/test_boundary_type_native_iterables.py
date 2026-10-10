# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Exact native Iterable decisions retain known structure and accepted opacity."""

import json
import subprocess
import sys
from pathlib import Path

import pytest
from test_analyzer import _observe
from test_boundary_type_opaque_map_values import _app, _opacity_facts
from test_boundary_types_contained_mapping import _commit_report_fixture

from archkeel.ir.codec import decode_canonical_model, parse_observation
from archkeel.ir.trace import trace_valid_violations


def _fixture(
    root: Path,
    *,
    facade: bool = False,
    annotation: str = "Iterable[object]",
    prefix: str = "from collections.abc import Iterable\n",
    change: dict[str, object] | None = None,
    allowed: bool = True,
    position: str = "return",
) -> None:
    module = f"sample.app{'' if facade else '.impl'}"
    allowance = {
        "qualified_name": f"{module}.read",
        "position": position,
        "field_path": "",
        "annotation": annotation,
        "container_depth": 1,
        **(change or {}),
    }
    _app(
        root,
        source=(
            prefix
            + (
                f"def read(value: {annotation}) -> None: pass\n"
                if position == "value"
                else f"def read() -> {annotation}: return []\n"
            )
            + "def fixed_control(value: object) -> None: pass\n"
            + "def unknown_control(value: Missing) -> None: pass\n"
            + "def mapping_control(value: dict[str, object]) -> None: pass\n"
        ),
        declared=tuple(
            f"{module}:{name}"
            for name in ("read", "fixed_control", "unknown_control", "mapping_control")
        ),
        allowances=((allowance,) if allowed else ())
        + (
            {
                "qualified_name": f"{module}.mapping_control",
                "position": "value",
                "annotation": "dict[str, object]",
            },
            {
                "qualified_name": f"{module}.mapping_control",
                "position": "value",
                "annotation": "dict[str, object]",
                "container_depth": 1,
            },
        ),
    )
    if facade:
        (root / "sample/app/__init__.py").write_text(
            "from .impl import read, fixed_control, unknown_control, mapping_control\n"
            "__all__ = ['read', 'fixed_control', 'unknown_control', 'mapping_control']\n"
        )
    (root / "archkeel.toml").write_text(
        '[scan]\nroots = ["."]\nnamespace = "sample"\ncontract = "contract.json"\n'
    )


def _iterable_facts(result):
    return [
        fact
        for fact in _opacity_facts(result)
        if str(fact.data.get("qualified_name")).endswith(".read")
    ]


@pytest.mark.parametrize("facade", [False, True], ids=["direct", "facade"])
@pytest.mark.parametrize("annotation", ["Iterable[object]", "Iterable[object] | None"])
@pytest.mark.parametrize("position", ["return", "value"])
def test_native_iterable_accepts_only_exact_signature(tmp_path, facade, annotation, position):
    _fixture(tmp_path, facade=facade, annotation=annotation, position=position, allowed=False)
    control = _observe(tmp_path)
    _fixture(tmp_path, facade=facade, annotation=annotation, position=position)
    result = _observe(tmp_path)
    assert result.observation is not None and control.observation is not None
    assert result.diagnostics == ()
    findings = trace_valid_violations(result.observation)
    assert len(findings) == 1 and str(findings[0].data.get("qualified_name")).endswith(
        ".fixed_control"
    )
    assert (
        tuple(
            item
            for item in trace_valid_violations(control.observation)
            if not str(item.data.get("qualified_name")).endswith(".read")
        )
        == findings
    )
    assert result.observation.records("unknowns") == control.observation.records("unknowns")
    [fact] = _iterable_facts(result)
    assert fact.data.get("annotation") == annotation
    assert fact.data.get("nested_annotation") == "object"
    assert fact.data.get("container_depth") == 1
    assert fact.provenance == ("docs/architecture/sample.md",)
    assert fact.evidence_ids and fact.fact_ids and fact.rule_ids == ("APP-TYPES-NOT-DICT",)
    assert "accepted opacity" in fact.title and "type closure remains unproven" in fact.title
    assert "iterable element" in fact.title
    assert len(_opacity_facts(result)) == 2


@pytest.mark.parametrize(
    "change",
    [
        {"qualified_name": "sample.app.impl.fixed_control"},
        {"qualified_name": "sample.app.read"},
        {"position": "value"},
        {"annotation": "object"},
        {"annotation": "Iterable[object]|None"},
        {"field_path": "value"},
        {"container_depth": 0},
        {"container_depth": 2},
    ],
)
def test_native_iterable_rejects_wrong_coordinates(tmp_path, change):
    _fixture(tmp_path, annotation="Iterable[object] | None", change=change)
    result = _observe(tmp_path)
    if change.get("container_depth") == 0:
        assert result.diagnostics
        return
    assert _iterable_facts(result) == []
    assert result.observation is not None
    assert len(trace_valid_violations(result.observation)) == 2


@pytest.mark.parametrize(
    ("annotation", "prefix"),
    [
        ("Rows", "from collections.abc import Iterable\nRows = Iterable[object]\n"),
        ("Iterable[Value]", "from collections.abc import Iterable\nValue = object\n"),
        ("Iterable[Missing]", "from collections.abc import Iterable\n"),
        ("Iterable[object] | Missing", "from collections.abc import Iterable\n"),
        ("Iterable[object] | str", "from collections.abc import Iterable\n"),
        ("Iterable[object] | Iterable[object]", "from collections.abc import Iterable\n"),
        ("Iterable[object | None]", "from collections.abc import Iterable\n"),
        ("list[Iterable[object]]", "from collections.abc import Iterable\n"),
        ("list[object]", ""),
        ("Iterator[object]", "from collections.abc import Iterator\n"),
        ("tuple[object, object]", ""),
        ("dict[object, object]", ""),
        ("Annotated[Iterable[object], 'native']", "from typing import Annotated, Iterable\n"),
        ("Iterable[object]", "class Iterable: pass\n"),
        ("Iterable[object]", "Iterable = Missing\n"),
        ("Iterable[object]", "from missing import Iterable\n"),
        (
            "Iterable[object]",
            "from collections.abc import Iterable\nfrom typing import Iterator as Iterable\n",
        ),
        (
            "Iterable[object]",
            "from collections.abc import Iterable\nif condition: Iterable = Missing\n",
        ),
        ("Iterable[object]", "from collections.abc import Iterable\nfor Iterable in (): pass\n"),
        ("Iterable[object]", "from collections.abc import Iterable\nclass object: pass\n"),
        ("Iterable[object]", "from collections.abc import Iterable\nobject = Missing\n"),
        ("Iterable[object]", "from collections.abc import Iterable\nfrom missing import *\n"),
    ],
)
def test_native_iterable_requires_one_literal_proven_element(tmp_path, annotation, prefix):
    _fixture(tmp_path, annotation=annotation, prefix=prefix)
    result = _observe(tmp_path)
    assert _iterable_facts(result) == []


@pytest.mark.parametrize("facade", [False, True])
@pytest.mark.parametrize("depth", [1, 2])
def test_native_iterable_ordinary_cli_preserves_controls(tmp_path, facade, depth):
    _fixture(
        tmp_path,
        facade=facade,
        annotation="Iterable[object] | None",
        change={"container_depth": depth},
    )
    _observe(tmp_path)
    _commit_report_fixture(tmp_path)
    output = tmp_path / "architecture.json"
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-c",
            "from archkeel.cli import main; raise SystemExit(main())",
            "report",
            "--root",
            str(tmp_path),
            "--output",
            str(output),
            "--json",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    summary = json.loads(result.stdout)
    assert summary["coverage"]["status"] == "PASS" and summary["diagnostics"] == []
    assert summary["declared_rules"] == "FAIL"
    observation = parse_observation(decode_canonical_model(json.loads(output.read_text())))
    assert len(trace_valid_violations(observation)) == (1 if depth == 1 else 2)
    facts = [
        item
        for item in observation.records("typing_signals") or ()
        if item.kind == "boundary_type_allowance"
        and str(item.data.get("qualified_name")).endswith(".read")
    ]
    assert len(facts) == (1 if depth == 1 else 0)
    assert any(
        item.kind == "boundary_type_position" for item in observation.records("unknowns") or ()
    )


@pytest.mark.parametrize("prefix", ["from typing import Iterable\n", "import typing\n"])
def test_native_iterable_proves_typing_origins(tmp_path, prefix):
    annotation = "typing.Iterable[object]" if prefix == "import typing\n" else "Iterable[object]"
    _fixture(tmp_path, prefix=prefix, annotation=annotation)
    result = _observe(tmp_path)
    assert len(_iterable_facts(result)) == 1


def test_native_iterable_dto_field_is_outside_this_permission(tmp_path):
    _app(
        tmp_path,
        source=(
            "from dataclasses import dataclass\n"
            "from collections.abc import Iterable\n@dataclass\nclass Payload:\n"
            "    values: Iterable[object]\ndef read() -> Payload: ...\n"
        ),
        declared=("sample.app.impl:read",),
        allowances=(
            {
                "qualified_name": "sample.app.impl.read",
                "position": "return",
                "field_path": "values",
                "annotation": "Iterable[object]",
                "container_depth": 1,
            },
        ),
    )
    result = _observe(tmp_path)
    assert _iterable_facts(result) == []
    assert result.observation is not None
    assert trace_valid_violations(result.observation)


def test_native_iterable_permission_against_base_requires_bound_amendment(tmp_path):
    from archkeel.check.ports import ScanConfig
    from archkeel.check.validation import run_validate
    from archkeel.cli.observe import observe

    _app(
        tmp_path,
        source="from collections.abc import Iterable\ndef read() -> Iterable[object]: ...\n",
        declared=("sample.app.impl:read",),
    )
    _observe(tmp_path)
    _commit_report_fixture(tmp_path)
    base = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=tmp_path, text=True).strip()
    contract_path = tmp_path / "contract.json"
    raw = json.loads(contract_path.read_text())
    raw["rules"][0]["allowed_positions"] = [
        {
            "qualified_name": "sample.app.impl.read",
            "position": "return",
            "field_path": "",
            "annotation": "Iterable[object]",
            "container_depth": 1,
        }
    ]
    contract_path.write_text(json.dumps(raw))
    config = ScanConfig((".",), "sample", "contract.json", "0" * 64)
    result, _ = run_validate(tmp_path, config, observe, against=base)
    assert result.exit_code == 1
    assert any(
        "allowed_positions gained" in item and "container_depth=1" in item
        for item in result.failures
    )
    amendment = tmp_path / "amendment.json"
    written, files = run_validate(
        tmp_path,
        config,
        observe,
        against=base,
        amendment=amendment,
        write_amendment=True,
        decided_by="architect",
        rationale="Accept exactly one native iterable element.",
    )
    assert written.exit_code == 0, written.failures
    amendment.write_bytes(files[str(amendment)])
    accepted, _ = run_validate(tmp_path, config, observe, against=base, amendment=amendment)
    assert accepted.exit_code == 0 and accepted.failures == ()
