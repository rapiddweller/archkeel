# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
import ast
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import patch

import pytest
from test_analyzer import _parsed_module
from test_boundary_types_reexport_proofs import _OVERLOAD_GROUP, _observe_facade

from archkeel.analyzer.python import source
from archkeel.analyzer.python.binding_types import ImportKind
from archkeel.analyzer.python.source import (
    AliasBinding,
    stable_direct_module_bindings,
    static_overload_bindings,
    unique_direct_module_bindings,
    unproven_member_bindings,
)
from archkeel.ir.decisions import rule_assessments, unknown_positions_by_rule


def _expanded_member_containment(
    module, nodes, *, owner_exposure_only=False, unsafe_providers=frozenset()
):
    edges, owners = source._contained_member_roots(
        module, nodes, owner_exposure_only=owner_exposure_only, unsafe_providers=unsafe_providers
    )
    return edges | {(owner, name) for owner in owners for name in module.scope_bound_names}


@pytest.mark.parametrize(
    ("expression", "initial", "first", "second"),
    [
        ("alias", "alias", "first.provider", "second.provider"),
        (
            "alias.member.inner",
            "alias.member.inner",
            "first.provider.member.inner",
            "second.provider.member.inner",
        ),
        ("factory().member", "factory().member", "factory().member", "factory().member"),
        ("alias[Payload]", "alias[Payload]", "alias[Payload]", "alias[Payload]"),
        ("'alias.member'", "'alias.member'", "'alias.member'", "'alias.member'"),
    ],
)
def test_static_name_text_keeps_live_alias_resolution(expression, initial, first, second):
    module = _parsed_module("value = 1\n")
    node = ast.parse(expression, mode="eval").body
    assert source.resolve_static_name(module, node) == initial
    module.aliases["alias"] = AliasBinding("first.provider", ImportKind.MODULE)
    assert source.resolve_static_name(module, node) == first
    module.aliases["alias"] = AliasBinding("second.provider", ImportKind.SYMBOL)
    assert source.resolve_static_name(module, node) == second
    del module.aliases["alias"]
    assert source.resolve_static_name(module, node) == initial


@pytest.mark.parametrize(
    ("effect", "mutation"),
    [
        ("annotations", "['run'].__annotations__['value'] = dict"),
        ("binding", "['run'] = lambda value: {}"),
    ],
)
def test_declared_signature_does_not_claim_opaque_callback_effect_freedom(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, effect: str, mutation: str
) -> None:
    api = (
        "from opaque import probe\n"
        "def run(value: str) -> str:\n    probe()\n    return value\n"
        "run('x')\n"
    )
    observation = _observe_facade(tmp_path, api=api, public="sample.app.api:run")
    function = next(
        item
        for item in observation.records("symbols") or ()
        if item.data.get("qualified_name") == "sample.app.api.run"
    )
    assert function.data.get("source_binding_unique") is True
    assert function.data.get("signature_decorators_proven") is True
    assert function.data.get("source_member_binding_static") is False
    [assessment] = rule_assessments(
        observation, undecided_by_rule=unknown_positions_by_rule(observation)
    )
    assert assessment.status == "PASS"
    assert not [
        item
        for item in observation.records("unknowns") or ()
        if item.kind == "boundary_type_position"
    ]

    opaque = ModuleType("opaque")
    exec("import sys\ndef probe():\n    sys._getframe(1).f_globals" + mutation, opaque.__dict__)
    monkeypatch.setitem(sys.modules, "opaque", opaque)
    namespace: dict[str, object] = {}
    declarations, invocation = api.rsplit("\n", 2)[:2]
    exec(declarations, namespace)
    original = namespace["run"]
    assert original.__annotations__["value"] is str
    exec(invocation, namespace)
    if effect == "annotations":
        assert namespace["run"] is original
        assert original.__annotations__["value"] is dict
    else:
        assert namespace["run"] is not original
        assert namespace["run"]("x") == {}


def test_symbol_collection_reuses_proofs_only_within_one_invocation() -> None:
    from archkeel.analyzer.python import symbols as collector
    from archkeel.analyzer.python.imports import collect_imports

    module = _parsed_module(
        "from typing import TypeAlias\n"
        "Text: TypeAlias = str\n"
        "class First: pass\n"
        "class Second: pass\n"
    )
    collect_imports([module], {module.module}, {}, namespace="sample")
    with patch.object(
        collector, "unproven_member_bindings", wraps=unproven_member_bindings
    ) as prove:
        records, _, _ = collector.collect_symbols([module], {})
    assert prove.call_count == 1
    assert {item["data"]["name"] for item in records} >= {"Text", "First", "Second"}
    assert all(
        item["data"]["source_member_binding_static"]
        for item in records
        if item["kind"] in {"class", "type_alias"}
    )

    module.incoming_member_escapes.add("First")
    records, _, _ = collector.collect_symbols([module], {})
    first = next(item["data"] for item in records if item["data"]["name"] == "First")
    assert first["source_member_binding_static"] is False
    assert all(item["status"] == "complete" for item in first["member_inventories"])


@pytest.mark.parametrize("member_surface", [False, True])
def test_member_closure_preserves_alias_direction_and_live_inputs(member_surface):
    nodes = tuple(ast.walk(ast.parse("Alias = Original\nMember = Alias.value\n")))
    contained = {("Container", "Alias"), ("Alias", "Nested"), ("Nested", "Container")}
    roots = {"Original", "Absent"}
    expected = {"Original", "Alias", "Nested", "Container", "Absent"}
    if member_surface:
        expected.add("Member")
    assert (
        source.member_binding_closure(
            nodes, roots, member_surface=member_surface, contained=contained
        )
        == expected
    )
    assert roots == {"Original", "Absent"}
    assert source.member_binding_closure(nodes, {"Alias"}, member_surface=False) == {
        "Alias",
        "Original",
    }
    assert source.member_binding_closure(
        nodes, {"Nested"}, member_surface=member_surface, contained={("Alias", "Nested")}
    ) == {"Nested"}
    assert (
        source.member_binding_closure(
            nodes, set(), member_surface=member_surface, contained=contained
        )
        == set()
    )


