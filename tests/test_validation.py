# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
import json
from pathlib import Path
from unittest.mock import Mock

import pytest
from test_analyzer import _component
from test_architecture_demo import CONFIG as SHOP_CONFIG
from test_architecture_demo import _prepare_repo
from test_delta import _model, _record

from archkeel.analyzer import observe
from archkeel.check.onboarding import architecture_document
from archkeel.check.ports import ScanConfig
from archkeel.check.validation import (
    COMPONENT_GRAPH_MARKER,
    TARGET_GRAPH_MARKER,
    graph_diagnostics,
    inside_diagnostics,
    interface_diagnostics,
    reference_diagnostics,
    rewrite_component_graph,
    run_validate,
)
from archkeel.cli.config import load_config
from archkeel.ir.codec import (
    CONTRACT_SCHEMA_VERSION,
    decode_canonical_model,
    parse_contract,
    parse_observation,
)
from archkeel.ir.model import ArchitectureContract
from fixtures.architecture_demo import CATALOG

ROOT = Path(__file__).parents[1]
CONFIG = ScanConfig(("sample",), "sample", "contract.json", "0" * 64)


def test_an_inside_may_not_grant_what_requires_never_named(tmp_path: Path) -> None:
    """AD-32 decides pairs by absence, so absence has to reach the inside as a prohibition.

    Archkeel's own top level holds no `forbidden_dependency` for check, so a check that reads
    only those rules would pass anything the inside granted itself.
    """
    outer = json.loads((ROOT / "architecture-contract.json").read_text())
    inner = json.loads((ROOT / "src/archkeel/check/architecture-contract.json").read_text())
    analyzer_inner = json.loads(
        (ROOT / "src/archkeel/analyzer/architecture-contract.json").read_text()
    )
    root = tmp_path / "repository"
    inside = root / "src/archkeel/check/architecture-contract.json"
    inside.parent.mkdir(parents=True)
    analyzer_inside = root / "src/archkeel/analyzer/architecture-contract.json"
    analyzer_inside.parent.mkdir(parents=True)
    (root / "architecture-contract.json").write_text(json.dumps(outer))
    inside.write_text(json.dumps(inner))
    analyzer_inside.write_text(json.dumps(analyzer_inner))

    assert inside_diagnostics(root, parse_contract(outer)) == ()

    inner["rules"].append(
        {
            "id": "DEP-ENTRY-ALLOWS-RENDER",
            "kind": "allowed_dependency",
            "source": "archkeel.check.run",
            "target": "archkeel.render",
            "rationale": "The inside grants an edge the level above never named in requires.",
            "provenance": ["docs/architecture/archkeel.md"],
            "decided_by": "architect",
        }
    )
    inside.write_text(json.dumps(inner))

    diagnostics = inside_diagnostics(root, parse_contract(outer))

    assert [item.code for item in diagnostics] == ["inside.forbidden_import"]
    assert "REQUIRES-COMPLETE" in diagnostics[0].unknown_claim


def test_validate_accepts_archkeel_self_contract() -> None:
    result, _ = run_validate(ROOT, load_config(ROOT), observe)
    assert result.exit_code == 0
    assert result.observation_complete == result.declared_rules == "PASS"
    assert result.expectation_fulfilled == "n/a"


def test_validate_rejects_contract_1_1_with_exact_pointer(tmp_path: Path) -> None:
    (tmp_path / "contract.json").write_text('{"schema_version":"1.1.0","components":[],"rules":[]}')
    analyzer = Mock()
    result, _ = run_validate(tmp_path, CONFIG, analyzer)
    analyzer.assert_not_called()
    assert result.exit_code == 2
    assert result.diagnostics[0].pointer == "/schema_version"
    assert result.diagnostics[0].unknown_claim == (
        "Contract schema 1.1.0 cannot be validated as 2.1.0."
    )


