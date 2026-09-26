# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Each inside level owns an explicit public surface of its own."""

import json
from pathlib import Path

import pytest
from test_analyzer import _component, _inside_component, _observe
from test_recursive_inside_independent_contracts import _commit_tree, _scan_config

from archkeel.analyzer import observe
from archkeel.check.ports import ScanConfig
from archkeel.check.validation import COMPONENT_GRAPH_MARKER, inside_diagnostics, run_validate
from archkeel.ir.codec import parse_contract
from archkeel.ir.levels import inside_levels
from archkeel.ir.trace import trace_valid_violations


def _rule(rule_id: str, kind: str, **fields: object) -> dict[str, object]:
    return {
        "id": rule_id,
        "kind": kind,
        "rationale": "Exercise the declared boundary.",
        "provenance": ["docs/architecture/sample.md"],
        "decided_by": "architect",
        **fields,
    }


def _child(label: str, package: str, *, public: list[str] | None = None) -> dict[str, object]:
    return _inside_component(label, []) | {
        "packages": [package],
        "public": public or [],
    }


def _write_project(
    root: Path,
    *,
    components: list[dict[str, object]],
    rules: list[dict[str, object]],
    insides: dict[str, dict[str, object]],
    files: dict[str, str],
) -> None:
    (root / "contract.json").write_text(
        json.dumps({"schema_version": "2.1.0", "components": components, "rules": rules})
    )
    for path, contract in insides.items():
        (root / path).write_text(json.dumps(contract))
    for relative_path, contents in {
        "sample/__init__.py": "",
        "docs/architecture/sample.md": "Architecture decision.\n",
        **files,
    }.items():
        path = root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(contents)


def _inside(
    components: list[dict[str, object]], rules: list[dict[str, object]]
) -> dict[str, object]:
    return {"schema_version": "2.1.0", "components": components, "rules": rules}


def test_child_public_can_be_local_to_the_inside(tmp_path: Path) -> None:
    local_api = "sample.core.api:helper"
    _write_project(
        tmp_path,
        components=[
            _component("core", packages=["sample.core"], public=[]) | {"inside": "core.json"}
        ],
        rules=[],
        insides={
            "core.json": _inside(
                [
                    _child("api", "sample.core.api", public=[local_api]),
                    _child("worker", "sample.core.worker"),
                ],
                [_rule("LOCAL-INTERFACE", "interface_boundary")],
            )
        },
        files={
            "sample/core/api.py": "def helper() -> int:\n    return 1\n",
            "sample/core/worker.py": "from sample.core.api import helper\n\nVALUE = helper()\n",
        },
    )

    result = _observe(tmp_path)
    assert result.observation is not None, result.diagnostics
    assert not [
        item
        for item in trace_valid_violations(result.observation)
        if item.rule_ids == ("core:LOCAL-INTERFACE",)
    ]
    assert (
        inside_diagnostics(
            tmp_path,
            parse_contract(json.loads((tmp_path / "contract.json").read_bytes())),
            ScanConfig(("sample",), "sample", "contract.json", "0" * 64),
        )
        == ()
    )


def test_outer_consumer_cannot_import_a_child_only_public_api(tmp_path: Path) -> None:
    local_api = "sample.core.api:helper"
    _write_project(
        tmp_path,
        components=[
            _component("core", packages=["sample.core"], public=[]) | {"inside": "core.json"},
            _component("client", packages=["sample.client"]),
        ],
        rules=[_rule("ROOT-INTERFACE", "interface_boundary")],
        insides={
            "core.json": _inside(
                [
                    _child("api", "sample.core.api", public=[local_api]),
                    _child("worker", "sample.core.worker"),
                ],
                [_rule("LOCAL-INTERFACE", "interface_boundary")],
            )
        },
        files={
            "sample/core/api.py": "def helper() -> int:\n    return 1\n",
            "sample/core/worker.py": "from sample.core.api import helper\n",
            "sample/client.py": "from sample.core.api import helper\n",
        },
    )

    result = _observe(tmp_path)
    assert result.observation is not None, result.diagnostics
    violations = trace_valid_violations(result.observation)
    assert [item.rule_ids for item in violations] == [("ROOT-INTERFACE",)]
    assert violations[0].data.get("source_module") == "sample.client"
    assert violations[0].data.get("symbol") == "helper"