@pytest.mark.parametrize("local_name", ["Alias", "Original"])
def test_member_closure_keeps_setter_local_references_excluded(local_name):
    nodes = tuple(ast.walk(ast.parse("Alias = Original\n")))
    local = {node for node in nodes if isinstance(node, ast.Name) and node.id == local_name}
    assert source.member_binding_closure(
        nodes, {"Original"}, member_surface=True, local_references=local
    ) == {"Original"}
    assert source.member_binding_closure(nodes, {"Original"}, member_surface=True) == {
        "Original",
        "Alias",
    }


def test_static_member_indexes_keep_alias_and_type_proofs_live():
    from archkeel.analyzer.python.imports import collect_imports

    module = _parsed_module(
        "from typing import TypeAlias, Callable\n"
        "class Left: pass\nclass Right: pass\n"
        "Alias: TypeAlias = Left | Right\n"
        "Handler: TypeAlias = Callable[[Left], Right]\n"
    )
    collect_imports([module], {module.module}, {}, namespace="sample")
    values = {
        node.target.id: node.value for node in module.tree.body if isinstance(node, ast.AnnAssign)
    }
    owners, static = module._contained_owners, module._static_containment
    first = _expanded_member_containment(module, module.all_nodes)
    assert ("Alias", "Left") not in first and ("Handler", "Right") not in first
    module._proven_map_union_expressions = frozenset({values["Alias"]})
    second = _expanded_member_containment(module, module.all_nodes)
    assert {("Alias", "Left"), ("Alias", "Right")} <= second - first
    module._proven_callable_expressions = frozenset({values["Handler"]})
    third = _expanded_member_containment(module, module.all_nodes)
    assert {("Handler", "Left"), ("Handler", "Right")} <= third - second
    module.aliases["TypeAlias"] = AliasBinding("opaque.TypeAlias", ImportKind.SYMBOL)
    assert _expanded_member_containment(module, module.all_nodes) == first
    module.aliases["TypeAlias"] = AliasBinding("typing.TypeAlias", ImportKind.SYMBOL)
    module._proven_map_union_expressions = frozenset()
    module._proven_callable_expressions = frozenset()
    assert _expanded_member_containment(module, module.all_nodes) == first
    assert module._contained_owners is owners and module._static_containment is static


def test_static_member_indexes_keep_namespace_and_provider_uncertainty_live():
    from archkeel.analyzer.python.imports import collect_imports

    module = _parsed_module(
        "from typing import TypedDict\nclass Record(TypedDict):\n value: int\nsentinel = 1\n"
    )
    collect_imports([module], {module.module}, {}, namespace="sample")
    owners, static = module._contained_owners, module._static_containment
    first = _expanded_member_containment(module, module.all_nodes, owner_exposure_only=True)
    assert ("Record", "sentinel") not in first
    unsafe = _expanded_member_containment(
        module, module.all_nodes, owner_exposure_only=True, unsafe_providers=frozenset({"typing"})
    )
    assert ("Record", "sentinel") in unsafe - first
    assert _expanded_member_containment(module, module.all_nodes, owner_exposure_only=True) == first
    module.incoming_member_escapes.add("TypedDict")
    exposed = _expanded_member_containment(module, module.all_nodes, owner_exposure_only=True)
    assert ("Record", "sentinel") in exposed - first
    module.incoming_member_escapes.clear()
    assert _expanded_member_containment(module, module.all_nodes, owner_exposure_only=True) == first
    assert _expanded_member_containment(module, module.all_nodes) == first
    assert module._contained_owners is owners and module._static_containment is static


def test_static_member_indexes_do_not_replace_a_requested_subtree():
    module = _parsed_module("class First:\n value: Left\nclass Second:\n value: Right\n")
    assert _expanded_member_containment(module, module.all_nodes) == {
        ("First", "Left"),
        ("Second", "Right"),
    }
    nodes = tuple(ast.walk(module.tree.body[0]))
    assert _expanded_member_containment(module, nodes) == {("First", "Left")}


def test_member_escape_pass_reuses_proofs_until_incoming_changes():
    from archkeel.analyzer.python import imports as collector

    module = _parsed_module("class Payload: pass\n")
    modules = {module.module: module}
    exposed = {module.module: set()}
    transferred = {module.module: set()}
    proofs = {}
    with patch.object(
        collector, "unproven_member_bindings", wraps=unproven_member_bindings
    ) as prove:
        first = collector._member_escape_pass(modules, exposed, transferred, frozenset(), proofs)
        assert (
            collector._member_escape_pass(modules, exposed, transferred, frozenset(), proofs)
            == first
        )
        assert prove.call_count == 3
        module.incoming_member_escapes.add("Payload")
        changed = collector._member_escape_pass(modules, exposed, transferred, frozenset(), proofs)
        assert "Payload" in changed[0][module.module]
        assert prove.call_count == 6
        exposed[module.module].add("Payload")
        changed = collector._member_escape_pass(modules, exposed, transferred, frozenset(), proofs)
        assert "Payload" in changed[1][module.module]
        assert "Payload" not in changed[2][module.module]
        assert prove.call_count == 7


def test_member_escape_pass_separates_creation_modes_and_unsafe_providers():
    from archkeel.analyzer.python import imports as collector

    module = _parsed_module(
        "from typing import TypedDict\nclass Payload(TypedDict):\n value: str\n"
    )
    collector.collect_imports([module], {module.module}, {}, namespace="sample")
    modules = {module.module: module}
    incoming = {module.module: set()}
    proofs = {}
    safe = collector._member_escape_pass(modules, incoming, incoming, frozenset(), proofs)
    unsafe = collector._member_escape_pass(modules, incoming, incoming, {"typing"}, proofs)
    assert "Payload" not in safe[1][module.module]
    assert "Payload" in unsafe[1][module.module]
    assert "Payload" not in unsafe[2][module.module]


