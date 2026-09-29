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
from archkeel.check.validation import (
    COMPONENT_GRAPH_MARKER,
    inside_diagnostics,
    interface_diagnostics,
    run_validate,
)
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


def _generic_facade_diagnostics(
    tmp_path: Path,
    api: str,
    *,
    extra_packages: tuple[str, ...] = (),
    extra_files: dict[str, str] | None = None,
) -> tuple[list[str], list[str], tuple[object, ...], tuple[object, ...]]:
    payload = "sample.models:Payload"
    noise = "sample.models:Noise"
    unrelated = "sample.models:Unrelated"
    contract = {
        "schema_version": "2.1.0",
        "components": [
            _component(
                "core",
                packages=["sample.api", "sample.models", *extra_packages],
                public=["sample.api:Child", payload, noise, unrelated],
            ),
            _component("client", packages=["sample.client"]),
        ],
        "rules": [
            _rule("INTERFACE", "interface_boundary"),
            _rule("TYPES", "boundary_types", source="sample.api"),
        ],
    }
    _write_project(
        tmp_path,
        components=contract["components"],
        rules=contract["rules"],
        insides={},
        files={
            "sample/models.py": ("class Payload: pass\nclass Noise: pass\nclass Unrelated: pass\n"),
            "sample/api.py": api,
            "sample/client.py": "from sample.api import Child\nVALUE = Child()\n",
            **(extra_files or {}),
        },
    )
    result = _observe(tmp_path)
    assert result.observation is not None, result.diagnostics
    diagnostics = interface_diagnostics(parse_contract(contract), result.observation)
    unused = [item.subject for item in diagnostics if item.code == "interface.unused"]
    usage_unknown = tuple(item for item in diagnostics if item.code == "interface.usage_unknown")
    facade_types = [
        name
        for item in result.observation.records("symbols") or ()
        if item.data.get("qualified_name") == "sample.api.Child"
        for name in item.data.get("facade_types", ())
    ]
    return unused, facade_types, tuple(result.observation.records("unknowns") or ()), usage_unknown


def test_inherited_generic_return_reaches_the_concrete_model(tmp_path: Path) -> None:
    unused, facade_types, unknowns, _ = _generic_facade_diagnostics(
        tmp_path,
        "from typing import Generic, TypeVar\n"
        "from sample.models import Payload\n"
        "T = TypeVar('T')\n"
        "class Base(Generic[T]):\n"
        "    def get(self) -> T: ...\n"
        "class Child(Base[Payload]):\n"
        "    pass\n",
    )

    assert "sample.models:Payload" not in unused
    assert "sample.models.Payload" in facade_types
    assert "sample.models:Noise" in unused
    assert "sample.models.Noise" not in facade_types
    assert any(
        item.kind == "boundary_type_position"
        and item.data.get("position") == "inherited methods"
        and item.data.get("qualified_name") == "sample.api.Child.__inherited_methods__"
        for item in unknowns
    )


def test_reexported_generic_base_substitutes_only_the_used_typevar(tmp_path: Path) -> None:
    unused, facade_types, unknowns, _ = _generic_facade_diagnostics(
        tmp_path,
        "from sample.models import Payload, Noise\n"
        "from sample.base import Base\n"
        "class Child(Base[Payload, Noise]):\n"
        "    pass\n",
        extra_packages=("sample.base",),
        extra_files={
            "sample/base/__init__.py": "from sample.base.impl import Base\n__all__ = ['Base']\n",
            "sample/base/impl.py": (
                "from typing import Generic, TypeVar\n"
                "T = TypeVar('T')\n"
                "U = TypeVar('U')\n"
                "class Base(Generic[T, U]):\n"
                "    def get(self) -> list[T]: ...\n"
                "T = str\n"
            ),
        },
    )

    assert "sample.models.Payload" in facade_types
    assert "sample.models.Noise" not in facade_types
    assert "sample.models:Payload" not in unused
    assert "sample.models:Noise" in unused
    assert any(
        item.kind == "boundary_type_position" and item.data.get("position") == "inherited methods"
        for item in unknowns
    )


