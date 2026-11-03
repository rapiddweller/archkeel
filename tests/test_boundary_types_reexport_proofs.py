# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Issue #165: an ordinary-module re-export needs static export and binding proof."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from test_analyzer import _component

from archkeel.analyzer.python.collect import collect
from archkeel.analyzer.python.imports import collect_imports
from archkeel.analyzer.python.source import parse_sources, stable_direct_module_bindings
from archkeel.check.evaluation.evaluate import evaluate_source
from archkeel.cli.observe import observe
from archkeel.ir.codec import parse_contract
from archkeel.ir.facts_codec import RawRecord, decode_response, encode_response
from archkeel.ir.model import Observation
from archkeel.ir.protocol import (
    CollectionRequest,
    CollectionResponse,
    PythonSettings,
    SnapshotInput,
    SourceScope,
)
from archkeel.ir.reexports import resolve_reexports
from archkeel.ir.trace import trace_valid_violations

_OVERLOAD_GROUP = (
    "from typing import overload\n\n"
    "@overload\n"
    "def resolve_source_entity(source_entity: str | None, type_: str | None, "
    "name: str) -> str: ...\n\n"
    "@overload\n"
    "def resolve_source_entity(source_entity: str | None, type_: str | None, "
    "name: None) -> str | None: ...\n\n"
    "def resolve_source_entity(source_entity: str | None, type_: str | None, "
    "name: str | None) -> str | None:\n"
    "    return source_entity or type_ or name\n"
)
_OVERLOAD_PARTS = _OVERLOAD_GROUP.split("\n\n")


def _observe_facade(
    tmp_path: Path,
    *,
    api: str,
    init: str = "",
    intermediate: str | None = None,
    implementation: str | None = None,
    public: str = "sample.app.api:constraints",
):
    (tmp_path / "pyproject.toml").write_text('[project]\nrequires-python = ">=3.11"\n')
    (tmp_path / "contract.json").write_text(
        json.dumps(
            {
                "schema_version": "2.1.0",
                "components": [_component("app", public=[public])],
                "rules": [
                    {
                        "id": "APP-TYPES-NOT-DICT",
                        "kind": "boundary_types",
                        "source": "sample.app",
                        "rationale": "Keep the declared application boundary typed.",
                        "provenance": ["docs/architecture/sample.md"],
                        "decided_by": "architect",
                    }
                ],
            }
        )
    )
    package = tmp_path / "sample/app"
    package.mkdir(parents=True)
    (tmp_path / "sample/__init__.py").write_text("")
    (package / "__init__.py").write_text(init)
    (package / "api.py").write_text(api)
    if intermediate is not None:
        (package / "intermediate.py").write_text(intermediate)
    (package / "impl.py").write_text(
        implementation
        or "def element_constraints(first: dict, second: dict) -> object:\n    return first\n"
    )
    result = observe(
        tmp_path,
        roots=("sample",),
        namespace="sample",
        contract="contract.json",
        git_head="a" * 40,
        dirty=False,
        contract_root=tmp_path,
    )
    assert result.observation is not None, result.diagnostics
    return result.observation


@pytest.mark.parametrize(
    "api",
    [
        (
            "from .impl import element_constraints as constraints\n"
            '__all__ = ["constraints"]\n'
            "constraints = object\n"
        ),
        (
            "from .impl import element_constraints as constraints\n"
            "if enabled:\n    __all__ = ['constraints']\n"
        ),
        (
            "from .impl import element_constraints as constraints\n"
            "def configure():\n    __all__ = ['constraints']\n"
        ),
        (
            "from .impl import element_constraints as constraints\n"
            '__all__ = ["constraints"]\n'
            "__all__.append('other')\n"
        ),
        (
            "if enabled:\n"
            "    from .impl import element_constraints as constraints\n"
            '__all__ = ["constraints"]\n'
        ),
    ],
    ids=("rebound-export", "conditional-all", "local-all", "mutated-all", "conditional-import"),
)
def test_unproven_non_init_exports_leave_the_rule_unknown(tmp_path: Path, api: str) -> None:
    observation = _observe_facade(tmp_path, api=api)

    assert not observation.records("violations")
    assert any(
        item.kind in {"rule-without-subjects", "boundary_type_limit"}
        for item in observation.records("unknowns") or ()
    )