def test_validate_gives_every_contract_invalid_diagnostic_a_code(tmp_path: Path) -> None:
    broken = (ROOT / "tests/contracts/invalid/wrong-type.json").read_bytes()
    (tmp_path / "contract.json").write_bytes(broken)
    result, _ = run_validate(tmp_path, CONFIG, Mock())
    assert result.diagnostics
    assert all(item.code == "contract.invalid" for item in result.diagnostics)


def test_validate_sorts_namespace_and_provenance_diagnostics(tmp_path: Path) -> None:
    contract = json.loads((ROOT / "tests/contracts/valid/minimal.json").read_bytes())
    contract["components"][0]["packages"] = ["outside.x"]
    contract["components"][0]["provenance"] = ["missing.md"]
    contract["components"] = contract["components"][:1]
    contract["rules"] = []
    (tmp_path / "contract.json").write_text(json.dumps(contract))
    result, _ = run_validate(tmp_path, CONFIG, Mock())
    assert [item.pointer for item in result.diagnostics] == [
        "/components/0/packages/0",
        "/components/0/provenance/0",
    ]


def test_reference_check_rejects_a_component_without_scanned_modules() -> None:
    raw = json.loads((ROOT / "tests/contracts/valid/minimal.json").read_bytes())
    contract = parse_contract(raw)
    observation = parse_observation(
        decode_canonical_model(
            json.loads((ROOT / "fixtures/D-self/architecture.json").read_bytes())
        )
    )
    diagnostics = reference_diagnostics(ROOT, CONFIG, contract, observation)
    assert any(item.pointer == "/components/0/packages/0" for item in diagnostics)


def test_public_entry_outside_namespace_is_a_diagnostic() -> None:
    contract = parse_contract(
        {
            "schema_version": "2.1.0",
            "components": [_component("core", public=["other.module"])],
            "rules": [],
        }
    )
    diagnostics = reference_diagnostics(ROOT, CONFIG, contract)
    assert any(
        item.pointer == "/components/0/public/0" and "outside namespace" in item.unknown_claim
        for item in diagnostics
    )


def test_exact_source_outside_namespace_is_a_diagnostic() -> None:
    """AD-49: an exact source is a module name like a prefix one, held to the same namespace."""
    rule = {
        "id": "EXTERNAL-JSON",
        "kind": "external_dependency_scope",
        "dependency": "json",
        "exact_sources": ["other"],
        "rationale": "Probe.",
        "provenance": ["docs/architecture/sample.md"],
        "decided_by": "architect",
    }
    contract = parse_contract({"schema_version": "2.1.0", "components": [], "rules": [rule]})
    diagnostics = reference_diagnostics(ROOT, CONFIG, contract)
    assert "/rules/0/exact_sources/0" in [item.pointer for item in diagnostics]


def test_public_entry_owned_by_another_component_is_a_diagnostic() -> None:
    contract = parse_contract(
        {
            "schema_version": "2.1.0",
            "components": [
                _component("core", public=["sample.cli"]),
                _component("cli"),
            ],
            "rules": [],
        }
    )
    diagnostics = reference_diagnostics(ROOT, CONFIG, contract)
    assert any(
        item.pointer == "/components/0/public/0"
        and "not owned by this component" in item.unknown_claim
        for item in diagnostics
    )


def test_public_entry_with_underscore_name_is_a_diagnostic() -> None:
    contract = parse_contract(
        {
            "schema_version": "2.1.0",
            "components": [_component("core", public=["sample.core:_Hidden"])],
            "rules": [],
        }
    )
    diagnostics = reference_diagnostics(ROOT, CONFIG, contract)
    assert any(
        item.pointer == "/components/0/public/0" and "Underscore" in item.unknown_claim
        for item in diagnostics
    )


def test_planned_entry_owned_by_another_component_is_a_diagnostic() -> None:
    """AD-56: a planned entry is held to the same ownership check as a public one."""
    contract = parse_contract(
        {
            "schema_version": "2.1.0",
            "components": [
                _component("core", planned=["sample.cli"]),
                _component("cli"),
            ],
            "rules": [],
        }
    )
    diagnostics = reference_diagnostics(ROOT, CONFIG, contract)
    assert any(
        item.pointer == "/components/0/planned/0"
        and "not owned by this component" in item.unknown_claim
        for item in diagnostics
    )


