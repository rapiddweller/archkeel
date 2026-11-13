# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Decorators do not hide the direct lexical members written in TypeScript source."""

import json
from pathlib import Path

import pytest
from test_source_graph import _graph_from_source_facts
from test_typescript_inner import _collected, _collected_files
from test_typescript_partial_uml import _live, _project

from archkeel.check.report import run_saved_report
from archkeel.check.uml_compare import compare_graphs
from archkeel.ir.architecture_graph import ArchitectureGraph, Entity, TargetScope
from archkeel.ir.codec import decode_canonical_model, parse_observation
from archkeel.ir.report_graph import architecture_report

SOURCE = """@Controller('api')
export class Endpoint {
  @Field() public token: string;
  @First
  // A comment does not detach a decorator.
  @Get('route')
  public static run(value: string): string { return value; }
  plain(): void {}
}
"""
# Inventory controls bind decorator names so unrelated import gaps cannot decide them.
DECORATORS = """
function Get() { return () => {}; }
function Controller(path: string) { return () => {}; }
function Field() { return () => {}; }
function First() {}
"""
QUALIFIED = "app.src.main_x2e_ts.Endpoint"


def _target(
    names: tuple[str, ...], *, qualified: str = QUALIFIED, kind: str = "method"
) -> ArchitectureGraph:
    owner = Entity(
        "endpoint",
        "class",
        qualified,
        "typescript",
        presence="planned",
        provenance=("docs/target.md",),
    )
    children = tuple(
        Entity(
            name,
            kind,
            f"{qualified}.{name}",
            "typescript",
            parent_id=owner.id,
            presence="planned",
            provenance=("docs/target.md",),
        )
        for name in names
    )
    return ArchitectureGraph(
        "declared",
        (owner, *children),
        target_scopes=(
            TargetScope(owner.id, "closed", "All direct members.", ("docs/target.md",), (kind,)),
        ),
    )


def test_plain_top_level_and_nested_functions_publish_signature_identity(tmp_path):
    facts = _collected(
        tmp_path,
        "export function build(value: string): string { "
        "function nested(text: string): string { return text; } return nested(value); }",
    )
    functions = [
        record
        for section in facts.sections
        if section.name == "symbols"
        for record in section.records
        if record.kind == "function"
    ]
    assert {record.data.get("name") for record in functions} == {"build", "nested"}
    assert all(record.data.get("signature_decorators_proven") is True for record in functions)


def test_constructor_overload_bindings_remain_ambiguous_in_a_decorated_class(
    tmp_path: Path,
) -> None:
    source = (
        "class Endpoint { constructor(repo: string); constructor(repo: string) {} @Get() run() {} }"
    )
    graph = _graph_from_source_facts(_collected(tmp_path, source + DECORATORS), ("src",))
    comparison = compare_graphs(graph, _target(("constructor", "run")))
    assert comparison.status == "UNKNOWN"
    assert any(
        item.status == "UNKNOWN" and item.change == "ambiguous" for item in comparison.assessments
    )


@pytest.mark.parametrize(
    "names,status",
    [
        (("run", "plain"), "PASS"),
        (("run",), "FAIL"),
        (("run", "plain", "missing"), "FAIL"),
    ],
)
def test_decorated_closed_methods_detect_known_presence_extra_and_absence(
    tmp_path: Path,
    names: tuple[str, ...],
    status: str,
) -> None:
    graph = _graph_from_source_facts(_collected(tmp_path, SOURCE + DECORATORS), ("src",))
    comparison = compare_graphs(graph, _target(names))
    assert comparison.status == status
    assert not any(item.status == "UNKNOWN" for item in comparison.assessments)


def test_duplicate_decorated_owners_keep_closed_inventory_unknown(tmp_path: Path) -> None:
    graph = _graph_from_source_facts(
        _collected(tmp_path, "class Endpoint { @Get() run() {} } class Endpoint {}" + DECORATORS),
        ("src",),
    )
    comparison = compare_graphs(graph, _target(("run",)))
    assert comparison.status == "UNKNOWN"
    assert not any(item.status == "FAIL" for item in comparison.assessments)


@pytest.mark.parametrize(
    "member",
    [
        "@Get() [key]() {}",
        "@Get() run() {} static { initialize(); }",
        "@Get()",
    ],
)
def test_unsupported_decorated_inventory_cannot_prove_member_absence(
    tmp_path: Path,
    member: str,
) -> None:
    graph = _graph_from_source_facts(
        _collected(tmp_path, f"class Endpoint {{ {member} }}" + DECORATORS),
        ("src",),
    )
    names = ("run", "missing", "constructor") if "constructor" in member else ("run", "missing")
    comparison = compare_graphs(graph, _target(names))
    assert comparison.status == "UNKNOWN"
    assert not any(item.status == "FAIL" for item in comparison.assessments)


