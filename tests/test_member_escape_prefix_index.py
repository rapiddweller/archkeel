# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Preserve dotted import-escape decisions without rescanning every escape per import."""

from pathlib import Path
from unittest.mock import patch

import pytest

from archkeel.analyzer.python.imports import _propagate_member_escapes, collect_imports
from archkeel.analyzer.python.source import parse_sources, stable_direct_module_bindings
from archkeel.ir.facts import in_scope
from archkeel.ir.reexports import resolve_reexports


def _imports(tmp_path: Path, statement: str):
    package = tmp_path / "sample"
    package.mkdir()
    (package / "user.py").write_text(statement)
    (package / "owner.py").write_text("class User: pass\n")
    parsed = parse_sources(
        tuple(sorted(package.glob("*.py"))), root=tmp_path, namespace="sample"
    ).modules
    modules = {module.module: module for module in parsed}
    imports = collect_imports(parsed, set(modules), {}, namespace="sample")
    resolve_reexports(
        imports,
        {module.module: module.all_exports for module in parsed},
        {module.module: stable_direct_module_bindings(module) for module in parsed},
    )
    return imports, modules


@pytest.mark.parametrize("namespace", [False, True])
@pytest.mark.parametrize(
    "escaped",
    [
        set(),
        {"sample"},
        {"sample.owner"},
        {"sample.owner.User"},
        {"sample.owner.User.field"},
        {"sample.ownerish.User"},
        {"sample.owner.Userish"},
        {"sample.owners"},
    ],
)
def test_escape_matches_canonical_dotted_scope(tmp_path, namespace, escaped):
    statement = (
        "import sample.owner as Visible\n"
        if namespace
        else "from sample.owner import User as Visible\n"
    )
    imports, modules = _imports(tmp_path, statement)
    origin = "sample.owner" if namespace else "sample.owner.User"
    expected = any(
        in_scope(origin, name) or (namespace and in_scope(name, origin)) for name in escaped
    )
    incoming = {name: set() for name in modules}
    _propagate_member_escapes(
        imports,
        modules,
        {"sample.owner": {"User"}},
        escaped,
        {name: set() for name in modules},
        incoming_escapes=incoming,
    )
    assert ("Visible" in incoming["sample.user"]) is expected


def test_ambiguous_origin_candidates_keep_escape_evidence(tmp_path):
    imports, modules = _imports(tmp_path, "from sample.owner import User as Visible\n")
    imports[0]["data"]["origin_definition"] = None
    imports[0]["data"]["reexport_candidates"] = ["sample.owner.User", "other.User"]
    incoming = {name: set() for name in modules}
    _propagate_member_escapes(
        imports,
        modules,
        {},
        {"sample.owner"},
        {name: set() for name in modules},
        incoming_escapes=incoming,
    )
    assert incoming["sample.user"] == {"Visible"}


def test_new_escape_origins_are_visible_on_the_next_pass(tmp_path):
    imports, modules = _imports(tmp_path, "from sample.owner import User as Visible\n")
    incoming = {name: set() for name in modules}
    escaped = set()
    _propagate_member_escapes(imports, modules, {}, escaped, incoming, incoming_escapes=incoming)
    assert incoming["sample.user"] == set()
    escaped.add("sample.owner.User")
    _propagate_member_escapes(imports, modules, {}, escaped, incoming, incoming_escapes=incoming)
    assert incoming["sample.user"] == {"Visible"}


def test_escaped_origins_are_not_rescanned_for_every_import(tmp_path):
    class CountedOrigins(set):
        visited = 0

        def __iter__(self):
            for origin in super().__iter__():
                self.visited += 1
                yield origin

    size = 128
    imports, modules = _imports(
        tmp_path, "".join(f"from sample.owner import User as value{i}\n" for i in range(size))
    )
    origins = CountedOrigins(f"unrelated.module{i}.Value" for i in range(size))
    incoming = {name: set() for name in modules}
    _propagate_member_escapes(
        imports, modules, {}, origins, {name: set() for name in modules}, incoming_escapes=incoming
    )
    assert incoming["sample.user"] == set()
    assert origins.visited <= 4 * (len(imports) + len(origins))