def test_planned_entry_with_underscore_name_is_a_diagnostic() -> None:
    contract = parse_contract(
        {
            "schema_version": "2.1.0",
            "components": [_component("core", planned=["sample.core:_Hidden"])],
            "rules": [],
        }
    )
    diagnostics = reference_diagnostics(ROOT, CONFIG, contract)
    assert any(
        item.pointer == "/components/0/planned/0" and "Underscore" in item.unknown_claim
        for item in diagnostics
    )


def test_planned_entry_outside_namespace_is_a_diagnostic() -> None:
    contract = parse_contract(
        {
            "schema_version": "2.1.0",
            "components": [_component("core", planned=["other.module"])],
            "rules": [],
        }
    )
    diagnostics = reference_diagnostics(ROOT, CONFIG, contract)
    assert any(
        item.pointer == "/components/0/planned/0" and "outside namespace" in item.unknown_claim
        for item in diagnostics
    )


_INTERFACE_RULE = {
    "id": "INTERFACE",
    "kind": "interface_boundary",
    "rationale": "Probe.",
    "provenance": ["docs/architecture/sample.md"],
    "decided_by": "architect",
}


def _contract_with_allowed_dependency(source: str, target: str) -> dict[str, object]:
    """A two-component contract whose only decision permits `source` to depend on `target`."""
    return {
        "schema_version": "2.1.0",
        "components": [_component(source), _component(target)],
        "rules": [
            {
                "id": "DEP-ALLOW",
                "kind": "allowed_dependency",
                "source": f"sample.{source}",
                "target": f"sample.{target}",
                "rationale": "Probe.",
                "provenance": ["docs/architecture/sample.md"],
                "decided_by": "architect",
            }
        ],
    }


def _cross_import(target_module: str, **data: object) -> dict[str, object]:
    return _record(
        "IMPORT-1",
        kind="import",
        data={"source_module": "sample.cli", "target_module": target_module, **data},
    )


def _module(qualified_name: str) -> dict[str, object]:
    return _record(f"MOD-{qualified_name}", kind="module", data={"qualified_name": qualified_name})


def test_undeclared_interface_is_a_diagnostic_when_a_rule_is_present() -> None:
    contract = parse_contract(
        {
            "schema_version": "2.1.0",
            "components": [_component("core"), _component("cli")],
            "rules": [_INTERFACE_RULE],
        }
    )
    observation = parse_observation(
        _model(git_head="a" * 40, imports=[_cross_import("sample.core")])
    )
    diagnostics = interface_diagnostics(contract, observation)
    assert [item.pointer for item in diagnostics] == ["/components/0"]


def test_declared_public_interface_has_no_undeclared_diagnostic() -> None:
    contract = parse_contract(
        {
            "schema_version": "2.1.0",
            "components": [_component("core", public=["sample.core"]), _component("cli")],
            "rules": [_INTERFACE_RULE],
        }
    )
    observation = parse_observation(
        _model(git_head="a" * 40, imports=[_cross_import("sample.core")])
    )
    assert interface_diagnostics(contract, observation) == ()


def test_unused_public_entry_is_a_diagnostic() -> None:
    contract = parse_contract(
        {
            "schema_version": "2.1.0",
            "components": [_component("core", public=["sample.core:Widget"]), _component("cli")],
            "rules": [_INTERFACE_RULE],
        }
    )
    observation = parse_observation(
        _model(git_head="a" * 40, modules=[_module("sample.core")], imports=[])
    )
    diagnostics = interface_diagnostics(contract, observation)
    assert [item.pointer for item in diagnostics] == ["/components/0/public/0"]
    assert diagnostics[0].code == "interface.unused"