def test_init_facade_does_not_make_an_unproven_module_export_decidable(tmp_path: Path) -> None:
    observation = _observe_facade(
        tmp_path,
        api=(
            "from .impl import element_constraints as constraints\n"
            "if enabled:\n    __all__ = ['constraints']\n"
        ),
        init=('from .api import constraints\n__all__ = ["constraints"]\n'),
    )

    assert not observation.records("violations")
    assert any(
        item.kind == "rule-without-subjects" for item in observation.records("unknowns") or ()
    )


def test_source_import_hop_without_all_checks_the_original_signature(tmp_path: Path) -> None:
    observation = _observe_facade(
        tmp_path,
        public="sample.app.api:constraints",
        api=('from .intermediate import constraints\n__all__ = ["constraints"]\n'),
        intermediate="from .impl import element_constraints as constraints\n",
    )

    violations = observation.records("violations") or ()
    assert len(violations) == 3
    assert {item.data.get("position") for item in violations} == {"first", "second", "return"}
    assert {item.data.get("qualified_name") for item in violations} == {
        "sample.app.api.constraints"
    }
    assert not [
        item
        for item in observation.records("unknowns") or ()
        if "APP-TYPES-NOT-DICT" in item.rule_ids
    ]


@pytest.mark.parametrize("route", ["direct-function", "reexport", "intermediate"])
@pytest.mark.parametrize("descriptor", [False, True], ids=["function-globals", "set-name"])
@pytest.mark.parametrize("annotation", ["str", "dict"], ids=["typed-source", "broad-source"])
def test_declared_function_signature_is_separate_from_runtime_namespace_mutation(
    tmp_path: Path, route: str, descriptor: bool, annotation: str
) -> None:
    mutation = (
        "class Descriptor:\n"
        "    def __set_name__(self, owner, name):\n"
        "        owner.helper.__globals__['element_constraints'] = lambda first, second: {}\n"
        "class Holder:\n"
        "    helper = element_constraints\n"
        "    value = Descriptor()\n"
        if descriptor
        else "def mutate(fn):\n"
        "    fn.__globals__['element_constraints'] = lambda first, second: {}\n"
        "mutate(element_constraints)\n"
    )
    observation = _observe_facade(
        tmp_path,
        api=(
            f"from .{'intermediate' if route == 'intermediate' else 'impl'} import "
            "element_constraints as constraints\n__all__ = ['constraints']\n"
        ),
        intermediate=(
            "from .impl import element_constraints\n__all__ = ['element_constraints']\n"
            if route == "intermediate"
            else None
        ),
        implementation=(
            f"def element_constraints(first: {annotation}, second: {annotation}) -> {annotation}:\n"
            "    return first\n" + mutation
        ),
        public="sample.app.impl:element_constraints"
        if route == "direct-function"
        else "sample.app.api:constraints",
    )

    violations = trace_valid_violations(observation)
    assert len(violations) == (3 if annotation == "dict" else 0)
    unknowns = [
        item
        for item in observation.records("unknowns") or ()
        if "APP-TYPES-NOT-DICT" in item.rule_ids
    ]
    assert not unknowns
    [function] = [
        item
        for item in observation.records("symbols") or ()
        if item.data.get("qualified_name") == "sample.app.impl.element_constraints"
    ]
    assert function.data.get("source_member_binding_static") is False


