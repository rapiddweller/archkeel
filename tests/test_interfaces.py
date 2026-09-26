# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Unit tests for the AD-9 component communication derivation."""

import json
import shutil
from pathlib import Path
from typing import Any

from test_delta import _model

from archkeel.analyzer import observe
from archkeel.ir.codec import parse_observation
from archkeel.ir.interfaces import (
    InterfaceEdge,
    InterfaceName,
    InterfaceProfile,
    interface_edges,
    interface_profile,
)
from archkeel.ir.model import Observation

ROOT = Path(__file__).resolve().parents[1]


def _declaration(
    label: str, packages: list[str], public: list[str] | None = None
) -> dict[str, Any]:
    return {
        "id": f"COMP-{label}",
        "evidence_class": "DECLARED_RULE",
        "area": "components",
        "kind": "component_responsibility",
        "title": label,
        "subjects": packages,
        "evidence_ids": [],
        "rule_ids": [],
        "fact_ids": [],
        "provenance": [],
        "data": {} if public is None else {"public": public},
    }


def _import_record(
    identifier: str,
    *,
    source_module: str,
    target_module: str,
    symbol: str | None,
    origin_definition: str | None,
    binding: str | None = None,
    reexport: bool = False,
    declared_in_all: bool = False,
    reexport_chain: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "id": identifier,
        "evidence_class": "FACT",
        "area": "dependencies",
        "kind": "import",
        "title": "import",
        "subjects": [source_module, target_module],
        "evidence_ids": [],
        "rule_ids": [],
        "fact_ids": [],
        "provenance": [],
        "data": {
            "source_module": source_module,
            "target_module": target_module,
            "symbol": symbol,
            "origin_definition": origin_definition,
            "binding": binding if binding is not None else symbol,
            "reexport": reexport,
            "declared_in_all": declared_in_all,
            "under_type_checking": False,
            **({"reexport_chain": reexport_chain} if reexport_chain is not None else {}),
        },
    }


def _symbol_record(
    identifier: str,
    *,
    kind: str,
    qualified_name: str,
    module: str,
    name: str,
    class_kind: str | None = None,
    parameters: list[dict[str, str | None]] | None = None,
    returns: str | None = None,
) -> dict[str, Any]:
    data: dict[str, Any] = {
        "qualified_name": qualified_name,
        "module": module,
        "name": name,
        "parent": None,
        "visibility": "public_name",
    }
    if kind == "class":
        data["class_kind"] = class_kind or "class"
    else:
        data["parameters"] = parameters or []
        data["returns"] = returns
    return {
        "id": identifier,
        "evidence_class": "FACT",
        "area": "repository_topology",
        "kind": kind,
        "title": name,
        "subjects": [qualified_name, module],
        "evidence_ids": [],
        "rule_ids": [],
        "fact_ids": [],
        "provenance": [],
        "data": data,
    }


def _module_record(
    identifier: str, name: str, exports: list[str], *, all_literal: bool | None = None
) -> dict[str, Any]:
    literal = {} if all_literal is None else {"all_literal": all_literal}
    return {
        "id": identifier,
        "evidence_class": "FACT",
        "area": "module_topology",
        "kind": "module",
        "title": name,
        "subjects": [name],
        "evidence_ids": [],
        "rule_ids": [],
        "fact_ids": [],
        "provenance": [],
        "data": {"qualified_name": name, "all_exports": exports, **literal},
    }


def _observation(
    *,
    declarations: tuple[dict[str, Any], ...] = (),
    imports: tuple[dict[str, Any], ...] = (),
    symbols: tuple[dict[str, Any], ...] = (),
    modules: tuple[dict[str, Any], ...] = (),
) -> Observation:
    raw = _model(git_head="a" * 40, imports=list(imports))
    raw["declarations"] = list(declarations)
    raw["symbols"] = list(symbols)
    raw["modules"] = list(modules)
    return parse_observation(raw)


