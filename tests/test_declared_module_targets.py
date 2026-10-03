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
from archkeel.analyzer.embedded.report import _declared_module_name, analyze_snapshot
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
    inside_modules: list[dict[str, str]] | None = None,
    extra_files: dict[str, str] | None = None,
    config: ScanConfig = _CONFIG,
    source_paths: list[str] | None = None,
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
    if inside_modules is not None:
        inside["declarations"] = {"modules": inside_modules}
    deep: dict[str, Any] = {"schema_version": "2.1.0", "components": [], "rules": []}
    if nested_modules is not None:
        deep["declarations"] = {"modules": nested_modules}
    files = {
        "pyproject.toml": '[project]\nrequires-python = ">=3.11"\n',
        "sample/__init__.py": "",
        "sample/core/__init__.py": "",
        "sample/core/api.py": "VALUE = 1\n",
        "sample/core/private.py": "VALUE = 2\n",
        "sample/api.py": "VALUE = 3\n",
        "sample/core/authoring/__init__.py": "",
        "sample/core/authoring/scaffold.py": "VALUE = 4\n",
        "sample/vendor/sample/core/api.py": "VALUE = 5\n",
        "docs/architecture/sample.md": "Architecture.\n",
        "contracts/inside.json": json.dumps(inside),
        "contracts/two.json": json.dumps(deep),
        "architecture-contract.json": json.dumps(contract),
    }
    files.update(extra_files or {})
    root = _prepare_repo(tmp_path, files)
    result, architecture = run_report(root, config=config, analyzer=observe)
    if architecture is None:
        return result, "", None, set()
    if source_paths is None:
        observation = parse_observation(decode_canonical_model(json.loads(architecture)))
    else:
        model, _ = analyze_snapshot(
            root,
            git_head="test",
            dirty=False,
            contract_path=root / "architecture-contract.json",
            source_paths=[root / path for path in source_paths],
            roots=config.roots,
            namespace=config.namespace,
        )
        observation = parse_observation(model)
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
    module_inventory = next(
        node for node in explorers["target"] if node["label"] == "Declared module inventory"
    )
    assert module_inventory["label"] == "Declared module inventory"
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
        "sample/core/api.txt",
        r"sample\\api.py",
    ],
)
def test_module_declaration_rejects_unsafe_or_non_python_paths(path: str) -> None:
    raw = _contract()
    raw["declarations"] = {"modules": [_module(path)]}
    with pytest.raises(ValueError):
        parse_contract(raw)


@pytest.mark.parametrize(
    "suffix", [".py", ".dart", ".ts", ".tsx", ".mts", ".cts", ".js", ".jsx", ".mjs", ".cjs"]
)
def test_module_declaration_accepts_supported_language_source_suffixes(suffix: str) -> None:
    raw = _contract()
    raw["declarations"] = {"modules": [_module(f"sample/core/api{suffix}")]}

    assert parse_contract(raw).declarations.modules[0].path == f"sample/core/api{suffix}"


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
        "contracts/two.json",
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
    core = next(node for node in _walk(explorers["target"]) if node["label"] == "core")
    missing = next(
        node for node in _walk([core]) if _declared_file(node) == "sample/core/missing.py"
    )
    assert "Navigation" in {detail["label"] for detail in missing["details"]}
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


def test_root_declaration_provenance_survives_nested_component_navigation(tmp_path: Path) -> None:
    contract = _contract()
    contract["components"][0]["inside"] = "contracts/inside.json"
    contract["declarations"] = {"modules": [_module("sample/core/api.py")]}
    result, _, payload, _ = _report(
        tmp_path,
        contract,
        nested_modules=[_module("sample/core/private.py", "Keep private implementation local.")],
    )
    assert result.exit_code == 0
    assert payload is not None
    target = payload["explorers"]["target"]
    core = next(node for node in _walk(target) if node["label"] == "core")
    module = next(node for node in _walk([core]) if _declared_file(node) == "sample/core/api.py")
    assert {detail["label"]: detail["value"] for detail in module["details"]} == {
        "File": "sample/core/api.py",
        "Responsibility": "Own this module.",
        "Declared in": "architecture-contract.json",
        "Navigation": "Grouped by declared package scope sample.core.",
    }
    assert not any(node["kind"] == "folder" for node in _walk(target))
    assert sum(_declared_file(node) == "sample/core/api.py" for node in _walk(target)) == 1


