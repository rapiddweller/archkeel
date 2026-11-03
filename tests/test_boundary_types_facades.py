# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""boundary_types follows facade re-exports and owned DTO fields."""

from __future__ import annotations

import ast
import json
from collections import Counter
from pathlib import Path

import pytest
from test_analyzer import _component, _observe
from test_boundary_type_recursive_aliases import _native_case
from test_inside_publication import _child, _inside, _rule, _write_project

from archkeel.check.evaluation.boundary_types import _declared_facade_positions
from archkeel.check.ports import ScanConfig
from archkeel.check.validation import inside_diagnostics
from archkeel.check.validation.public_api import interface_diagnostics
from archkeel.ir.codec import parse_contract
from archkeel.ir.facts_codec import raw_record
from archkeel.ir.trace import trace_valid_violations


@pytest.mark.parametrize("scoped", [False, True], ids=["root", "mounted"])
def test_facade_resolution_reuses_only_one_invocations_native_context(
    tmp_path, monkeypatch, scoped
):
    from archkeel.analyzer.python.imports import collect_imports
    from archkeel.analyzer.python.source import parse_sources
    from archkeel.analyzer.python.symbols import collect_symbols
    from archkeel.analyzer.python.type_shapes import collect_type_shapes, symbol_type_expressions
    from archkeel.check.evaluation import boundary_types

    package = tmp_path / "sample"
    package.mkdir()
    source = (
        "class Other: pass\nclass Payload:\n    child: Other\n"
        "def one(value: Payload) -> Payload: return value\n"
        "def two(value: Other) -> Other: return value\n"
        "def missing(value: Missing) -> Missing: return value\n"
        "def broad(value: object) -> object: return value\n"
    )
    for name in ("a", "b"):
        (package / f"{name}.py").write_text(source)
    modules = parse_sources(sorted(package.glob("*.py")), root=tmp_path, namespace="sample").modules
    exports = {module.module: frozenset() for module in modules}
    imports = collect_imports(modules, set(exports), {}, namespace="sample")
    symbols, _, _ = collect_symbols(modules, {})
    shapes = collect_type_shapes(symbol_type_expressions(symbols))
    original = boundary_types._boundary_type_verdict
    calls = Counter()
    verdicts = {}
    depth = 0

    def verdict(*args, **kwargs):
        nonlocal depth
        top_level = depth == 0 and set(kwargs) == {"type_shapes"}
        depth += 1
        try:
            result = original(*args, **kwargs)
        finally:
            depth -= 1
        if top_level:
            key = (args[1], args[0])
            calls[key] += 1
            verdicts[key] = result
        return result

    monkeypatch.setattr(boundary_types, "_boundary_type_verdict", verdict)
    for exposed in (True, False, True):
        names = ["one", "two", "missing", "broad"] + (["Payload", "Other"] if exposed else [])
        contract = parse_contract(
            {
                **_contract(),
                "components": [
                    _component(
                        "app",
                        packages=["sample"],
                        public=[f"{module}:{name}" for module in exports for name in names],
                    )
                ],
            }
        )
        kwargs = (
            {
                "source_modules": frozenset(exports),
                "scope_id": "app:api",
                "ancestor_contracts": (contract,),
            }
            if scoped
            else {}
        )
        calls.clear()
        result = boundary_types.facade_signature_types(
            symbols, imports, contract, exports, type_shapes=shapes, **kwargs
        )
        reached = {
            row["data"]["qualified_name"]: (
                row["data"]
                .get("facade_types_by_mount", {})
                .get("app:api", {})
                .get(row["data"]["module"], [])
                if scoped
                else row["data"].get("facade_types", [])
            )
            for row in result
            if row["kind"] == "function"
        }
        for module in exports:
            for annotation in ("Payload", "Other", "Missing", "object"):
                assert calls[module, annotation] == 1
            assert reached[f"{module}.one"] == ([f"{module}.Other"] if exposed else []) + [
                f"{module}.Payload"
            ]
            assert reached[f"{module}.two"] == [f"{module}.Other"]
            assert reached[f"{module}.missing"] == reached[f"{module}.broad"] == []
            assert verdicts[module, "Missing"].undecidable is not None
            assert verdicts[module, "object"].violation is not None


