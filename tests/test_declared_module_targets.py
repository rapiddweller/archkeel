# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Acceptance checks for exact repository module targets."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from test_architecture_demo import _prepare_repo

from archkeel.analyzer import observe
from archkeel.check.ports import ScanConfig
from archkeel.check.report import run_report
from archkeel.ir.codec import (
    contract_bytes,
    decode_canonical_model,
    parse_contract,
    parse_observation,
)
from archkeel.render.html import render_html

ROOT = Path(__file__).parents[1]
_PROVENANCE = ["docs/architecture/sample.md"]
_CONFIG = ScanConfig(("sample",), "sample", "architecture-contract.json", "0" * 64)


def _contract() -> dict[str, Any]:
    return {
        "schema_version": "2.1.0",
        "components": [
            {
                "id": "COMP-APP",
                "label": "app",
                "role": "component",
                "packages": ["sample"],
                "responsibilities": ["Own the sample package."],
                "forbidden_responsibilities": [],
                "provenance": _PROVENANCE,
                "inside": "contracts/inside.json",
            }
        ],
        "rules": [],
    }


def _module(path: str, responsibility: str = "Own this module.") -> dict[str, str]:
    return {"path": path, "responsibility": responsibility}


def _walk(nodes: list[dict[str, Any]]):
    for node in nodes:
        yield node
        yield from _walk(node["children"])


def _declared_file(node: dict[str, Any]) -> str | None:
    return next(
        (
            item["value"]
            for item in node["details"]
            if item["label"] == "File" and isinstance(item["value"], str)
        ),
        None,
    )


def _report(
    tmp_path: Path,
    contract: dict[str, Any],
    *,
    nested_modules: list[dict[str, str]] | None = None,
) -> tuple[Any, str, dict[str, Any] | None, set[str]]:
    inside = {
        "schema_version": "2.1.0",
        "components": [
            {
                "id": "COMP-CORE",
                "label": "core",
                "role": "component",
                "packages": ["sample.core"],
                "responsibilities": ["Own core behavior."],
                "forbidden_responsibilities": [],
                "provenance": _PROVENANCE,
                "inside": "contracts/two.json",
            }
        ],
        "rules": [],
    }
    deep: dict[str, Any] = {"schema_version": "2.1.0", "components": [], "rules": []}
    if nested_modules is not None:
        deep["declarations"] = {"modules": nested_modules}
    files = {
        "pyproject.toml": '[project]\nrequires-python = ">=3.11"\n',
        "sample/__init__.py": "",
        "sample/core/__init__.py": "",
        "sample/core/api.py": "VALUE = 1\n",
        "sample/core/private.py": "VALUE = 2\n",
        "docs/architecture/sample.md": "Architecture.\n",
        "contracts/inside.json": json.dumps(inside),
        "contracts/two.json": json.dumps(deep),
        "architecture-contract.json": json.dumps(contract),
    }
    root = _prepare_repo(tmp_path, files)
    result, architecture = run_report(root, config=_CONFIG, analyzer=observe)
    if architecture is None:
        return result, "", None, set()
    observation = parse_observation(decode_canonical_model(json.loads(architecture)))
    page = render_html(
        result, observation, repository="sample", architecture_href="architecture.json"
    ).decode()
    start = page.index('id="flow-data"')
    payload = json.loads(page[page.index(">", start) + 1 : page.index("</script>", start)])
    actual = {
        record.data.get("qualified_name")
        for record in observation.records("modules") or ()
        if isinstance(record.data.get("qualified_name"), str)
    }
    return result, page, payload, actual


def _observed_files(nodes: list[dict[str, Any]]) -> set[str]:
    return {
        item["value"]
        for node in _walk(nodes)
        for item in node["details"]
        if item["label"] == "File" and isinstance(item["value"], str)
    }


def test_module_declarations_round_trip_and_remain_optional() -> None:
    raw = _contract()
    raw["declarations"] = {"modules": [_module("sample/core/api.py", "Own the public API.")]}
    parsed = parse_contract(raw)
    assert parse_contract(json.loads(contract_bytes(parsed))) == parsed

    omitted = parse_contract(_contract())
    assert parse_contract(json.loads(contract_bytes(omitted))) == omitted
    assert "declarations" not in json.loads(contract_bytes(omitted))


def test_explicit_empty_module_inventory_differs_from_omission(tmp_path: Path) -> None:
    (tmp_path / "legacy").mkdir()
    omitted = _contract()
    omitted.pop("declarations", None)
    _, _, legacy, legacy_actual = _report(tmp_path / "legacy", omitted)
    assert legacy is not None
    legacy_explorers = legacy["explorers"]
    assert not any(node["id"] == "module-targets" for node in legacy_explorers["target"])
    assert not any(
        node["kind"] == "observed_only_module_target" for node in _walk(legacy_explorers["diff"])
    )

    (tmp_path / "empty").mkdir()
    empty = _contract()
    empty["declarations"] = {"modules": []}
    _, _, inventory, actual = _report(tmp_path / "empty", empty)
    assert inventory is not None
    explorers = inventory["explorers"]
    module_inventory = next(node for node in explorers["target"] if node["id"] == "module-targets")
    assert module_inventory["children"] == []
    observed_only = [
        node for node in _walk(explorers["diff"]) if node["kind"] == "observed_only_module_target"
    ]
    assert _observed_files(observed_only) == _observed_files(explorers["actual"])
    assert actual == legacy_actual