def _real_barrel_profile(tmp_path: Path, consumer_source: str) -> InterfaceProfile:
    source = tmp_path / "repo"
    (source / "sample/model").mkdir(parents=True)
    (source / "sample/consumer").mkdir()
    (source / "sample/model/impl.py").write_text("class Widget:\n    pass\n")
    (source / "sample/model/api.py").write_text(
        'from sample.model.impl import Widget\n\n__all__ = ["Widget"]\n'
    )
    (source / "sample/consumer/use.py").write_text(consumer_source)
    (source / "pyproject.toml").write_text('[project]\nrequires-python = ">=3.11"\n')
    (source / "architecture-contract.json").write_text(
        json.dumps(
            {
                "$schema": "https://raw.githubusercontent.com/rapiddweller/archkeel/main/"
                "schema/architecture-contract.schema.json",
                "schema_version": "2.1.0",
                "components": [
                    {
                        "id": "COMP-MODEL",
                        "label": "model",
                        "role": "component",
                        "packages": ["sample.model"],
                        "public": ["sample.model.api"],
                        "responsibilities": [],
                        "forbidden_responsibilities": [],
                        "provenance": ["tests/test_interfaces.py"],
                    },
                    {
                        "id": "COMP-CONSUMER",
                        "label": "consumer",
                        "role": "component",
                        "packages": ["sample.consumer"],
                        "public": [],
                        "responsibilities": [],
                        "forbidden_responsibilities": [],
                        "provenance": ["tests/test_interfaces.py"],
                    },
                ],
                "rules": [],
            },
            indent=2,
        )
    )
    result = observe(
        source,
        roots=("sample",),
        namespace="sample",
        contract="architecture-contract.json",
        git_head="0" * 40,
        dirty=False,
        contract_root=source,
    )
    assert result.diagnostics == ()
    assert result.observation is not None
    return interface_profile(result.observation)


def test_ownership_overlap_produces_no_edge() -> None:
    observation = _observation(
        declarations=(
            _declaration("a", ["pkg.a"]),
            _declaration("shared1", ["pkg.shared"]),
            _declaration("shared2", ["pkg.shared"]),
        ),
        imports=(
            _import_record(
                "IMP-1",
                source_module="pkg.a.mod",
                target_module="pkg.shared.thing",
                symbol="Widget",
                origin_definition="pkg.shared.thing.Widget",
            ),
        ),
    )
    assert interface_edges(observation) == ()


def test_origin_definition_follows_reexport_chain_without_guessing_missing_kinds() -> None:
    observation = _observation(
        declarations=(_declaration("a", ["pkg.a"]), _declaration("b", ["pkg.b"])),
        imports=(
            _import_record(
                "IMP-1",
                source_module="pkg.a.mod",
                target_module="pkg.b",
                symbol="Widget",
                origin_definition="pkg.b.impl.Widget",
            ),
            _import_record(
                "IMP-2",
                source_module="pkg.a.mod",
                target_module="pkg.b",
                symbol=None,
                origin_definition=None,
            ),
            _import_record(
                "IMP-3",
                source_module="pkg.a.mod",
                target_module="pkg.b",
                symbol="Missing",
                origin_definition="pkg.b.Missing",
            ),
            _import_record(
                "IMP-4",
                source_module="pkg.a.mod",
                target_module="pkg.b",
                symbol="*",
                origin_definition=None,
            ),
        ),
        symbols=(
            _symbol_record(
                "SYM-1",
                kind="class",
                qualified_name="pkg.b.impl.Widget",
                module="pkg.b.impl",
                name="Widget",
                class_kind="dataclass",
            ),
        ),
    )
    edges = interface_edges(observation)
    assert edges == (
        InterfaceEdge(
            "a",
            "b",
            (
                InterfaceName("pkg.b", "module", (), ""),
                InterfaceName("pkg.b:*", "star import", (), ""),
                InterfaceName("pkg.b:Missing", "unknown", (), ""),
                InterfaceName("pkg.b:Widget", "dataclass", (), ""),
            ),
        ),
    )


def test_interface_profile_measures_a_declared_barrel() -> None:
    observation = _observation(
        declarations=(
            _declaration("consumer", ["pkg.consumer"]),
            _declaration("other", ["pkg.other"]),
            _declaration("provider", ["pkg.provider"], ["pkg.provider"]),
        ),
        modules=(_module_record("MOD-provider", "pkg.provider", ["Widget", "run"]),),
        symbols=(
            _symbol_record(
                "SYM-run",
                kind="function",
                qualified_name="pkg.provider.run",
                module="pkg.provider",
                name="run",
            ),
        ),
        imports=(
            _import_record(
                "IMP-barrel",
                source_module="pkg.provider",
                target_module="pkg.impl",
                symbol="Widget",
                origin_definition="pkg.impl.Widget",
                binding="Widget",
                declared_in_all=True,
            ),
            _import_record(
                "IMP-consumer-widget",
                source_module="pkg.consumer.mod",
                target_module="pkg.provider",
                symbol="Widget",
                origin_definition="pkg.impl.Widget",
            ),
            _import_record(
                "IMP-consumer-run",
                source_module="pkg.consumer.mod",
                target_module="pkg.provider",
                symbol="run",
                origin_definition="pkg.provider.run",
            ),
            _import_record(
                "IMP-other-widget",
                source_module="pkg.other.mod",
                target_module="pkg.provider",
                symbol="Widget",
                origin_definition="pkg.impl.Widget",
            ),
        ),
    )

    profile = interface_profile(observation)

    assert profile.facades[0].exported_name_count == 2
    assert profile.facades[0].reexported_names == ("Widget",)
    assert profile.facades[0].defined_names == ("run",)
    assert profile.facades[0].unused_reexports == ()
    assert {(item.name, item.consumer_count) for item in profile.exports} == {
        ("Widget", 2),
        ("run", 1),
    }
    assert {(item.source, item.target, item.width) for item in profile.coupling} == {
        ("consumer", "provider", 2),
        ("other", "provider", 1),
    }


