# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Keep recursive boundary checks from rescanning all imports per facade function."""

import json
from pathlib import Path
from unittest.mock import patch

from test_recursive_inside_independent_contracts import _write_three_levels

import archkeel.check.evaluation.rules as boundary_violations
from archkeel.cli.observe import analyze_snapshot


def test_recursive_boundary_indexes_do_not_scale_with_public_function_count(
    tmp_path: Path,
) -> None:
    import archkeel.check.evaluation.boundary_types as boundary

    import_lines = [
        "from sample.layer.target.api import Payload",
        *(f"import sample.layer.target.api as dep_{index}" for index in range(20)),
    ]
    functions = [f"def run_{index}(value: Payload) -> str:\n    return ''" for index in range(20)]
    _write_three_levels(
        tmp_path,
        source_import="\n".join(import_lines) + "\n\n" + "\n\n".join(functions),
    )
    rule = {
        "id": "SOURCE-TYPES",
        "kind": "boundary_types",
        "source": "sample.layer.source",
        "rationale": "Keep the source API typed.",
        "provenance": ["docs/architecture/sample.md"],
        "decided_by": "architect",
    }
    for relative in ("contract.json", "contracts/one.json", "contracts/two.json"):
        path = tmp_path / relative
        contract = json.loads(path.read_text())
        contract["rules"].append(rule)
        contract["components"][0]["public"] = [
            f"sample.layer.source.api:run_{index}" for index in range(20)
        ]
        path.write_text(json.dumps(contract))

    original = boundary._reexport_facade_entries
    fallback_rows = 0
    indexed_rows = 0

    def count_fallback_rows(*args, **kwargs):
        nonlocal fallback_rows
        imports = args[3]
        reexports = args[5] if len(args) > 5 else kwargs.get("reexports")
        if reexports is None:
            fallback_rows += len(imports)
        return original(*args, **kwargs)

    index = boundary_violations._reexport_index

    def count_index_rows(imports, uncertain_reexport_origins=None):
        nonlocal indexed_rows
        indexed_rows += len(imports)
        return index(imports, uncertain_reexport_origins)

    with (
        patch.object(boundary, "_reexport_facade_entries", side_effect=count_fallback_rows),
        patch.object(boundary_violations, "_reexport_index", side_effect=count_index_rows),
    ):
        model, exit_code = analyze_snapshot(
            tmp_path,
            git_head="a" * 40,
            dirty=False,
            contract_root=tmp_path,
            contract_path=tmp_path / "contract.json",
            roots=("sample",),
            namespace="sample",
        )

    assert exit_code == 0
    import_count = len(model["imports"])
    assert import_count > 0
    assert fallback_rows <= import_count, (
        f"recursive boundary checks rescanned {fallback_rows} import rows "
        f"for {import_count} imports and 20 public functions"
    )
    # Three contract levels each run at most four boundary passes, not one per function.
    assert indexed_rows <= import_count * 12, (
        f"recursive boundary checks rebuilt indexes over {indexed_rows} import rows "
        f"for {import_count} imports and 20 public functions"
    )


