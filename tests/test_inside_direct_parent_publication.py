# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""An outside consumer reaches a nested API the ancestor publishes directly."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from test_analyzer import _component, _observe
from test_inside_publication import (
    _child,
    _inside,
    _rule,
    _write_project,
)

from archkeel.check.ports import ScanConfig
from archkeel.check.validation import inside_diagnostics
from archkeel.ir.codec import parse_contract
from archkeel.ir.trace import trace_valid_violations


def _inside_findings(tmp_path: Path):
    result = _observe(tmp_path)
    assert result.observation is not None, result.diagnostics
    diagnostics = inside_diagnostics(
        tmp_path,
        parse_contract(json.loads((tmp_path / "contract.json").read_bytes())),
        ScanConfig((".",), "sample", "contract.json", "0" * 64),
        observation=result.observation,
    )
    return result, diagnostics


@pytest.mark.parametrize(
    ("entry", "consumer"),
    [
        ("sample.core.api", "import sample.core.api\n"),
        ("sample.core.api:run", "from sample.core.api import run\n"),
    ],
    ids=["module-entry", "symbol-entry"],
)
def test_outside_consumer_uses_identical_ancestor_and_child_public_entry(
    tmp_path: Path, entry: str, consumer: str
) -> None:
    _write_project(
        tmp_path,
        components=[
            _component("core", packages=["sample.core"], public=[entry]) | {"inside": "core.json"},
            _component("client", packages=["sample.client"]),
        ],
        rules=[
            _rule("ROOT-INTERFACE", "interface_boundary"),
            _rule(
                "CLIENT-TO-CORE",
                "allowed_dependency",
                source="sample.client",
                target="sample.core",
            ),
        ],
        insides={
            "core.json": _inside(
                [_child("api", "sample.core.api", public=[entry])],
                [_rule("LOCAL-INTERFACE", "interface_boundary")],
            )
        },
        files={
            "sample/core/api.py": "def run() -> int:\n    return 1\n",
            "sample/client.py": consumer,
        },
    )

    _, diagnostics = _inside_findings(tmp_path)

    assert not [item for item in diagnostics if item.code == "interface.unused"]


def test_caller_in_common_ancestor_sibling_counts_as_local_use(tmp_path: Path) -> None:
    entry = "sample.core.api:run"
    _write_project(
        tmp_path,
        components=[
            _component("core", packages=["sample.core"], public=[entry]) | {"inside": "core.json"}
        ],
        rules=[_rule("ROOT-INTERFACE", "interface_boundary")],
        insides={
            "core.json": _inside(
                [
                    _child("api", "sample.core.api", public=[entry]),
                    _child("worker", "sample.core.worker"),
                ],
                [_rule("LOCAL-INTERFACE", "interface_boundary")],
            )
        },
        files={
            "sample/core/api.py": "def run() -> int:\n    return 1\n",
            "sample/core/worker.py": "from sample.core.api import run\n",
        },
    )

    _, diagnostics = _inside_findings(tmp_path)

    assert not [item for item in diagnostics if item.code == "interface.unused"]


@pytest.mark.parametrize(
    ("root_publishes", "middle_publishes", "used"),
    [
        (True, True, True),
        (True, False, False),
        (False, True, False),
    ],
    ids=["all-levels-publish", "middle-private", "root-private"],
)
def test_outside_consumer_reaches_direct_entry_at_every_nested_level(
    tmp_path: Path, root_publishes: bool, middle_publishes: bool, used: bool
) -> None:
    entry = "sample.core.service.api:run"
    _write_project(
        tmp_path,
        components=[
            _component("core", packages=["sample.core"], public=[entry] if root_publishes else [])
            | {"inside": "core.json"},
            _component("client", packages=["sample.client"]),
        ],
        rules=[
            _rule("ROOT-INTERFACE", "interface_boundary"),
            _rule(
                "CLIENT-TO-CORE",
                "allowed_dependency",
                source="sample.client",
                target="sample.core",
            ),
        ],
        insides={
            "core.json": _inside(
                [
                    _child(
                        "service",
                        "sample.core.service",
                        public=[entry] if middle_publishes else [],
                    )
                    | {"inside": "service.json"}
                ],
                [_rule("SERVICE-INTERFACE", "interface_boundary")],
            ),
            "service.json": _inside(
                [_child("api", "sample.core.service.api", public=[entry])],
                [_rule("API-INTERFACE", "interface_boundary")],
            ),
        },
        files={
            "sample/core/service/api.py": "def run() -> int:\n    return 1\n",
            "sample/client.py": "from sample.core.service.api import run\n",
        },
    )

    _, diagnostics = _inside_findings(tmp_path)

    unused = [item.subject for item in diagnostics if item.code == "interface.unused"]
    assert (unused == []) is used