def test_namespace_inventory_is_scanned_once_per_import_target_and_stays_live(tmp_path):
    class CountedNamespaces(dict):
        visits = 0

        def items(self):
            for item in super().items():
                self.visits += 1
                yield item

    imports, modules = _imports(
        tmp_path, "".join(f"import sample.owner as value{i}\n" for i in range(128))
    )
    namespaces = CountedNamespaces(
        {"sample.owner": {"User"}, **{f"unrelated.module{i}": {"Value"} for i in range(127)}}
    )
    incoming = {name: set() for name in modules}
    escaped = {name: set() for name in modules}
    _propagate_member_escapes(
        imports, modules, namespaces, set(), escaped, incoming_escapes=incoming
    )
    assert incoming["sample.user"] == set()
    assert namespaces.visits == len(namespaces)
    namespaces["sample.owner"].add("Changed")
    escaped["sample.owner"].add("Changed")
    _propagate_member_escapes(
        imports, modules, namespaces, set(), escaped, incoming_escapes=incoming
    )
    assert incoming["sample.user"] == {f"value{i}" for i in range(128)}
    assert namespaces.visits == 2 * len(namespaces)


@pytest.mark.parametrize("symbol", [None, "External"])
@pytest.mark.parametrize("body", ["value = External\n", "class Local: pass\n"])
@pytest.mark.parametrize("owner_only", [False, True])
def test_opaque_owner_without_bases_needs_no_alias_closure(symbol, body, owner_only):
    from test_analyzer import _parsed_module

    from archkeel.analyzer.python import imports as collector

    module = _parsed_module("from external import External\n" + body)
    data = {
        "symbol": symbol,
        "binding": "External",
        "source_binding_unique": True,
        "origin_binding_unique": True,
        "origin_definition": "external.External",
        "reexport_chain": ["external.External"],
    }
    with patch.object(
        collector, "member_binding_closure", wraps=collector.member_binding_closure
    ) as closure:
        assert collector._opaque_import_member_escapes(
            data, module, owner_exposure_only=owner_only, unsafe_providers=frozenset()
        ) == ({"External"} if not owner_only and symbol is not None else set())
    closure.assert_not_called()


@pytest.mark.parametrize(
    "body",
    [
        "class Derived(External): pass\n",
        "class Derived(External[int]): pass\n",
        "Alias = External\nclass Derived(Alias): pass\n",
        "class Outer:\n class Derived(External): pass\n",
    ],
)
def test_opaque_import_still_transfers_direct_aliased_and_nested_bases(tmp_path, body):
    from archkeel.analyzer.python import imports as collector

    imports, modules = _imports(tmp_path, "from external import External\n" + body)
    assert collector._opaque_import_member_escapes(
        imports[0]["data"],
        modules["sample.user"],
        owner_exposure_only=True,
        unsafe_providers=frozenset(),
    ) == {"Derived"}


def test_cyclic_imports_keep_incoming_bindings_live_within_a_pass(tmp_path):
    package = tmp_path / "sample"
    package.mkdir()
    (package / "user.py").write_text("from sample.owner import User as Visible\n")
    (package / "owner.py").write_text("class User: pass\nfrom sample.user import Visible as Back\n")
    parsed = parse_sources(
        tuple(sorted(package.glob("*.py"))), root=tmp_path, namespace="sample"
    ).modules
    modules = {module.module: module for module in parsed}
    imports = collect_imports(parsed, set(modules), {}, namespace="sample")
    imports.sort(key=lambda item: item["data"]["source_module"] == "sample.owner")
    for item in imports:
        data = item["data"]
        data["origin_definition"] = f"{data['target_module']}.{data['symbol']}"
    incoming = {"sample.owner": {"User"}, "sample.user": set()}
    _propagate_member_escapes(imports, modules, {}, set(), incoming, incoming_escapes=incoming)
    assert incoming == {"sample.owner": {"User", "Back"}, "sample.user": {"Visible"}}