def test_missing_public_entry_is_a_diagnostic() -> None:
    """AD-56: a public entry whose module the scan never saw is missing, not merely unused."""
    contract = parse_contract(
        {
            "schema_version": "2.1.0",
            "components": [_component("core", public=["sample.core:Widget"]), _component("cli")],
            "rules": [_INTERFACE_RULE],
        }
    )
    observation = parse_observation(_model(git_head="a" * 40, imports=[]))
    diagnostics = interface_diagnostics(contract, observation)
    assert [item.pointer for item in diagnostics] == ["/components/0/public/0"]
    assert diagnostics[0].code == "interface.missing"


def test_planned_entry_not_yet_built_has_no_diagnostic() -> None:
    """AD-56: a planned entry the scan never saw is target work, not a finding."""
    contract = parse_contract(
        {
            "schema_version": "2.1.0",
            "components": [
                _component("core", planned=["sample.core:Widget"]),
                _component("cli"),
            ],
            "rules": [_INTERFACE_RULE],
        }
    )
    observation = parse_observation(_model(git_head="a" * 40, imports=[]))
    assert interface_diagnostics(contract, observation) == ()


def test_planned_entry_now_built_is_a_diagnostic() -> None:
    """AD-56: a planned entry whose module the scan now sees is a stale marker."""
    contract = parse_contract(
        {
            "schema_version": "2.1.0",
            "components": [
                _component("core", planned=["sample.core:Widget"]),
                _component("cli"),
            ],
            "rules": [_INTERFACE_RULE],
        }
    )
    observation = parse_observation(
        _model(git_head="a" * 40, modules=[_module("sample.core")], imports=[])
    )
    diagnostics = interface_diagnostics(contract, observation)
    assert [item.pointer for item in diagnostics] == ["/components/0/planned/0"]
    assert diagnostics[0].code == "interface.planned_built"


def test_public_entry_used_through_a_reexport_chain_has_no_diagnostic() -> None:
    contract = parse_contract(
        {
            "schema_version": "2.1.0",
            "components": [
                _component("core", public=["sample.core.impl:Widget"]),
                _component("cli"),
            ],
            "rules": [_INTERFACE_RULE],
        }
    )
    observation = parse_observation(
        _model(
            git_head="a" * 40,
            imports=[
                _cross_import(
                    "sample.core",
                    reexport_chain=["sample.core.Widget", "sample.core.impl.Widget"],
                )
            ],
        )
    )
    assert interface_diagnostics(contract, observation) == ()


@pytest.mark.parametrize(
    ("public", "pointers"),
    [("sample.core.impl", []), ("sample.core:impl", ["/components/0/public/0"])],
)
def test_a_submodule_import_uses_the_module_entry_and_never_the_name_entry(
    public: str, pointers: list[str]
) -> None:
    """`from sample.core import impl` records the module `sample.core.impl` and no symbol."""
    contract = parse_contract(
        {
            "schema_version": "2.1.0",
            "components": [_component("core", public=[public]), _component("cli")],
            "rules": [_INTERFACE_RULE],
        }
    )
    observation = parse_observation(
        _model(
            git_head="a" * 40,
            modules=[_module("sample.core")],
            imports=[_cross_import("sample.core.impl", symbol=None, reexport_chain=[])],
        )
    )
    diagnostics = interface_diagnostics(contract, observation)
    assert [item.pointer for item in diagnostics] == pointers


def test_no_interface_rule_means_neither_diagnostic() -> None:
    contract = parse_contract(
        {
            "schema_version": "2.1.0",
            "components": [_component("core"), _component("cli")],
            "rules": [],
        }
    )
    observation = parse_observation(
        _model(git_head="a" * 40, imports=[_cross_import("sample.core")])
    )
    assert interface_diagnostics(contract, observation) == ()