@pytest.mark.parametrize(
    ("ancestor_public", "consumer"),
    [
        ([], ""),
        (["sample.core.api:other"], "from sample.core.api import run\n"),
    ],
    ids=["unused-grant", "wrong-name"],
)
def test_unreached_or_differently_published_child_entry_stays_unused(
    tmp_path: Path, ancestor_public: list[str], consumer: str
) -> None:
    entry = "sample.core.api:run"
    _write_project(
        tmp_path,
        components=[
            _component("core", packages=["sample.core"], public=ancestor_public)
            | {"inside": "core.json"},
            _component("client", packages=["sample.client"]),
        ],
        rules=[
            _rule("ROOT-INTERFACE", "interface_boundary"),
            _rule(
                "CLIENT-TO-CORE",
                "allowed_dependency",
                source="sample.client",
                target="sample.core",
            ),
        ],
        insides={
            "core.json": _inside(
                [_child("api", "sample.core.api", public=[entry])],
                [_rule("LOCAL-INTERFACE", "interface_boundary")],
            )
        },
        files={
            "sample/core/api.py": (
                "def run() -> int:\n    return 1\n\ndef other() -> int:\n    return 2\n"
            ),
            "sample/client.py": consumer,
        },
    )

    _, diagnostics = _inside_findings(tmp_path)

    assert [item.subject for item in diagnostics if item.code == "interface.unused"] == [entry]


@pytest.mark.parametrize(
    "module",
    [
        "sample.core.api",
        "sample.core.middle.api",
        "sample.core.middle.outer.api",
    ],
    ids=["private-immediate", "private-middle", "private-outer"],
)
def test_private_outside_access_is_still_rejected(tmp_path: Path, module: str) -> None:
    entry = "sample.core"
    module_path = module.replace(".", "/") + ".py"
    package_files = {
        "/".join(module.split(".")[:index]) + "/__init__.py": ""
        for index in range(2, len(module.split(".")))
    }
    _write_project(
        tmp_path,
        components=[
            _component("core", packages=["sample.core"], public=[entry]),
            _component("client", packages=["sample.client"]),
        ],
        rules=[_rule("ROOT-INTERFACE", "interface_boundary")],
        insides={},
        files={
            **package_files,
            module_path: "def _run() -> int:\n    return 1\n",
            "sample/client.py": f"from {module} import _run\n",
        },
    )

    result = _observe(tmp_path)
    assert result.observation is not None, result.diagnostics

    assert [item.rule_ids for item in trace_valid_violations(result.observation)] == [
        ("ROOT-INTERFACE",)
    ]


def test_underscore_entry_is_rejected_even_when_parent_and_child_match(
    tmp_path: Path,
) -> None:
    entry = "sample.core.api:_run"
    _write_project(
        tmp_path,
        components=[
            _component("core", packages=["sample.core"], public=[entry]) | {"inside": "core.json"}
        ],
        rules=[_rule("ROOT-INTERFACE", "interface_boundary")],
        insides={
            "core.json": _inside(
                [_child("api", "sample.core.api", public=[entry])],
                [_rule("LOCAL-INTERFACE", "interface_boundary")],
            )
        },
        files={
            "sample/core/api.py": "def _run() -> int:\n    return 1\n",
        },
    )

    diagnostics = inside_diagnostics(
        tmp_path,
        parse_contract(json.loads((tmp_path / "contract.json").read_bytes())),
        ScanConfig(("sample",), "sample", "contract.json", "0" * 64),
    )

    assert any(item.code == "reference.public_underscore" for item in diagnostics)


def test_planned_child_requires_promotion_when_outside_consumer_reaches_it(
    tmp_path: Path,
) -> None:
    entry = "sample.core.api:run"
    _write_project(
        tmp_path,
        components=[
            _component("core", packages=["sample.core"], public=[entry]) | {"inside": "core.json"},
            _component("client", packages=["sample.client"]),
        ],
        rules=[
            _rule("ROOT-INTERFACE", "interface_boundary"),
            _rule(
                "CLIENT-TO-CORE",
                "allowed_dependency",
                source="sample.client",
                target="sample.core",
            ),
        ],
        insides={
            "core.json": _inside(
                [
                    _child("api", "sample.core.api") | {"planned": [entry]},
                ],
                [_rule("LOCAL-INTERFACE", "interface_boundary")],
            )
        },
        files={
            "sample/core/api.py": "def run() -> int:\n    return 1\n",
            "sample/client.py": "from sample.core.api import run\n",
        },
    )

    _, diagnostics = _inside_findings(tmp_path)

    assert [(item.code, item.subject) for item in diagnostics] == [
        ("interface.planned_built", entry)
    ]


