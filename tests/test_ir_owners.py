# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-315: the IR owners are inner components of Core and import in one direction."""

import ast
import json
import os
from pathlib import Path

import pytest
from archkeel.check.validation import mermaid_edges
from archkeel.check.validation.closed_world import target_component_edges
from archkeel.ir import codec, decisions, dependency
from archkeel.ir.model import ArchitectureContract

ROOT = Path(__file__).parents[1]
IR_SOURCE = ROOT / "src/archkeel/ir"
PAGE = ROOT / "docs/architecture/ir-owners.md"
BEGIN = "<!-- archkeel-ir-owner-graph:begin -->"
END = "<!-- archkeel-ir-owner-graph:end -->"
WRITE_VARIABLE = "ARCHKEEL_WRITE_IR_OWNER_PAGE"
OWNERS = ("architecture", "evidence", "wire", "views")
# The direction table of AD-315. A cycle between owners cannot form from these entries.
DIRECTION = {
    "architecture": {"facts", "profiles", "dependency-policy", "contract-version"},
    "evidence": {"architecture", "facts", "facts-codec", "dependency-policy"},
    "wire": {
        "architecture",
        "facts",
        "facts-codec",
        "profiles",
        "contract-version",
        "dependency-policy",
    },
    "views": {"architecture", "evidence", "wire", "facts", "dependency-policy"},
}


def _components() -> dict[str, dict]:
    contract = json.loads((ROOT / "docs/architecture/contracts/ir.json").read_text())
    return {item["label"]: item for item in contract["components"]}


def _owner_of(module: str, components: dict[str, dict]) -> str | None:
    for label, item in components.items():
        if module in item.get("exact_modules", ()):
            return label
        if any(module == p or module.startswith(p + ".") for p in item.get("packages", ())):
            return label
    return None


def _imported_ir_modules(path: Path) -> set[str]:
    """Every `archkeel.ir` module that a file imports, also inside functions."""
    found: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            found.update(a.name for a in node.names if a.name.startswith("archkeel.ir"))
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            if node.level == 1:
                base = f"archkeel.ir.{base}" if base else "archkeel.ir"
            if base == "archkeel.ir":
                found.update(f"archkeel.ir.{a.name}" for a in node.names)
            elif base.startswith("archkeel.ir."):
                found.add(base)
    return found


def test_selector_grammar_lives_with_the_dependency_policy() -> None:
    assert dependency.parse_dependency_selector.__module__ == "archkeel.ir.dependency"
    assert codec.parse_dependency_selector is dependency.parse_dependency_selector


def test_decisions_do_not_import_the_contract_codec() -> None:
    assert "archkeel.ir.codec_contract" not in _imported_ir_modules(IR_SOURCE / "decisions.py")
    assert decisions.parse_dependency_selector is dependency.parse_dependency_selector


def test_core_declares_the_four_owners_with_the_direction_table() -> None:
    components = _components()
    assert set(OWNERS) <= set(components)
    assert "governance" not in components
    for owner in OWNERS:
        required = {item["component"] for item in components[owner]["requires"]}
        assert required == DIRECTION[owner], owner
        assert all(item["rationale"] for item in components[owner]["requires"])


@pytest.mark.parametrize("owner", OWNERS)
def test_owner_modules_import_only_what_the_direction_table_allows(owner: str) -> None:
    components = _components()
    modules = components[owner]["exact_modules"]
    assert modules
    for module in modules:
        path = IR_SOURCE / f"{module.rsplit('.', 1)[-1]}.py"
        if module == "archkeel.ir":
            path = IR_SOURCE / "__init__.py"
        for target in _imported_ir_modules(path):
            target_owner = _owner_of(target, components)
            assert target_owner is not None, (module, target)
            assert target_owner == owner or target_owner in DIRECTION[owner], (module, target)


def _inside_contract() -> ArchitectureContract:
    return codec.parse_contract(
        codec.decode_json((ROOT / "docs/architecture/contracts/ir.json").read_bytes())
    )


def _generated_region() -> str:
    """The table and the Mermaid graph of the `ir` inside contract, from the contract alone."""
    contract = _inside_contract()
    modules = {
        item.label: len(item.packages) + len(item.exact_modules or ())
        for item in contract.components
    }
    names = {
        label: f"{label} ({count} {'module' if count == 1 else 'modules'})"
        for label, count in modules.items()
    }
    edges = frozenset((names[a], names[b]) for a, b in target_component_edges(contract))
    ordered = [*OWNERS, *sorted(label for label in modules if label not in OWNERS)]
    by_label = {item.label: item for item in contract.components}
    rows = []
    for label in ordered:
        item = by_label[label]
        required = ", ".join(f"`{entry.component}`" for entry in item.requires or ())
        text = " ".join(item.responsibilities)
        assert "|" not in text
        kind = "owner" if label in OWNERS else "inner component"
        rows.append(f"| `{label}` | {kind} | {modules[label]} | {text} | {required or 'none'} |")
    table = "\n".join(
        [
            "| Name | Kind | Modules | Responsibility | Requires |",
            "| --- | --- | --- | --- | --- |",
            *rows,
        ]
    )
    graph = "```mermaid\ngraph TD\n" + mermaid_edges(edges) + "```"
    return f"\n{table}\n\n{graph}\n"


def test_owner_page_shows_the_graph_of_the_contract() -> None:
    """The marked-graph check of `archkeel validate` reads the root contract only."""
    page = PAGE.read_text(encoding="utf-8")
    start = page.index(BEGIN) + len(BEGIN)
    end = page.index(END)
    expected = _generated_region()
    if os.environ.get(WRITE_VARIABLE):
        PAGE.write_text(page[:start] + expected + page[end:], encoding="utf-8")
        return
    assert page[start:end] == expected, f"Regenerate the page with {WRITE_VARIABLE}=1."


def test_owner_page_counts_every_module_of_the_package_once() -> None:
    counted = sum(
        len(item.packages) + len(item.exact_modules or ()) for item in _inside_contract().components
    )
    assert counted == len(list(IR_SOURCE.glob("*.py")))
