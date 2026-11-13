# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Every public re-export hop needs proof; private aliases cannot change that proof."""

import json
from pathlib import Path

import pytest
from test_analyzer import _component, _parsed_module
from test_boundary_types_non_init_facades import _write_app

from archkeel.cli.observe import observe


@pytest.mark.parametrize(
    "declaration,proven",
    [
        ("Table: Final[dict[str, Choice]] = {'a': Choice()}\n", True),
        ("Table = {'a': Choice()}\n", False),
        ("Table: Final[dict[str, Choice]] = {}\nTable = {}\n", False),
        ("if enabled:\n    Table: Final[dict[str, Choice]] = {}\n", False),
        ("Table: Final[dict[str, Choice]] = {}\nfrom missing import *\n", False),
    ],
    ids=["annotated", "unannotated", "rebound", "conditional", "star"],
)
def test_annotated_value_route_proves_declaration_without_runtime_shape(
    tmp_path, declaration, proven
):
    _write_app(
        tmp_path,
        public=["sample.app.api"],
        init="",
        api="from .impl import Table\n__all__ = ['Table']\n" + SAFE,
        implementation="from typing import Final\nclass Choice: pass\n" + declaration,
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
    unknowns = [
        row
        for row in result.observation.records("unknowns") or ()
        if row.kind == "boundary_type_route"
    ]
    assert bool(unknowns) is not proven
    if proven:
        [symbol] = [
            row
            for row in result.observation.records("symbols") or ()
            if row.data.get("qualified_name") == "sample.app.impl.Table"
        ]
        assert symbol.kind == "dynamic_binding"
        assert symbol.data.get("source_binding_unique") is True
        assert symbol.data.get("annotation") == "Final[dict[str, Choice]]"
        assert symbol.data.get("constant") is None
        assert symbol.data.get("symbol_category") is None


@pytest.mark.parametrize(
    "bridge,proven",
    [
        ("from .impl import run\n", True),
        ("from .impl import run as run\n", True),
        ("from .impl import run\nrun = object\n", False),
        ("if enabled:\n    from .impl import run\n", False),
        ("from .impl import run\nfrom missing import *\n", False),
        ("from .api import run\n", False),
        ("def configure():\n    from .impl import run\n", False),
        ("from .missing import run\n", False),
    ],
    ids=["plain", "same-name", "rebound", "conditional", "star", "cycle", "local", "missing"],
)
def test_source_import_hops_do_not_require_export_promotion(bridge, proven):
    from archkeel.analyzer.python.imports import collect_imports, resolve_reexports
    from archkeel.analyzer.python.source import stable_direct_module_bindings
    from archkeel.analyzer.python.symbols import collect_symbols

    from archkeel.check.evaluation.boundary_types import _public_alias_route_has_unproven_hop

    modules = [
        _parsed_module(
            "def run(value: str) -> str: return value\n", "sample.impl", rel_path="sample/impl.py"
        ),
        _parsed_module(bridge, "sample.bridge", rel_path="sample/bridge.py"),
        _parsed_module(
            "from .bridge import run\n__all__ = ['run']\n", "sample.api", rel_path="sample/api.py"
        ),
    ]
    imports = collect_imports(modules, {m.module for m in modules}, {}, namespace="sample")
    resolve_reexports(imports, {m.module: m.all_exports for m in modules}, modules)
    symbols, _, _ = collect_symbols(modules, {})
    publisher = next(item for item in imports if item["data"]["source_module"] == "sample.api")
    route = ("sample.api.run", *publisher["data"]["reexport_chain"])
    stable = {m.module: stable_direct_module_bindings(m) for m in modules}
    definitions = {("sample.impl", "run"): symbols}
    bindings = {}
    for item in imports:
        data = item["data"]
        bindings.setdefault((data["source_module"], data["binding"]), []).append(item)
    assert all(
        not item["data"]["reexport"]
        for item in imports
        if item["data"]["source_module"] == "sample.bridge"
    )
    if proven:
        assert route == ("sample.api.run", "sample.bridge.run", "sample.impl.run")
    assert (
        _public_alias_route_has_unproven_hop(
            route, definitions, bindings, set(stable), stable, type_shapes={}
        )
        is not proven
    )


SAFE = "\ndef safe(value: str) -> str:\n    return value\n"
EXPORT = '__all__ = ["constraints", "safe"]\n'


@pytest.mark.parametrize("condition", ["TYPE_CHECKING", "enabled"])
def test_unproven_ordinary_import_is_not_promoted_to_reexport_candidate(condition):
    from archkeel.analyzer.python.imports import collect_imports, resolve_reexports

    modules = [
        _parsed_module("class Projection: pass\n", "sample.projection"),
        _parsed_module(
            f"from typing import TYPE_CHECKING\nif {condition}:\n"
            "    from .projection import Projection\n",
            "sample.model",
        ),
    ]
    imports = collect_imports(modules, {m.module for m in modules}, {}, namespace="sample")
    uncertain, _ = resolve_reexports(imports, {m.module: m.all_exports for m in modules}, modules)
    [binding] = [item["data"] for item in imports if item["data"]["binding"] == "Projection"]
    assert binding["module_level_import"] is True
    assert binding["source_binding_unique"] is False
    assert binding["reexport"] is False
    assert binding["reexport_candidate"] is False
    assert "sample.model.Projection" not in uncertain


@pytest.mark.parametrize(
    ("api", "middle", "package", "proven", "typed_origin"),
    [
        (
            "from .middle import constraints\n" + EXPORT + SAFE,
            'from .impl import element_constraints as constraints\n__all__ = ["constraints"]\n',
            False,
            True,
            False,
        ),
        (
            "from .middle import constraints\n" + EXPORT + SAFE,
            'from ..impl import element_constraints as constraints\n__all__ = ["constraints"]\n',
            True,
            True,
            False,
        ),
        (
            "from .middle import constraints\n" + EXPORT + SAFE,
            "from .impl import element_constraints as constraints\n"
            '__all__ = ["constraints"]\n__all__.append("other")\n',
            False,
            False,
            False,
        ),
        (
            "from .middle import constraints\n" + EXPORT + SAFE,
            'from ..impl import element_constraints as constraints\n__all__ = ["constraints"]\n'
            + SAFE
            + "constraints = safe\n",
            True,
            False,
            False,
        ),
        (
            "from .impl import element_constraints as constraints\n" + EXPORT + SAFE,
            "from .impl import element_constraints as constraints\n"
            '__all__ = ["constraints"]\nconstraints = object\n',
            False,
            True,
            False,
        ),
        (
            "from .impl import element_constraints as constraints\n"
            + EXPORT
            + SAFE
            + "constraints = safe\n",
            "",
            False,
            False,
            True,
        ),
    ],
    ids=(
        "ordinary-control",
        "init-control",
        "mutated-intermediate",
        "rebound-init",
        "private-alias-does-not-poison-public",
        "unknown-does-not-prove-facade-types",
    ),
)
def test_public_chain_proof_is_complete_and_entry_scoped(
    tmp_path: Path,
    api: str,
    middle: str,
    package: bool,
    proven: bool,
    typed_origin: bool,
) -> None:
    _write_app(tmp_path, public=["sample.app.api"], init="", api=api)
    path = tmp_path / "sample/app/middle.py"
    if package:
        path = tmp_path / "sample/app/middle/__init__.py"
        path.parent.mkdir()
    path.write_text(middle)
    if typed_origin:
        (tmp_path / "sample/app/impl.py").write_text(
            "class Payload:\n    pass\n"
            "def element_constraints(value: Payload) -> Payload:\n    return value\n"
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
    observation = result.observation
    violations = observation.records("violations") or ()
    unknowns = [
        record
        for record in observation.records("unknowns") or ()
        if record.kind.startswith("boundary")
    ]
    if proven:
        assert len(violations) == 3
        assert not unknowns
    else:
        assert not violations
        assert unknowns, "An unresolved export must remain UNKNOWN beside a typed local function"
    if typed_origin:
        assert not [
            record
            for record in observation.records("symbols") or ()
            if record.data.get("facade_types")
        ]


def test_uncertain_public_alias_keeps_other_alias_violations(tmp_path: Path) -> None:
    _write_app(
        tmp_path,
        public=["sample.app.api", "sample.app.middle"],
        init="",
        api="from .impl import element_constraints as constraints\n" + EXPORT + SAFE,
    )
    (tmp_path / "sample/app/middle.py").write_text(
        "from .impl import element_constraints as constraints\n"
        '__all__ = ["constraints"]\nconstraints = object\n'
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
    observation = result.observation
    violations = observation.records("violations") or ()
    assert len(violations) == 3
    assert all(record.data.get("module") == "sample.app.api" for record in violations)
    assert any(
        record.kind.startswith("boundary") for record in observation.records("unknowns") or ()
    )


@pytest.mark.parametrize("uncertain", [False, True])
@pytest.mark.parametrize("hops", [2, 3])
def test_uncertainty_survives_multiple_intermediate_aliases(
    tmp_path: Path, hops: int, uncertain: bool
) -> None:
    _write_app(
        tmp_path,
        public=["sample.app.api"],
        init="",
        api="from .middle0 import constraints\n" + EXPORT + SAFE,
    )
    for index in range(hops):
        target = (
            "from .impl import element_constraints as constraints\n"
            if index == hops - 1
            else f"from .middle{index + 1} import constraints\n"
        )
        (tmp_path / f"sample/app/middle{index}.py").write_text(
            target
            + '__all__ = ["constraints"]\n'
            + ('__all__.append("other")\n' if uncertain else "")
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
    findings = result.observation.records("violations") or ()
    unknowns = [
        record
        for record in result.observation.records("unknowns") or ()
        if record.kind.startswith("boundary")
    ]
    if uncertain:
        assert not findings
        assert unknowns, "Every uncertain hop must reach the public facade as UNKNOWN"
    else:
        assert len(findings) == 3
        assert not unknowns


@pytest.mark.parametrize("rebound", [False, True])
def test_candidate_chain_cannot_authorize_an_interface_import(
    tmp_path: Path, rebound: bool
) -> None:
    _write_app(
        tmp_path,
        public=["sample.app.impl:element_constraints"],
        init="",
        api='from .impl import element_constraints as constraints\n__all__ = ["constraints"]\n'
        + ("constraints = object\n" if rebound else ""),
    )
    (tmp_path / "sample/client.py").write_text("from sample.app.api import constraints\n")
    path = tmp_path / "contract.json"
    contract = json.loads(path.read_bytes())
    contract["components"].append(_component("client", public=[]))
    contract["rules"] = [
        {
            "id": "APP-BOUNDARY",
            "kind": "interface_boundary",
            "rationale": "Only the declared implementation symbol is public.",
            "provenance": ["docs/architecture/sample.md"],
            "decided_by": "architect",
        }
    ]
    path.write_text(json.dumps(contract))
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
    blocked = [
        record
        for section in ("violations", "unknowns")
        for record in result.observation.records(section) or ()
        if "APP-BOUNDARY" in record.rule_ids
    ]
    assert bool(blocked) is rebound, "A candidate origin cannot prove a public interface route"


def test_uncertain_alias_cycle_terminates_without_proving_the_facade(tmp_path: Path) -> None:
    _write_app(
        tmp_path,
        public=["sample.app.api"],
        init="",
        api="from .middle0 import constraints\n" + EXPORT + SAFE,
    )
    (tmp_path / "sample/app/middle0.py").write_text(
        "from .middle1 import constraints\n"
        "from .impl import element_constraints as constraints\n"
        '__all__ = ["constraints"]\n'
    )
    (tmp_path / "sample/app/middle1.py").write_text(
        'from .middle0 import constraints\n__all__ = ["constraints"]\n'
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
    assert not result.observation.records("violations")
    assert any(
        record.kind.startswith("boundary")
        for record in result.observation.records("unknowns") or ()
    )


def test_public_alias_cycle_is_unknown_beside_a_typed_function(tmp_path: Path) -> None:
    _write_app(
        tmp_path,
        public=["sample.app.api"],
        init="",
        api="from .middle0 import constraints\n" + EXPORT + SAFE,
    )
    for index in (0, 1):
        (tmp_path / f"sample/app/middle{index}.py").write_text(
            f'from .middle{1 - index} import constraints\n__all__ = ["constraints"]\n'
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
    route_unknowns = [
        record
        for record in result.observation.records("unknowns") or ()
        if "APP-TYPES-NOT-DICT" in record.rule_ids and record.kind == "boundary_type_route"
    ]
    assert route_unknowns, "A cyclic alias cannot disappear from public-boundary coverage"
    assert all(
        record.data.get("position") is None and record.data.get("annotation") is None
        for record in route_unknowns
    )
    assert not any(
        record.kind == "rule-without-subjects"
        for record in result.observation.records("unknowns") or ()
    )


@pytest.mark.parametrize(
    ("middle", "unknown", "violations"),
    [
        ("from .impl import element_constraints as constraints\n", False, 3),
        (
            "from .impl import element_constraints as constraints\n"
            'if enabled:\n    __all__ = ["constraints"]\n',
            False,
            3,
        ),
        ('__all__ = ["constraints"]\n', True, 0),
        ('constraints = 42\n__all__ = ["constraints"]\n', False, 0),
        ('class constraints:\n    pass\n__all__ = ["constraints"]\n', False, 0),
        (
            'constraints = 42\n__all__ = ["constraints"]\n'
            "def other():\n    from .impl import element_constraints as constraints\n",
            False,
            0,
        ),
        (
            'class constraints:\n    pass\n__all__ = ["constraints"]\n'
            "def other():\n    from .impl import element_constraints as constraints\n",
            False,
            0,
        ),
    ],
    ids=(
        "no-all",
        "conditional-all",
        "missing-symbol",
        "known-constant",
        "known-class",
        "constant-with-local-import",
        "class-with-local-import",
    ),
)
def test_public_route_endpoint_must_be_known_beside_a_typed_function(
    tmp_path: Path, middle: str, unknown: bool, violations: int
) -> None:
    _write_app(
        tmp_path,
        public=["sample.app.api"],
        init="",
        api="from .middle import constraints\n" + EXPORT + SAFE,
    )
    (tmp_path / "sample/app/middle.py").write_text(middle)
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
    observation = result.observation
    actual = observation.records("violations") or ()
    assert len(actual) == violations
    if violations:
        assert {row.data.get("position") for row in actual} == {"first", "second", "return"}
        assert {row.data.get("qualified_name") for row in actual} == {"sample.app.api.constraints"}
    unresolved = [
        record
        for record in observation.records("unknowns") or ()
        if "APP-TYPES-NOT-DICT" in record.rule_ids
    ]
    assert bool(unresolved) is unknown

    if unknown:
        assert all(record.kind == "boundary_type_route" for record in unresolved)


def test_unscanned_public_alias_is_unknown_beside_a_typed_function(tmp_path: Path) -> None:
    _write_app(
        tmp_path,
        public=["sample.app.api"],
        init="",
        api="from outside_package import exported as constraints\n" + EXPORT + SAFE,
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
    assert not result.observation.records("violations")
    assert any(
        record.kind == "boundary_type_route" and "APP-TYPES-NOT-DICT" in record.rule_ids
        for record in result.observation.records("unknowns") or ()
    )


@pytest.mark.parametrize(
    ("target", "unknown", "violations"),
    [
        ("from sample.app.impl import element_constraints as constraints\n", False, 3),
        ('__all__ = ["constraints"]\n', True, 0),
        ("constraints = 42\n", False, 0),
    ],
    ids=("unowned-unproved-hop", "unowned-missing-symbol", "unowned-known-constant"),
)
def test_public_route_uses_source_identity_independently_of_target_ownership(
    tmp_path: Path, target: str, unknown: bool, violations: int
) -> None:
    _write_app(
        tmp_path,
        public=["sample.app.api"],
        init="",
        api="from sample.unowned import constraints\n" + EXPORT + SAFE,
    )
    (tmp_path / "sample/unowned.py").write_text(target)
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
    actual = result.observation.records("violations") or ()
    assert len(actual) == violations
    if violations:
        assert {row.data.get("position") for row in actual} == {"first", "second", "return"}
        assert {row.data.get("qualified_name") for row in actual} == {"sample.app.api.constraints"}
    unresolved = [
        record
        for record in result.observation.records("unknowns") or ()
        if "APP-TYPES-NOT-DICT" in record.rule_ids
    ]
    assert bool(unresolved) is unknown


@pytest.mark.parametrize(
    ("implementation", "unknown", "violations"),
    [
        ("Export = lambda value: value\n", True, 0),
        ("def actual(value: dict) -> object:\n    return value\nExport = actual\n", True, 0),
        ("Export = 42\ndel Export\n", True, 0),
        ("class Export:\n    pass\nif enabled:\n    Export = lambda value: value\n", True, 0),
        (
            "Export = 42\ndef configure():\n    global Export\n"
            "    Export = lambda value: value\nconfigure()\n",
            True,
            0,
        ),
        ("Export = 42\nmatch (lambda value: value):\n    case Export:\n        pass\n", True, 0),
        ("Export = 42\ndef configure(value=(Export := lambda item: item)):\n    pass\n", True, 0),
        ("Export = 42\nother = (Export := lambda value: value)\n", True, 0),
        ("Export = 42\nfrom unknown_external import *\n", True, 0),
        (
            "Export = 42\ndef configure():\n    global Export\n"
            "    def Export(value: dict) -> object:\n        return value\nconfigure()\n",
            True,
            0,
        ),
        ("Export = 42\n", False, 0),
        ("class Export:\n    pass\n", False, 0),
        ("def Export(value: dict) -> object:\n    return value\n", False, 2),
    ],
    ids=(
        "lambda",
        "function-alias",
        "deleted",
        "conditional-rebinding",
        "global-rebinding",
        "match-capture-rebinding",
        "default-expression-rebinding",
        "assignment-rhs-rebinding",
        "star-import-rebinding",
        "nested-global-function-rebinding",
        "stable-constant",
        "stable-class",
        "declared-function",
    ),
)
def test_public_endpoint_needs_stable_kind_evidence(
    tmp_path: Path, implementation: str, unknown: bool, violations: int
) -> None:
    _write_app(
        tmp_path,
        public=["sample.app.api"],
        init="",
        api="from .impl import Export as constraints\n" + EXPORT + SAFE,
        implementation=implementation,
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
    assert len(result.observation.records("violations") or ()) == violations
    undecided = [
        record
        for record in result.observation.records("unknowns") or ()
        if "APP-TYPES-NOT-DICT" in record.rule_ids
    ]
    assert bool(undecided) is unknown
    if unknown:
        assert all(record.kind == "boundary_type_route" for record in undecided)


def test_star_import_keeps_rebound_builtin_endpoint_unknown(tmp_path: Path) -> None:
    _write_app(
        tmp_path,
        public=["sample.app.api"],
        init="",
        api="from .impl import open as constraints\n" + EXPORT + SAFE,
        implementation="open = 42\nfrom builtins import *\n",
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
    assert not result.observation.records("violations")
    assert any(
        record.kind == "boundary_type_route" and "APP-TYPES-NOT-DICT" in record.rule_ids
        for record in result.observation.records("unknowns") or ()
    )


def test_rebound_public_union_alias_is_unknown_beside_private_violation(
    tmp_path: Path,
) -> None:
    _write_app(
        tmp_path,
        public=["sample.app.api"],
        init="",
        api=("from .impl import run, Payload\n__all__ = ['run', 'Payload']\nPayload = object\n"),
        implementation=(
            "class Payload:\n    value: str\n"
            "class Private:\n    value: str\n"
            "def run() -> Payload | Private:\n    return Payload()\n"
        ),
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
    violations = result.observation.records("violations") or ()
    assert len(violations) == 1
    assert "Private" in violations[0].title
    assert violations[0].data.get("qualified_name") == "sample.app.api.run"
    assert any(
        record.kind == "boundary_type_route"
        and record.data.get("qualified_name") == "sample.app.api.Payload"
        for record in result.observation.records("unknowns") or ()
    )


def test_proven_public_alias_survives_an_unstable_alias_to_same_type(
    tmp_path: Path,
) -> None:
    _write_app(
        tmp_path,
        public=["sample.app.api"],
        init="",
        api=(
            "from .impl import run, Payload\n"
            "from .impl import Payload as PublicPayload\n"
            "__all__ = ['run', 'Payload', 'PublicPayload']\n"
            "Payload = object\n"
        ),
        implementation=(
            "class Payload:\n    value: str\ndef run() -> Payload:\n    return Payload()\n"
        ),
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
    assert not result.observation.records("violations")
    boundary_unknowns = [
        record
        for record in result.observation.records("unknowns") or ()
        if "APP-TYPES-NOT-DICT" in record.rule_ids
    ]
    assert [(item.kind, item.data.get("qualified_name")) for item in boundary_unknowns] == [
        ("boundary_type_route", "sample.app.api.Payload")
    ]