def test_parent_publication_does_not_allow_a_forbidden_outside_edge(
    tmp_path: Path,
) -> None:
    entry = "sample.core.api:run"
    _write_project(
        tmp_path,
        components=[
            _component("core", packages=["sample.core"], public=[entry]) | {"inside": "core.json"},
            _component("client", packages=["sample.client"]),
        ],
        rules=[
            _rule("ROOT-INTERFACE", "interface_boundary"),
            _rule(
                "NO-CLIENT-TO-CORE",
                "forbidden_dependency",
                source="sample.client",
                target="sample.core",
                include_type_checking=True,
            ),
        ],
        insides={
            "core.json": _inside(
                [_child("api", "sample.core.api", public=[entry])],
                [_rule("LOCAL-INTERFACE", "interface_boundary")],
            )
        },
        files={
            "sample/core/api.py": "def run() -> int:\n    return 1\n",
            "sample/client.py": "from sample.core.api import run\n",
        },
    )

    result = _observe(tmp_path)
    assert result.observation is not None, result.diagnostics

    assert [item.rule_ids for item in trace_valid_violations(result.observation)] == [
        ("NO-CLIENT-TO-CORE",)
    ]


def test_parent_publication_does_not_resolve_ambiguous_child_ownership(
    tmp_path: Path,
) -> None:
    entry = "sample.core.api:run"
    _write_project(
        tmp_path,
        components=[
            _component("core", packages=["sample.core"], public=[entry]) | {"inside": "core.json"},
            _component("client", packages=["sample.client"]),
        ],
        rules=[
            _rule("ROOT-INTERFACE", "interface_boundary"),
            _rule(
                "CLIENT-TO-CORE",
                "allowed_dependency",
                source="sample.client",
                target="sample.core",
            ),
        ],
        insides={
            "core.json": _inside(
                [
                    _child("api", "sample.core.api", public=[entry]),
                    _child("duplicate", "sample.core.api", public=[entry]),
                ],
                [_rule("LOCAL-INTERFACE", "interface_boundary")],
            )
        },
        files={
            "sample/core/api.py": "def run() -> int:\n    return 1\n",
            "sample/client.py": "from sample.core.api import run\n",
        },
    )

    _, diagnostics = _inside_findings(tmp_path)

    assert len([item for item in diagnostics if item.code == "interface.unused"]) == 2


def test_out_of_parent_sibling_claim_cannot_consume_a_private_api(tmp_path: Path) -> None:
    entry = "sample.core.service.api:run"
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
                    _child("service", "sample.core.service", public=[entry])
                    | {"inside": "service.json"},
                    _child("escaped", "sample.client"),
                ],
                [_rule("CORE-INTERFACE", "interface_boundary")],
            ),
            "service.json": _inside(
                [_child("api", "sample.core.service.api", public=[entry])],
                [_rule("SERVICE-INTERFACE", "interface_boundary")],
            ),
        },
        files={
            "sample/core/service/api.py": "def run() -> int:\n    return 1\n",
            "sample/client.py": "from sample.core.service.api import run\n",
        },
    )

    result, diagnostics = _inside_findings(tmp_path)

    unused = [item for item in diagnostics if item.code == "interface.unused"]
    assert {item.pointer for item in unused} == {
        "/components/0/inside/components/0/public/0",
        "/components/0/inside/components/0/inside/components/0/public/0",
    }
    assert any(
        item.rule_ids == ("ROOT-INTERFACE",) for item in trace_valid_violations(result.observation)
    )


def test_ambiguous_local_caller_cannot_fall_back_to_root_publication(tmp_path: Path) -> None:
    entry = "sample.core.service.api:run"
    _write_project(
        tmp_path,
        components=[
            _component("core", packages=["sample.core"], public=[entry]) | {"inside": "core.json"}
        ],
        rules=[],
        insides={
            "core.json": _inside(
                [
                    _child("service", "sample.core.service", public=[entry])
                    | {"inside": "service.json"},
                    _child("client", "sample.core.client"),
                    _child("duplicate", "sample.core.client"),
                ],
                [_rule("CORE-INTERFACE", "interface_boundary")],
            ),
            "service.json": _inside(
                [_child("api", "sample.core.service.api", public=[entry])],
                [_rule("SERVICE-INTERFACE", "interface_boundary")],
            ),
        },
        files={
            "sample/core/client.py": "from sample.core.service.api import run\n",
            "sample/core/service/api.py": "def run() -> int:\n    return 1\n",
        },
    )

    result = _observe(tmp_path)
    assert result.observation is not None, result.diagnostics
    contract = parse_contract(json.loads((tmp_path / "contract.json").read_bytes()))
    diagnostics = inside_diagnostics(
        tmp_path,
        contract,
        ScanConfig((".",), "sample", "contract.json", "0" * 64),
        observation=result.observation,
    )

    leaf_entry = [
        item
        for item in diagnostics
        if item.code == "interface.unused"
        and item.pointer == "/components/0/inside/components/0/inside/components/0/public/0"
    ]
    assert len(leaf_entry) == 1


