# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Each inside level owns an explicit public surface of its own."""

import json
from pathlib import Path

import pytest
from test_analyzer import _component, _inside_component, _observe
from test_recursive_inside_independent_contracts import (
    _commit_tree,
    _scan_config,
    _write_three_levels,
)

from archkeel.analyzer import observe
from archkeel.check.ports import ScanConfig
from archkeel.check.validation import COMPONENT_GRAPH_MARKER, inside_diagnostics, run_validate
from archkeel.ir.codec import (
    canonical_report_bytes,
    decode_canonical_model,
    parse_contract,
    parse_observation,
)
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
    ] == [
        (
            expected_code,
            f"/components/0/inside/components/0/{field}/0",
            "outside.api" if expected_code == "reference.namespace" else entry,
        )
    ]


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


@pytest.mark.parametrize(
    "case",
    [
        "missing-public",
        "no-interface-rule",
        "constant",
        "planned",
        "planned-import",
        "parent-facade",
    ],
)
def test_local_public_module_validation(tmp_path: Path, case: str) -> None:
    _write_three_levels(tmp_path)
    path = tmp_path / "contracts/two.json"
    contract = json.loads(path.read_text())
    contract["rules"] = (
        [] if case == "no-interface-rule" else [_rule("INTERFACE", "interface_boundary")]
    )
    source = contract["components"][0]
    if case == "constant":
        source["public"] = ["sample.layer.source.api:VALUE"]
        (tmp_path / "sample/layer/source/api.py").write_text("VALUE = 1\n")
        (tmp_path / "sample/layer/target/api.py").write_text(
            "from sample.layer.source.api import VALUE\n"
        )
    elif case == "planned":
        source["planned"] = ["sample.layer.source.missing:run"]
    elif case in {"planned-import", "parent-facade"}:
        (tmp_path / "sample/layer/source/api.py").write_text(
            "def run() -> str:\n    return 'ok'\n__all__ = ['run']\n"
        )
        if case == "planned-import":
            source["planned"] = ["sample.layer.source.api:run"]
            (tmp_path / "sample/layer/target/api.py").write_text(
                "from sample.layer.source.api import run\n"
            )
        else:
            source["public"] = ["sample.layer.source.api:run"]
            (tmp_path / "sample/layer/__init__.py").write_text(
                "from sample.layer.source.api import run\n__all__ = ['run']\n"
            )
            root_path = tmp_path / "contract.json"
            root_contract = json.loads(root_path.read_text())
            root_contract["components"][0]["public"] = ["sample.layer:run"]
            root_path.write_text(json.dumps(root_contract))
    else:
        source["public"] = ["sample.layer.source.missing:run"]
    path.write_text(json.dumps(contract))
    _commit_tree(tmp_path)

    result, _ = run_validate(tmp_path, _scan_config(), observe)

    if case == "missing-public":
        assert result.exit_code == 2, result
        assert [(item.code, item.pointer, item.subject) for item in result.diagnostics] == [
            (
                "interface.missing",
                "/components/0/inside/components/0/inside/components/0/public/0",
                "sample.layer.source.missing:run",
            )
        ]
    elif case == "planned-import":
        assert result.exit_code == 2, result
        assert any(item.code == "rule.violated" for item in result.diagnostics), result
    else:
        assert result.exit_code == 0, result.diagnostics


@pytest.mark.parametrize(
    ("publisher_inside", "expected_unused"),
    [(True, False), (False, True)],
    ids=["inside-publisher-external-definition", "outside-publisher-does-not-count"],
)
def test_nested_facade_type_usage_follows_publisher_scope(
    tmp_path: Path, publisher_inside: bool, expected_unused: bool
) -> None:
    internal_public = ["sample.core.api:run"] if publisher_inside else []
    external_public = [] if publisher_inside else ["sample.foreign.api:run"]
    api_module = "sample.core.api" if publisher_inside else "sample.foreign.api"
    components = [
        _component("core", packages=["sample.core"], public=[]) | {"inside": "core.json"},
        _component("foreign", packages=["sample.foreign"], public=external_public),
    ]
    files = {
        "sample/core/types.py": "class Payload:\n    pass\n",
        "sample/shared_impl.py": (
            "from sample.core.types import Payload\n\ndef run() -> Payload:\n    return Payload()\n"
        ),
        f"{api_module.replace('.', '/')}.py": (
            "from sample.shared_impl import run\n__all__ = ['run']\n"
        ),
    }
    _write_project(
        tmp_path,
        components=components,
        rules=[],
        insides={
            "core.json": _inside(
                [
                    _child("api", "sample.core.api", public=internal_public),
                    _child("types", "sample.core.types", public=["sample.core.types:Payload"]),
                ],
                [_rule("LOCAL-INTERFACE", "interface_boundary")],
            )
        },
        files=files,
    )

    result = _observe(tmp_path)
    assert result.observation is not None, result.diagnostics
    contract = parse_contract(json.loads((tmp_path / "contract.json").read_bytes()))
    diagnostics = inside_diagnostics(
        tmp_path,
        contract,
        ScanConfig(("sample",), "sample", "contract.json", "0" * 64),
        observation=result.observation,
    )

    assert (
        any(
            item.code == "interface.unused" and item.subject == "sample.core.types:Payload"
            for item in diagnostics
        )
        is expected_unused
    )


