# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Literal dynamic dependencies obey the same target policy as static imports."""

import pytest
from test_absent_import_namespace import _observe_namespace

from archkeel.ir.decisions import rule_assessments


@pytest.mark.parametrize(
    "body, expected",
    [
        ('import importlib\nimportlib.import_module("sample.retired.old")\n', "FAIL"),
        ('import importlib as loader\nloader.import_module("sample.retired.old")\n', "FAIL"),
        ('from importlib import import_module as load\nload("sample.retired.old")\n', "FAIL"),
        ('__import__("sample.retired.old")\n', "FAIL"),
        ('import importlib\nimportlib.import_module(".retired.old", package="sample")\n', "FAIL"),
        ('import importlib\nimportlib.import_module(name="sample.retired.old")\n', "FAIL"),
        ('import importlib\nimportlib.import_module("sample.errors")\n', "PASS"),
        ("import importlib\ndef run(name):\n    return importlib.import_module(name)\n", "UNKNOWN"),
        (
            "from importlib import import_module\n"
            "def import_module(name):\n    return name\n"
            'import_module("sample.retired.old")\n',
            "UNKNOWN",
        ),
    ],
)
@pytest.mark.parametrize("mounted", [False, True])
def test_native_dynamic_dependency_policy(tmp_path, body, expected, mounted):
    result = _observe_namespace(tmp_path, body, mounted=mounted)
    assert result.observation is not None, result.diagnostics
    [row] = [
        r
        for r in rule_assessments(result.observation, undecided_by_rule={})
        if r.kind == "forbidden_dependency"
    ]
    assert row.status == expected, row
    if expected != "UNKNOWN":
        assert row.evaluation_proven
    findings = result.observation.records("violations") or ()
    if expected == "FAIL":
        assert all(item.rule_ids and item.fact_ids and item.evidence_ids for item in findings)


@pytest.mark.parametrize(
    "body, expected",
    [
        ('from builtins import __import__ as load\nload("sample.retired.old")\n', "FAIL"),
        ('import importlib\nimportlib.import_module(".old", package=package)\n', "UNKNOWN"),
        ('import importlib\nimportlib.import_module("sample.retired." + name)\n', "UNKNOWN"),
        (
            "import importlib\nfrom typing import TYPE_CHECKING\nif TYPE_CHECKING:\n"
            '    importlib.import_module("sample.retired.old")\n',
            "PASS",
        ),
        (
            "from importlib import import_module as load\ndef other(name):\n    return name\n"
            'load = other\nload("sample.retired.old")\n',
            "UNKNOWN",
        ),
        (
            "from importlib import import_module as load\ndef other(name):\n    return name\n"
            'if condition:\n    load = other\nload("sample.retired.old")\n',
            "UNKNOWN",
        ),
    ],
)
def test_loader_proof_limits(tmp_path, body, expected):
    result = _observe_namespace(tmp_path, body, include_type_checking=False)
    assert result.observation is not None, result.diagnostics
    [row] = [
        r
        for r in rule_assessments(result.observation, undecided_by_rule={})
        if r.kind == "forbidden_dependency"
    ]
    assert row.status == expected, row


def test_known_violation_survives_an_unproven_dynamic_target(tmp_path):
    result = _observe_namespace(
        tmp_path,
        "import sample.retired.old\nimport importlib\ndef run(name):\n"
        "    return importlib.import_module(name)\n",
    )
    assert result.observation is not None, result.diagnostics
    [row] = [
        r
        for r in rule_assessments(result.observation, undecided_by_rule={})
        if r.kind == "forbidden_dependency"
    ]
    assert row.status == "FAIL"
    assert result.observation.records("violations")


@pytest.mark.parametrize(
    "fromlist, expected", [("()", "PASS"), ('("retired",)', "UNKNOWN"), ("names", "UNKNOWN")]
)
def test_builtin_fromlist_never_hides_possible_child_imports(tmp_path, fromlist, expected):
    result = _observe_namespace(tmp_path, f'__import__("sample", fromlist={fromlist})\n')
    assert result.observation is not None, result.diagnostics
    [row] = [
        r
        for r in rule_assessments(result.observation, undecided_by_rule={})
        if r.kind == "forbidden_dependency"
    ]
    assert row.status == expected
    assert row.evaluation_proven is (expected == "PASS")
    assert any(
        r.data.get("target_module") == "sample" for r in result.observation.records("imports") or ()
    )