def test_parent_published_facade_passes_but_direct_private_import_fails(tmp_path: Path) -> None:
    published = "sample.core:published"
    _write_project(
        tmp_path,
        components=[
            _component("core", packages=["sample.core"], public=[published])
            | {"inside": "core.json"},
            _component("client", packages=["sample.client"]),
        ],
        rules=[_rule("ROOT-INTERFACE", "interface_boundary")],
        insides={
            "core.json": _inside(
                [
                    _child("api", "sample.core.api", public=["sample.core.api:published"]),
                    _child("worker", "sample.core.worker"),
                ],
                [_rule("LOCAL-INTERFACE", "interface_boundary")],
            )
        },
        files={
            "sample/core/api.py": (
                "def published(value: str) -> str:\n    return value\n\n"
                "def private_api(value: str) -> str:\n    return value\n"
            ),
            "sample/core/__init__.py": (
                "from sample.core.api import published\n__all__ = ['published']\n"
            ),
            "sample/client.py": (
                "from sample.core import published\nfrom sample.core.api import private_api\n"
            ),
        },
    )

    result = _observe(tmp_path)
    assert result.observation is not None, result.diagnostics
    violations = trace_valid_violations(result.observation)
    assert [(item.rule_ids, item.data.get("symbol")) for item in violations] == [
        (("ROOT-INTERFACE",), "private_api")
    ]


def test_child_allow_does_not_override_ancestor_forbidden_dependency(tmp_path: Path) -> None:
    _write_project(
        tmp_path,
        components=[
            _component("core", packages=["sample.core"], public=[]) | {"inside": "core.json"},
            _component("external", packages=["sample.external"]),
        ],
        rules=[
            _rule(
                "ROOT-NO-EXTERNAL",
                "forbidden_dependency",
                source="sample.core",
                target="sample.external",
                include_type_checking=True,
            )
        ],
        insides={
            "core.json": _inside(
                [_child("api", "sample.core.api")],
                [
                    _rule(
                        "LOCAL-ALLOW-EXTERNAL",
                        "allowed_dependency",
                        source="sample.core.api",
                        target="sample.external",
                    )
                ],
            )
        },
        files={
            "sample/core/api.py": "import sample.external\n",
            "sample/external/__init__.py": "",
        },
    )

    result = _observe(tmp_path)
    assert result.observation is not None, result.diagnostics
    assert any(
        item.rule_ids == ("ROOT-NO-EXTERNAL",)
        for item in trace_valid_violations(result.observation)
    )


def test_inner_interface_rule_does_not_leak_to_an_unrelated_sibling(tmp_path: Path) -> None:
    core_local = "sample.core.api:allowed"
    service_local = "sample.service.api:allowed"
    _write_project(
        tmp_path,
        components=[
            _component("core", packages=["sample.core"], public=[]) | {"inside": "core.json"},
            _component("service", packages=["sample.service"], public=[])
            | {"inside": "service.json"},
        ],
        rules=[],
        insides={
            "core.json": _inside(
                [
                    _child("api", "sample.core.api", public=[core_local]),
                    _child("client", "sample.core.client"),
                ],
                [_rule("LOCAL-INTERFACE", "interface_boundary")],
            ),
            "service.json": _inside(
                [
                    _child("api", "sample.service.api", public=[service_local]),
                    _child("client", "sample.service.client"),
                ],
                [],
            ),
        },
        files={
            "sample/core/api.py": "allowed = 1\nhidden = 2\n",
            "sample/core/client.py": "from sample.core.api import hidden\n",
            "sample/service/api.py": "allowed = 1\nhidden = 2\n",
            "sample/service/client.py": "from sample.service.api import hidden\n",
        },
    )

    result = _observe(tmp_path)
    assert result.observation is not None, result.diagnostics
    violations = trace_valid_violations(result.observation)
    assert [item.rule_ids for item in violations] == [("core:LOCAL-INTERFACE",)]
    assert violations[0].data.get("source_module") == "sample.core.client"