def test_member_escape_convergence_does_not_reuse_another_invocations_source():
    from archkeel.analyzer.python import imports as collector

    results = []
    for extra in ("", "mutate(Payload)\n"):
        module = _parsed_module("class Payload: pass\n" + extra)
        results.append(
            collector._converge_member_escapes(
                [],
                {module.module: module},
                {module.module: stable_direct_module_bindings(module)},
                {module.module: unproven_member_bindings(module)},
                {module.module: {}},
            )[0][module.module]
        )
    assert "Payload" not in results[0]
    assert "Payload" in results[1]


def test_member_escape_convergence_recomputes_after_late_protection_revocation():
    from archkeel.analyzer.python import imports as collector

    modules, _, _ = _map_union_project(local=True)
    module = modules[1]
    candidates = {
        module.module: {
            expression: frozenset({(module.module, "SexKey")})
            for expression in module._proven_map_union_expressions
        }
    }
    states = {}
    retain_calls = 0
    retain = collector._retain_type_reference_protection

    def revoke_after_first_pass(modules, candidates, escaped, exposed, transferred):
        nonlocal retain_calls
        retain_calls += 1
        if retain_calls == 2:
            # Arriving dependency uncertainty must invalidate otherwise identical proof inputs.
            escaped[module.module] |= {"SexKey"}
        return retain(modules, candidates, escaped, exposed, transferred)

    def trace(module, **options):
        incoming = options.get("incoming")
        state = (
            options.get("owner_exposure_only", False),
            options.get("include_creation_uncertainty", True),
            None if incoming is None else frozenset(incoming),
            frozenset(module.incoming_member_escapes),
            frozenset(options.get("unsafe_providers", ())),
        )
        states.setdefault(state, set()).add(bool(module._proven_map_union_expressions))
        return unproven_member_bindings(module, **options)

    with (
        patch.object(collector, "unproven_member_bindings", side_effect=trace),
        patch.object(
            collector, "_retain_type_reference_protection", side_effect=revoke_after_first_pass
        ),
    ):
        escaped, _ = collector._converge_member_escapes(
            [],
            {module.module: module},
            {module.module: stable_direct_module_bindings(module)},
            {module.module: frozenset()},
            candidates,
        )
    assert not module._proven_map_union_expressions
    assert "SexKey" in escaped[module.module]
    assert any(protection == {False, True} for protection in states.values())


def test_module_function_proofs_do_not_grant_nested_or_conditional_bindings() -> None:
    from archkeel.analyzer.python.symbols import collect_symbols

    module = _parsed_module(
        "def outer():\n    def inner(): pass\n"
        "if condition:\n    def conditional(): pass\n"
        "def rebound(): pass\nrebound = lambda: None\n"
        "class Owner:\n    def method(self): pass\n"
    )
    records, _, _ = collect_symbols([module], {})
    by_name = {item["data"]["name"]: item["data"] for item in records}
    assert by_name["outer"]["source_binding_unique"] is True
    assert by_name["conditional"]["source_binding_unique"] is False
    assert by_name["rebound"]["source_binding_unique"] is False
    assert by_name["inner"]["source_binding_unique"] is True
    assert by_name["inner"]["namespace_bound"] is False
    from archkeel.check.evaluation.boundary_types import _declared_function_signature

    assert not _declared_function_signature(by_name["inner"])
    assert "source_binding_unique" not in by_name["method"]
    assert by_name["outer"]["signature_decorators_proven"] is True


def test_overload_origin_proof_keeps_bound_once_inventories_unchanged() -> None:
    from archkeel.analyzer.python.imports import collect_imports, resolve_reexports

    modules = [
        _parsed_module(_OVERLOAD_GROUP, "sample.impl", rel_path="sample/impl.py"),
        _parsed_module(
            "from .impl import resolve_source_entity\n__all__ = ['resolve_source_entity']\n",
            "sample.api",
            rel_path="sample/api.py",
        ),
    ]
    imports = collect_imports(modules, {m.module for m in modules}, {}, namespace="sample")
    stable = {m.module: stable_direct_module_bindings(m) for m in modules}
    unique = {m.module: unique_direct_module_bindings(m) for m in modules}
    assert "resolve_source_entity" not in stable["sample.impl"] | unique["sample.impl"]
    assert static_overload_bindings(modules[0]) == frozenset({"resolve_source_entity"})
    uncertain, unsafe = resolve_reexports(
        imports, {m.module: m.all_exports for m in modules}, modules
    )
    assert not uncertain
    assert not unsafe
    imported = next(item for item in imports if item["data"]["source_module"] == "sample.api")
    assert imported["data"]["origin_binding_unique"] is True
    assert imported["data"]["origin_definition"] == "sample.impl.resolve_source_entity"
    assert {m.module: stable_direct_module_bindings(m) for m in modules} == stable
    assert {m.module: unique_direct_module_bindings(m) for m in modules} == unique


def test_enum_mutation_scan_is_reused_for_repeated_member_reads(monkeypatch) -> None:
    from archkeel.analyzer.python import imports as import_module

    original = import_module._enum_owner_is_mutated
    calls = 0

    def count_mutation_scans(owner_module, owner, proofs, mutation_index):
        nonlocal calls
        calls += 1
        return original(owner_module, owner, proofs, mutation_index)

    monkeypatch.setattr(import_module, "_enum_owner_is_mutated", count_mutation_scans)

    def observe(mutation: str):
        provider = _parsed_module(
            "from enum import StrEnum\n"
            "class OptionKey(StrEnum):\n"
            "    READY = 'ready'\n"
            "    DISABLED = 'disabled'\n",
            "sample.options",
            rel_path="sample/options.py",
        )
        consumer = _parsed_module(
            "from .options import OptionKey\n"
            + "".join("consume(OptionKey.READY)\n" for _ in range(100)),
            "sample.api",
            rel_path="sample/api.py",
        )
        mutator = _parsed_module(
            "from .options import OptionKey\n" + mutation,
            "sample.mutator",
            rel_path="sample/mutator.py",
        )
        modules = [provider, consumer, mutator]
        records = import_module.collect_imports(
            modules, {module.module for module in modules}, {}, namespace="sample"
        )
        import_module.resolve_reexports(
            records, {module.module: module.all_exports for module in modules}, modules
        )
        return consumer

    assert len(observe("")._non_escaping_enum_values) == 100
    for mutation in (
        "OptionKey.READY = 'changed'\n",
        "setattr(OptionKey, 'READY', 'changed')\n",
        "del OptionKey.READY\n",
        "delattr(OptionKey, 'READY')\n",
    ):
        assert not observe(mutation)._non_escaping_enum_values
    assert calls == 5