def test_interface_profile_measures_a_real_barrel(tmp_path: Path) -> None:
    """The shop fixture's __init__.py barrel is observed, not hand-modelled."""
    source = tmp_path / "repo"
    shutil.copytree(ROOT / "fixtures/F-architecture", source)
    contract = source / "architecture-contract.json"
    contract.write_text(
        contract.read_text().replace(
            '"shop.store.repository:OrderRepository"', '"shop.store:OrderRepository"'
        )
    )
    result = observe(
        source,
        roots=("shop",),
        namespace="shop",
        contract="architecture-contract.json",
        git_head="0" * 40,
        dirty=False,
        contract_root=source,
    )
    assert result.diagnostics == ()
    assert result.observation is not None

    profile = interface_profile(result.observation)
    store = next(item for item in profile.facades if item.module == "shop.store")
    assert store.exported_names == ("OrderRepository",)
    assert store.reexported_names == ("OrderRepository",)
    assert store.unused_reexports == ()
    repository = next(item for item in profile.exports if item.module == "shop.store")
    assert repository.consumers == ("app",)
    coupling = next(
        item for item in profile.coupling if item.source == "app" and item.target == "store"
    )
    assert "shop.store:OrderRepository" in coupling.names


def test_interface_profile_measures_a_real_non_package_barrel(tmp_path: Path) -> None:
    profile = _real_barrel_profile(tmp_path, "from sample.model.api import Widget\n")

    barrel = next(item for item in profile.facades if item.module == "sample.model.api")
    assert barrel.exported_names == ("Widget",)
    assert barrel.reexported_names == ("Widget",)
    usage = next(item for item in profile.exports if item.module == "sample.model.api")
    assert usage.consumers == ("consumer",)
    assert ("consumer", "model", ("sample.model.api:Widget",)) in {
        (item.source, item.target, item.names) for item in profile.coupling
    }


def test_interface_profile_counts_no_name_for_a_module_alias(tmp_path: Path) -> None:
    """A whole-module import proves no name use; AD-99 records it as uncounted instead."""
    profile = _real_barrel_profile(tmp_path, "import sample.model.api as api\n")

    usage = next(item for item in profile.exports if item.module == "sample.model.api")
    assert usage.consumers == ()
    assert [
        (item.names, item.uncounted)
        for item in profile.coupling
        if item.source == "consumer" and item.target == "model"
    ] == [((), ("sample.model.api",))]


def test_interface_profile_follows_a_reexport_to_the_declared_facade_name() -> None:
    """AD-99: `from pkg.b import Widget` reaches the declared `pkg.b.impl:Widget` entry."""
    observation = _observation(
        declarations=(
            _declaration("a", ["pkg.a"]),
            _declaration("b", ["pkg.b"], ["pkg.b.impl:Widget", "pkg.b.open"]),
        ),
        imports=(
            _import_record(
                "IMP-chain",
                source_module="pkg.a.mod",
                target_module="pkg.b",
                symbol="Widget",
                origin_definition="pkg.b.impl.Widget",
                reexport_chain=["pkg.b.Widget", "pkg.b.impl.Widget"],
            ),
            _import_record(
                "IMP-star",
                source_module="pkg.a.mod",
                target_module="pkg.b.impl",
                symbol="*",
                origin_definition=None,
            ),
            _import_record(
                "IMP-unrecorded",
                source_module="pkg.a.mod",
                target_module="pkg.b.open",
                symbol="LIMIT",
                origin_definition="pkg.b.open.LIMIT",
            ),
            _import_record(
                "IMP-private",
                source_module="pkg.a.mod",
                target_module="pkg.b.open",
                symbol="_hidden",
                origin_definition="pkg.b.open._hidden",
            ),
        ),
    )

    profile = interface_profile(observation)

    assert [(item.module, item.enumerated) for item in profile.facades] == [
        ("pkg.b.impl", True),
        ("pkg.b.open", False),
    ]
    assert [(item.names, item.uncounted) for item in profile.coupling] == [
        (("pkg.b.impl:Widget",), ("pkg.b.open:LIMIT",))
    ]
    widget = next(item for item in profile.exports if item.name == "Widget")
    assert widget.consumers == ("a",)


