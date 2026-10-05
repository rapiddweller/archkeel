# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Ancestor publication survives exact ownership of its initializer (#338)."""

import json
from pathlib import Path

import pytest
from test_analyzer import _component, _observe
from test_recursive_inside_independent_contracts import _commit_tree, _scan_config

from archkeel.check.validation import COMPONENT_GRAPH_MARKER, run_validate
from archkeel.cli.observe import observe

_MODULE = "sample.provider.factory"
_POINTER = "/components/0/inside/components/0/public/0"
_RULE = {
    "id": "INTERFACE",
    "kind": "interface_boundary",
    "rationale": "Require intentional APIs.",
    "provenance": ["docs/architecture/sample.md"],
    "decided_by": "architect",
}


def _published_provider(root: Path, entry: str, *, case: str = "published") -> None:
    (root / "sample/provider").mkdir(parents=True)
    (root / "contracts").mkdir()
    (root / "docs/architecture").mkdir(parents=True)
    name = "_run" if case == "private" else "run"
    (root / "sample/provider/factory.py").write_text(f"def {name}() -> str:\n    return 'ok'\n")
    initializer = f"from sample.provider.factory import {name}\n__all__ = ['{name}']\n"
    if case == "ambiguous":
        initializer += f"from sample.provider.factory import {name}\n"
    elif case == "overwritten":
        initializer += f"{name} = choose()\n"
    (root / "sample/provider/__init__.py").write_text(initializer)
    (root / "sample/consumer.py").write_text(
        f"from sample.provider import {name}\nVALUE = {name}()\n"
    )
    (root / "pyproject.toml").write_text('[project]\nrequires-python = ">=3.11"\n')
    (root / "docs/architecture/sample.md").write_text(
        f"{COMPONENT_GRAPH_MARKER}\n```mermaid\ngraph TD\n consumer --> provider\n```\n"
    )
    provider = _component(
        "provider",
        packages=["sample.provider"],
        public=[] if case == "unpublished" else ["sample.provider"],
    )
    provider["inside"] = "contracts/inner.json"
    (root / "contract.json").write_text(
        json.dumps(
            {
                "schema_version": "2.1.0",
                "components": [
                    provider,
                    _component("consumer", packages=["sample.consumer"], public=[]),
                ],
                "rules": [_RULE],
            }
        )
    )
    (root / "contracts/inner.json").write_text(
        json.dumps(
            {
                "schema_version": "2.1.0",
                "components": [
                    _component("factory", packages=[_MODULE], public=[entry]),
                ],
                "rules": [_RULE],
            }
        )
    )
    _commit_tree(root)


def _assign_initializer(root: Path) -> None:
    path = root / "contracts/inner.json"
    contract = json.loads(path.read_text())
    contract["components"][0]["exact_modules"] = ["sample.provider"]
    path.write_text(json.dumps(contract))


@pytest.mark.parametrize("entry", [_MODULE, f"{_MODULE}:run"])
def test_exact_initializer_keeps_proven_external_provider_use(tmp_path: Path, entry: str) -> None:
    _published_provider(tmp_path, entry)
    before, _ = run_validate(tmp_path, _scan_config(), observe)
    before_observed = _observe(tmp_path)
    assert before_observed.observation is not None, before_observed.diagnostics
    _assign_initializer(tmp_path)

    after, _ = run_validate(tmp_path, _scan_config(), observe)
    after_observed = _observe(tmp_path)
    assert after_observed.observation is not None, after_observed.diagnostics
    for observation in (before_observed.observation, after_observed.observation):
        record = next(
            item
            for item in observation.records("imports") or ()
            if item.data.get("source_module") == "sample.consumer"
        )
        assert record.id == "IMP-46c5aeef9d152f4f"
        assert record.data.get("reexport_chain") == (
            "sample.provider.run",
            "sample.provider.factory.run",
        )
        assert record.data.get("symbols_known") is True
        assert record.data.get("source_binding_unique") is True
    assert [(item.code, item.pointer, item.subject) for item in after.diagnostics] == [
        ("decision.open", "/components", "2 open dependency decisions"),
    ]
    assert after.diagnostics == before.diagnostics


@pytest.mark.parametrize("case", ["private", "unpublished"])
def test_exact_initializer_does_not_publish_private_or_unpublished_routes(
    tmp_path: Path,
    case: str,
) -> None:
    _published_provider(tmp_path, _MODULE, case=case)
    for exact in (False, True):
        if exact:
            _assign_initializer(tmp_path)
        result, _ = run_validate(tmp_path, _scan_config(), observe)
        assert [(item.code, item.pointer, item.subject) for item in result.diagnostics] == [
            ("decision.open", "/components", "2 open dependency decisions"),
            ("interface.unused", _POINTER, _MODULE),
            ("rule.violated", "/rules/0", "INTERFACE"),
        ]