@pytest.mark.parametrize(
    "path",
    [
        "",
        "sample/core/api",
        "sample//core/api.py",
        "sample/../outside.py",
        "../sample/api.py",
        "/sample/api.py",
        r"sample\\api.py",
    ],
)
def test_module_declaration_rejects_unsafe_or_non_python_paths(path: str) -> None:
    raw = _contract()
    raw["declarations"] = {"modules": [_module(path)]}
    with pytest.raises(ValueError):
        parse_contract(raw)


def test_module_declaration_paths_are_unique_and_responsibility_is_required() -> None:
    raw = _contract()
    raw["declarations"] = {
        "modules": [_module("sample/core/api.py"), _module("sample/core/api.py", "Another.")]
    }
    with pytest.raises(ValueError):
        parse_contract(raw)

    raw["declarations"] = {"modules": [{"path": "sample/core/api.py", "responsibility": " "}]}
    with pytest.raises(ValueError):
        parse_contract(raw)


def test_exact_module_declaration_does_not_choose_an_overlapping_semantic_owner() -> None:
    raw = _contract()
    raw["components"].append(
        {
            "id": "COMP-CORE",
            "label": "core",
            "role": "component",
            "packages": ["sample.core"],
            "responsibilities": ["Own core behavior."],
            "forbidden_responsibilities": [],
            "provenance": _PROVENANCE,
        }
    )
    raw["declarations"] = {"modules": [_module("sample/core/api.py")]}
    contract = parse_contract(raw)
    assert contract.component_for("sample.core.api") is None


def test_nested_module_targets_are_repo_local_and_reachable_at_depth(tmp_path: Path) -> None:
    raw = _contract()
    raw["components"][0]["inside"] = "contracts/inside.json"
    raw["declarations"] = {}
    _, _, payload, actual = _report(
        tmp_path,
        raw,
        nested_modules=[_module("sample/core/api.py", "Expose the supported core API.")],
    )
    assert payload is not None
    explorers = payload["explorers"]
    target = list(_walk(explorers["target"]))
    module = next(node for node in target if _declared_file(node) == "sample/core/api.py")
    assert module["kind"] == "module_target"
    assert {item["value"] for item in module["details"]} >= {
        "sample/core/api.py",
        "Expose the supported core API.",
    }
    assert "sample.core.api" in actual
    assert "sample.core.private" in actual


def test_target_and_diff_keep_declared_and_observed_modules_independent(tmp_path: Path) -> None:
    raw = _contract()
    raw["declarations"] = {
        "modules": [
            _module("sample/core/api.py", "Expose the supported core API."),
            _module("sample/core/missing.py", "Planned extension point."),
        ]
    }
    _, _, payload, actual = _report(tmp_path, raw)
    assert payload is not None
    explorers = payload["explorers"]
    target = list(_walk(explorers["target"]))
    diff = list(_walk(explorers["diff"]))

    assert {_declared_file(node) for node in target if node["kind"] == "module_target"} == {
        "sample/core/api.py",
        "sample/core/missing.py",
    }
    assert "sample.core.api" in actual
    assert "sample.core.missing" not in actual
    assert any(
        node["label"] == "sample/core/missing.py"
        or _declared_file(node) == "sample/core/missing.py"
        for node in diff
    )

    # This observed file has no exact declaration. Keep it in Diff as observed-only even though
    # the broad component package owns its semantic import boundary.
    assert "sample.core.private" in actual
    assert not any(_declared_file(node) == "sample/core/private.py" for node in target)
    assert any(_declared_file(node) == "sample/core/private.py" for node in diff)


def test_duplicate_exact_path_across_nested_contract_mounts_is_rejected(tmp_path: Path) -> None:
    raw = _contract()
    raw["declarations"] = {"modules": [_module("sample/core/api.py", "Root claim.")]}
    result, _, _payload, _ = _report(
        tmp_path,
        raw,
        nested_modules=[_module("sample/core/api.py", "Nested claim.")],
    )
    assert result.exit_code != 0
    assert any(
        "duplicate" in diagnostic.unknown_claim.casefold() for diagnostic in result.diagnostics
    )


def test_root_module_target_remains_independent_of_deeper_component_mount(tmp_path: Path) -> None:
    contract = _contract()
    contract["declarations"] = {"modules": [_module("sample/core/api.py")]}
    result, _, payload, _ = _report(
        tmp_path,
        contract,
        nested_modules=[_module("sample/core/private.py", "Keep private implementation local.")],
    )
    assert result.exit_code == 0
    assert payload is not None
    target = payload["explorers"]["target"]
    module_category = next(node for node in target if node["id"] == "module-targets")
    module = next(
        node
        for node in _walk(module_category["children"])
        if _declared_file(node) == "sample/core/api.py"
    )
    assert "Owner" not in {detail["label"] for detail in module["details"]}
    app = next(node for node in target if node["id"] == "COMP-APP")
    assert not any(_declared_file(node) == "sample/core/api.py" for node in _walk([app]))