def _contract(*public: str) -> dict[str, object]:
    return {
        "schema_version": "2.1.0",
        "components": [_component("app", public=list(public))],
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


def _write_app(root: Path, *, init: str, impl: str) -> None:
    (root / "contract.json").write_text(json.dumps(_contract("sample.app:run")))
    (root / "sample/app").mkdir(parents=True)
    (root / "sample/app/__init__.py").write_text(init)
    (root / "sample/app/impl.py").write_text(impl)


def _native_function_facade(tmp_path: Path, source: str):
    facts = _native_case(tmp_path, source)
    [function] = [
        raw_record(row)
        for section in facts.sections
        if section.name == "symbols"
        for row in section.records
        if row.data.get("name") == "options"
    ]
    contract = parse_contract(
        {
            **_contract(),
            "components": [_component("app", packages=["sample"], public=["sample.values"])],
        }
    )
    return function, contract


@pytest.mark.parametrize("actual_source", [False, True])
def test_native_local_function_is_not_rebased_to_module_facade(
    tmp_path: Path, actual_source: bool
) -> None:
    source = (
        "def _report_filters():\n"
        "    def options(values: tuple[str, ...] | list[str]) -> str:\n"
        "        return ''.join(values)\n"
        "    return options(['one'])\n"
    )
    if actual_source:
        html = (Path(__file__).parents[1] / "src/archkeel/render/html.py").read_text()
        [outer] = [
            node
            for node in ast.parse(html).body
            if isinstance(node, ast.FunctionDef) and node.name == "_report_filters"
        ]
        source = ast.get_source_segment(html, outer)
        assert source is not None
    function, contract = _native_function_facade(
        tmp_path,
        source,
    )
    assert function["data"]["namespace_bound"] is False
    assert function["data"].get("source_binding_unique") is True
    assert _declared_facade_positions(function, contract, {}) is None


@pytest.mark.parametrize(
    "source",
    [
        "def _factory():\n    global options\n"
        "    def options(value: dict) -> object: return value\n",
        "def _factory():\n    options = None\n"
        "    def options(value: dict) -> object: return value\n",
        "def _factory():\n    if enabled:\n"
        "        def options(value: dict) -> object: return value\n",
        "if enabled:\n    def options(value: dict) -> object: return value\n",
        "def identity(value): return value\n@identity\n"
        "def options(value: dict) -> object: return value\n",
        "__all__ = ['options']\ndef _factory():\n"
        "    def options(value: dict) -> object: return value\n",
        "def _outer():\n    options = None\n    def _factory():\n"
        "        nonlocal options\n"
        "        def options(value: dict) -> object: return value\n",
    ],
    ids=[
        "global",
        "rebound",
        "conditional-local",
        "conditional-module",
        "decorated",
        "all",
        "nonlocal",
    ],
)
def test_native_uncertain_and_published_function_positions_remain(tmp_path, source):
    function, contract = _native_function_facade(tmp_path, source)
    found = _declared_facade_positions(function, contract, {})
    assert found is not None and len(found[2]) == 2
    assert all(entry[3] for entry in found[4])


@pytest.mark.parametrize(
    ("field", "proof"),
    [
        ("source_binding_unique", None),
        ("source_binding_unique", False),
        ("namespace_bound", None),
        ("lexical_parent_id", None),
        ("parent", None),
        ("qualified_name", "sample.values.other.options"),
    ],
)
def test_local_function_without_positive_binding_proof_remains(tmp_path, field, proof):
    function, contract = _native_function_facade(
        tmp_path, "def _factory():\n    def options(value: dict) -> object: return value\n"
    )
    if proof is None:
        function["data"].pop(field, None)
    else:
        function["data"][field] = proof
    assert _declared_facade_positions(function, contract, {}) is not None


def test_explicit_module_target_does_not_publish_a_lexical_local(tmp_path):
    function, _ = _native_function_facade(
        tmp_path, "def _factory():\n    def options(value: dict) -> object: return value\n"
    )
    contract = parse_contract(
        {
            **_contract(),
            "components": [
                _component("app", packages=["sample"], public=["sample.values:options"])
            ],
        }
    )
    found = _declared_facade_positions(function, contract, {})
    assert found is not None and len(found[2]) == 2
    assert all(entry[3] for entry in found[4])
    function["data"]["signature_decorators_proven"] = True
    found = _declared_facade_positions(function, contract, {})
    assert found is not None and all(entry[3] for entry in found[4])
    del function["data"]["namespace_bound"]
    found = _declared_facade_positions(function, contract, {})
    assert found is not None and all(entry[3] for entry in found[4])


@pytest.mark.parametrize("scoped", [False, True], ids=["root", "mounted"])
@pytest.mark.parametrize("binding", ["plain", "decorated", "namespace-escape"])
def test_function_type_usage_follows_declaration_proof(
    tmp_path: Path, scoped: bool, binding: str
) -> None:
    module = "sample.core.api"
    public = [f"{module}:{name}" for name in ("make", "Payload", "Noise")]
    rules = [_rule("INTERFACE", "interface_boundary")]
    _write_project(
        tmp_path,
        components=[
            _component("core", packages=["sample.core"], public=[] if scoped else public)
            | ({"inside": "core.json"} if scoped else {}),
            _component("client", packages=["sample.client"]),
        ],
        rules=[] if scoped else rules,
        insides={
            "core.json": _inside(
                [_child("api", module, public=public), _child("client", "sample.core.client")],
                rules,
            )
        }
        if scoped
        else {},
        files={
            "sample/core/api.py": (
                "class Payload: pass\nclass Noise: pass\n"
                "def identity(function): return function\n"
                + ("@identity\n" if binding == "decorated" else "")
                + "def make(value: Payload) -> Payload: return value\n"
                + ("ns = make.__globals__\n" if binding == "namespace-escape" else "")
                + "def internal(value: Noise) -> Noise: return value\n"
            ),
            "sample/core/client.py" if scoped else "sample/client.py": (
                "from sample.core.api import make\n"
            ),
        },
    )
    result = _observe(tmp_path)
    assert result.observation is not None, result.diagnostics
    contract = parse_contract(json.loads((tmp_path / "contract.json").read_bytes()))
    diagnostics = (
        inside_diagnostics(
            tmp_path,
            contract,
            ScanConfig(("sample",), "sample", "contract.json", "0" * 64),
            observation=result.observation,
        )
        if scoped
        else interface_diagnostics(contract, result.observation)
    )
    assert [(item.code, item.subject) for item in diagnostics] == (
        ([("interface.usage_unknown", f"{module}:Payload")] if binding == "decorated" else [])
        + [("interface.unused", f"{module}:Noise")]
    )
    make = next(
        item
        for item in result.observation.records("symbols") or ()
        if item.data.get("qualified_name") == f"{module}.make"
    )
    if scoped:
        positive = make.data.get("facade_types_by_mount", {}).get("core", {}).get(module, ())
        candidates = (
            make.data.get("facade_type_candidates_by_mount", {}).get("core", {}).get(module, ())
        )
        assert not make.data.get("facade_type_candidates_by_publisher")
    else:
        positive = make.data.get("facade_types", ())
        candidates = make.data.get("facade_type_candidates_by_publisher", {}).get(module, ())
    assert positive == (() if binding == "decorated" else (f"{module}.Payload",))
    assert candidates == ((f"{module}.Payload",) if binding == "decorated" else ())
    if binding == "namespace-escape":
        assert make.data.get("source_member_binding_static") is False


@pytest.mark.parametrize("binding", ["decorated", "namespace-escape"])
def test_function_type_usage_stays_with_its_publisher_mount(tmp_path: Path, binding: str) -> None:
    _write_project(
        tmp_path,
        components=[
            _component(name, packages=[f"sample.{name}"], public=[]) | {"inside": f"{name}.json"}
            for name in ("left", "right")
        ],
        rules=[],
        insides={
            f"{name}.json": _inside(
                [
                    _child(
                        "api",
                        f"sample.{name}.api",
                        public=[f"sample.{name}.api:{entry}" for entry in ("make", "Payload")],
                    ),
                    _child("client", f"sample.{name}.client"),
                ],
                [_rule("INTERFACE", "interface_boundary")],
            )
            for name in ("left", "right")
        },
        files={
            "sample/left/api.py": (
                "class Payload: pass\ndef identity(function): return function\n"
                + ("@identity\n" if binding == "decorated" else "")
                + "def make(value: Payload) -> Payload: return value\n"
                + ("ns = make.__globals__\n" if binding == "namespace-escape" else "")
            ),
            "sample/right/api.py": (
                "class Payload: pass\ndef make(value: str) -> str: return value\n"
            ),
            "sample/left/client.py": "from sample.left.api import make\n",
            "sample/right/client.py": "from sample.right.api import make\n",
        },
    )
    result = _observe(tmp_path)
    assert result.observation is not None, result.diagnostics
    diagnostics = inside_diagnostics(
        tmp_path,
        parse_contract(json.loads((tmp_path / "contract.json").read_bytes())),
        ScanConfig(("sample",), "sample", "contract.json", "0" * 64),
        observation=result.observation,
    )
    assert [(item.code, item.subject) for item in diagnostics] == (
        [("interface.usage_unknown", "sample.left.api:Payload")] if binding == "decorated" else []
    ) + [("interface.unused", "sample.right.api:Payload")]


def test_boundary_types_checks_a_function_at_its_reexport_definition(
    tmp_path: Path,
) -> None:
    """A package facade owns the subject, while the definition supplies its signature."""
    _write_app(
        tmp_path,
        init="from .impl import run\n",
        impl="def run(value: dict) -> str:\n    return str(value)\n",
    )

    result = _observe(tmp_path)

    assert result.observation is not None
    [violation] = trace_valid_violations(result.observation)
    assert violation.subjects == ("sample.app", "sample.app.run")
    assert violation.data.get("module") == "sample.app"
    assert violation.data.get("qualified_name") == "sample.app.run"


@pytest.mark.parametrize(
    ("facade", "public_type", "field_type", "expected_violations"),
    [
        ("sample.app", "Request", "str", 0),
        ("sample.app.api", "Request", "str", 0),
        ("sample.app.api", "PublicRequest", "str", 0),
        ("sample.app.api", None, "str", 1),
        ("sample.app.api", "Request", "dict", 1),
    ],
    ids=("package", "ordinary", "renamed-type", "private-type", "broad-field"),
)
def test_reexported_type_uses_its_owners_declared_public_facade(
    tmp_path: Path,
    facade: str,
    public_type: str | None,
    field_type: str,
    expected_violations: int,
) -> None:
    package = tmp_path / "sample/app"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("")
    (package / "impl.py").write_text(
        f"class Request:\n    metadata: {field_type}\n\n"
        "def run() -> Request:\n    return Request()\n"
    )
    names = ["run"]
    imports = "from .impl import run\n"
    if public_type is not None:
        names.append(public_type)
        imports += f"from .impl import Request as {public_type}\n"
    path = package / ("__init__.py" if facade == "sample.app" else "api.py")
    path.write_text(imports + f"__all__ = {names!r}\n")
    (tmp_path / "contract.json").write_text(json.dumps(_contract(facade)))

    result = _observe(tmp_path)

    assert result.observation is not None, result.diagnostics
    findings = trace_valid_violations(result.observation)
    assert len(findings) == expected_violations
    if expected_violations:
        expected_reason = "does not declare" if public_type is None else "metadata"
        assert expected_reason in findings[0].title
    else:
        assert not [item for item in result.observation.records("unknowns") or () if item.rule_ids]


def test_foreign_component_facade_does_not_publish_an_owned_type(tmp_path: Path) -> None:
    (tmp_path / "contract.json").write_text(
        json.dumps(
            {
                "schema_version": "2.1.0",
                "components": [
                    _component("app", packages=["sample.app"], public=["sample.app.api"]),
                    _component("owner", packages=["sample.owner"], public=[]),
                ],
                "rules": _contract("sample.app.api:run")["rules"],
            }
        )
    )
    package = tmp_path / "sample/app"
    package.mkdir(parents=True)
    (package / "api.py").write_text(
        "from sample.owner.impl import Request\n"
        "__all__ = ['run', 'Request']\n"
        "def run() -> Request:\n    return Request()\n"
    )
    owner = tmp_path / "sample/owner"
    owner.mkdir(parents=True)
    (owner / "impl.py").write_text("class Request:\n    metadata: str\n")

    result = _observe(tmp_path)

    assert result.observation is not None, result.diagnostics
    [finding] = trace_valid_violations(result.observation)
    assert "which owner does not declare" in finding.title


def test_unproven_public_route_is_unknown_without_hiding_private_type_violation(
    tmp_path: Path,
) -> None:
    (tmp_path / "contract.json").write_text(
        json.dumps(
            _contract("sample.app.api:run", "sample.app.api:private", "sample.app.api:Payload")
        )
    )
    package = tmp_path / "sample/app"
    package.mkdir(parents=True)
    (package / "api.py").write_text(
        "from .middle import Payload\n"
        "from .impl import Private\n"
        "__all__ = ['run', 'Payload', 'private']\n"
        "def run() -> Payload:\n    return Payload()\n"
        "def private() -> Private:\n    return Private()\n"
    )
    (package / "middle.py").write_text(
        "class Payload:\n    metadata: str\nif enabled:\n    Payload = object\n"
    )
    (package / "impl.py").write_text("class Private:\n    metadata: str\n")

    result = _observe(tmp_path)

    assert result.observation is not None, result.diagnostics
    findings = trace_valid_violations(result.observation)
    assert len(findings) == 1
    assert findings[0].subjects == ("sample.app.api", "sample.app.api.private")
    assert any(
        item.kind == "boundary_type_position"
        and "APP-TYPES-NOT-DICT" in item.rule_ids
        and item.evidence_class.value == "UNKNOWN"
        for item in result.observation.records("unknowns") or ()
    )


@pytest.mark.parametrize("annotation,violations", [("str", 0), ("dict", 1)])
def test_public_type_route_follows_source_import_without_all(
    tmp_path: Path, annotation, violations
) -> None:
    (tmp_path / "contract.json").write_text(
        json.dumps(_contract("sample.app.api:run", "sample.app.api:PublicPayload"))
    )
    package = tmp_path / "sample/app"
    package.mkdir(parents=True)
    (package / "api.py").write_text(
        "from .middle import Payload as PublicPayload\n"
        "__all__ = ['run', 'PublicPayload']\n"
        "def run() -> PublicPayload:\n    return PublicPayload()\n"
    )
    (package / "middle.py").write_text("from .impl import Payload\n")
    (package / "impl.py").write_text(f"class Payload:\n    metadata: {annotation}\n")

    result = _observe(tmp_path)

    assert result.observation is not None, result.diagnostics
    assert len(trace_valid_violations(result.observation)) == violations
    assert not [
        item
        for item in result.observation.records("unknowns") or ()
        if "APP-TYPES-NOT-DICT" in item.rule_ids
    ]


def test_boundary_types_uses_the_facade_in_the_rule_scope_when_reexported_twice(
    tmp_path: Path,
) -> None:
    """A second declared facade must not hide the occurrence in this rule's source."""
    (tmp_path / "contract.json").write_text(
        json.dumps(
            {
                "schema_version": "2.1.0",
                "components": [
                    {
                        **_component("app", public=["sample.a:run", "sample.app:run"]),
                        "packages": ["sample"],
                    }
                ],
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
    (tmp_path / "sample/a").mkdir(parents=True)
    (tmp_path / "sample/app").mkdir(parents=True)
    (tmp_path / "sample/a/__init__.py").write_text("from ..impl import run\n")
    (tmp_path / "sample/app/__init__.py").write_text("from ..impl import run\n")
    (tmp_path / "sample/impl.py").write_text(
        "def run(value: dict) -> str:\n    return str(value)\n"
    )

    result = _observe(tmp_path)

    assert result.observation is not None
    [violation] = trace_valid_violations(result.observation)
    assert violation.subjects == ("sample.app", "sample.app.run")


@pytest.mark.parametrize(
    "init",
    [
        "from .impl_a import run\nfrom .impl_b import run\n",
        "from .impl_b import run\nfrom .impl_a import run\n",
    ],
)
def test_boundary_types_marks_two_reexport_origins_unknown_in_either_order(
    tmp_path: Path, init: str
) -> None:
    """Two typed origins for one facade binding are ambiguous, independent of import order."""
    (tmp_path / "contract.json").write_text(json.dumps(_contract("sample.app:run")))
    (tmp_path / "sample/app").mkdir(parents=True)
    (tmp_path / "sample/app/__init__.py").write_text(init)
    for name in ("impl_a", "impl_b"):
        (tmp_path / f"sample/app/{name}.py").write_text(
            "def run(value: dict) -> str:\n    return str(value)\n"
        )

    result = _observe(tmp_path)

    assert result.observation is not None
    assert trace_valid_violations(result.observation) == ()
    [limit] = [
        item
        for item in result.observation.records("unknowns") or ()
        if item.kind == "boundary_type_limit"
    ]
    assert limit.data.get("ambiguous_facade") == 4


def test_boundary_types_accepts_two_aliases_of_one_reexport_origin(
    tmp_path: Path,
) -> None:
    """Two facade aliases of one definition are decidable, not ambiguous."""
    (tmp_path / "contract.json").write_text(
        json.dumps(
            {
                "schema_version": "2.1.0",
                "components": [
                    _component(
                        "app",
                        public=["sample.app:run", "sample.app:run_alias"],
                    )
                ],
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
    (tmp_path / "sample/app").mkdir(parents=True)
    (tmp_path / "sample/app/__init__.py").write_text(
        "from .impl import run\n"
        "from .impl import run as run_alias\n"
        "\n"
        '__all__ = ["run", "run_alias"]\n'
    )
    (tmp_path / "sample/app/impl.py").write_text(
        "def run(value: dict) -> str:\n    return str(value)\n"
    )

    result = _observe(tmp_path)

    assert result.observation is not None
    [violation] = trace_valid_violations(result.observation)
    assert violation.rule_ids == ("APP-TYPES-NOT-DICT",)
    assert violation.subjects == ("sample.app", "sample.app.run")
    assert not [
        item
        for item in result.observation.records("unknowns") or ()
        if item.kind == "boundary_type_limit" and item.data.get("ambiguous_facade")
    ]


def test_boundary_types_checks_direct_fields_of_a_reexported_model(
    tmp_path: Path,
) -> None:
    _write_app(
        tmp_path,
        init="from .impl import Request, run\n",
        impl=(
            "class Request:\n"
            "    metadata: dict\n\n\n"
            "def run(value: Request) -> str:\n"
            "    return str(value)\n"
        ),
    )
    (tmp_path / "contract.json").write_text(
        json.dumps(_contract("sample.app:run", "sample.app.impl:Request"))
    )

    result = _observe(tmp_path)

    assert result.observation is not None
    [violation] = trace_valid_violations(result.observation)
    assert violation.subjects == ("sample.app", "sample.app.run")
    assert "field metadata" in violation.title


def test_boundary_types_checks_fields_of_a_nested_model(
    tmp_path: Path,
) -> None:
    _write_app(
        tmp_path,
        init="from .impl import Inner, Request, run\n",
        impl=(
            "class Inner:\n"
            "    metadata: dict\n\n\n"
            "class Request:\n"
            "    left: Inner\n"
            "    right: Inner\n\n\n"
            "def run(value: Request) -> str:\n"
            "    return str(value)\n"
        ),
    )
    (tmp_path / "contract.json").write_text(
        json.dumps(
            _contract(
                "sample.app:run",
                "sample.app.impl:Request",
                "sample.app.impl:Inner",
            )
        )
    )

    result = _observe(tmp_path)

    assert result.observation is not None
    violations = trace_valid_violations(result.observation)
    assert {item.data.get("path") for item in violations} == {
        "value.left.metadata",
        "value.right.metadata",
    }
    assert all("field metadata" in item.title for item in violations)
    assert all(item.data.get("nested_annotation") == "dict" for item in violations)


def test_boundary_types_keeps_violations_from_each_union_member(tmp_path: Path) -> None:
    _write_app(
        tmp_path,
        init="from .impl import Request, run\n",
        impl=(
            "class Left:\n"
            "    metadata: dict\n\n\n"
            "class Right:\n"
            "    details: object\n\n\n"
            "class Request:\n"
            "    payload: Left | Right | dict\n\n\n"
            "def run(value: Request) -> str:\n"
            "    return str(value)\n"
        ),
    )
    (tmp_path / "contract.json").write_text(
        json.dumps(
            _contract(
                "sample.app:run",
                "sample.app.impl:Request",
                "sample.app.impl:Left",
                "sample.app.impl:Right",
            )
        )
    )

    result = _observe(tmp_path)

    assert result.observation is not None
    violations = trace_valid_violations(result.observation)
    assert {item.data.get("path") for item in violations} == {
        "value.payload",
        "value.payload.metadata",
        "value.payload.details",
    }
    assert (
        next(item for item in violations if item.data.get("path") == "value.payload").data.get(
            "nested_annotation"
        )
        == "dict"
    )


def test_boundary_types_reports_unknown_for_an_unresolved_model_field(
    tmp_path: Path,
) -> None:
    _write_app(
        tmp_path,
        init="from .impl import Request, run\n",
        impl=(
            "class Request:\n"
            "    value: Missing\n\n\n"
            "def run(value: Request) -> str:\n"
            "    return str(value)\n"
        ),
    )
    (tmp_path / "contract.json").write_text(
        json.dumps(_contract("sample.app:run", "sample.app.impl:Request"))
    )

    result = _observe(tmp_path)

    assert result.observation is not None
    assert trace_valid_violations(result.observation) == ()
    [limit] = [
        item
        for item in result.observation.records("unknowns") or ()
        if item.kind == "boundary_type_limit"
    ]
    assert limit.data.get("unresolved_name") == 1