@pytest.mark.parametrize(
    ("module", "missing"),
    [
        ("api", "source_member_binding_static"),
        ("api", "origin_member_binding_static"),
        ("api", "source_binding_unique"),
        ("api", "origin_binding_unique"),
        ("api", "module_level_import"),
        ("intermediate", "source_member_binding_static"),
        ("intermediate", "origin_member_binding_static"),
        ("intermediate", "source_binding_unique"),
        ("intermediate", "origin_binding_unique"),
        ("intermediate", "module_level_import"),
        ("impl", "source_binding_unique"),
        ("impl", "source_member_binding_static"),
        ("impl", "signature_decorators_proven"),
    ],
)
def test_reexported_function_requires_declaration_evidence_not_runtime_effect_proof(
    tmp_path: Path, module: str, missing: str
) -> None:
    observation = _observe_facade(
        tmp_path,
        api=(
            "from .intermediate import element_constraints as constraints\n"
            "__all__ = ['constraints']\n"
        ),
        intermediate="from .impl import element_constraints\n__all__ = ['element_constraints']\n",
        implementation="def element_constraints(value: str) -> str: return value\n",
    )
    assert not trace_valid_violations(observation)
    assert not [
        item
        for item in observation.records("unknowns") or ()
        if "APP-TYPES-NOT-DICT" in item.rule_ids
    ]
    request = CollectionRequest(
        SnapshotInput(str(tmp_path), "a" * 40, False),
        SourceScope(("sample",), "sample"),
        PythonSettings(),
    )
    payload = json.loads(encode_response(CollectionResponse(collect(request))))
    section = next(
        section
        for section in payload["facts"]["sections"]
        if section["name"] == ("symbols" if module == "impl" else "imports")
    )
    imported = next(
        item
        for item in section["records"]
        if (item["data"].get("module", item["data"].get("source_module")) == f"sample.app.{module}")
    )
    assert imported["data"].pop(missing) is True
    facts = decode_response(json.dumps(payload).encode()).facts
    scan = evaluate_source(
        facts,
        parse_contract(json.loads((tmp_path / "contract.json").read_text())),
        roots=("sample",),
        namespace="sample",
    )

    assert not scan.violations
    unknowns = [item for item in scan.unknowns if "APP-TYPES-NOT-DICT" in item["rule_ids"]]
    required = missing not in {"source_member_binding_static", "origin_member_binding_static"}
    assert bool(unknowns) is required
    if required:
        assert any(item["kind"] == "boundary_type_route" for item in unknowns)
        assert any(item["kind"] == "boundary_type_position" for item in unknowns)


@pytest.mark.parametrize(
    ("implementation", "proven"),
    [
        ("def element_constraints(value: str) -> str: return value\n", True),
        (_OVERLOAD_GROUP.replace("resolve_source_entity", "element_constraints"), True),
        (
            "def element_constraints(value: str) -> str: return value\n"
            "element_constraints = lambda value: {}\n",
            False,
        ),
        (
            "def wrap(fn): return lambda value: {}\n"
            "@wrap\ndef element_constraints(value: str) -> str: return value\n",
            False,
        ),
        (
            "from typing import overload\n"
            "@overload\ndef element_constraints(value: str) -> str: ...\n",
            False,
        ),
        (
            "from typing import overload\n"
            "@overload\ndef element_constraints(value: str) -> str: ...\n"
            "@overload\ndef element_constraints(value: int) -> int: ...\n",
            False,
        ),
        ("if enabled:\n    def element_constraints(value: str) -> str: return value\n", False),
        (
            "def outer():\n    def element_constraints(value: str) -> str: return value\n",
            False,
        ),
    ],
    ids=[
        "stable",
        "overloads",
        "rebound",
        "decorated",
        "one-stub",
        "no-implementation",
        "conditional",
        "nested",
    ],
)
def test_direct_function_signature_requires_its_native_binding_proof(
    tmp_path: Path, implementation: str, proven: bool
) -> None:
    observation = _observe_facade(
        tmp_path,
        api="",
        implementation=implementation,
        public="sample.app.impl:element_constraints",
    )
    assert not trace_valid_violations(observation)
    unknowns = [
        item
        for item in observation.records("unknowns") or ()
        if "APP-TYPES-NOT-DICT" in item.rule_ids
    ]
    assert bool(unknowns) is not proven


@pytest.mark.parametrize(
    "api",
    [
        (
            "from .impl import element_constraints as constraints\n"
            "def safe(value: str) -> str:\n    return value\n"
            "if enabled:\n    constraints = safe\n"
            '__all__ = ["safe", "constraints"]\n'
        ),
        (
            "if enabled:\n"
            "    from .impl import element_constraints as constraints\n"
            "def safe(value: str) -> str:\n    return value\n"
            '__all__ = ["safe", "constraints"]\n'
        ),
        (
            "from .impl import element_constraints as constraints\n"
            "def safe(value: str) -> str:\n    return value\n"
            '__all__ = ["safe", "constraints"]\n'
            "__all__.append('other')\n"
        ),
    ],
    ids=("rebound-import", "conditional-import", "mutated-all"),
)
def test_mixed_ordinary_facade_keeps_unproven_export_unknown(tmp_path: Path, api: str) -> None:
    observation = _observe_facade(
        tmp_path,
        public="sample.app.api",
        api=api,
    )

    assert not observation.records("violations")
    limit = next(
        item for item in observation.records("unknowns") or () if item.kind == "boundary_type_limit"
    )
    assert limit.data.get("undecidable_positions")