def test_boundary_type_rules_run_at_both_explicit_levels(tmp_path: Path) -> None:
    parent_entry = "sample.core:constraints"
    child_entry = "sample.core.api:element_constraints"
    _write_project(
        tmp_path,
        components=[
            _component("core", packages=["sample.core"], public=[parent_entry])
            | {"inside": "core.json"},
        ],
        rules=[_rule("ROOT-TYPES", "boundary_types", source="sample.core")],
        insides={
            "core.json": _inside(
                [
                    _child("api", "sample.core.api", public=[child_entry]),
                ],
                [_rule("LOCAL-TYPES", "boundary_types", source="sample.core.api")],
            )
        },
        files={
            "sample/core/__init__.py": (
                "from sample.core.api import element_constraints as _element_constraints\n"
                "def constraints(first: dict, second: dict) -> object:\n"
                "    return _element_constraints(first, second)\n"
                "__all__ = ['constraints']\n"
            ),
            "sample/core/api.py": (
                "def element_constraints(first: dict, second: dict) -> object:\n"
                "    return first\n"
                "__all__ = ['element_constraints']\n"
            ),
        },
    )

    result = _observe(tmp_path)
    assert result.observation is not None, result.diagnostics
    violations = trace_valid_violations(result.observation)
    assert {item.rule_ids[0] for item in violations} == {"ROOT-TYPES", "core:LOCAL-TYPES"}
    definitions = [
        item
        for item in result.observation.records("symbols") or ()
        if item.kind == "function"
        and item.data.get("module") == "sample.core"
        and item.data.get("name") == "constraints"
    ]
    assert len(definitions) == 1
    assert len({item.id for item in violations}) == len(violations)


def test_overlapping_child_scopes_leave_init_and_ambiguous_module_unassigned(
    tmp_path: Path,
) -> None:
    _write_project(
        tmp_path,
        components=[
            _component("core", packages=["sample.core"], public=["sample.core:constraints"])
            | {"inside": "core.json"}
        ],
        rules=[],
        insides={
            "core.json": _inside(
                [
                    _child("api", "sample.core.api"),
                    _child("nested", "sample.core.api.nested"),
                ],
                [],
            )
        },
        files={
            "sample/core/__init__.py": "def constraints() -> None:\n    return None\n",
            "sample/core/api.py": "VALUE = 1\n",
            "sample/core/api/nested.py": "VALUE = 2\n",
        },
    )

    result = _observe(tmp_path)
    assert result.observation is not None, result.diagnostics
    level = next(item for item in inside_levels(result.observation) if item.parent == "core")
    assert level.unassigned == ("sample.core", "sample.core.api.nested")
    owners = {item.label: item.modules for item in level.components}
    assert owners == {"api": ("sample.core.api",), "nested": ()}