def test_out_of_parent_target_claim_cannot_suppress_deep_interface_missing(
    tmp_path: Path,
) -> None:
    entry = "sample.foreign.api:run"
    _write_project(
        tmp_path,
        components=[
            _component("core", packages=["sample.core"], public=[]) | {"inside": "core.json"},
            _component("foreign", packages=["sample.foreign"], public=[]),
        ],
        rules=[_rule("ROOT-INTERFACE", "interface_boundary")],
        insides={
            "core.json": _inside(
                [
                    _child("escaped", "sample.foreign") | {"inside": "foreign.json"},
                ],
                [_rule("CORE-INTERFACE", "interface_boundary")],
            ),
            "foreign.json": _inside(
                [
                    _child("api", "sample.foreign.api", public=[entry]),
                    _child("client", "sample.foreign.client"),
                ],
                [_rule("FOREIGN-INTERFACE", "interface_boundary")],
            ),
        },
        files={
            "sample/foreign/api.py": "def run() -> int:\n    return 1\n",
            "sample/foreign/client.py": "from sample.foreign.api import run\n",
        },
    )

    _, diagnostics = _inside_findings(tmp_path)

    assert any(
        item.code == "interface.missing"
        and item.pointer == "/components/0/inside/components/0/inside/components/0/public/0"
        for item in diagnostics
    )


def test_out_of_ancestor_source_claim_cannot_consume_deep_api(tmp_path: Path) -> None:
    entry = "sample.core.service.api:run"
    _write_project(
        tmp_path,
        components=[
            _component("core", packages=["sample.core"], public=[]) | {"inside": "core.json"},
            _component("foreign", packages=["sample.foreign"], public=[]),
        ],
        rules=[_rule("ROOT-INTERFACE", "interface_boundary")],
        insides={
            "core.json": _inside(
                [
                    _child("service", "sample.core.service", public=[entry])
                    | {
                        "packages": ["sample.core.service", "sample.foreign"],
                        "inside": "service.json",
                    }
                ],
                [_rule("CORE-INTERFACE", "interface_boundary")],
            ),
            "service.json": _inside(
                [
                    _child("api", "sample.core.service.api", public=[entry]),
                    _child("client", "sample.foreign.client"),
                ],
                [_rule("SERVICE-INTERFACE", "interface_boundary")],
            ),
        },
        files={
            "sample/core/service/api.py": "def run() -> int:\n    return 1\n",
            "sample/foreign/client.py": "from sample.core.service.api import run\n",
        },
    )

    _, diagnostics = _inside_findings(tmp_path)

    assert any(
        item.code == "interface.unused"
        and item.pointer == "/components/0/inside/components/0/inside/components/0/public/0"
        for item in diagnostics
    )


def test_ancestor_facade_with_all_excluding_name_does_not_publish_child_entry(
    tmp_path: Path,
) -> None:
    entry = "sample.core.api:run"
    _write_project(
        tmp_path,
        components=[
            _component("core", packages=["sample.core"], public=["sample.core"])
            | {"inside": "core.json"},
            _component("client", packages=["sample.client"]),
        ],
        rules=[
            _rule("ROOT-INTERFACE", "interface_boundary"),
            _rule(
                "CLIENT-TO-CORE",
                "allowed_dependency",
                source="sample.client",
                target="sample.core",
            ),
        ],
        insides={
            "core.json": _inside(
                [_child("api", "sample.core.api", public=[entry])],
                [_rule("LOCAL-INTERFACE", "interface_boundary")],
            )
        },
        files={
            "sample/core/__init__.py": (
                "from sample.core.api import run\n__all__ = ['other']\nother = 2\n"
            ),
            "sample/core/api.py": "def run() -> int:\n    return 1\n",
            "sample/client.py": "from sample.core.api import run\n",
        },
    )

    result = _observe(tmp_path)
    assert result.observation is not None, result.diagnostics
    contract = parse_contract(json.loads((tmp_path / "contract.json").read_bytes()))
    diagnostics = inside_diagnostics(
        tmp_path,
        contract,
        ScanConfig((".",), "sample", "contract.json", "0" * 64),
        observation=result.observation,
    )

    assert any(item.code == "interface.unused" and item.subject == entry for item in diagnostics)