def test_a_violated_inside_rule_points_at_the_component_that_declares_the_level(
    tmp_path: Path,
) -> None:
    """AD-36: the rule is in no `rules` array here, so `/rules/0` would blame another rule."""
    variant = next(item for item in CATALOG if item.id == "class-a-complete-requires-inside")
    root = _prepare_repo(tmp_path, dict(variant.files))

    diagnostics = run_validate(root, SHOP_CONFIG, observe)[0].diagnostics

    assert {item.pointer for item in diagnostics} == {"/components/1/inside"}
    assert {item.subject for item in diagnostics} == {"store:STORE-REQUIRES-COMPLETE"}


def test_write_graph_writes_the_graph_init_writes() -> None:
    """AD-46: one edge format for both writers, and a current graph is left alone."""
    empty = ArchitectureContract(CONTRACT_SCHEMA_VERSION, (), ())
    edges = frozenset({("cli", "app"), ("app", "model")})
    drafted = architecture_document("shop", empty, frozenset({("cli", "model")}), ())
    current = architecture_document("shop", empty, edges, ())

    assert rewrite_component_graph((("shop.md", drafted),), edges, frozenset()) == (
        ("shop.md", current),
    )
    assert rewrite_component_graph((("shop.md", current),), edges, frozenset()) == ()
    # A block without a diagram line gets the one `init` writes.
    block = f"{COMPONENT_GRAPH_MARKER}\n```mermaid\n```\n"
    assert rewrite_component_graph((("shop.md", block),), edges, frozenset()) == (
        (
            "shop.md",
            block.replace("```\n", "graph TD\n    app --> model\n    cli --> app\n```\n"),
        ),
    )


def test_write_graph_changes_nothing_without_exactly_one_marked_graph() -> None:
    """AD-46: which graph to rewrite is ambiguous there, so `graph.count` is the answer."""
    edges = frozenset({("cli", "app")})
    page = f"# Shop\n\n{COMPONENT_GRAPH_MARKER}\n```mermaid\ngraph TD\n```\n"
    assert (
        rewrite_component_graph(
            (("a.md", "# Shop\n```mermaid\ngraph TD\n```\n"),), edges, frozenset()
        )
        == ()
    )
    assert rewrite_component_graph((("a.md", page), ("b.md", page)), edges, frozenset()) == ()
    assert rewrite_component_graph((("a.md", page + page),), edges, frozenset()) == ()


def test_write_graph_adds_the_declaration_a_block_lacks() -> None:
    """AD-46: a `%%` comment is kept, but it is no diagram declaration and cannot stand in."""
    block = (
        f"{COMPONENT_GRAPH_MARKER}\n```mermaid\n%% generated component graph\ncli --> core\n```\n"
    )
    assert rewrite_component_graph(
        (("a.md", block),), frozenset({("cli", "core")}), frozenset()
    ) == (
        (
            "a.md",
            f"{COMPONENT_GRAPH_MARKER}\n```mermaid\ngraph TD\n%% generated component graph\n"
            "    cli --> core\n```\n",
        ),
    )


@pytest.mark.parametrize(
    ("body", "structure"),
    [
        ("flowchart LR\n    subgraph core\n    cli --> core\n    end\n", "subgraph core"),
        ("flowchart LR\n    cli -->|uses| core\n    core --> ir\n", "cli -->|uses| core"),
        ("flowchart LR\n    cli --> core\n    classDef hot fill:#f96\n", "classDef hot fill:#f96"),
    ],
    ids=["subgraph", "labeled-edge", "style"],
)
def test_write_graph_leaves_a_block_it_cannot_read_to_the_architect(
    body: str, structure: str
) -> None:
    """AD-46: only a declaration, `%%` comments and plain edges are known to survive a rewrite."""
    documents = (("a.md", f"{COMPONENT_GRAPH_MARKER}\n```mermaid\n{body}```\n"),)
    assert rewrite_component_graph(documents, frozenset({("core", "ir")}), frozenset()) == ()

    contract = parse_contract({"schema_version": "2.1.0", "components": [], "rules": []})
    observation = parse_observation(_model(git_head="a" * 40))
    (drift,) = graph_diagnostics(contract, observation, documents)
    assert drift.code == "graph.drift"
    assert f"`{structure}`" in drift.remedy
    assert "by hand" in drift.remedy