@pytest.mark.parametrize(
    ("field", "entry", "expected_code"),
    [
        ("public", "sample.core.worker:helper", "reference.public_owner"),
        ("public", "sample.core.api:_helper", "reference.public_underscore"),
        ("planned", "sample.core.worker:helper", "reference.public_owner"),
        ("planned", "sample.core.api:_helper", "reference.public_underscore"),
        ("public", "outside.api:helper", "reference.namespace"),
    ],
    ids=["public-owner", "public-underscore", "planned-owner", "planned-underscore", "namespace"],
)
def test_inside_public_and_planned_entries_keep_reference_validation(
    tmp_path: Path, field: str, entry: str, expected_code: str
) -> None:
    api = _child("api", "sample.core.api")
    api[field] = [entry]
    _write_project(
        tmp_path,
        components=[
            _component(
                "core",
                packages=["sample.core"],
                public=[entry] if field == "public" else [],
            )
            | {"inside": "core.json"}
        ],
        rules=[],
        insides={"core.json": _inside([api, _child("worker", "sample.core.worker")], [])},
        files={
            "sample/core/api.py": "def helper() -> int:\n    return 1\n",
            "sample/core/worker.py": "def helper() -> int:\n    return 1\n",
        },
    )

    diagnostics = inside_diagnostics(
        tmp_path,
        parse_contract(json.loads((tmp_path / "contract.json").read_bytes())),
        ScanConfig(("sample",), "sample", "contract.json", "0" * 64),
    )

    assert [
        (item.code, item.pointer, item.subject)
        for item in diagnostics
        if item.code == expected_code
    ] == [(expected_code, f"/components/0/inside/components/0/{field}/0", entry)]


@pytest.mark.parametrize("external_import", [False, True], ids=["local-pass", "outside-blocked"])
def test_nested_child_public_stays_local_in_validate(tmp_path: Path, external_import: bool) -> None:
    local_api = "sample.core.service.api:helper"
    root_api = "sample.core:published"
    service = _child("service", "sample.core.service") | {"inside": "service.json"}
    service_contract = _inside(
        [
            _child("api", "sample.core.service.api", public=[local_api]),
            _child("worker", "sample.core.service.worker"),
        ],
        [
            _rule("LOCAL-INTERFACE", "interface_boundary"),
            _rule(
                "LOCAL-ALLOW-WORKER",
                "allowed_dependency",
                source="sample.core.service.worker",
                target="sample.core.service.api",
            ),
        ],
    )
    _write_project(
        tmp_path,
        components=[
            _component("core", packages=["sample.core"], public=[root_api])
            | {"inside": "core.json"},
            _component("client", packages=["sample.client"]),
        ],
        rules=[
            _rule("ROOT-INTERFACE", "interface_boundary"),
            _rule(
                "ROOT-ALLOW-CLIENT",
                "allowed_dependency",
                source="sample.client",
                target="sample.core",
            ),
            _rule(
                "ROOT-NO-REVERSE",
                "forbidden_dependency",
                source="sample.core",
                target="sample.client",
                include_type_checking=True,
            ),
        ],
        insides={"core.json": _inside([service], []), "service.json": service_contract},
        files={
            "sample/core/__init__.py": "def published() -> int:\n    return 1\n",
            "sample/core/service/api.py": "def helper() -> int:\n    return 1\n",
            "sample/core/service/worker.py": "from sample.core.service.api import helper\n",
            "sample/client.py": (
                "from sample.core import published\n"
                + ("from sample.core.service.api import helper\n" if external_import else "")
            ),
        },
    )
    (tmp_path / "pyproject.toml").write_text('[project]\nrequires-python = ">=3.11"\n')
    graph_edge = "  client --> core\n"
    (tmp_path / "docs/architecture/sample.md").write_text(
        f"{COMPONENT_GRAPH_MARKER}\n```mermaid\ngraph TD\n{graph_edge}```\n"
    )
    _commit_tree(tmp_path)

    result, _ = run_validate(tmp_path, _scan_config(), observe)

    assert result.exit_code == (2 if external_import else 0), [
        (item.code, item.subject, item.unknown_claim) for item in result.diagnostics
    ]
    assert [
        (item.code, item.pointer, item.subject)
        for item in result.diagnostics
        if item.code == "rule.violated"
    ] == ([("rule.violated", "/rules/0", "ROOT-INTERFACE")] if external_import else [])
    assert not [item for item in result.diagnostics if item.code != "rule.violated"], [
        (item.code, item.subject, item.unknown_claim)
        for item in result.diagnostics
        if item.code != "rule.violated"
    ]