@pytest.mark.parametrize(
    ("path", "component_label", "declaration_source"),
    [
        ("sample/api.py", "app", "architecture-contract.json"),
        ("sample/core/authoring/scaffold.py", "core", "architecture-contract.json"),
    ],
)
def test_declared_target_navigates_to_deepest_component_without_folders(
    tmp_path: Path, path: str, component_label: str, declaration_source: str
) -> None:
    contract = _contract()
    if component_label == "core":
        contract["components"][0]["inside"] = "contracts/inside.json"
    contract["declarations"] = {"modules": [_module(path, "Navigate by declared package.")]}
    result, _, payload, _ = _report(tmp_path, contract)
    assert result.exit_code == 0
    assert payload is not None
    target = payload["explorers"]["target"]
    component = next(node for node in _walk(target) if node["label"] == component_label)
    module = next(node for node in _walk([component]) if _declared_file(node) == path)
    assert module["kind"] == "module_target"
    navigation_scope = "sample" if component_label == "app" else "sample.core"
    assert {detail["label"]: detail["value"] for detail in module["details"]} == {
        "File": path,
        "Responsibility": "Navigate by declared package.",
        "Declared in": declaration_source,
        "Navigation": f"Grouped by declared package scope {navigation_scope}.",
    }
    assert sum(_declared_file(node) == path for node in _walk(target)) == 1


@pytest.mark.parametrize("roots", [("src",), ("src/sample",)])
def test_target_name_uses_configured_src_or_narrowed_root(
    tmp_path: Path, roots: tuple[str, ...]
) -> None:
    path = "src/sample/core/api.py"
    contract = _contract()
    contract["declarations"] = {"modules": [_module(path)]}
    result, _, payload, _ = _report(
        tmp_path,
        contract,
        extra_files={
            "src/sample/__init__.py": "",
            "src/sample/core/__init__.py": "",
            path: "VALUE = 1\n",
        },
        config=ScanConfig(roots, "sample", "architecture-contract.json", "0" * 64),
    )
    assert result.exit_code == 0
    assert payload is not None
    core = next(node for node in _walk(payload["explorers"]["target"]) if node["label"] == "core")
    module = next(node for node in _walk([core]) if _declared_file(node) == path)
    assert "Grouped by declared package scope sample.core." in {
        detail["value"] for detail in module["details"]
    }


def test_init_module_target_maps_to_its_package(tmp_path: Path) -> None:
    contract = _contract()
    contract["declarations"] = {"modules": [_module("sample/__init__.py")]}
    _, _, payload, _ = _report(tmp_path, contract)
    assert payload is not None
    app = next(node for node in _walk(payload["explorers"]["target"]) if node["label"] == "app")
    assert any(_declared_file(node) == "sample/__init__.py" for node in _walk([app]))


@pytest.mark.parametrize(
    ("source_state", "source_paths"),
    [("present", None), ("syntax-broken", None), ("excluded", [])],
)
def test_component_navigation_does_not_depend_on_source_state(
    tmp_path: Path, source_state: str, source_paths: list[str] | None
) -> None:
    path = "sample/core/stateful.py"
    contract = _contract()
    contract["declarations"] = {"modules": [_module(path)]}
    extra_files = {path: "VALUE = 1\n" if source_state == "present" else "if:\n"}
    _, _, payload, actual = _report(
        tmp_path,
        contract,
        extra_files=extra_files,
        source_paths=source_paths,
    )
    assert payload is not None
    core = next(node for node in _walk(payload["explorers"]["target"]) if node["label"] == "core")
    module = next(node for node in _walk([core]) if _declared_file(node) == path)
    assert "Grouped by declared package scope sample.core." in {
        detail["value"] for detail in module["details"]
    }
    if source_state != "present":
        assert "sample.core.stateful" not in actual