def test_parent_facade_type_does_not_leak_into_a_deeper_mount(tmp_path: Path) -> None:
    _write_project(
        tmp_path,
        components=[
            _component("core", packages=["sample.core"], public=["sample.core:run"])
            | {"inside": "core.json"}
        ],
        rules=[_rule("ROOT-INTERFACE", "interface_boundary")],
        insides={
            "core.json": _inside(
                [
                    _child("middle", "sample.core.middle") | {"inside": "middle.json"},
                ],
                [_rule("MIDDLE-INTERFACE", "interface_boundary")],
            ),
            "middle.json": _inside(
                [
                    _child(
                        "types",
                        "sample.core.middle.types",
                        public=["sample.core.middle.types:Payload"],
                    ),
                ],
                [_rule("DEEP-INTERFACE", "interface_boundary")],
            ),
        },
        files={
            "sample/core/__init__.py": ("from sample.core.impl import run\n__all__ = ['run']\n"),
            "sample/core/impl.py": (
                "from sample.core.middle.types import Payload\n\n"
                "def run() -> Payload:\n    return Payload()\n"
            ),
            "sample/core/middle/types.py": "class Payload:\n    pass\n",
        },
    )

    result = _observe(tmp_path)
    assert result.observation is not None, result.diagnostics
    contract = parse_contract(json.loads((tmp_path / "contract.json").read_bytes()))
    diagnostics = inside_diagnostics(
        tmp_path,
        contract,
        ScanConfig(("sample",), "sample", "contract.json", "0" * 64),
        observation=result.observation,
    )

    assert [
        (item.code, item.subject) for item in diagnostics if item.code == "interface.unused"
    ] == [("interface.unused", "sample.core.middle.types:Payload")]