def test_interface_profile_trusts_all_only_when_the_analyzer_proved_it_literal() -> None:
    """AD-99: `all_exports` alone cannot tell a literal from one a later statement extends; the
    analyzer's `all_literal` fact decides. An empty `__all__` stays open, the way
    `interface_boundary` reads it."""
    observation = _observation(
        declarations=(
            _declaration("b", ["pkg.b"], ["pkg.b.empty", "pkg.b.extended", "pkg.b.legacy"]),
        ),
        modules=(
            _module_record("MOD-empty", "pkg.b.empty", [], all_literal=True),
            _module_record("MOD-extended", "pkg.b.extended", ["A"], all_literal=False),
            _module_record("MOD-legacy", "pkg.b.legacy", ["A"]),
        ),
        symbols=(
            _symbol_record(
                "SYM-helper",
                kind="function",
                qualified_name="pkg.b.empty.helper",
                module="pkg.b.empty",
                name="helper",
            ),
        ),
    )

    assert [
        (item.module, item.exported_names, item.enumerated)
        for item in interface_profile(observation).facades
    ] == [
        ("pkg.b.empty", ("helper",), False),
        ("pkg.b.extended", ("A",), False),
        ("pkg.b.legacy", ("A",), False),
    ]


def test_interface_profile_has_no_coupling_row_past_a_facade() -> None:
    """Review D: a target without a facade, or a module outside it, is interface_boundary's
    finding, not a coupling width: main shows no row for either, and neither does AD-99."""
    observation = _observation(
        declarations=(
            _declaration("a", ["pkg.a"]),
            _declaration("b", ["pkg.b"]),
            _declaration("c", ["pkg.c"], ["pkg.c.api:Widget"]),
        ),
        imports=(
            _import_record(
                "IMP-b-whole",
                source_module="pkg.a.mod",
                target_module="pkg.b.mod",
                symbol=None,
                origin_definition=None,
            ),
            _import_record(
                "IMP-b-name",
                source_module="pkg.a.mod",
                target_module="pkg.b.mod",
                symbol="Thing",
                origin_definition="pkg.b.mod.Thing",
            ),
            _import_record(
                "IMP-c-internal",
                source_module="pkg.a.mod",
                target_module="pkg.c.internal",
                symbol=None,
                origin_definition=None,
            ),
            _import_record(
                "IMP-c-star",
                source_module="pkg.a.mod",
                target_module="pkg.c.internal",
                symbol="*",
                origin_definition=None,
            ),
        ),
    )

    assert interface_profile(observation).coupling == ()


def test_typed_and_untyped_function_signatures() -> None:
    observation = _observation(
        declarations=(_declaration("a", ["pkg.a"]), _declaration("b", ["pkg.b"])),
        imports=(
            _import_record(
                "IMP-1",
                source_module="pkg.a.mod",
                target_module="pkg.b",
                symbol="typed",
                origin_definition="pkg.b.typed",
            ),
            _import_record(
                "IMP-2",
                source_module="pkg.a.mod",
                target_module="pkg.b",
                symbol="untyped",
                origin_definition="pkg.b.untyped",
            ),
        ),
        symbols=(
            _symbol_record(
                "SYM-1",
                kind="function",
                qualified_name="pkg.b.typed",
                module="pkg.b",
                name="typed",
                parameters=[{"name": "value", "annotation": "int"}],
                returns="str",
            ),
            _symbol_record(
                "SYM-2",
                kind="function",
                qualified_name="pkg.b.untyped",
                module="pkg.b",
                name="untyped",
                parameters=[{"name": "value", "annotation": None}],
                returns=None,
            ),
        ),
    )
    edges = interface_edges(observation)
    assert edges == (
        InterfaceEdge(
            "a",
            "b",
            (
                InterfaceName("pkg.b:typed", "function", ("value: int",), "str"),
                InterfaceName("pkg.b:untyped", "function", ("value: UNKNOWN",), "UNKNOWN"),
            ),
        ),
    )
