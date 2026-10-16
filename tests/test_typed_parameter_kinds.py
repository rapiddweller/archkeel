# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""One source calling convention reaches actual writers and graph consumers."""

import ast
import copy
import json
from pathlib import Path
from typing import get_type_hints

import pytest
from test_architecture_demo import _prepare_repo
from test_uml_evaluation import _model

from archkeel.analyzer.python import symbols
from archkeel.check.ports import ScanConfig
from archkeel.ir import architecture_graph, facts
from archkeel.ir.report_graph import architecture_report
from archkeel.ir.trace import trace_valid_violations

ROOT = Path(__file__).parents[1]
TAGS = ("positional_only", "positional", "keyword_only", "varargs", "kwargs", "unknown")


def _api():
    kind = getattr(facts, "ParameterKind", None)
    assert kind is not None, "Facts must own the consumed source calling convention"
    return kind


def test_parameter_kind_has_one_owner_and_preserves_graph_import_identity():
    kind = _api()
    assert architecture_graph.ParameterKind is kind
    assert kind.__module__ == "archkeel.ir.facts"
    assert tuple(item.value for item in kind) == TAGS
    assert get_type_hints(symbols._parameter)["kind"] is kind
    assert get_type_hints(architecture_graph.Parameter)["kind"] is kind


def test_actual_signature_writers_keep_nominal_kinds_and_exact_record_bytes():
    kind = _api()
    node = ast.parse(
        "async def run(first: int, /, second: str = 'x', *items: float, "
        "option: bool = True, **options: int) -> str: ...\n"
    ).body[0]
    raw = symbols._function_signature(node)
    expected = [
        ("first", "int", kind.POSITIONAL_ONLY, None),
        ("second", "str", kind.POSITIONAL, "'x'"),
        ("*items", "float", kind.VARARGS, None),
        ("option", "bool", kind.KEYWORD_ONLY, "True"),
        ("**options", "int", kind.KWARGS, None),
    ]
    rows = raw["parameters"]
    assert len(rows) == len(expected)
    for row, (name, annotation, member, default) in zip(rows, expected, strict=True):
        assert row["kind"] is member
        assert row == {
            "name": name,
            "annotation": annotation,
            "kind": member.value,
            "default": default,
            "default_known": True,
        }
    assert json.loads(json.dumps(raw)) == {
        "parameters": [
            {
                "name": name,
                "annotation": annotation,
                "kind": member.value,
                "default": default,
                "default_known": True,
            }
            for name, annotation, member, default in expected
        ],
        "receiver_parameter": "first",
        "returns": "str",
        "async": True,
    }


@pytest.mark.parametrize("tag", TAGS)
def test_graph_legacy_constructor_normalizes_the_identical_existing_members(tag):
    kind = _api()
    parameter = architecture_graph.Parameter("value", kind=tag)
    assert parameter.kind is kind(tag)
    assert architecture_graph.Parameter("value", kind=kind(tag)).kind is kind(tag)


@pytest.mark.parametrize("tag", ("", "POSITIONAL", "future"))
def test_graph_unknown_spelling_retains_its_existing_rejection(tag):
    with pytest.raises(ValueError):
        architecture_graph.Parameter("value", kind=tag)


def _repository(tmp_path, producer):
    owner = "python" if producer else "ir"
    contract = copy.deepcopy(
        json.loads((ROOT / f"docs/architecture/contracts/{owner}.json").read_text())
    )
    contract.pop("$schema", None)
    contract["rules"] = []
    contract["declarations"]["modules"] = []
    uml = contract["declarations"]["uml"]
    uml["relationships"] = []
    uml["scopes"] = []
    ids = (
        {"PYTHON-PARAMETER-SYMBOLS", "PYTHON-PARAMETER-PRODUCER"}
        if producer
        else {"archkeel.ir.facts", "IR-GRAPH-ParameterKind"}
    )
    uml["entities"] = [entity for entity in uml["entities"] if entity["id"] in ids]
    assert {entity["id"] for entity in uml["entities"]} == ids
    relative = "analyzer/python/symbols.py" if producer else "ir/facts.py"
    files = {
        "archkeel/__init__.py": "",
        "archkeel/ir/__init__.py": "",
        "archkeel/analyzer/__init__.py": "",
        "archkeel/analyzer/python/__init__.py": "",
        "contract.json": json.dumps(contract),
        "docs/architecture/shared-parameter-kind.md": "Shared calling convention.\n",
        "docs/architecture/language-adapter-target.md": "Source facts.\n",
        "archkeel/" + relative: (ROOT / "src/archkeel" / relative).read_text(),
    }
    root = _prepare_repo(tmp_path, files)
    return root, ScanConfig(("archkeel",), "archkeel", "contract.json", "0" * 64), relative


@pytest.mark.parametrize("producer", [False, True])
def test_actual_source_fulfils_the_independent_canonical_parameter_target(tmp_path, producer):
    root, config, _ = _repository(tmp_path, producer)
    model = _model(root, config)
    comparison = architecture_report(model).comparison
    assert comparison is not None and comparison.status == "PASS", comparison
    assert not trace_valid_violations(model)


def test_actual_producer_kind_widening_fails_the_unchanged_authored_target(tmp_path):
    root, config, relative = _repository(tmp_path, True)
    path = root / ("archkeel/" + relative)
    text = path.read_text()
    assert "kind: ParameterKind" in text
    path.write_text(text.replace("kind: ParameterKind", "kind: str", 1))
    before = (root / "contract.json").read_bytes()
    comparison = architecture_report(_model(root, config)).comparison
    assert comparison is not None
    assert any(
        item.status == "FAIL" and item.aspect == "signature" for item in comparison.assessments
    ), comparison
    assert (root / "contract.json").read_bytes() == before