def test_uncertain_reexport_index_preserves_old_candidate_selection():
    from archkeel.check.evaluation.rule_support import _reexport_index
    from archkeel.ir.facts import EvidenceClass
    from archkeel.ir.facts_codec import classified

    def imported(identity, source, origin, chain, reexport=True):
        return classified(
            item_id=identity,
            evidence_class=EvidenceClass.FACT,
            area="imports",
            kind="import",
            title=identity,
            data={
                "source_module": source,
                "binding": "run",
                "origin_definition": origin,
                "reexport_chain": chain,
                "reexport": reexport,
            },
        )

    bridge = imported("bridge", "sample.bridge", "sample.impl.run", ["sample.impl.run"])
    publisher = imported(
        "publisher", "sample.api", "sample.impl.run", ["sample.bridge.run", "sample.impl.run"]
    )
    other = imported("other", "sample.api", "sample.other.run", ["sample.other.run"])
    ordinary = imported("ordinary", "sample.direct", None, [], False)
    # Same-ID replacement must preserve the old dict's insertion and last-value semantics.
    replacement = imported("publisher", "sample.api", "sample.third.run", ["sample.bridge.run"])
    imports = [bridge, publisher, publisher, other, ordinary, replacement]
    uncertain = {
        "sample.bridge.run": frozenset({"sample.impl.run", "sample.hidden.run"}),
        "sample.direct.run": frozenset({"sample.hidden.run"}),
        "sample.absent.run": frozenset({"sample.missing.run"}),
        "sample.api.run": frozenset(),
    }
    old_origins, old_aliases, old_ambiguous = _reexport_index(imports)
    origins, aliases, ambiguous = _reexport_index(imports, uncertain)
    assert aliases == old_aliases
    assert ambiguous == old_ambiguous
    for origin in (*old_origins, "sample.hidden.run", "sample.missing.run", "absent"):
        expected = {item["id"]: item for item in old_origins.get(origin, ())}
        for alias, candidates in uncertain.items():
            if origin in candidates:
                expected.update({item["id"]: item for item in old_aliases.get(alias, ())})
        actual = {item["id"]: item for item in origins.get(origin, ())}
        assert list(actual.items()) == list(expected.items())


def test_uncertain_reexport_routes_are_scanned_once_for_many_facades():
    from archkeel.check.evaluation.boundary_types import _reexport_facade_entries
    from archkeel.check.evaluation.rule_support import _reexport_index

    class CountedOrigins(dict):
        scans = 0

        def items(self):
            self.scans += 1
            return super().items()

    uncertain = CountedOrigins(
        {f"sample.alias{i}.run": frozenset({f"sample.impl{i}.run"}) for i in range(40)}
    )
    index = _reexport_index([], uncertain)
    for i in range(40):
        # No candidate means the contract is never consulted; missing routes remain empty.
        assert _reexport_facade_entries(f"sample.impl{i}.run", None, {}, [], uncertain, index) == []
    assert uncertain.scans == 1


def test_field_static_routes_are_built_once_and_refresh_on_the_next_pass():
    import archkeel.check.evaluation.boundary_types as boundary

    bindings = {
        ("sample.a", "nested.Name"): {"source_binding_unique": True},
        ("sample.b", "Name"): {"source_binding_unique": False},
    }
    captured = []

    def scoped(*args, static_routes, **kwargs):
        captured.append(static_routes)
        for _ in range(20):
            assert boundary._declared_field_reach(
                {"data": {"module": "sample.a"}},
                None,
                {},
                bindings,
                {},
                True,
                imports_by_alias={},
                static_routes=static_routes,
                type_shapes={},
            ) == ([], [])
        return []

    with (
        patch.object(boundary, "boundary_type_indexes", return_value=(bindings, {})),
        patch.object(boundary, "_scoped_facade_signature_types", side_effect=scoped),
        patch.object(
            boundary, "_alias_binding_static", wraps=boundary._alias_binding_static
        ) as proof,
    ):
        for stable in (True, False):
            bindings[("sample.a", "nested.Name")]["source_binding_unique"] = stable
            boundary.facade_signature_types(
                [],
                [],
                None,
                {},
                type_shapes={},
                source_modules=frozenset({"sample.a"}),
                scope_id="scope",
            )
        assert proof.call_count == 2 * len(bindings)
    assert captured == [frozenset({"sample.a.nested.Name"}), frozenset()]