@pytest.mark.parametrize(
    "missing",
    [
        "origin_binding_unique",
        "source_binding_unique",
        "origin_definition",
        "namespace_bound",
        "definition_contexts",
        "overload_signature",
        "implementation",
        "competing-import",
        "unrelated-origin",
        "ambiguous-publisher",
        "parent",
        "all-async-flags",
    ],
)
def test_core_overload_route_needs_the_exact_complete_origin_proof(missing: str) -> None:
    from archkeel.analyzer.python.imports import collect_imports, resolve_reexports
    from archkeel.analyzer.python.symbols import collect_symbols
    from archkeel.check.evaluation.boundary_types import _public_alias_route_has_unproven_hop

    modules = [
        _parsed_module(_OVERLOAD_GROUP, "sample.impl", rel_path="sample/impl.py"),
        _parsed_module(
            "from .impl import resolve_source_entity as constraints\n__all__ = ['constraints']\n",
            "sample.api",
            rel_path="sample/api.py",
        ),
    ]
    imports = collect_imports(modules, {m.module for m in modules}, {}, namespace="sample")
    resolve_reexports(imports, {m.module: m.all_exports for m in modules}, modules)
    symbols, _, _ = collect_symbols(modules, {})
    definitions = {("sample.impl", "resolve_source_entity"): symbols}
    publisher = next(item for item in imports if item["data"]["source_module"] == "sample.api")
    bindings = {("sample.api", "constraints"): [publisher]}
    route = ("sample.api.constraints", "sample.impl.resolve_source_entity")
    stable = {m.module: stable_direct_module_bindings(m) for m in modules}
    assert not _public_alias_route_has_unproven_hop(
        route, definitions, bindings, set(stable), stable, type_shapes={}
    )

    if missing in {"namespace_bound", "definition_contexts", "overload_signature", "parent"}:
        symbols[0]["data"].pop(missing)
    elif missing == "all-async-flags":
        for item in symbols:
            item["data"].pop("async")
    elif missing == "implementation":
        definitions["sample.impl", "resolve_source_entity"] = [
            item for item in symbols if item["data"]["overload_signature"]
        ]
    elif missing == "competing-import":
        bindings["sample.impl", "resolve_source_entity"] = [publisher]
    elif missing == "unrelated-origin":
        publisher["data"]["origin_definition"] = "sample.other.resolve_source_entity"
    elif missing == "ambiguous-publisher":
        bindings["sample.api", "constraints"].append(publisher)
    else:
        publisher["data"].pop(missing)
    assert _public_alias_route_has_unproven_hop(
        route, definitions, bindings, set(stable), stable, type_shapes={}
    )


@pytest.mark.parametrize("change", ["missing-hop", "different-origin", "different-suffix", "cycle"])
def test_reexport_route_requires_each_exact_source_suffix(change: str) -> None:
    from archkeel.analyzer.python.imports import collect_imports, resolve_reexports
    from archkeel.analyzer.python.symbols import collect_symbols
    from archkeel.check.evaluation.boundary_types import (
        _public_alias_route_has_unproven_hop,
        _reexport_declaration_proven,
    )
    from archkeel.check.evaluation.rule_support import _reexport_index

    modules = [
        _parsed_module("def run(value: str) -> str: return value\n", "sample.impl"),
        _parsed_module("from .impl import run\n__all__ = ['run']\n", "sample.bridge"),
        _parsed_module("from .bridge import run\n__all__ = ['run']\n", "sample.api"),
    ]
    imports = collect_imports(modules, {m.module for m in modules}, {}, namespace="sample")
    resolve_reexports(imports, {m.module: m.all_exports for m in modules}, modules)
    symbols, _, _ = collect_symbols(modules, {})
    publisher = next(item for item in imports if item["data"]["source_module"] == "sample.api")
    bridge = next(item for item in imports if item["data"]["source_module"] == "sample.bridge")
    route = ("sample.api.run", "sample.bridge.run", "sample.impl.run")
    stable = {m.module: stable_direct_module_bindings(m) for m in modules}
    definitions = {("sample.impl", "run"): symbols}
    bindings = {("sample.api", "run"): [publisher], ("sample.bridge", "run"): [bridge]}
    assert _reexport_declaration_proven(publisher["data"], _reexport_index(imports)[1])
    assert not _public_alias_route_has_unproven_hop(
        route, definitions, bindings, set(stable), stable, type_shapes={}
    )
    if change == "missing-hop":
        imports.remove(bridge)
        del bindings["sample.bridge", "run"]
    elif change == "different-origin":
        bridge["data"]["origin_definition"] = "sample.other.run"
        bridge["data"]["reexport_chain"] = ["sample.other.run"]
    else:
        bridge["data"]["reexport_chain"] = [
            "sample.api.run" if change == "cycle" else "sample.extra.run",
            "sample.impl.run",
        ]
    assert not _reexport_declaration_proven(publisher["data"], _reexport_index(imports)[1])
    assert _public_alias_route_has_unproven_hop(
        route, definitions, bindings, set(stable), stable, type_shapes={}
    )


def _callable_proof_modules(extra: str = "", provider: str | None = None):
    from archkeel.analyzer.python.imports import collect_imports, resolve_reexports

    consumer = _parsed_module(
        "from typing import Callable\nclass Payload: value: str\n"
        "Lookup = Callable[[Payload], Payload]\n"
        "def lookup(value: Lookup) -> bool: return True\n" + extra,
        "sample.api",
        rel_path="sample/api.py",
    )
    modules = [consumer]
    if provider is not None:
        modules.append(_parsed_module(provider, "typing", rel_path="typing.py"))
    imports = collect_imports(
        modules, {module.module for module in modules}, {}, namespace="sample"
    )
    stable = stable_direct_module_bindings(consumer)
    unique = unique_direct_module_bindings(consumer)
    resolve_reexports(imports, {module.module: module.all_exports for module in modules}, modules)
    assert stable_direct_module_bindings(consumer) == stable
    assert unique_direct_module_bindings(consumer) == unique
    return modules, imports