@pytest.mark.parametrize(
    ("method", "override"),
    [
        ("def get(self) -> T: ...", "def get(self) -> str: ..."),
        ("def _get(self) -> T: ...", ""),
    ],
    ids=["subclass-override", "private-inherited-method"],
)
def test_generic_override_and_private_method_do_not_publish_base_type(
    tmp_path: Path, method: str, override: str
) -> None:
    api = (
        "from typing import Generic, TypeVar\n"
        "from sample.models import Payload\n"
        "T = TypeVar('T')\n"
        "class Base(Generic[T]):\n"
        f"    {method}\n"
        "class Child(Base[Payload]):\n"
    )
    api += f"    {override}\n" if override else "    pass\n"
    unused, facade_types, unknowns, _ = _generic_facade_diagnostics(tmp_path, api)

    assert "sample.models:Payload" in unused
    assert "sample.models.Payload" not in facade_types
    assert any(
        item.kind == "boundary_type_position"
        and item.data.get("position") == "inherited methods"
        and item.data.get("qualified_name") == "sample.api.Child.__inherited_methods__"
        for item in unknowns
    )


def test_class_body_non_method_override_blocks_inherited_method_publication(
    tmp_path: Path,
) -> None:
    unused, facade_types, _, _ = _generic_facade_diagnostics(
        tmp_path,
        "from typing import Generic, TypeVar\n"
        "from sample.models import Payload\n"
        "T = TypeVar('T')\n"
        "class Base(Generic[T]):\n"
        "    def get(self) -> T: ...\n"
        "class Child(Base[Payload]):\n"
        "    get = None\n",
    )

    assert "sample.models:Payload" in unused
    assert "sample.models.Payload" not in facade_types


def test_overload_implementation_does_not_publish_its_return_type(tmp_path: Path) -> None:
    unused, facade_types, _, _ = _generic_facade_diagnostics(
        tmp_path,
        "from typing import Generic, TypeVar, overload\n"
        "from sample.models import Payload, Noise\n"
        "T = TypeVar('T')\n"
        "class Base(Generic[T]):\n"
        "    @overload\n"
        "    def get(self) -> T: ...\n"
        "    def get(self) -> Noise: ...\n"
        "class Child(Base[Payload]):\n"
        "    pass\n",
    )

    assert "sample.models:Payload" not in unused
    assert "sample.models.Payload" in facade_types
    assert "sample.models.Noise" not in facade_types


def test_ambiguous_generic_argument_not_named_in_signature_remains_unused(
    tmp_path: Path,
) -> None:
    unused, _, _, usage_unknown = _generic_facade_diagnostics(
        tmp_path,
        "from typing import Generic, TypeVar\n"
        "from sample.models import Payload, Noise\n"
        "T = TypeVar('T')\n"
        "U = TypeVar('U')\n"
        "class First(Generic[T]):\n"
        "    def get(self) -> T: ...\n"
        "class Second(Generic[U]):\n"
        "    def get(self) -> int: ...\n"
        "class Child(First[Payload], Second[Noise]):\n"
        "    pass\n",
    )

    assert {item.subject for item in usage_unknown} == {"sample.models:Payload"}
    assert "sample.models:Noise" in unused


def test_proven_import_wins_over_ambiguous_inherited_candidate(tmp_path: Path) -> None:
    unused, _, _, usage_unknown = _generic_facade_diagnostics(
        tmp_path,
        "from typing import Generic, TypeVar\n"
        "from sample.models import Payload, Noise\n"
        "T = TypeVar('T')\n"
        "U = TypeVar('U')\n"
        "class First(Generic[T]):\n"
        "    def get(self) -> T: ...\n"
        "class Second(Generic[U]):\n"
        "    def get(self) -> U: ...\n"
        "class Child(First[Payload], Second[Noise]):\n"
        "    pass\n",
        extra_files={"sample/client.py": "from sample.models import Payload\n"},
    )

    assert "sample.models:Payload" not in unused
    assert {item.subject for item in usage_unknown} == {"sample.models:Noise"}