@pytest.mark.parametrize(
    "names,status", [(("token",), "PASS"), ((), "FAIL"), (("token", "missing"), "FAIL")]
)
def test_decorated_closed_attributes_detect_extra_and_missing_fields(
    tmp_path: Path,
    names: tuple[str, ...],
    status: str,
) -> None:
    graph = _graph_from_source_facts(_collected(tmp_path, SOURCE + DECORATORS), ("src",))
    comparison = compare_graphs(graph, _target(names, kind="attribute"))
    assert comparison.status == status
    assert not any(item.status == "UNKNOWN" for item in comparison.assessments)


def test_unchanged_nest_app_controller_has_a_complete_direct_method_inventory(
    tmp_path: Path,
) -> None:
    fixture = Path(__file__).parents[1] / "fixtures/L-nest-realworld/src/app.controller.ts"
    package = fixture.parents[1] / "resolver-inputs/@nestjs/common"
    facts = _collected_files(
        tmp_path,
        {
            "src/main.ts": fixture.read_text(),
            **{
                f"node_modules/@nestjs/common/{name}": (package / name).read_text()
                for name in ("package.json", "index.js", "index.d.ts")
            },
        },
    )
    symbols = {
        record.data.get("name"): record
        for section in facts.sections
        if section.name == "symbols"
        for record in section.records
    }
    assert symbols["AppController"].data.get("decorators") == ("@Controller('api')",)
    assert symbols["root"].data.get("decorators") == ("@Get()",)
    methods = [
        item
        for item in symbols["AppController"].data.get("member_inventories")
        if item.get("kind") == "method"
    ]
    assert len(methods) == 1 and methods[0].get("status") == "complete"
    assert methods[0].get("definition_ids") == (symbols["root"].id,)
    graph = _graph_from_source_facts(facts, ("src",))
    comparison = compare_graphs(
        graph,
        _target(("root",), qualified="app.src.main_x2e_ts.AppController"),
    )
    assert comparison.status == "PASS"


@pytest.mark.parametrize(
    "names,status",
    [
        (("run", "plain"), "PASS"),
        (("run",), "FAIL"),
        (("run", "plain", "missing"), "FAIL"),
    ],
)
def test_decorated_inventory_live_and_saved_reports_agree(
    tmp_path: Path,
    names: tuple[str, ...],
    status: str,
) -> None:
    root, config = _project(tmp_path / "decorated", matching=True)
    (root / "src/main.ts").write_text(SOURCE + DECORATORS)
    contract_path = root / config.contract
    contract = json.loads(contract_path.read_text())
    qualified = "demo.src.main_x2e_ts.Endpoint"
    entities = [
        {
            "id": "endpoint",
            "kind": "class",
            "qualified_name": qualified,
            "language": "typescript",
            "presence": "planned",
            "provenance": ["docs/target.md"],
            "responsibilities": ["Own the direct endpoint methods."],
        },
        *(
            {
                "id": name,
                "kind": "method",
                "qualified_name": f"{qualified}.{name}",
                "parent_id": "endpoint",
                "language": "typescript",
                "presence": "planned",
                "provenance": ["docs/target.md"],
                "responsibilities": ["Handle a request."],
            }
            for name in names
        ),
    ]
    contract["declarations"]["uml"] = {
        "schema_version": "1.0.0",
        "entities": entities,
        "scopes": [
            {
                "scope_id": "endpoint",
                "mode": "closed",
                "entity_kinds": ["method"],
                "rationale": "All direct methods.",
                "provenance": ["docs/target.md"],
            }
        ],
    }
    contract_path.write_text(json.dumps(contract))
    result, encoded = _live(root, config)
    assert encoded is not None
    comparison = architecture_report(
        parse_observation(decode_canonical_model(json.loads(encoded)))
    ).comparison
    assert comparison is not None and comparison.status == status
    path = root / "architecture.json"
    path.write_bytes(encoded)
    saved = run_saved_report(path)
    assert saved.rule_assessments == result.rule_assessments
    assert saved.architecture_projection == result.architecture_projection
    assert saved.declared_rules == result.declared_rules == status
    assert saved.exit_code == result.exit_code


@pytest.mark.parametrize("names", [("run",), ("run", "missing")])
def test_missing_decorator_binding_cannot_certify_closed_inventory(tmp_path, names):
    facts = _collected(tmp_path, "class Endpoint { @Get() run() {} }")
    assert len(facts.coverage.gaps) == 1
    gap = facts.coverage.gaps[0]
    assert gap.kind == "source_resolution_gap"
    assert gap.data.get("resolution_dimension") == "imports"
    assert gap.data.get("module") == "app.src.main_x2e_ts"
    comparison = compare_graphs(_graph_from_source_facts(facts, ("src",)), _target(names))
    assert comparison.status == "UNKNOWN"
    assert not any(item.status == "FAIL" for item in comparison.assessments)