@pytest.mark.parametrize(
    "setup, expected",
    [
        ("", "FAIL"),
        ("    importlib.import_module = lambda name: name\n", "UNKNOWN"),
        ("    mutate(importlib)\n", "UNKNOWN"),
    ],
)
def test_local_loader_requires_unchanged_members(tmp_path, setup, expected):
    result = _observe_namespace(
        tmp_path,
        "def run():\n    import importlib\n"
        + setup
        + '    return importlib.import_module("sample.retired.old")\n',
    )
    assert result.observation is not None, result.diagnostics
    [row] = [
        r
        for r in rule_assessments(result.observation, undecided_by_rule={})
        if r.kind == "forbidden_dependency"
    ]
    assert row.status == expected


@pytest.mark.parametrize("kind", ["complete_requires", "interface_boundary", "sibling_isolation"])
@pytest.mark.parametrize("type_only", [False, True])
def test_unknown_loader_honors_dependency_scope_and_type_exclusion(tmp_path, kind, type_only):
    from test_absent_import_namespace import _namespace_contract
    from test_exact_module_ownership import _observe_tree

    contract = _namespace_contract()
    contract["rules"] = [
        dict(
            id="POLICY",
            kind=kind,
            rationale="Keep dependency proof complete.",
            provenance=["docs/architecture/sample.md"],
            decided_by="agent",
            include_type_checking=False,
        )
    ]
    if kind == "sibling_isolation":
        contract["rules"][0]["members"] = ["sample.caller", "sample.errors"]
    for component in contract["components"]:
        component["packages"] = component["packages"][:1]
        component["requires"] = []
        component["public"] = []
    body = "import importlib\n"
    body += (
        "from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    importlib.import_module(name)\n"
        if type_only
        else "def run(name):\n    return importlib.import_module(name)\n"
    )
    result = _observe_tree(
        tmp_path,
        {
            "sample/__init__.py": "",
            "sample/caller/__init__.py": body,
            "sample/errors/__init__.py": "",
        },
        contract,
    )
    assert result.observation is not None, result.diagnostics
    [row] = [
        r for r in rule_assessments(result.observation, undecided_by_rule={}) if r.kind == kind
    ]
    assert row.status == ("PASS" if type_only else "UNKNOWN")
    assert row.evaluation_proven is type_only


@pytest.mark.parametrize(
    "body, expected",
    [
        (
            "import importlib\ndef other(importlib):\n    mutate(importlib)\n"
            'importlib.import_module("sample.retired.old")\n',
            "FAIL",
        ),
        (
            "import builtins\nbuiltins.__import__ = lambda name: name\n"
            '__import__("sample.retired.old")\n',
            "UNKNOWN",
        ),
        (
            "import importlib\nother = importlib\nother.import_module = lambda name: name\n"
            'importlib.import_module("sample.retired.old")\n',
            "UNKNOWN",
        ),
        (
            "import importlib\nimportlib.import_module = lambda name: name\n"
            'from importlib import import_module as load\nload("sample.retired.old")\n',
            "UNKNOWN",
        ),
        (
            "import importlib\ndef mutate_loader():\n    import importlib as other\n"
            "    other.import_module = lambda name: name\nmutate_loader()\n"
            'importlib.import_module("sample.retired.old")\n',
            "UNKNOWN",
        ),
    ],
)
def test_loader_mutations_use_import_identity_instead_of_spelling(tmp_path, body, expected):
    result = _observe_namespace(tmp_path, body)
    assert result.observation is not None, result.diagnostics
    [row] = [
        r
        for r in rule_assessments(result.observation, undecided_by_rule={})
        if r.kind == "forbidden_dependency"
    ]
    assert row.status == expected


@pytest.mark.parametrize(
    "mutation", ["importlib.import_module = lambda name: name\n", "mutate(importlib)\n"]
)
def test_loader_mutation_in_another_scanned_module_withholds_proof(tmp_path, mutation):
    from test_absent_import_namespace import _namespace_contract
    from test_exact_module_ownership import _observe_tree

    contract = _namespace_contract()
    for component in contract["components"]:
        component["packages"] = component["packages"][:1]
    result = _observe_tree(
        tmp_path,
        {
            "sample/__init__.py": "",
            "sample/caller/__init__.py": "import importlib\nfrom sample.errors import marker\n"
            'importlib.import_module("sample.retired.old")\n',
            "sample/errors/__init__.py": "import importlib\n" + mutation + "marker = 1\n",
        },
        contract,
    )
    assert result.observation is not None, result.diagnostics
    [row] = [
        r
        for r in rule_assessments(result.observation, undecided_by_rule={})
        if r.kind == "forbidden_dependency"
    ]
    assert row.status == "UNKNOWN" and not row.evaluation_proven