def test_ordinary_facade_does_not_follow_rebound_origin_definition(tmp_path: Path) -> None:
    observation = _observe_facade(
        tmp_path,
        api=('from .impl import element_constraints as constraints\n__all__ = ["constraints"]\n'),
        implementation=(
            "def element_constraints(first: dict, second: dict) -> object:\n"
            "    return first\n"
            "def actual(first: str, second: str) -> str:\n"
            "    return first\n"
            "element_constraints = actual\n"
        ),
    )

    assert not observation.records("violations")
    assert any(item.kind == "boundary_type_limit" for item in observation.records("unknowns") or ())


def _union_alias_reexports(
    tmp_path: Path, *, rebind: bool
) -> tuple[RawRecord, dict[str, frozenset[str]]]:
    constraints = tmp_path / "sample/app/constraints"
    constraints.mkdir(parents=True)
    (tmp_path / "sample/__init__.py").write_text("")
    (tmp_path / "sample/app/__init__.py").write_text("")
    alias_source = "Constraint = str | int\n"
    if rebind:
        alias_source += "Constraint = object\n"
    (constraints / "types.py").write_text(alias_source)
    (constraints / "__init__.py").write_text(
        "from .types import Constraint\n__all__ = ['Constraint']\n"
    )
    (tmp_path / "sample/app/api.py").write_text(
        "from .constraints import Constraint\n__all__ = ['Constraint']\n"
    )
    parsed = parse_sources(sorted(tmp_path.rglob("*.py")), root=tmp_path, namespace="sample")
    imports = collect_imports(
        parsed.modules, {module.module for module in parsed.modules}, {}, namespace="sample"
    )
    uncertain = resolve_reexports(
        imports,
        {module.module: module.all_exports for module in parsed.modules},
        {module.module: stable_direct_module_bindings(module) for module in parsed.modules},
    )
    api_import = next(
        item
        for item in imports
        if item["data"]["source_module"] == "sample.app.api"
        and item["data"]["binding"] == "Constraint"
    )
    return api_import, uncertain


def test_union_type_alias_reexport_through_package_facade_is_proven(tmp_path: Path) -> None:
    api_import, uncertain = _union_alias_reexports(tmp_path, rebind=False)

    assert api_import["data"]["reexport"] is True
    assert api_import["data"]["origin_definition"] == "sample.app.constraints.types.Constraint"
    assert not uncertain


def test_rebound_union_alias_reexport_remains_uncertain(tmp_path: Path) -> None:
    api_import, uncertain = _union_alias_reexports(tmp_path, rebind=True)

    assert api_import["data"]["reexport"] is False
    assert api_import["data"]["reexport_candidate"] is True
    assert "sample.app.constraints.Constraint" in uncertain


def _observe_declared_constraint_api(tmp_path: Path, *, alias_source: str) -> Observation:
    (tmp_path / "pyproject.toml").write_text('[project]\nrequires-python = ">=3.11"\n')
    (tmp_path / "contract.json").write_text(
        json.dumps(
            {
                "schema_version": "2.1.0",
                "components": [
                    _component(
                        "app",
                        packages=["sample.app"],
                        public=[
                            "sample.app.api:check_constraints",
                            "sample.app.api:Constraint",
                        ],
                    )
                ],
                "rules": [
                    {
                        "id": "APP-TYPES-NOT-DICT",
                        "kind": "boundary_types",
                        "source": "sample.app",
                        "rationale": "Keep declared API types resolvable.",
                        "provenance": ["docs/architecture/sample.md"],
                        "decided_by": "architect",
                    }
                ],
            }
        )
    )
    constraints = tmp_path / "sample/app/constraints"
    constraints.mkdir(parents=True)
    (tmp_path / "sample/__init__.py").write_text("")
    (tmp_path / "sample/app/__init__.py").write_text("")
    (constraints / "types.py").write_text(alias_source)
    (constraints / "__init__.py").write_text(
        "from .types import Constraint\n__all__ = ['Constraint']\n"
    )
    (tmp_path / "sample/app/api.py").write_text(
        "from .constraints import Constraint\n"
        "__all__ = ['Constraint', 'check_constraints']\n"
        "def check_constraints(value: Constraint) -> bool:\n    return True\n"
    )
    result = observe(
        tmp_path,
        roots=("sample",),
        namespace="sample",
        contract="contract.json",
        git_head="a" * 40,
        dirty=False,
        contract_root=tmp_path,
    )
    assert result.observation is not None, result.diagnostics
    return result.observation