def test_owner_indexes_scale_with_modules_and_preserve_ambiguous_ownership():
    from test_analyzer import _component

    from archkeel.check.evaluation.rules import (
        _component_cycle_violations,
        _requires_import_verdicts,
    )
    from archkeel.ir.codec import parse_contract
    from archkeel.ir.facts_codec import classified
    from archkeel.ir.model import ArchitectureContract, EvidenceClass

    raw = {
        "schema_version": "2.1.0",
        "components": [
            _component("source", packages=["sample.source"], public=[]),
            _component("target", packages=["sample.target"], public=[]),
        ],
        "rules": [
            {
                "id": "requires",
                "kind": "complete_requires",
                "rationale": "Probe.",
                "provenance": ["docs/architecture/sample.md"],
                "decided_by": "architect",
            },
            {
                "id": "cycles",
                "kind": "no_component_cycles",
                "rationale": "Probe.",
                "provenance": ["docs/architecture/sample.md"],
                "decided_by": "architect",
            },
        ],
    }
    imports = [
        classified(
            item_id=f"import-{i}",
            evidence_class=EvidenceClass.FACT,
            area="imports",
            kind="import",
            title="Probe",
            data={
                "source_module": "sample.source.api",
                "target_module": "sample.target.api",
                "symbol": "Value",
                "symbols_known": True,
                "under_type_checking": False,
            },
        )
        for i in range(64)
    ]
    original = ArchitectureContract.component_for
    for overlapping in (False, True):
        raw["components"][1]["packages"] = ["sample.source" if overlapping else "sample.target"]
        contract = parse_contract(raw)
        rule = contract.rules[0]
        with patch.object(
            ArchitectureContract, "component_for", autospec=True, side_effect=original
        ) as lookup:
            verdicts = list(_requires_import_verdicts(imports, contract, rule))
            assert len(verdicts) == (0 if overlapping else len(imports))
            assert all(verdict.value == "FAIL" for _, _, _, verdict in verdicts)
            assert lookup.call_count == 2
        with patch.object(
            ArchitectureContract, "component_for", autospec=True, side_effect=original
        ) as lookup:
            assert _component_cycle_violations(imports, contract, []) == []
            assert lookup.call_count == 2
    with patch.object(ArchitectureContract, "component_for", side_effect=AssertionError):
        assert list(_requires_import_verdicts(imports, contract, rule, frozenset())) == []


def test_facade_owner_index_keeps_proven_and_uncertain_routes_separate():
    from test_analyzer import _component

    from archkeel.check.evaluation.boundary_types import boundary_type_indexes
    from archkeel.ir.codec import parse_contract
    from archkeel.ir.model import ArchitectureContract

    contract = parse_contract(
        {
            "schema_version": "2.1.0",
            "components": [_component("app", packages=["sample"], public=["sample.api"])],
            "rules": [],
        }
    )
    imports = [
        {
            "id": f"import-{i}",
            "data": {
                "source_module": "sample.api",
                "target_module": "sample.impl",
                "binding": f"run{i}",
                "symbol": "Value",
                "reexport": True,
                "origin_definition": "sample.impl.Value",
                "source_binding_unique": True,
                "module_level_import": True,
            },
        }
        for i in range(64)
    ]
    uncertain = {
        f"sample.api.run{i}": frozenset({"sample.impl.Uncertain", "external.Unknown"})
        for i in range(0, 64, 2)
    }
    original = ArchitectureContract.component_for
    with patch.object(
        ArchitectureContract, "component_for", autospec=True, side_effect=original
    ) as lookup:
        index, _ = boundary_type_indexes([], imports, contract, {}, uncertain)
        assert lookup.call_count == 3
    [component] = contract.components
    assert index.owner_facade_type_states == {
        (component.id, "sample.impl", "Value"): True,
        (component.id, "sample.impl", "Uncertain"): False,
    }


