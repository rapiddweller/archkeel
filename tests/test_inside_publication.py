# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Each inside level owns an explicit public surface of its own."""

import json
from pathlib import Path

from test_analyzer import _component, _inside_component, _observe

from archkeel.check.ports import ScanConfig
from archkeel.check.validation import inside_diagnostics
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