def test_declared_union_alias_through_facade_is_decided(tmp_path: Path) -> None:
    observation = _observe_declared_constraint_api(
        tmp_path, alias_source="Constraint = str | int\n"
    )

    assert not trace_valid_violations(observation)
    assert not [
        item
        for item in observation.records("unknowns") or ()
        if "APP-TYPES-NOT-DICT" in item.rule_ids
    ]


@pytest.mark.parametrize(
    ("alias_source", "route_is_unknown"),
    [
        ("Constraint = make_constraint()\n", True),
        ("Constraint = str | make_constraint()\n", False),
        ("Constraint = str | int\nif enabled:\n    Constraint = object\n", True),
    ],
    ids=("opaque-dynamic-value", "call-inside-union", "conditional-terminal-rebind"),
)
def test_dynamic_or_conditionally_rebound_alias_stays_unknown(
    tmp_path: Path, alias_source: str, route_is_unknown: bool
) -> None:
    observation = _observe_declared_constraint_api(tmp_path, alias_source=alias_source)

    assert not trace_valid_violations(observation)
    assert any(
        item.kind == "boundary_type_limit" and "APP-TYPES-NOT-DICT" in item.rule_ids
        for item in observation.records("unknowns") or ()
    )
    if route_is_unknown:
        assert any(
            item.kind == "boundary_type_route" and "APP-TYPES-NOT-DICT" in item.rule_ids
            for item in observation.records("unknowns") or ()
        )


@pytest.mark.parametrize("multihop", [False, True], ids=["ordinary", "package-aliased"])
def test_static_overload_reexport_evaluates_every_signature(tmp_path: Path, multihop: bool) -> None:
    observation = _observe_facade(
        tmp_path,
        public="sample.app:constraints" if multihop else "sample.app.api:constraints",
        api="from .impl import resolve_source_entity as constraints\n__all__ = ['constraints']\n",
        init="from .api import constraints\n__all__ = ['constraints']\n" if multihop else "",
        implementation=_OVERLOAD_GROUP,
    )

    assert not trace_valid_violations(observation)
    assert not [
        item
        for item in observation.records("unknowns") or ()
        if "APP-TYPES-NOT-DICT" in item.rule_ids
    ]
    group = [
        item
        for item in observation.records("symbols") or ()
        if item.data.get("qualified_name") == "sample.app.impl.resolve_source_entity"
    ]
    assert len({item.id for item in group}) == 3
    signatures = [item for item in group if item.data.get("overload_signature") is True]
    assert len(signatures) == 2
    assert sum(len(item.data.get("parameters")) + 1 for item in signatures) == 8
    imported = next(
        item
        for item in observation.records("imports") or ()
        if item.data.get("source_module") == "sample.app.api"
    )
    assert imported.data.get("origin_definition") == "sample.app.impl.resolve_source_entity"
    assert imported.data.get("reexport") is True


@pytest.mark.parametrize("arm", [0, 1])
@pytest.mark.parametrize("reverse", [False, True])
@pytest.mark.parametrize("position", ["return", "source_entity"])
def test_broad_overload_reexport_retains_the_declaring_arm(
    tmp_path: Path, arm: int, reverse: bool, position: str
) -> None:
    sections = _OVERLOAD_GROUP.split("\n\n")
    declaration = sections[arm + 1]
    sections[arm + 1] = (
        declaration.replace("-> str", "-> object")
        if position == "return"
        else declaration.replace("source_entity: str | None", "source_entity: object")
    )
    if reverse:
        sections[1:3] = reversed(sections[1:3])
    observation = _observe_facade(
        tmp_path,
        api="from .impl import resolve_source_entity as constraints\n__all__ = ['constraints']\n",
        implementation="\n\n".join(sections),
    )

    violations = trace_valid_violations(observation)
    assert len(violations) == 1
    finding = violations[0]
    assert finding.data.get("position") == position
    assert finding.data.get("qualified_name") == "sample.app.api.constraints"
    symbol = next(
        item for item in observation.records("symbols") or () if item.id in finding.fact_ids
    )
    assert symbol.data.get("overload_signature") is True
    assert symbol.data.get("parameters")[-1].get("annotation") == ("str" if arm == 0 else "None")
    expected_annotation = "object | None" if position == "return" and arm == 1 else "object"
    assert finding.data.get("annotation") == expected_annotation
    assert not [
        item
        for item in observation.records("unknowns") or ()
        if "APP-TYPES-NOT-DICT" in item.rule_ids
    ]