@pytest.mark.parametrize("entry", [_MODULE, f"{_MODULE}:run"])
@pytest.mark.parametrize("case", ["ambiguous", "overwritten"])
def test_exact_initializer_retains_unproven_provider_candidates_as_unknown(
    tmp_path: Path,
    entry: str,
    case: str,
) -> None:
    _published_provider(tmp_path, entry, case=case)
    for exact in (False, True):
        if exact:
            _assign_initializer(tmp_path)
        result, _ = run_validate(tmp_path, _scan_config(), observe)
        observed = _observe(tmp_path)
        assert observed.observation is not None, observed.diagnostics
        record = next(
            item
            for item in observed.observation.records("imports") or ()
            if item.data.get("source_module") == "sample.consumer"
        )
        assert record.id == "IMP-46c5aeef9d152f4f"
        assert record.data.get("reexport_chain") == ("sample.provider.run",)
        assert record.data.get("reexport_candidates") == ("sample.provider.factory.run",)
        assert [(item.code, item.pointer, item.subject) for item in result.diagnostics] == [
            ("decision.open", "/components", "2 open dependency decisions"),
            ("interface.usage_unknown", _POINTER, entry),
        ]


def test_external_use_does_not_leak_between_mounts_with_the_same_child_label(
    tmp_path: Path,
) -> None:
    _published_provider(tmp_path, _MODULE)
    _assign_initializer(tmp_path)
    outer_path = tmp_path / "contract.json"
    outer = json.loads(outer_path.read_text())
    other = _component("other", packages=["sample.other"], public=["sample.other.provider"])
    other["inside"] = "contracts/other.json"
    outer["components"].append(other)
    outer_path.write_text(json.dumps(outer))
    (tmp_path / "sample/other/provider").mkdir(parents=True)
    (tmp_path / "sample/other/provider/factory.py").write_text(
        "def run() -> str:\n    return 'ok'\n"
    )
    (tmp_path / "sample/other/provider/__init__.py").write_text(
        "from sample.other.provider.factory import run\n__all__ = ['run']\n"
    )
    inner = json.loads((tmp_path / "contracts/inner.json").read_text())
    inner["components"][0]["packages"] = ["sample.other.provider.factory"]
    inner["components"][0]["exact_modules"] = ["sample.other.provider"]
    inner["components"][0]["public"] = ["sample.other.provider.factory"]
    (tmp_path / "contracts/other.json").write_text(json.dumps(inner))

    result, _ = run_validate(tmp_path, _scan_config(), observe)

    assert [
        (item.code, item.pointer, item.subject)
        for item in result.diagnostics
        if item.code and item.code.startswith("interface.")
    ] == [
        (
            "interface.unused",
            "/components/2/inside/components/0/public/0",
            "sample.other.provider.factory",
        ),
        ("interface.unused", "/components/2/public/0", "sample.other.provider"),
    ]


def test_duplicate_initializer_ownership_still_fails_assignment(tmp_path: Path) -> None:
    _published_provider(tmp_path, _MODULE)
    _assign_initializer(tmp_path)
    path = tmp_path / "contracts/inner.json"
    inner = json.loads(path.read_text())
    duplicate = _component("duplicate", public=[])
    duplicate["packages"] = []
    duplicate["exact_modules"] = ["sample.provider"]
    inner["components"].append(duplicate)
    inner["rules"].append(
        _RULE | {"id": "ASSIGN", "kind": "complete_assignment", "source": "sample.provider"}
    )
    path.write_text(json.dumps(inner))

    result, _ = run_validate(tmp_path, _scan_config(), observe)

    assert result.exit_code == 2
    assert any(
        item.code == "rule.violated" and item.subject == "provider:ASSIGN"
        for item in result.diagnostics
    )


def test_missing_provider_owner_does_not_turn_candidate_into_use(tmp_path: Path) -> None:
    _published_provider(tmp_path, _MODULE, case="ambiguous")
    _assign_initializer(tmp_path)
    path = tmp_path / "contracts/inner.json"
    inner = json.loads(path.read_text())
    inner["components"][0]["packages"] = ["sample.provider.missing"]
    inner["rules"].append(
        _RULE | {"id": "ASSIGN", "kind": "complete_assignment", "source": "sample.provider"}
    )
    path.write_text(json.dumps(inner))

    result, _ = run_validate(tmp_path, _scan_config(), observe)

    assert result.exit_code == 2
    assert any(
        item.code == "rule.violated" and item.subject == "provider:ASSIGN"
        for item in result.diagnostics
    )
    assert any(
        item.code == "interface.unused" and item.subject == _MODULE for item in result.diagnostics
    )