@pytest.mark.parametrize(
    "target, expected", [("external_lib", "FAIL"), ("other_lib", "PASS"), (None, "UNKNOWN")]
)
def test_external_dependency_policy_includes_dynamic_loads(tmp_path, target, expected):
    from test_absent_import_namespace import _namespace_contract
    from test_exact_module_ownership import _observe_tree

    contract = _namespace_contract()
    contract["rules"] = [
        dict(
            id="EXTERNAL",
            kind="external_dependency_scope",
            dependency="external_lib",
            allowed_sources=["sample.errors"],
            rationale="Keep dependency with its owner.",
            provenance=["docs/architecture/sample.md"],
            decided_by="agent",
        )
    ]
    for component in contract["components"]:
        component["packages"] = component["packages"][:1]
    argument = repr(target) if target is not None else "name"
    result = _observe_tree(
        tmp_path,
        {
            "sample/__init__.py": "",
            "sample/caller/__init__.py": "import importlib\ndef run(name):\n"
            f"    return importlib.import_module({argument})\n",
            "sample/errors/__init__.py": "",
        },
        contract,
    )
    assert result.observation is not None, result.diagnostics
    [row] = [
        r
        for r in rule_assessments(result.observation, undecided_by_rule={})
        if r.kind == "external_dependency_scope"
    ]
    assert row.status == expected
    assert row.evaluation_proven is (expected != "UNKNOWN")


@pytest.mark.parametrize(
    "provider, caller",
    [
        ("import importlib as route\n", "route.import_module = lambda name: name\n"),
        ("from importlib import import_module as route\n", "mutate(route)\n"),
        ("import importlib as route\n", 'route.import_module("sample.retired.old")\n'),
        ("from importlib import import_module as route\n", 'route("sample.retired.old")\n'),
    ],
)
def test_reexported_loader_identity_cannot_authorize_a_false_proof(tmp_path, provider, caller):
    from test_absent_import_namespace import _namespace_contract
    from test_exact_module_ownership import _observe_tree

    contract = _namespace_contract()
    for component in contract["components"]:
        component["packages"] = component["packages"][:1]
    result = _observe_tree(
        tmp_path,
        {
            "sample/__init__.py": "",
            "sample/caller/__init__.py": "import importlib\nfrom sample.errors import route\n"
            + caller
            + 'importlib.import_module("sample.retired.old")\n',
            "sample/errors/__init__.py": provider,
        },
        contract,
    )
    assert result.observation is not None, result.diagnostics
    [row] = [
        r
        for r in rule_assessments(result.observation, undecided_by_rule={})
        if r.kind == "forbidden_dependency"
    ]
    if "lambda" in caller or "mutate" in caller:
        assert row.status == "UNKNOWN" and not row.evaluation_proven
    else:
        assert (
            row.status == "FAIL"
        )  # The known direct violation survives the unproved reexport call.
        assert any(
            r.kind == "dynamic_dependency_limit"
            for r in result.observation.records("unknowns") or ()
        )


def test_class_reexport_with_the_module_name_keeps_collection_finite(tmp_path):
    from test_absent_import_namespace import _namespace_contract
    from test_exact_module_ownership import _observe_tree

    contract = _namespace_contract()
    for component in contract["components"]:
        component["packages"] = component["packages"][:1]
    result = _observe_tree(
        tmp_path,
        {
            "sample/__init__.py": "",
            "sample/caller/__init__.py": "from sample.errors import route\nroute.run()\n",
            "sample/errors/__init__.py": "from .route import Handler as route\n",
            "sample/errors/route.py": (
                "class Handler:\n    @staticmethod\n    def run(): return 1\n"
            ),
        },
        contract,
    )
    assert result.observation is not None, result.diagnostics
    [row] = [
        r
        for r in rule_assessments(result.observation, undecided_by_rule={})
        if r.kind == "forbidden_dependency"
    ]
    assert row.status == "PASS" and row.evaluation_proven