@pytest.mark.parametrize(
    "implementation",
    [
        pytest.param(
            _OVERLOAD_GROUP.replace("@overload\n", "if enabled:\n    @overload\n    ", 1),
            id="conditional-declaration",
        ),
        pytest.param(
            _OVERLOAD_GROUP.replace(
                _OVERLOAD_PARTS[-1],
                "if enabled:\n    "
                + _OVERLOAD_PARTS[-1].replace("\n    return", "\n        return"),
            ),
            id="conditional-implementation",
        ),
        pytest.param(_OVERLOAD_GROUP + _OVERLOAD_PARTS[-1], id="duplicate-implementation"),
        pytest.param("\n\n".join(_OVERLOAD_PARTS[:-1]), id="missing-implementation"),
        pytest.param(
            "\n\n".join([_OVERLOAD_PARTS[0], _OVERLOAD_PARTS[-1], *_OVERLOAD_PARTS[1:3]]),
            id="early-implementation",
        ),
        pytest.param(
            "\n\n".join([*_OVERLOAD_PARTS[:2], "marker = 1", *_OVERLOAD_PARTS[2:]]),
            id="interleaved",
        ),
        pytest.param(_OVERLOAD_GROUP + "resolve_source_entity = str\n", id="assignment"),
        pytest.param(_OVERLOAD_GROUP + "from other import resolve_source_entity\n", id="import"),
        pytest.param(_OVERLOAD_GROUP + "del resolve_source_entity\n", id="delete"),
        pytest.param(
            _OVERLOAD_GROUP.replace(
                "from typing import overload", "def overload(function): return function"
            ),
            id="fake-decorator",
        ),
        pytest.param(_OVERLOAD_GROUP + "overload = str\n", id="rebound-decorator"),
        pytest.param(_OVERLOAD_GROUP.replace("@overload", "@overload()"), id="called-decorator"),
        pytest.param(
            _OVERLOAD_GROUP.replace("@overload", "@other\n@overload"), id="extra-decorator"
        ),
        pytest.param("from other import *\n" + _OVERLOAD_GROUP, id="star-import"),
        pytest.param(
            _OVERLOAD_GROUP + "def configure():\n    global resolve_source_entity\n",
            id="global-rebind",
        ),
        pytest.param(_OVERLOAD_GROUP + "exec('pass')\n", id="dynamic-namespace"),
        pytest.param(
            _OVERLOAD_GROUP + "resolve_source_entity.__defaults__ = ()\n", id="member-write"
        ),
        pytest.param(
            _OVERLOAD_GROUP + "setattr(resolve_source_entity, '__defaults__', ())\n",
            id="explicit-mutation",
        ),
        pytest.param(
            "from typing import TypeVar\nT = TypeVar('T')\n"
            + _OVERLOAD_GROUP.replace("source_entity: str | None", "source_entity: T"),
            id="generic",
        ),
        pytest.param(
            _OVERLOAD_GROUP + "def configure(value=(resolve_source_entity := None)): pass\n",
            id="default-rebind",
        ),
        pytest.param(
            _OVERLOAD_GROUP + "marker: (resolve_source_entity := str)\n", id="annotation-rebind"
        ),
        pytest.param(
            _OVERLOAD_GROUP.replace("-> str: ...", "-> str:\n    return 'changed'", 1),
            id="non-inert-stub",
        ),
        pytest.param(
            _OVERLOAD_GROUP.replace(
                "def resolve_source_entity", "async def resolve_source_entity", 1
            ),
            id="mixed-async",
        ),
    ],
)
def test_unproven_overload_origin_keeps_reexport_unknown(
    tmp_path: Path, implementation: str
) -> None:
    observation = _observe_facade(
        tmp_path,
        api="from .impl import resolve_source_entity as constraints\n__all__ = ['constraints']\n",
        implementation=implementation,
    )

    assert not trace_valid_violations(observation)
    assert any(
        item.kind == "boundary_type_route" and "APP-TYPES-NOT-DICT" in item.rule_ids
        for item in observation.records("unknowns") or ()
    )