@pytest.mark.parametrize(
    ("extra", "syntax_proven"),
    [
        ("", True),
        ("mutate(Lookup)\n", False),
        ("Payload.attr = 1\n", True),
        ("mutate(Callable)\n", False),
        ("other = Unknown[Payload]\n", False),
        ("other = Callable[[factory(Payload)], int]\n", False),
        ("def other(value=Payload): pass\n", True),
        ("@decorate(Payload)\ndef other(): pass\n", False),
        ("setattr(Payload, 'value', str)\n", True),
        ("expose(globals())\n", False),
        ("if condition: Callable = other\n", False),
        ("Callable = other\n", False),
        ("from unknown import *\n", False),
    ],
)
def test_callable_syntax_proof_and_payload_member_safety_are_separate(
    extra: str,
    syntax_proven: bool,
) -> None:
    from archkeel.analyzer.python.source import unproven_member_bindings

    modules, imports = _callable_proof_modules(extra)
    assert bool(modules[0]._proven_callable_expressions) is syntax_proven
    assert imports[0]["data"]["source_member_binding_static"] is syntax_proven
    assert ("Payload" in unproven_member_bindings(modules[0])) is bool(extra)


@pytest.mark.parametrize("provider", ["def Callable(): pass\n", "class Callable: pass\n"])
def test_locally_scanned_stdlib_spelling_does_not_prove_callable(provider: str) -> None:
    modules, imports = _callable_proof_modules(provider=provider)
    assert not modules[0]._proven_callable_expressions
    assert imports[0]["data"]["source_member_binding_static"] is False


def test_callable_protection_replaces_snapshot_and_rechecks_incoming_escape() -> None:
    from archkeel.analyzer.python.imports import resolve_reexports

    modules, imports = _callable_proof_modules()
    original = modules[0]._proven_callable_expressions
    assert original
    modules[0].incoming_member_escapes.add("Lookup")
    resolve_reexports(imports, {module.module: module.all_exports for module in modules}, modules)
    assert not modules[0]._proven_callable_expressions
    fresh, _imports = _callable_proof_modules()
    assert fresh[0]._proven_callable_expressions
    assert original.isdisjoint(fresh[0]._proven_callable_expressions)


def test_unique_proof_does_not_repeat_ast_walks() -> None:
    with patch.object(ast, "iter_fields", wraps=ast.iter_fields) as visits:
        module = _parsed_module("class Api: pass\nclass Other: pass\n")
        assert unique_direct_module_bindings(module) == frozenset({"Api", "Other"})
        first_visits = visits.call_count
        assert unique_direct_module_bindings(module) == frozenset({"Api", "Other"})
        assert visits.call_count == first_visits


def test_local_annotation_carrier_does_not_inherit_the_imported_identity() -> None:
    from archkeel.analyzer.python.imports import collect_imports, resolve_reexports
    from archkeel.analyzer.python.symbols import collect_symbols

    text = (
        "from typing import Sequence\nclass Payload: pass\n"
        "def build(Sequence):\n    def consume(value: Sequence[Payload]): pass\n"
    )
    module = _parsed_module(text)
    imports = collect_imports([module], {module.module}, {}, namespace="sample")
    resolve_reexports(imports, {module.module: module.all_exports}, [module])
    symbols, _, _ = collect_symbols([module], {})
    payload = next(item["data"] for item in symbols if item["data"]["name"] == "Payload")
    assert not module._proven_annotation_carriers
    assert payload["source_member_binding_static"] is False
    assert all(item["status"] == "complete" for item in payload["member_inventories"])

    class Evil:
        @classmethod
        def __class_getitem__(cls, value):
            value.changed = True
            return int

    namespace: dict[str, object] = {}
    exec(text, namespace)
    assert "changed" not in vars(namespace["Payload"])
    namespace["build"](Evil)
    assert namespace["Payload"].changed is True


def test_stable_proof_does_not_repeat_namespace_scans() -> None:
    module = _parsed_module("class Api: pass\nclass Other: pass\nalias = Api\n")
    with patch.object(
        source, "exposes_dynamic_namespace", wraps=source.exposes_dynamic_namespace
    ) as visits:
        assert stable_direct_module_bindings(module) == frozenset({"Api", "Other", "alias"})
        first_visits = visits.call_count
        assert first_visits > 0
        assert stable_direct_module_bindings(module) == frozenset({"Api", "Other", "alias"})
        assert visits.call_count == first_visits


def test_alias_changes_invalidate_even_an_empty_stable_proof() -> None:
    module = _parsed_module("from builtins import exec as run\nclass C: pass\nrun('x')\n")
    original = frozenset({"C", "run"})
    assert stable_direct_module_bindings(module) == original
    module.aliases["run"] = AliasBinding("builtins.exec", ImportKind.SYMBOL, "exec")
    assert stable_direct_module_bindings(module) == frozenset()
    assert stable_direct_module_bindings(module) == frozenset()
    module.aliases["run"] = AliasBinding("safe.run", ImportKind.SYMBOL, "run")
    assert stable_direct_module_bindings(module) == original
    del module.aliases["run"]
    assert stable_direct_module_bindings(module) == original


def test_alias_kind_change_invalidates_import_origin_proof() -> None:
    module = _parsed_module(
        "import pkg as route\nfrom pkg import X as second\nroute.attr = 1\nclass C: pass\n"
    )
    assert "second" in stable_direct_module_bindings(module)
    module.aliases.update(
        route=AliasBinding("pkg", ImportKind.MODULE),
        second=AliasBinding("pkg.X", ImportKind.SYMBOL, "X"),
    )
    assert "second" not in stable_direct_module_bindings(module)
    module.aliases["second"] = AliasBinding("pkg.X", ImportKind.MODULE, "X")
    assert "second" in stable_direct_module_bindings(module)