def test_long_assignment_aliases_do_not_recurse_in_loader_identity():
    import ast

    from archkeel.analyzer.python.imports import _import_targets, collect_imports
    from archkeel.analyzer.python.scopes import LexicalScopes
    from test_analyzer import _parsed_module

    body = (
        "import importlib\nalias0 = importlib\n"
        + "".join(f"alias{i} = alias{i - 1}\n" for i in range(1, 1100))
        + 'alias1099.import_module("sample.retired")\n'
    )
    module = _parsed_module(body, "sample.api", rel_path="sample/api.py")
    collect_imports([module], {module.module}, {}, namespace="sample")
    [call] = [node for node in ast.walk(module.tree) if isinstance(node, ast.Call)]
    assert _import_targets(LexicalScopes(module), call.func) == frozenset(
        {"importlib.import_module"}
    )


@pytest.mark.parametrize(
    "body, expected",
    [
        (
            'if condition:\n    __import__ = lambda name: name\n__import__("sample.retired.old")\n',
            "UNKNOWN",
        ),
        (
            "if condition:\n    def __import__(name): return name\n"
            '__import__("sample.retired.old")\n',
            "UNKNOWN",
        ),
        (
            "if condition:\n    __import__ = lambda name: name\n"
            'load = __import__\nload("sample.retired.old")\n',
            "UNKNOWN",
        ),
        (
            '__import__ = lambda name: name\ndel __import__\n__import__("sample.retired.old")\n',
            "UNKNOWN",
        ),
        (
            "def shadow():\n    global __import__\n"
            "    if condition:\n        __import__ = lambda name: name\n"
            '__import__("sample.retired.old")\n',
            "UNKNOWN",
        ),
        (
            "class X:\n    if flag:\n        __import__ = lambda name: name\n"
            '    __import__("sample.retired.old")\n',
            "UNKNOWN",
        ),
        (
            "__import__ = lambda name: name\n"
            "class X:\n    if flag:\n        __import__ = lambda name: name\n"
            '    __import__("sample.retired.old")\n',
            "PASS",
        ),
        (
            'class X:\n    __import__ = lambda name: name\n    __import__("sample.retired.old")\n',
            "PASS",
        ),
        (
            "def outer():\n    __import__ = lambda name: name\n"
            "    class C:\n        if flag:\n            __import__ = lambda name: name\n"
            '        __import__("sample.retired.old")\n',
            "UNKNOWN",
        ),
        (
            "def outer():\n    __import__ = lambda name: name\n"
            '    class C:\n        __import__("sample.retired.old")\n',
            "PASS",
        ),
        (
            "def outer():\n    __import__ = lambda name: name\n"
            "    class C:\n        nonlocal __import__\n"
            "        if flag:\n            __import__ = lambda name: name\n"
            '        __import__("sample.retired.old")\n',
            "PASS",
        ),
        (
            '__import__("sample.retired.old")\n__import__ = lambda name: name\n',
            "UNKNOWN",
        ),
        (
            'load = __import__\n__import__ = lambda name: name\nload("sample.retired.old")\n',
            "UNKNOWN",
        ),
        (
            '__import__ = __import__("sample.retired.old")\n',
            "UNKNOWN",
        ),
        (
            '__import__ = lambda name: name; __import__("sample.retired.old")\n',
            "PASS",
        ),
        (
            '__import__("sample.retired.old"); __import__ = lambda name: name\n',
            "UNKNOWN",
        ),
        (
            'def run():\n    __import__("sample.retired.old")\n'
            "    __import__ = lambda name: name\n",
            "PASS",
        ),
        (
            'class C:\n    __import__ = __import__("sample.retired.old")\n',
            "UNKNOWN",
        ),
        (
            "__import__ = lambda name: name\n"
            'class C:\n    __import__ = __import__("sample.retired.old")\n',
            "PASS",
        ),
        (
            "def shadow():\n    global __import__\n    __import__ = lambda name: name\n"
            '__import__("sample.retired.old")\n',
            "UNKNOWN",
        ),
        (
            '__import__: object\n__import__("sample.retired.old")\n',
            "UNKNOWN",
        ),
        (
            '__import__ = lambda name: name\n__import__("sample.retired.old")\n',
            "PASS",
        ),
        (
            "def run():\n    if condition:\n        __import__ = lambda name: name\n"
            '    return __import__("sample.retired.old")\n',
            "PASS",
        ),
        (
            "def outer():\n    if condition:\n        __import__ = lambda name: name\n"
            "    def run():\n        nonlocal __import__\n"
            '        return __import__("sample.retired.old")\n',
            "PASS",
        ),
    ],
)
def test_builtin_import_fallback_respects_lexical_owner(tmp_path, body, expected):
    result = _observe_namespace(tmp_path, body)
    assert result.observation is not None, result.diagnostics
    [row] = [
        r
        for r in rule_assessments(result.observation, undecided_by_rule={})
        if r.kind == "forbidden_dependency"
    ]
    assert row.status == expected, row
    assert row.evaluation_proven is (expected == "PASS")
    assert any(
        item.kind == "dynamic_dependency_limit"
        for item in result.observation.records("unknowns") or ()
    ) is (expected == "UNKNOWN")