@pytest.mark.parametrize(
    "implementation",
    [
        pytest.param(
            _OVERLOAD_GROUP.replace(
                "    return source_entity",
                "    resolve_source_entity = None\n    return source_entity",
            ),
            id="same-name-local",
        ),
        pytest.param(
            _OVERLOAD_GROUP.replace("def resolve_source_entity", "async def resolve_source_entity"),
            id="async",
        ),
        pytest.param(
            _OVERLOAD_GROUP.replace("from typing import overload", "import typing as t").replace(
                "@overload", "@t.overload"
            ),
            id="module-alias",
        ),
        pytest.param(
            _OVERLOAD_GROUP.replace(
                "from typing import overload", "from typing_extensions import overload as ol"
            ).replace("@overload", "@ol"),
            id="extension-alias",
        ),
        pytest.param(_OVERLOAD_GROUP.replace(": ...", ":\n    pass"), id="pass-stubs"),
        pytest.param(
            _OVERLOAD_GROUP.replace("-> str | None:\n", "-> object:\n"),
            id="broad-implementation",
        ),
    ],
)
def test_static_overload_group_variants_keep_reexport_decidable(
    tmp_path: Path, implementation: str
) -> None:
    observation = _observe_facade(
        tmp_path,
        api="from .impl import resolve_source_entity as constraints\n__all__ = ['constraints']\n",
        implementation=implementation,
    )

    assert not trace_valid_violations(observation)
    assert not [
        item
        for item in observation.records("unknowns") or ()
        if "APP-TYPES-NOT-DICT" in item.rule_ids
    ]


def test_static_overload_route_does_not_prove_an_unsupported_annotation(tmp_path: Path) -> None:
    observation = _observe_facade(
        tmp_path,
        api="from .impl import resolve_source_entity as constraints\n__all__ = ['constraints']\n",
        implementation=_OVERLOAD_GROUP.replace("-> str: ...", "-> Missing: ...", 1),
    )
    unknowns = [
        item
        for item in observation.records("unknowns") or ()
        if "APP-TYPES-NOT-DICT" in item.rule_ids
    ]
    assert any(
        item.kind == "boundary_type_position" and item.data.get("annotation") == "Missing"
        for item in unknowns
    )
    assert not any(item.kind == "boundary_type_route" for item in unknowns)


@pytest.mark.requires_python(12)
def test_generic_overload_group_remains_outside_static_origin_proof(tmp_path: Path) -> None:
    observation = _observe_facade(
        tmp_path,
        api="from .impl import resolve_source_entity as constraints\n__all__ = ['constraints']\n",
        implementation=_OVERLOAD_GROUP.replace(
            "def resolve_source_entity(", "def resolve_source_entity[T]("
        ),
    )
    assert any(
        item.kind == "boundary_type_route" and "APP-TYPES-NOT-DICT" in item.rule_ids
        for item in observation.records("unknowns") or ()
    )


@pytest.mark.parametrize(
    ("api", "intermediate"),
    [
        (
            "from .impl import resolve_source_entity as constraints\n"
            "if enabled:\n    __all__ = ['constraints']\n",
            None,
        ),
        (
            "from .impl import resolve_source_entity as constraints\n"
            "__all__ = ['constraints']\n__all__.append('other')\n",
            None,
        ),
        (
            "from .intermediate import constraints\n__all__ = ['constraints']\n",
            "from .impl import resolve_source_entity as constraints\n"
            "if enabled:\n    constraints = str\n__all__ = ['constraints']\n",
        ),
        (
            "from .impl import resolve_source_entity as constraints\n"
            "from .intermediate import constraints\n__all__ = ['constraints']\n",
            "def constraints(value: str) -> str: return value\n__all__ = ['constraints']\n",
        ),
    ],
    ids=["conditional-export", "mutated-export", "intermediate-rebind", "ambiguous-import"],
)
def test_static_overload_origin_does_not_prove_an_uncertain_route(
    tmp_path: Path, api: str, intermediate: str | None
) -> None:
    observation = _observe_facade(
        tmp_path, api=api, intermediate=intermediate, implementation=_OVERLOAD_GROUP
    )
    assert not trace_valid_violations(observation)
    assert any(
        "APP-TYPES-NOT-DICT" in item.rule_ids for item in observation.records("unknowns") or ()
    )