def test_inherited_overload_findings_keep_distinct_ids(tmp_path: Path) -> None:
    contract = {
        "schema_version": "2.1.0",
        "components": [
            _component(
                "api",
                packages=["sample.api", "sample.models"],
                public=["sample.api:Child"],
            ),
            _component("client", packages=["sample.client"]),
        ],
        "rules": [_rule("TYPES", "boundary_types", source="sample.api")],
    }
    _write_project(
        tmp_path,
        components=contract["components"],
        rules=contract["rules"],
        insides={},
        files={
            "sample/models.py": "class ForeignA: pass\nclass ForeignB: pass\nclass Payload: pass\n",
            "sample/api.py": (
                "from typing import Generic, TypeVar, overload\n"
                "from sample.models import ForeignA, ForeignB, Payload\n"
                "T = TypeVar('T')\n"
                "class Base(Generic[T]):\n"
                "    @overload\n"
                "    def get(self, payload: ForeignA) -> ForeignA: ...\n"
                "    @overload\n"
                "    def get(self, payload: ForeignB) -> ForeignB: ...\n"
                "    def get(self, payload: object) -> object: ...\n"
                "class Child(Base[Payload]):\n"
                "    pass\n"
            ),
            "sample/client.py": "from sample.api import Child\nVALUE = Child()\n",
        },
    )
    result = _observe(tmp_path)

    assert result.observation is not None, result.diagnostics
    violations = [
        item
        for item in result.observation.records("violations") or ()
        if item.kind == "boundary_types"
    ]
    assert len(violations) == 4
    assert len({item.id for item in violations}) == 4
    assert {item.data.get("position") for item in violations} == {"payload", "return"}
    [limit] = [
        item
        for item in result.observation.records("unknowns") or ()
        if item.kind == "boundary_type_limit"
    ]
    assert (
        limit.data.get("positions"),
        limit.data.get("decided"),
        limit.data.get("undecided"),
    ) == (5, 4, 1)


@pytest.mark.parametrize(
    ("base_body", "child_body"),
    [
        ("payload: T", "pass"),
        ("def __init__(self, payload: T) -> None: ...", "pass"),
    ],
    ids=["inherited-field", "inherited-constructor"],
)
def test_inherited_fields_and_constructor_parameters_block_unused_without_publication(
    tmp_path: Path, base_body: str, child_body: str
) -> None:
    unused, facade_types, unknowns, usage_unknown = _generic_facade_diagnostics(
        tmp_path,
        "from typing import Generic, TypeVar\n"
        "from sample.models import Payload\n"
        "T = TypeVar('T')\n"
        "class Base(Generic[T]):\n"
        f"    {base_body}\n"
        "class Child(Base[Payload]):\n"
        f"    {child_body}\n",
    )

    assert "sample.models:Payload" not in unused
    assert {item.subject for item in usage_unknown} == {"sample.models:Payload"}
    assert "sample.models.Payload" not in facade_types
    assert any(
        item.kind == "boundary_type_position"
        and item.data.get("position") == "inherited methods"
        and item.data.get("reason") == "inherited_surface"
        for item in unknowns
    )


@pytest.mark.parametrize(
    ("base_body", "child_body"),
    [
        ("payload: T", "payload: str"),
        ("def __init__(self, payload: T) -> None: ...", "def __init__(self) -> None: ..."),
    ],
    ids=["field-shadow", "constructor-shadow"],
)
def test_subclass_field_or_constructor_shadows_inherited_candidate(
    tmp_path: Path, base_body: str, child_body: str
) -> None:
    unused, _, _, usage_unknown = _generic_facade_diagnostics(
        tmp_path,
        "from typing import Generic, TypeVar\n"
        "from sample.models import Payload\n"
        "T = TypeVar('T')\n"
        "class Base(Generic[T]):\n"
        f"    {base_body}\n"
        "class Child(Base[Payload]):\n"
        f"    {child_body}\n",
    )

    assert "sample.models:Payload" in unused
    assert usage_unknown == ()