def test_scoped_facade_owners_are_indexed_per_contract_without_pruning_reexports():
    from test_analyzer import _component

    from archkeel.check.evaluation import boundary_types
    from archkeel.check.evaluation.rule_support import _reexport_index
    from archkeel.ir.codec import parse_contract
    from archkeel.ir.model import ArchitectureContract

    def contract(identity, overlapping=False):
        components = [_component(identity, packages=["sample"], public=["sample.api"])]
        if overlapping:
            components.append(_component("overlap", packages=["sample"], public=[]))
        return parse_contract({"schema_version": "2.1.0", "components": components, "rules": []})

    symbols = [
        {
            "kind": "function",
            "data": {
                "module": "external.impl",
                "name": f"run{i}",
                "qualified_name": f"external.impl.run{i}",
                "symbol_category": "function",
                "source_binding_unique": True,
                "namespace_bound": True,
                "signature_decorators_proven": True,
                "parameters": [],
                "returns": "str",
            },
        }
        for i in range(64)
    ]
    imports = [
        {
            "id": f"import-{i}",
            "data": {
                "source_module": "sample.api",
                "target_module": "external.impl",
                "symbol": f"run{i}",
                "binding": f"run{i}",
                "reexport": True,
                "origin_definition": f"external.impl.run{i}",
                "reexport_chain": [f"external.impl.run{i}"],
                "module_level_import": True,
                "source_binding_unique": True,
                "origin_binding_unique": True,
            },
        }
        for i in range(64)
    ]
    original = ArchitectureContract.component_for
    ancestor = contract("ancestor")
    for overlapping in (False, True):
        mounted = contract("mounted", overlapping)
        with (
            patch.object(
                ArchitectureContract, "component_for", autospec=True, side_effect=original
            ) as lookup,
            patch.object(boundary_types, "_resolved_position_types", return_value=["sample.Value"]),
        ):
            result = boundary_types._scoped_facade_signature_types(
                symbols,
                imports,
                mounted,
                {},
                {},
                frozenset({"sample.api"}),
                "mount",
                (ancestor,),
                boundary_types.BindingIndex(),
                boundary_types.BindingIndex(),
                _reexport_index(imports),
                {},
                {},
                static_routes=frozenset(),
                type_shapes={},
            )
        assert lookup.call_count == 4
        assert {id(call.args[0]) for call in lookup.call_args_list} == {id(mounted), id(ancestor)}
        assert len(result) == len(symbols)
        assert all(
            item["data"]["facade_types_by_mount"] == {"mount": {"sample.api": ["sample.Value"]}}
            for item in result
        )


def test_field_candidates_use_the_alias_index_without_losing_duplicate_routes():
    from test_analyzer import _component

    from archkeel.check.evaluation.boundary_types import BindingIndex, _declared_field_reach
    from archkeel.check.evaluation.rule_support import _reexport_index
    from archkeel.ir.codec import parse_contract
    from archkeel.ir.type_shapes import TypeName

    class CountedImports(list):
        visits = 0

        def __iter__(self):
            for item in super().__iter__():
                self.visits += 1
                yield item

    imports = CountedImports(
        [
            {
                "id": str(i),
                "data": {
                    "source_module": "sample.api" if i < 2 else "other",
                    "binding": "Alias",
                    "reexport": False,
                    "reexport_chain": [f"provider.Route{i}"],
                    "reexport_candidates": [f"provider.Candidate{i}"],
                },
            }
            for i in range(64)
        ]
    )
    contract = parse_contract(
        {
            "schema_version": "2.1.0",
            "components": [_component("app", packages=["sample"], public=[])],
            "rules": [],
        }
    )
    _, aliases, _ = _reexport_index(imports)
    visits = imports.visits
    for _ in range(20):
        assert _declared_field_reach(
            {
                "data": {
                    "module": "sample.api",
                    "fields": [{"name": "value", "annotation": "Alias"}],
                }
            },
            contract,
            {},
            BindingIndex(),
            BindingIndex(),
            False,
            imports_by_alias=aliases,
            static_routes=frozenset(),
            type_shapes={"Alias": TypeName("Alias", "Alias")},
        ) == (
            [],
            ["provider.Candidate0", "provider.Candidate1", "provider.Route0", "provider.Route1"],
        )
    assert imports.visits == visits