def test_repeated_namespace_segment_does_not_falsely_match_nested_scope(tmp_path: Path) -> None:
    contract = _contract()
    contract["declarations"] = {"modules": [_module("sample/vendor/sample/core/api.py")]}
    result, _, payload, _ = _report(tmp_path, contract)
    assert result.exit_code == 0
    assert payload is not None
    target = payload["explorers"]["target"]
    app = next(node for node in _walk(target) if node["label"] == "app")
    core = next(node for node in _walk(target) if node["label"] == "core")
    assert any(_declared_file(node) == "sample/vendor/sample/core/api.py" for node in _walk([app]))
    assert not any(
        _declared_file(node) == "sample/vendor/sample/core/api.py" for node in _walk([core])
    )


@pytest.mark.parametrize("root", [("sample/vendor/sample",), ("sample/vendor",)])
def test_namespace_anchor_with_earlier_conflicting_segment_is_unresolved(
    tmp_path: Path, root: tuple[str, ...]
) -> None:
    path = "sample/vendor/sample/core/api.py"
    contract = _contract()
    contract["declarations"] = {"modules": [_module(path)]}
    _, _, payload, _ = _report(
        tmp_path,
        contract,
        config=ScanConfig(root, "sample", "architecture-contract.json", "0" * 64),
    )
    assert payload is not None
    unresolved = next(
        node for node in payload["explorers"]["target"] if node["id"] == "module-targets"
    )
    assert [_declared_file(node) for node in unresolved["children"]] == [path]


@pytest.mark.parametrize(
    ("path", "root"),
    [("sample.py", ("sample",)), ("src/sample.py", ("src/sample",))],
)
def test_module_file_cannot_masquerade_as_a_configured_root(
    path: str, root: tuple[str, ...]
) -> None:
    assert _declared_module_name(path, root, "sample") is None


@pytest.mark.parametrize(
    ("suffix", "encoded_suffix"),
    [
        (".ts", "_x2e_ts"),
        (".tsx", "_x2e_tsx"),
        (".mts", "_x2e_mts"),
        (".cts", "_x2e_cts"),
        (".js", "_x2e_js"),
        (".jsx", "_x2e_jsx"),
        (".mjs", "_x2e_mjs"),
        (".cjs", "_x2e_cjs"),
        (".d.ts", "_x2e_d_x2e_ts"),
    ],
)
def test_typescript_declared_module_name_maps_native_sources_under_dot_root(
    suffix: str, encoded_suffix: str
) -> None:
    path = f"src/nested/module{suffix}"

    assert _declared_module_name(path, (".",), "app", "typescript") == (
        f"app.src.nested.module{encoded_suffix}"
    )


def test_empty_inventory_ids_are_unique_across_root_and_component_named_root(
    tmp_path: Path,
) -> None:
    contract = _contract()
    contract["components"][0]["label"] = "root"
    contract["components"][0]["inside"] = "contracts/inside.json"
    contract["declarations"] = {"modules": []}
    _, _, payload, _ = _report(tmp_path, contract, inside_modules=[])
    assert payload is not None
    inventories = [
        node
        for node in _walk(payload["explorers"]["target"])
        if node["label"] == "Declared module inventory"
    ]
    assert len(inventories) == 2
    assert len({node["id"] for node in inventories}) == 2