def test_target_graph_matches_the_edges_the_contract_permits() -> None:
    """AD-57: a target marker whose edges equal `target_component_edges` passes cleanly."""
    contract = parse_contract(_contract_with_allowed_dependency("core", "cli"))
    observation = parse_observation(_model(git_head="a" * 40))
    documents = (
        (
            "sample.md",
            f"{COMPONENT_GRAPH_MARKER}\n```mermaid\ngraph TD\n```\n\n"
            f"{TARGET_GRAPH_MARKER}\n```mermaid\ngraph TD\n    core --> cli\n```\n",
        ),
    )
    assert graph_diagnostics(contract, observation, documents) == ()


def test_target_graph_drift_names_the_target_marker() -> None:
    """AD-57: a stale target marker is graph.drift naming the target graph, not the observed."""
    contract = parse_contract(_contract_with_allowed_dependency("core", "cli"))
    observation = parse_observation(_model(git_head="a" * 40))
    documents = (
        (
            "sample.md",
            f"{COMPONENT_GRAPH_MARKER}\n```mermaid\ngraph TD\n```\n\n"
            f"{TARGET_GRAPH_MARKER}\n```mermaid\ngraph TD\n```\n",
        ),
    )
    (drift,) = graph_diagnostics(contract, observation, documents)
    assert drift.code == "graph.drift"
    assert drift.subject == "sample.md (target graph)"
    assert "the edges the contract permits" in drift.unknown_claim
    assert "archkeel validate --write-graph" in drift.remedy


def test_a_page_with_only_the_observed_marker_behaves_exactly_as_before() -> None:
    """AD-57: the target marker is optional; its absence adds no diagnostic and no requirement."""
    contract = parse_contract(_contract_with_allowed_dependency("core", "cli"))
    observation = parse_observation(_model(git_head="a" * 40))
    documents = (("sample.md", f"{COMPONENT_GRAPH_MARKER}\n```mermaid\ngraph TD\n```\n"),)
    assert graph_diagnostics(contract, observation, documents) == ()


def test_write_graph_regenerates_both_marked_graphs_on_one_page() -> None:
    """AD-57: one page carrying both markers comes back once, with both blocks rewritten."""
    documents = (
        (
            "sample.md",
            f"{COMPONENT_GRAPH_MARKER}\n```mermaid\ngraph TD\n```\n\n"
            f"{TARGET_GRAPH_MARKER}\n```mermaid\ngraph TD\n```\n",
        ),
    )
    edits = rewrite_component_graph(
        documents, frozenset({("cli", "app")}), frozenset({("app", "model")})
    )
    assert edits == (
        (
            "sample.md",
            f"{COMPONENT_GRAPH_MARKER}\n```mermaid\ngraph TD\n    cli --> app\n```\n\n"
            f"{TARGET_GRAPH_MARKER}\n```mermaid\ngraph TD\n    app --> model\n```\n",
        ),
    )


def test_write_graph_leaves_a_target_block_it_cannot_read_to_the_architect() -> None:
    """AD-57: the target marker follows AD-46's same allowlist; a subgraph is left to a human."""
    documents = (
        (
            "sample.md",
            f"{COMPONENT_GRAPH_MARKER}\n```mermaid\ngraph TD\n```\n\n"
            f"{TARGET_GRAPH_MARKER}\n```mermaid\nflowchart LR\n    subgraph core\n"
            "    cli --> core\n    end\n```\n",
        ),
    )
    assert rewrite_component_graph(documents, frozenset(), frozenset({("cli", "core")})) == ()

    contract = parse_contract({"schema_version": "2.1.0", "components": [], "rules": []})
    observation = parse_observation(_model(git_head="a" * 40))
    (drift,) = graph_diagnostics(contract, observation, documents)
    assert drift.code == "graph.drift"
    assert drift.subject == "sample.md (target graph)"
    assert "`subgraph core`" in drift.remedy
    assert "by hand" in drift.remedy