def test_conditional_class_body_override_withholds_inherited_publication(tmp_path: Path) -> None:
    unused, facade_types, _, usage_unknown = _generic_facade_diagnostics(
        tmp_path,
        "from typing import Generic, TypeVar\n"
        "from sample.models import Payload\n"
        "T = TypeVar('T')\n"
        "class Base(Generic[T]):\n"
        "    def get(self) -> T: ...\n"
        "class Child(Base[Payload]):\n"
        "    if True:\n"
        "        def get(self) -> int: ...\n",
    )

    assert "sample.models:Payload" not in unused
    assert "sample.models.Payload" not in facade_types
    assert {item.subject for item in usage_unknown} == {"sample.models:Payload"}


def test_except_star_class_body_override_withholds_inherited_publication(tmp_path: Path) -> None:
    unused, facade_types, _, usage_unknown = _generic_facade_diagnostics(
        tmp_path,
        "from typing import Generic, TypeVar\n"
        "from sample.models import Payload\n"
        "T = TypeVar('T')\n"
        "class Base(Generic[T]):\n"
        "    def get(self) -> T: ...\n"
        "class Child(Base[Payload]):\n"
        "    try:\n"
        "        pass\n"
        "    except* Exception:\n"
        "        def get(self) -> int: ...\n",
    )

    assert "sample.models:Payload" not in unused
    assert "sample.models.Payload" not in facade_types
    assert {item.subject for item in usage_unknown} == {"sample.models:Payload"}


@pytest.mark.parametrize(
    ("api", "expected_unused", "expected_unknown", "ambiguous"),
    [
        (
            "from typing import Generic, TypeVar\n"
            "from sample.models import Payload\n"
            "T = TypeVar('T')\n"
            "class Base(Generic[T]):\n"
            "    def get(self) -> int: ...\n"
            "class Child(Base[Payload]):\n"
            "    pass\n",
            ["sample.models:Payload", "sample.models:Noise", "sample.models:Unrelated"],
            False,
            False,
        ),
        (
            "from typing import Generic, TypeVar\n"
            "from sample.models import Payload\n"
            "T = TypeVar('T')\n"
            "class Base(Generic[T]):\n"
            "    def get(self) -> T: ...\n"
            "Payload = object\n"
            "class Child(Base[Payload]):\n"
            "    pass\n",
            ["sample.models:Payload", "sample.models:Noise", "sample.models:Unrelated"],
            True,
            False,
        ),
        (
            "from typing import Generic, TypeVar\n"
            "from sample.models import Payload, Noise\n"
            "T = TypeVar('T')\n"
            "U = TypeVar('U')\n"
            "class First(Generic[T]):\n"
            "    def get(self) -> T: ...\n"
            "class Second(Generic[U]):\n"
            "    def get(self) -> U: ...\n"
            "class Child(First[Payload], Second[Noise]):\n"
            "    pass\n",
            ["sample.models:Unrelated"],
            True,
            True,
        ),
        (
            "from typing import Generic, TypeVar\n"
            "from sample.models import Payload\n"
            "T = TypeVar('T')\n"
            "class Base(Generic[T]):\n"
            "    def get(self) -> T: ...\n"
            "class Child(Base[T]):\n"
            "    pass\n",
            ["sample.models:Payload", "sample.models:Noise", "sample.models:Unrelated"],
            True,
            False,
        ),
    ],
    ids=[
        "unrelated-generic-argument",
        "rebound-base-argument",
        "ambiguous-bases",
        "unresolved-substitution",
    ],
)
def test_unproven_inherited_generic_return_does_not_reach_models(
    tmp_path: Path,
    api: str,
    expected_unused: list[str],
    expected_unknown: bool,
    ambiguous: bool,
) -> None:
    unused, facade_types, unknowns, usage_unknown = _generic_facade_diagnostics(tmp_path, api)

    assert set(unused) == set(expected_unused)
    if ambiguous:
        assert "sample.models:Payload" not in unused
        assert "sample.models:Noise" not in unused
        assert "sample.models.Payload" not in facade_types
        assert "sample.models.Noise" not in facade_types
        assert {item.subject for item in usage_unknown} == {
            "sample.models:Payload",
            "sample.models:Noise",
        }
    if expected_unknown:
        assert any(
            item.kind == "boundary_type_position"
            and item.data.get("position") == "inherited methods"
            and item.data.get("reason") == "inherited_surface"
            for item in unknowns
        )