def test_incoming_member_proofs_remain_live() -> None:
    module = _parsed_module("class C: pass\n")
    assert stable_direct_module_bindings(module) == frozenset({"C"})
    assert unproven_member_bindings(module) == frozenset()
    module.incoming_member_escapes.add("C")
    assert stable_direct_module_bindings(module) == frozenset({"C"})
    assert unproven_member_bindings(module) == frozenset({"C"})


def test_same_path_snapshots_have_separate_proofs() -> None:
    original = _parsed_module("class C: pass\n")
    changed = _parsed_module("class C: pass\nclass C: pass\n")
    assert original.path == changed.path
    for module, expected in (
        (original, frozenset({"C"})),
        (changed, frozenset()),
        (original, frozenset({"C"})),
    ):
        assert unique_direct_module_bindings(module) == expected
        assert stable_direct_module_bindings(module) == expected


@pytest.mark.parametrize(
    "expression", ["vars()", "vars(C)", "vars", "locals()", "locals(C)", "exec(C)", "eval(C)"]
)
def test_namespace_access_remains_unproven(expression: str) -> None:
    module = _parsed_module("class C: pass\n" + expression + "\n")
    assert stable_direct_module_bindings(module) == frozenset()
    assert stable_direct_module_bindings(module) == frozenset()


def test_absent_global_does_not_rescan_class_bodies() -> None:
    module = _parsed_module("class Service:\n class Nested:\n  staticmethod = 1\n")
    with patch.object(ast, "walk", wraps=ast.walk) as walks:
        for _ in range(3):
            assert not source.binding_may_exist_before(
                module, module.tree.body, None, "staticmethod"
            )
        assert walks.call_count == 0


def test_global_elsewhere_does_not_bind_inside_a_different_class() -> None:
    module = _parsed_module(
        "class First:\n global property\n property = None\nclass Second: pass\n"
    )
    second = module.tree.body[1]
    assert isinstance(second, ast.ClassDef)
    assert not source.binding_may_exist_before(module, second.body, None, "property")
    assert source.binding_may_exist_before(module, module.tree.body, second, "property")


def test_absent_binding_does_not_repeat_statement_scans() -> None:
    module = _parsed_module("def service(value=factory('x')): pass\n")
    with patch.object(ast, "iter_child_nodes", wraps=ast.iter_child_nodes) as visits:
        for _ in range(3):
            assert not source.binding_may_exist_before(
                module, module.tree.body, None, "staticmethod"
            )
        assert visits.call_count == 0


def test_wildcard_import_retains_arbitrary_binding_uncertainty() -> None:
    module = _parsed_module("from unknown import *\n")
    assert source.binding_may_exist_before(module, module.tree.body, None, "staticmethod")


@pytest.mark.parametrize(
    "declaration",
    [
        "del property",
        "property: object",
        "import unknown as property",
        "from unknown import value as property",
        "class property: pass",
        "def property(): pass",
        "async def property(): pass",
        "try:\n pass\nexcept Exception as property:\n pass",
        'match value:\n case {"x": property}: pass',
        "match value:\n case [*property]: pass",
        "match value:\n case {**property}: pass",
        "class First:\n global property",
        "def service(value=(property := 1)): pass",
    ],
)
def test_binding_index_preserves_every_binding_form(declaration: str) -> None:
    module = _parsed_module(declaration + "\n")
    assert source.binding_may_exist_before(module, module.tree.body, None, "property")


_MAP_UNION = "dict[str, float] | dict[tuple[int, int], float] | dict[SexKey, float]"


def _map_union_project(
    *,
    local: bool = False,
    extra: str = "",
    provider_extra: str = "",
    annotation: str = _MAP_UNION,
    body: str = _MAP_UNION,
    prefix: str = "",
    other_importer: str = "",
    provider_source: str = "SexKey = str | None\n",
    importer_source: str = "from .types import SexKey\n",
):
    from archkeel.analyzer.python.imports import collect_imports, resolve_reexports
    from archkeel.analyzer.python.symbols import collect_symbols

    modules = [
        _parsed_module(
            provider_source + provider_extra, "sample.types", rel_path="sample/types.py"
        ),
        _parsed_module(
            ("SexKey = str | None\n" if local else importer_source)
            + prefix
            + f"GroupMask = {body}\n"
            + f"class Session:\n    def prepare(self) -> {annotation}: pass\n"
            + extra,
            "sample.impl",
            rel_path="sample/impl.py",
        ),
    ]
    if other_importer:
        modules.append(_parsed_module(other_importer, "sample.other", rel_path="sample/other.py"))
    evidence = {}
    imports = collect_imports(
        modules, {module.module for module in modules}, evidence, namespace="sample"
    )
    resolve_reexports(imports, {module.module: module.all_exports for module in modules}, modules)
    symbols, _, _ = collect_symbols(modules, evidence)
    return modules, imports, symbols


@pytest.mark.parametrize("local", [False, True])
@pytest.mark.parametrize("named", [False, True])
def test_map_union_proves_both_annotation_and_admitted_assignment(local: bool, named: bool) -> None:
    modules, imports, symbols = _map_union_project(
        local=local, annotation="GroupMask" if named else _MAP_UNION
    )
    for module in modules:
        assert "SexKey" not in unproven_member_bindings(module)
    keys = [item for item in symbols if item["data"].get("name") == "SexKey"]
    assert keys and all(item["data"].get("source_member_binding_static") is True for item in keys)
    key_imports = [item for item in imports if item["data"]["binding"] == "SexKey"]
    assert all(
        item["data"].get("source_member_binding_static") is True
        and item["data"].get("origin_member_binding_static") is True
        for item in key_imports
    )