@pytest.mark.parametrize(
    "loader, suffix",
    [
        ("importlib.import_module", ".loads('sample.retired.old')"),
        ("importlib.import_module", ".dump('sample.retired.old')"),
        ("importlib.import_module", ".load().run()"),
        ("importlib.import_module", "(name)"),
        ("__import__", ".loads('sample.retired.old')"),
    ],
)
@pytest.mark.parametrize("target", ["name", "'sample.errors'"])
def test_chained_loader_keeps_exact_call_identity(tmp_path, loader, suffix, target):
    from archkeel.analyzer.python.collect import collect

    from archkeel.ir.facts_codec import decode_response, encode_response, record_payload
    from archkeel.ir.protocol import (
        CollectionRequest,
        CollectionResponse,
        PythonSettings,
        SnapshotInput,
        SourceScope,
    )

    package = tmp_path / "sample"
    package.mkdir()
    (package / "caller.py").write_text(
        f"import importlib\ndef run(name):\n    return {loader}({target}){suffix}\n"
    )
    facts = collect(
        CollectionRequest(
            SnapshotInput(str(tmp_path), "a" * 40, False),
            SourceScope(("sample",), "sample"),
            PythonSettings(),
        )
    )
    assert decode_response(encode_response(CollectionResponse(facts))).facts == facts
    sections = {
        str(section.name): [record_payload(record) for record in section.records]
        for section in facts.sections
    }
    [call] = [record for record in sections["calls"] if record["data"]["expression"] == loader]
    dynamic = [record for record in sections["imports"] if record["fact_ids"]]
    limits = [record for record in sections["unknowns"] if record["kind"] == "dynamic_import_limit"]
    if target == "name":
        assert not dynamic
        [limit] = limits
        assert limit["fact_ids"] == [call["id"]]
    else:
        assert not limits
        [dependency] = dynamic
        assert dependency["data"]["target_module"] == "sample.errors"
        assert dependency["fact_ids"] == [call["id"]]


def test_dynamic_import_producer_calls_keep_explicit_receivers(tmp_path):
    import sys
    from pathlib import Path

    from archkeel.analyzer.process import ProcessCollector
    from archkeel.ir.facts import SourceFacts, SourceSectionName
    from archkeel.ir.facts_codec import record_payload
    from archkeel.ir.protocol import CollectionRequest, PythonSettings, SnapshotInput, SourceScope

    source_root = Path(__file__).resolve().parents[1] / "src"
    selected = tmp_path / "archkeel" / "analyzer" / "python"
    selected.mkdir(parents=True)
    for name in ("imports.py", "collect.py"):
        (selected / name).write_bytes(
            (source_root / "archkeel" / "analyzer" / "python" / name).read_bytes()
        )
    facts = ProcessCollector(
        (sys.executable, "-I", "-B", "-m", "archkeel.analyzer.python.entry")
    ).collect(
        CollectionRequest(
            SnapshotInput(str(tmp_path), "a" * 40, False),
            SourceScope(("archkeel",), "archkeel"),
            PythonSettings(),
        )
    )
    assert isinstance(facts, SourceFacts), facts
    assert facts.coverage.files_parsed == 2
    controls = (
        ("imports._argument", "isinstance", "builtins.isinstance"),
        ("imports._import_origins", "name.rpartition", "builtins.str.rpartition"),
        ("imports._loader_mutations", "in_scope", "archkeel.ir.facts.in_scope"),
        ("imports._dynamic_target", "module_name.startswith", "builtins.str.startswith"),
        (
            "imports._DynamicImports.__init__",
            "ImportCollector.__init__",
            "archkeel.analyzer.python.imports.ImportCollector.__init__",
        ),
        ("imports._DynamicImports.visit_Call", "callee.split", "builtins.str.split"),
        ("imports._DynamicImports.visit_Call", "module_name.split", "builtins.str.split"),
        ("imports._DynamicImports.visit_Call", "part.isidentifier", "builtins.str.isidentifier"),
        ("imports.collect_dynamic_imports", "route.update", "builtins.set.update"),
        ("collect.collect", "imports.extend", "builtins.list.extend"),
    )
    calls = [
        record_payload(record)
        for section in facts.sections
        if section.name is SourceSectionName.CALLS
        for record in section.records
    ]
    failures = []
    for function, expression, target in controls:
        scope = "archkeel.analyzer.python." + function
        selected_calls = [
            call["data"]
            for call in calls
            if call["data"]["expression"] == expression
            and (
                call["data"]["source_scope"] == scope
                or call["data"]["source_scope"].startswith(scope + ".")
            )
        ]
        if not selected_calls or any(
            call["status"] == "unresolved" or target not in call["targets"]
            for call in selected_calls
        ):
            failures.append((function, expression, selected_calls))
    assert not failures, failures