def test_nested_inherited_generic_return_reaches_the_mounted_model(tmp_path: Path) -> None:
    _write_project(
        tmp_path,
        components=[
            _component(
                "core",
                packages=["sample.core"],
                public=["sample.core.models:Payload"],
            )
            | {"inside": "core.json"}
        ],
        rules=[_rule("ROOT", "interface_boundary")],
        insides={
            "core.json": _inside(
                [
                    _child(
                        "api",
                        "sample.core.api",
                        public=["sample.core.api:Child", "sample.core.models:Payload"],
                    )
                    | {"packages": ["sample.core.api", "sample.core.models"]},
                    _child("client", "sample.core.client"),
                ],
                [_rule("LOCAL", "interface_boundary")],
            )
        },
        files={
            "sample/core/models.py": "class Payload: pass\n",
            "sample/core/api.py": (
                "from typing import Generic, TypeVar\n"
                "from sample.core.models import Payload\n"
                "T = TypeVar('T')\n"
                "class Base(Generic[T]):\n"
                "    def get(self) -> T: ...\n"
                "class Child(Base[Payload]):\n"
                "    pass\n"
            ),
            "sample/core/client.py": "from sample.core.api import Child\nVALUE = Child()\n",
        },
    )

    result = _observe(tmp_path)
    assert result.observation is not None, result.diagnostics
    contract = parse_contract(json.loads((tmp_path / "contract.json").read_bytes()))
    root_diagnostics = interface_diagnostics(contract, result.observation)
    assert [
        (item.code, item.subject) for item in root_diagnostics if item.code == "interface.unused"
    ] == [("interface.unused", "sample.core.models:Payload")]
    nested_diagnostics = inside_diagnostics(
        tmp_path,
        contract,
        ScanConfig(("sample",), "sample", "contract.json", "0" * 64),
        observation=result.observation,
    )
    assert not any(
        item.code == "interface.unused" and item.subject == "sample.core.models:Payload"
        for item in nested_diagnostics
    )


def test_undeclared_model_returned_by_inherited_generic_is_a_boundary_violation(
    tmp_path: Path,
) -> None:
    contract = {
        "schema_version": "2.1.0",
        "components": [
            _component("app", packages=["sample.api"], public=["sample.api:Child"]),
            _component("models", packages=["sample.models"]),
            _component("client", packages=["sample.client"]),
        ],
        "rules": [_rule("APP-TYPES-NOT-DICT", "boundary_types", source="sample.api")],
    }
    _write_project(
        tmp_path,
        components=contract["components"],
        rules=contract["rules"],
        insides={},
        files={
            "sample/models.py": "class Extra: pass\n",
            "sample/api.py": (
                "from typing import Generic, TypeVar\n"
                "from sample.models import Extra\n"
                "T = TypeVar('T')\n"
                "class Base(Generic[T]):\n"
                "    def get(self) -> T: ...\n"
                "class Child(Base[Extra]):\n"
                "    pass\n"
            ),
            "sample/client.py": "from sample.api import Child\nVALUE = Child().get()\n",
        },
    )

    result = _observe(tmp_path)
    assert result.observation is not None, result.diagnostics
    violations = [
        item
        for item in trace_valid_violations(result.observation)
        if item.rule_ids == ("APP-TYPES-NOT-DICT",)
    ]

    assert len(violations) == 1
    assert violations[0].data.get("qualified_name") == "sample.api.Child.get"
    assert "__inherited_methods__" not in str(violations[0].data.get("qualified_name"))