@pytest.mark.parametrize(
    "change",
    [
        {"extra": "unknown(SexKey)\n"},
        {"extra": "SexKey.__args__ = ()\n"},
        {"extra": "unknown(GroupMask)\n"},
        {"provider_extra": "unknown(SexKey)\n"},
        {"extra": "from . import types\ntypes.SexKey = object\n"},
        {"other_importer": "from .types import SexKey\nunknown(SexKey)\n"},
    ],
)
def test_map_union_cannot_absolve_a_separate_escape(change) -> None:
    modules, imports, symbols = _map_union_project(**change)
    assert "SexKey" in unproven_member_bindings(modules[0])
    assert "SexKey" in unproven_member_bindings(modules[1])
    assert all(
        item["data"].get("source_member_binding_static") is False
        for item in symbols
        if item["data"].get("name") == "SexKey"
    )
    assert all(
        item["data"].get("source_member_binding_static") is False
        for item in imports
        if item["data"]["binding"] == "SexKey"
    )


@pytest.mark.parametrize(
    "annotation",
    [
        "dict[SexKey, float] | Missing",
        "Missing | dict[SexKey, float]",
        "dict[str, int] | dict[SexKey, float] | Missing",
        "dict[SexKey, float] | factory()",
        "factory()[SexKey] | dict[str, float]",
        "Unknown[SexKey] | dict[str, float]",
        "dict[SexKey, Custom] | dict[str, float]",
        "dict[Custom, float] | dict[SexKey, float]",
        "dict[SexKey, float] | Custom",
        "Custom | dict[SexKey, float]",
    ],
)
def test_unsafe_union_operand_or_argument_keeps_alias_escaped(annotation: str) -> None:
    prefix = (
        "class Meta(type):\n"
        "    def __or__(self, other): return other\n"
        "    def __ror__(self, other): return other\n"
        "    def __eq__(self, other): return True\n"
        "class Custom(metaclass=Meta): pass\n"
    )
    modules, imports, _ = _map_union_project(annotation=annotation, body=annotation, prefix=prefix)
    assert "SexKey" in unproven_member_bindings(modules[0])
    assert "SexKey" in unproven_member_bindings(modules[1])
    assert all(
        item["data"].get("source_member_binding_static") is False
        for item in imports
        if item["data"]["binding"] == "SexKey"
    )


def test_fresh_map_union_snapshot_does_not_inherit_an_old_proof() -> None:
    safe, _, _ = _map_union_project()
    unsafe, _, _ = _map_union_project(provider_extra="unknown(SexKey)\n")
    assert safe[1].path == unsafe[1].path
    assert "SexKey" not in unproven_member_bindings(safe[1])
    assert "SexKey" in unproven_member_bindings(unsafe[1])
    assert "SexKey" not in unproven_member_bindings(safe[1])


def test_rerunning_import_origins_replaces_the_map_union_proof() -> None:
    from archkeel.analyzer.python.imports import resolve_reexports

    modules, imports, _ = _map_union_project()
    assert "SexKey" not in unproven_member_bindings(modules[1])
    imported = next(item for item in imports if item["data"]["binding"] == "SexKey")
    imported["data"]["target_module"] = "sample.missing"
    modules[1].aliases["SexKey"] = AliasBinding(
        "sample.missing.SexKey", ImportKind.SYMBOL, "SexKey"
    )
    resolve_reexports(imports, {module.module: module.all_exports for module in modules}, modules)
    assert "SexKey" in unproven_member_bindings(modules[1])


@pytest.mark.parametrize(
    "change",
    [
        {"provider_source": "class str: pass\nSexKey = str | None\n"},
        {"provider_source": "SexKey = None | str\n"},
        {"provider_source": "Key = str | None\nSexKey = Key\n"},
        {"provider_source": "SexKey = str | None\nSexKey = str | None\n"},
        {"provider_source": "if flag:\n    SexKey = str | None\n"},
        {"provider_source": "from opaque import *\nSexKey = str | None\n"},
        {"provider_source": "SexKey = str | None\nunknown(globals())\n"},
        {"provider_source": "from .provider import SexKey\n"},
        {"importer_source": "from .missing import SexKey\n"},
        {"importer_source": "if flag:\n    from .types import SexKey\n"},
        {"importer_source": "from .types import SexKey\nfrom .types import SexKey\n"},
        {"importer_source": "from .types import *\n"},
        {
            "importer_source": (
                "from typing import TYPE_CHECKING\n"
                "if TYPE_CHECKING:\n    from .types import SexKey\n"
            )
        },
    ],
)
def test_map_union_requires_an_intrinsic_direct_provider(change) -> None:
    modules, imports, _ = _map_union_project(**change)
    assert not modules[1]._proven_map_union_expressions
    assert "SexKey" in unproven_member_bindings(modules[1])
    assert all(
        item["data"].get("source_member_binding_static") is False
        for item in imports
        if item["data"]["binding"] == "SexKey"
    )


def test_local_map_union_protection_revokes_without_an_import_edge() -> None:
    modules, _, _ = _map_union_project(local=True, extra="unknown(SexKey)\n")
    assert not modules[1]._proven_map_union_expressions
    assert "SexKey" in unproven_member_bindings(modules[1])


def test_setter_local_parameter_does_not_hide_real_outer_escape() -> None:
    module = _parsed_module(
        "class value: pass\nclass Counter:\n"
        " @property\n def value(self) -> int: return 7\n"
        " @value.setter\n def value(self, value: int) -> None:\n"
        "  copy = value\n  self._value = copy\n"
        "mutate(value)\n"
    )
    assert {"value", "Counter"} <= unproven_member_bindings(module)


def test_same_named_setter_incoming_escape_remains_live() -> None:
    module = _parsed_module(
        "class Counter:\n @property\n def value(self) -> int: return 7\n"
        " @value.setter\n def value(self, value: int) -> None: self._value = value\n"
    )
    assert "Counter" not in unproven_member_bindings(module)
    module.incoming_member_escapes.add("Counter")
    assert "Counter" in unproven_member_bindings(module)