@pytest.mark.parametrize("mount", ["root", "wide", "narrow"])
@pytest.mark.parametrize("level", [None, "module"])
@pytest.mark.parametrize("mode", ["unknown", "cycle", "acyclic", "shadowed", "missing"])
def test_cycle_proof_uses_its_actual_graph_domain(tmp_path, mount, level, mode):
    import json

    from test_exact_module_ownership import _component, _observe_tree, _rule

    contract = {
        "schema_version": "2.1.0",
        "components": [_component("owned", ["sample.owned"])],
        "rules": [
            _rule(
                "no_component_cycles", components=["owned"], **({"level": level} if level else {})
            )
        ],
    }
    bodies = {
        "unknown": "def load(name):\n    return __import__(name)\n",
        "cycle": 'def load():\n    return __import__("sample.owned")\n',
        "acyclic": 'def load():\n    return __import__("math")\n',
        "shadowed": '__import__ = lambda name: name\n__import__("sample.owned")\n',
        "missing": "VALUE = 1\n",
    }
    files = {"sample/__init__.py": "", "sample/unowned.py": bodies[mode]}
    if mode != "missing":
        files["sample/owned.py"] = "import sample.unowned\n"
    if mount != "root":
        files["inside.json"] = json.dumps(contract)
        contract = {
            "schema_version": "2.1.0",
            "components": [
                _component(
                    "host", ["sample" if mount == "wide" else "sample.owned"], inside="inside.json"
                )
            ],
            "rules": [],
        }
    result = _observe_tree(tmp_path, files, contract)
    assert result.observation is not None, result.diagnostics
    [row] = [
        r
        for r in rule_assessments(result.observation, undecided_by_rule={})
        if r.kind == "no_component_cycles"
    ]
    expected = (
        "UNKNOWN"
        if mode == "missing" or level == "module" and mode == "unknown"
        else "FAIL"
        if level == "module" and mode == "cycle"
        else "PASS"
    )
    assert row.status == expected, row
    assert row.evaluation_proven is (expected != "UNKNOWN")
    unknowns = result.observation.records("unknowns") or ()
    gaps = [r for r in unknowns if r.kind == "dynamic_import_limit"]
    assert bool(gaps) is (mode == "unknown")
    if gaps:
        assert all(
            r.data.get("source_module") == "sample.unowned" and r.fact_ids and r.evidence_ids
            for r in gaps
        )
    limits = [r for r in unknowns if r.kind == "dynamic_dependency_limit" and row.id in r.rule_ids]
    assert bool(limits) is (level == "module" and mode == "unknown")
    if limits:
        assert all(
            r.data.get("source_module") == "sample.unowned" and r.fact_ids and r.evidence_ids
            for r in limits
        )
    violations = [r for r in result.observation.records("violations") or () if row.id in r.rule_ids]
    if expected == "FAIL":
        [violation] = violations
        assert set(violation.subjects) == {"sample.owned", "sample.unowned"}
        assert violation.fact_ids and violation.evidence_ids
    else:
        assert not violations