@pytest.mark.parametrize(
    "publisher",
    [
        "from sample.core.types import Payload\n__all__ = ['Payload']\n",
        "from sample.core.types import Payload\n",
    ],
    ids=["declared-but-unpublished", "unowned-without-all"],
)
def test_unpublished_parent_import_does_not_use_a_local_public_entry(
    tmp_path: Path, publisher: str
) -> None:
    _write_project(
        tmp_path,
        components=[
            _component("core", packages=["sample.core"], public=[]) | {"inside": "core.json"}
        ],
        rules=[],
        insides={
            "core.json": _inside(
                [
                    _child("api", "sample.core.api"),
                    _child("types", "sample.core.types", public=["sample.core.types:Payload"]),
                ],
                [_rule("LOCAL-INTERFACE", "interface_boundary")],
            )
        },
        files={
            "sample/core/__init__.py": publisher,
            "sample/core/types.py": "class Payload:\n    pass\n",
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

    assert [
        (item.code, item.subject) for item in diagnostics if item.code == "interface.unused"
    ] == [("interface.unused", "sample.core.types:Payload")]


@pytest.mark.parametrize(
    "rebind",
    ["VALUE = 'replacement'\n", "if True:\n    VALUE = 'replacement'\n"],
    ids=["direct-rebind", "conditional-rebind"],
)
def test_rebound_parent_import_does_not_publish_the_original_constant(
    tmp_path: Path, rebind: str
) -> None:
    _write_project(
        tmp_path,
        components=[
            _component("core", packages=["sample.core"], public=["sample.core:VALUE"])
            | {"inside": "core.json"}
        ],
        rules=[],
        insides={
            "core.json": _inside(
                [
                    _child("types", "sample.core.types", public=["sample.core.types:VALUE"]),
                ],
                [_rule("LOCAL-INTERFACE", "interface_boundary")],
            )
        },
        files={
            "sample/core/__init__.py": (
                "from sample.core.types import VALUE\n" + rebind + "__all__ = ['VALUE']\n"
            ),
            "sample/core/types.py": "VALUE = 1\n",
        },
    )

    result = _observe(tmp_path)
    assert result.observation is not None, result.diagnostics
    parent_import = next(
        record
        for record in result.observation.records("imports") or ()
        if record.data.get("source_module") == "sample.core"
        and record.data.get("binding") == "VALUE"
    )
    assert parent_import.data.get("source_binding_unique") is False
    decoded = decode_canonical_model(json.loads(canonical_report_bytes(result.observation)))
    round_tripped = parse_observation(decoded)
    assert (
        next(
            record
            for record in round_tripped.records("imports") or ()
            if record.data.get("source_module") == "sample.core"
            and record.data.get("binding") == "VALUE"
        ).data.get("source_binding_unique")
        is False
    )
    diagnostics = inside_diagnostics(
        tmp_path,
        parse_contract(json.loads((tmp_path / "contract.json").read_bytes())),
        ScanConfig(("sample",), "sample", "contract.json", "0" * 64),
        observation=result.observation,
    )

    assert [
        (item.code, item.subject) for item in diagnostics if item.code == "interface.unused"
    ] == [("interface.unused", "sample.core.types:VALUE")]


@pytest.mark.parametrize(
    ("public", "publisher", "used"),
    [
        ("sample.core:VALUE", "from sample.core.types import VALUE\n", True),
        ("sample.core", "from sample.core.types import VALUE\n", True),
        (
            "sample.core",
            "from sample.core.types import VALUE\n__all__ = ['VALUE']\n",
            True,
        ),
        (
            "sample.core",
            "from sample.core.types import VALUE\n__all__ = ['other']\nother = 2\n",
            False,
        ),
        (
            "sample.core",
            "from sample.core.types import VALUE as _value\n__all__ = ['other']\nother = 2\n",
            False,
        ),
    ],
    ids=[
        "explicit-name-without-all",
        "module-without-all",
        "module-includes-all",
        "module-excludes-name",
        "module-private-alias",
    ],
)
def test_parent_publication_uses_facade_export_semantics(
    tmp_path: Path, public: str, publisher: str, used: bool
) -> None:
    _write_project(
        tmp_path,
        components=[
            _component("core", packages=["sample.core"], public=[public]) | {"inside": "core.json"}
        ],
        rules=[],
        insides={
            "core.json": _inside(
                [
                    _child("types", "sample.core.types", public=["sample.core.types:VALUE"]),
                ],
                [_rule("LOCAL-INTERFACE", "interface_boundary")],
            )
        },
        files={
            "sample/core/__init__.py": publisher,
            "sample/core/types.py": "VALUE = 1\n",
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
    unused = [item for item in diagnostics if item.code == "interface.unused"]
    assert (unused == []) is used


@pytest.mark.parametrize(
    ("case", "used"),
    [
        ("published", True),
        ("unpublished", False),
        ("rebound", False),
        ("outside", False),
        ("ambiguous", False),
    ],
)
def test_parent_reexport_chain_reaches_only_unique_local_targets(
    tmp_path: Path, case: str, used: bool
) -> None:
    parent_public = [] if case in {"unpublished", "outside"} else ["sample.core:Payload"]
    parent_source = "from sample.core.bridge import Payload\n__all__ = ['Payload']\n"
    if case == "rebound":
        parent_source = (
            "from sample.core.bridge import Payload\nPayload = 2\n__all__ = ['Payload']\n"
        )
    child_components = [_child("types", "sample.core.types", public=["sample.core.types:Payload"])]
    if case == "ambiguous":
        child_components.append(
            _child("duplicate", "sample.core.types", public=["sample.core.types:Payload"])
        )
    components = [
        _component("core", packages=["sample.core"], public=parent_public) | {"inside": "core.json"}
    ]
    files = {
        "sample/core/__init__.py": parent_source,
        "sample/core/bridge.py": "from sample.core.types import Payload\n__all__ = ['Payload']\n",
        "sample/core/types.py": "class Payload: pass\n",
    }
    if case == "outside":
        components.append(
            _component("facade", packages=["sample.facade"], public=["sample.facade:Payload"])
        )
        files["sample/core/__init__.py"] = ""
        files["sample/facade.py"] = parent_source

    _write_project(
        tmp_path,
        components=components,
        rules=[],
        insides={"core.json": _inside(child_components, [_rule("LOCAL", "interface_boundary")])},
        files=files,
    )

    result = _observe(tmp_path)
    assert result.observation is not None, result.diagnostics
    if case == "published":
        parent_import = next(
            record
            for record in result.observation.records("imports") or ()
            if record.data.get("source_module") == "sample.core"
        )
        assert parent_import.data.get("target_module") == "sample.core.bridge"
        assert "sample.core.types.Payload" in parent_import.data.get("reexport_chain", ())
    diagnostics = inside_diagnostics(
        tmp_path,
        parse_contract(json.loads((tmp_path / "contract.json").read_bytes())),
        ScanConfig(("sample",), "sample", "contract.json", "0" * 64),
        observation=result.observation,
    )
    unused = [
        item
        for item in diagnostics
        if item.code == "interface.unused" and item.subject == "sample.core.types:Payload"
    ]
    assert (unused == []) is used