@pytest.mark.parametrize("owner_exposure,creation", [(False, True), (True, True), (True, False)])
def test_setter_scope_is_shared_by_member_proof_modes(owner_exposure, creation):
    module = _parsed_module(
        "class Counter:\n @property\n def value(self) -> int: return 7\n"
        " @value.setter\n def value(self, value: int) -> None:\n"
        "  copy = value\n  self._value = copy\n"
    )
    assert "Counter" not in unproven_member_bindings(
        module, owner_exposure_only=owner_exposure, include_creation_uncertainty=creation
    )
    module.incoming_member_escapes.add("Counter")
    assert "Counter" in unproven_member_bindings(
        module, owner_exposure_only=owner_exposure, include_creation_uncertainty=creation
    )


@pytest.mark.parametrize("reverse", [False, True])
@pytest.mark.parametrize("escape", ["", "mutate(Payload)\n"])
def test_callable_source_proof_is_order_independent_and_keeps_safe_sibling(
    reverse: bool,
    escape: str,
) -> None:
    from archkeel.analyzer.python.imports import collect_imports, resolve_reexports

    provider = _parsed_module(
        "from typing import Callable\nclass Payload: value: str\n"
        "class Safe: value: str\nLookup = Callable[[Payload], Payload]\n"
        "Other = Callable[[Safe], Safe]\n" + escape,
        "sample.impl",
    )
    consumer = _parsed_module("from .impl import Lookup, Other\n", "sample.api")
    modules = [provider, consumer]
    if reverse:
        modules.reverse()
    imports = collect_imports(modules, {m.module for m in modules}, {}, namespace="sample")
    resolve_reexports(imports, {m.module: m.all_exports for m in modules}, modules)
    bindings = {
        r["data"]["binding"]: r["data"]
        for r in imports
        if r["data"]["source_module"] == "sample.api"
    }
    for name in ("Other", "Lookup"):
        assert bindings[name]["source_binding_unique"] is True
        assert bindings[name]["origin_binding_unique"] is True
        assert bindings[name]["origin_definition"] == f"sample.impl.{name}"
        assert bindings[name]["source_member_binding_static"] is not bool(escape)
    import ast

    from archkeel.analyzer.python.source import unproven_member_bindings

    protected = {ast.unparse(node) for node in provider._proven_callable_expressions}
    assert ("Callable[[Safe], Safe]" in protected) is not bool(escape)
    assert ("Callable[[Payload], Payload]" in protected) is not bool(escape)
    assert ("Payload" in unproven_member_bindings(provider)) is bool(escape)


def test_member_containment_reuses_only_immutable_syntax() -> None:
    with patch.object(
        source, "_protected_type_expressions", wraps=source._protected_type_expressions
    ) as scans:
        module = _parsed_module(
            "class Payload: pass\nclass Container:\n"
            "    def read(self, value: Payload) -> Payload: return value\n",
            "sample.api",
            rel_path="sample/api.py",
        )
        expected = _expanded_member_containment(module, module.all_nodes)
        first = scans.call_count
        assert first
        assert _expanded_member_containment(module, module.all_nodes) == expected
        assert scans.call_count == first
        assert _expanded_member_containment(module, ()) == set()
        fresh = _parsed_module(module.source, "sample.api", rel_path="sample/api.py")
        assert _expanded_member_containment(fresh, fresh.all_nodes) == expected
        assert scans.call_count > first


def test_import_source_projection_does_not_replace_factory_cache():
    module = _parsed_module("__import__('sample')\nVALUE = 1\n")
    call = next(node for node in module.all_nodes if isinstance(node, ast.Call))
    assert source.exposes_dynamic_namespace(module, call)
    assert not source.exposes_dynamic_namespace(module, call, include_import_effects=False)
    assert stable_direct_module_bindings(module) == frozenset()
    factory_cache = module.stable_binding_cache
    assert stable_direct_module_bindings(module, include_import_effects=False) == {"VALUE"}
    assert module.stable_binding_cache is factory_cache
    assert stable_direct_module_bindings(module) == frozenset()


@pytest.mark.parametrize(
    "expression",
    ["globals()", "exec('x = 1')", "eval('x')", "__builtins__", "frame.f_globals"],
)
def test_import_source_projection_preserves_namespace_mutation_guards(expression):
    module = _parsed_module(expression + "\n")
    assert any(
        source.exposes_dynamic_namespace(
            module, node, member_surface=True, include_import_effects=False
        )
        for node in module.all_nodes
    )


@pytest.mark.parametrize(
    "decorators,kind,proven",
    [
        ("", "instance", True),
        ("@staticmethod\n", "static", True),
        ("@classmethod\n", "class", True),
        ("@property\n", "instance", True),
        ("@unknown\n", "instance", False),
        ("@staticmethod()\n", "instance", False),
        ("@staticmethod\n@classmethod\n", "class", False),
    ],
)
def test_signature_only_proof_keeps_descriptor_semantics_without_property_work(
    decorators, kind, proven
):
    body = "".join("    " + line + "\n" for line in decorators.splitlines())
    module = _parsed_module("class Owner:\n" + body + "    def run(self): pass\n")
    owner = module.tree.body[0]
    method = owner.body[0]
    descriptor = source.method_descriptor(module, method, owner)
    with patch.object(
        source, "property_bindings", side_effect=AssertionError("unused property proof")
    ):
        actual_kind, actual_proof = source._method_signature(module, method, owner)
    assert actual_kind.value == kind
    assert actual_proof is proven
    assert actual_kind == descriptor.method_kind
    assert actual_proof == descriptor.signature_decorators_proven


def test_signature_only_proof_reads_changed_aliases_on_every_call():
    module = _parsed_module(
        "from builtins import staticmethod as marker\n"
        "class Owner:\n    @marker\n    def run(): pass\n"
    )
    owner = module.tree.body[1]
    method = owner.body[0]
    module.aliases["marker"] = AliasBinding("builtins.staticmethod", ImportKind.SYMBOL)
    assert source._method_signature(module, method, owner)[1] is True
    module.aliases["marker"] = AliasBinding("opaque.marker", ImportKind.SYMBOL)
    assert source._method_signature(module, method, owner)[1] is False
    module.aliases["marker"] = AliasBinding("builtins.staticmethod", ImportKind.SYMBOL)
    assert source._method_signature(module, method, owner)[1] is True