def test_nested_unresolved_target_stays_in_its_declaring_scope(tmp_path: Path) -> None:
    contract = _contract()
    contract["components"][0]["inside"] = "contracts/inside.json"
    _, _, payload, _ = _report(
        tmp_path,
        contract,
        inside_modules=[_module("elsewhere/api.py", "Retain unresolved scope.")],
    )
    assert payload is not None
    app = next(node for node in _walk(payload["explorers"]["target"]) if node["label"] == "app")
    unresolved = next(
        node for node in app["children"] if node["label"] == "Modules outside components"
    )
    leaf = unresolved["children"][0]
    assert _declared_file(leaf) == "elsewhere/api.py"
    assert {detail["label"]: detail["value"] for detail in leaf["details"]} == {
        "File": "elsewhere/api.py",
        "Responsibility": "Retain unresolved scope.",
        "Declared in": "contracts/inside.json",
    }


def test_ambiguous_nested_siblings_keep_target_unresolved_at_parent_scope(tmp_path: Path) -> None:
    contract = _contract()
    contract["components"][0]["inside"] = "contracts/inside.json"
    inside = {
        "schema_version": "2.1.0",
        "components": [
            {
                "id": component_id,
                "label": label,
                "role": "component",
                "packages": ["sample.core"],
                "responsibilities": [f"Own {label}."],
                "forbidden_responsibilities": [],
                "provenance": _PROVENANCE,
            }
            for component_id, label in (("COMP-ONE", "one"), ("COMP-TWO", "two"))
        ],
        "declarations": {"modules": [_module("sample/core/api.py")]},
        "rules": [],
    }
    extra_files = {"contracts/inside.json": json.dumps(inside)}
    _, _, payload, _ = _report(
        tmp_path,
        contract,
        extra_files=extra_files,
    )
    assert payload is not None
    app = next(node for node in _walk(payload["explorers"]["target"]) if node["label"] == "app")
    unresolved = next(
        node for node in app["children"] if node["label"] == "Modules outside components"
    )
    assert [_declared_file(node) for node in unresolved["children"]] == ["sample/core/api.py"]


def test_nested_empty_inventory_stays_at_its_declaring_scope(tmp_path: Path) -> None:
    contract = _contract()
    contract["components"][0]["inside"] = "contracts/inside.json"
    _, _, payload, _ = _report(tmp_path, contract, inside_modules=[])
    assert payload is not None
    app = next(node for node in _walk(payload["explorers"]["target"]) if node["label"] == "app")
    inventory = next(
        node for node in app["children"] if node["label"] == "Declared module inventory"
    )
    assert {detail["label"]: detail["value"] for detail in inventory["details"]} == {
        "Status": "Explicitly empty"
    }


@pytest.mark.parametrize("path", ["sample/core/api.py", "elsewhere/api.py"])
def test_ambiguous_or_unmatched_target_uses_unresolved_group(tmp_path: Path, path: str) -> None:
    contract = _contract()
    if path == "sample/core/api.py":
        contract["components"][0].pop("inside")
        contract["components"].append(
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
    contract["declarations"] = {"modules": [_module(path)]}
    result, _, payload, _ = _report(tmp_path, contract)
    assert result.exit_code == 0
    assert payload is not None
    target = payload["explorers"]["target"]
    unresolved = next(node for node in target if node["id"] == "module-targets")
    assert unresolved["label"] == "Modules outside components"
    assert [_declared_file(node) for node in _walk(unresolved["children"])] == [path]
    assert sum(_declared_file(node) == path for node in _walk(target)) == 1


def test_root_ambiguity_is_not_resolved_by_a_deeper_child(tmp_path: Path) -> None:
    contract = _contract()
    contract["components"].append(
        {
            "id": "COMP-OTHER",
            "label": "other",
            "role": "component",
            "packages": ["sample"],
            "responsibilities": ["Another root scope."],
            "forbidden_responsibilities": [],
            "provenance": _PROVENANCE,
        }
    )
    contract["declarations"] = {"modules": [_module("sample/core/api.py")]}
    result, _, payload, _ = _report(tmp_path, contract)
    assert result.exit_code == 0
    assert payload is not None
    target = payload["explorers"]["target"]
    unresolved = next(node for node in target if node["id"] == "module-targets")
    assert [_declared_file(node) for node in _walk(unresolved["children"])] == [
        "sample/core/api.py"
    ]
