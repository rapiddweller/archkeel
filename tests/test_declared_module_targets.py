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

from archkeel.check.observation import _declared_module_name
from archkeel.check.ports import ScanConfig
from archkeel.check.report import run_report
from archkeel.check.uml import assemble_uml
from archkeel.cli.observe import observe
from archkeel.ir.codec import (
    contract_bytes,
    decode_canonical_model,
    parse_contract,
    parse_observation,
)
from archkeel.ir.graph_codec import parse_report
from archkeel.ir.model import Diagnostic, ObservationResult
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
        from dataclasses import replace

        from archkeel.analyzer.python.collect import collect
        from archkeel.check.observation import assemble_observation
        from archkeel.ir.facts import CollectionCoverage, EvidenceClass
        from archkeel.ir.facts_codec import classified, parse_record
        from archkeel.ir.protocol import (
            CollectionRequest,
            PythonSettings,
            SnapshotInput,
            SourceScope,
        )
        from archkeel.ir.state_facts import StateFacts

        assert source_paths == []
        request = CollectionRequest(
            SnapshotInput(str(root), "test", False),
            SourceScope(config.roots, config.namespace),
            PythonSettings(),
        )
        facts = collect(request)
        gap = parse_record(
            classified(
                item_id="UNKNOWN-EXCLUDED-SOURCES",
                evidence_class=EvidenceClass.UNKNOWN,
                area="analysis_coverage",
                kind="excluded_sources",
                title="Source files were excluded from this test observation",
                subjects=[],
                evidence_ids=[],
                fact_ids=[],
                data={},
            )
        )
        empty = replace(
            facts,
            files=(),
            imports=(),
            inputs=(),
            sections=tuple(
                replace(section, records=(gap,) if section.name == "unknowns" else ())
                for section in facts.sections
            ),
            coverage=CollectionCoverage((), 0, 0, False, (gap,)),
            evidence=(),
            uncertain_reexports=(),
            type_shapes=(),
            state=StateFacts((), ()),
            candidate_evidence=(),
        )
        observation, _ = assemble_observation(
            empty,
            contract_root=root,
            contract_path=root / "architecture-contract.json",
            roots=config.roots,
            namespace=config.namespace,
            language="python",
        )
        assert observation.coverage.status == "FAIL"
        assert observation.coverage.failures
        incomplete = ObservationResult(
            observation,
            observation.coverage,
            (Diagnostic("parse_error", "sample", "Source was excluded.", "Repeat with source."),),
        )
        compiled = assemble_uml(incomplete, root, config.contract)
        assert compiled.diagnostics == incomplete.diagnostics and compiled.observation is not None
        observation = compiled.observation
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
    legacy_report = parse_report(legacy)
    assert legacy_report.target.module_inventories == ()

    (tmp_path / "empty").mkdir()
    empty = _contract()
    empty["declarations"] = {"modules": []}
    _, _, inventory, actual = _report(tmp_path / "empty", empty)
    empty_report = parse_report(inventory)
    assert len(empty_report.target.module_inventories) == 1
    assert empty_report.target.module_inventories[0].modules == ()
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
    report = parse_report(payload)
    assert report.target is not None
    inventories = report.target.module_inventories
    inventory = next(item for item in inventories if "contracts/two.json" in item.provenance)
    assert [(item.path, item.responsibility) for item in inventory.modules] == [
        ("sample/core/api.py", "Expose the supported core API.")
    ]
    assert inventory.component_id is not None
    assert {"sample.core.api", "sample.core.private"} <= actual


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
    report = parse_report(payload)
    assert report.target is not None
    inventories = report.target.module_inventories
    assert {item.path for inventory in inventories for item in inventory.modules} == {
        "sample/core/api.py",
        "sample/core/missing.py",
    }
    assert "sample.core.api" in actual and "sample.core.missing" not in actual
    assert "sample.core.private" in actual
    assert not any(
        item.path == "sample/core/private.py"
        for inventory in inventories
        for item in inventory.modules
    )


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
    report = parse_report(payload)
    assert report.target is not None
    inventories = report.target.module_inventories
    root_inventory = next(
        item for item in inventories if item.provenance == ("architecture-contract.json",)
    )
    assert [(item.path, item.responsibility) for item in root_inventory.modules] == [
        ("sample/core/api.py", "Own this module.")
    ]
    nested_inventory = next(item for item in inventories if "contracts/two.json" in item.provenance)
    assert nested_inventory.modules[0].path == "sample/core/private.py"
    assert root_inventory.component_id is None


@pytest.mark.parametrize(
    ("path", "component_label", "declaration_source"),
    [
        ("sample/api.py", "app", "architecture-contract.json"),
        ("sample/core/authoring/scaffold.py", "core", "architecture-contract.json"),
    ],
)
def test_declared_file_intent_keeps_its_independent_scope(
    tmp_path: Path, path: str, component_label: str, declaration_source: str
) -> None:
    contract = _contract()
    if component_label == "core":
        contract["components"][0]["inside"] = "contracts/inside.json"
    contract["declarations"] = {"modules": [_module(path, "Navigate by declared package.")]}
    result, _, payload, _ = _report(tmp_path, contract)
    assert result.exit_code == 0
    assert payload is not None
    report = parse_report(payload)
    assert report.target is not None
    inventories = report.target.module_inventories
    inventory = next(
        item for item in inventories if any(module.path == path for module in item.modules)
    )
    assert inventory.provenance == (declaration_source,)
    assert inventory.component_id is None
    assert inventory.modules[0].responsibility == "Navigate by declared package."


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
    report = parse_report(payload)
    assert report.target is not None
    inventories = report.target.module_inventories
    assert any(module.path == path for inventory in inventories for module in inventory.modules)
    assert _declared_module_name(path, roots, "sample") == "sample.core.api"


def test_init_module_target_maps_to_its_package(tmp_path: Path) -> None:
    contract = _contract()
    contract["declarations"] = {"modules": [_module("sample/__init__.py")]}
    _, _, payload, _ = _report(tmp_path, contract)
    assert payload is not None
    report = parse_report(payload)
    assert report.target is not None
    inventories = report.target.module_inventories
    assert any(
        module.path == "sample/__init__.py"
        for inventory in inventories
        for module in inventory.modules
    )
    assert _declared_module_name("sample/__init__.py", ("sample",), "sample") == "sample"


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
    report = parse_report(payload)
    assert report.target is not None
    inventories = report.target.module_inventories
    assert any(module.path == path for inventory in inventories for module in inventory.modules)
    assert ("sample.core.stateful" in actual) == (source_state == "present")


def test_repeated_namespace_segment_does_not_falsely_match_nested_scope(tmp_path: Path) -> None:
    contract = _contract()
    contract["declarations"] = {"modules": [_module("sample/vendor/sample/core/api.py")]}
    result, _, payload, _ = _report(tmp_path, contract)
    assert result.exit_code == 0
    assert payload is not None
    report = parse_report(payload)
    assert report.target is not None
    inventories = report.target.module_inventories
    path = "sample/vendor/sample/core/api.py"
    assert any(module.path == path for inventory in inventories for module in inventory.modules)
    assert _declared_module_name(path, ("sample",), "sample") == "sample.vendor.sample.core.api"


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
    report = parse_report(payload)
    assert report.target is not None
    inventories = report.target.module_inventories
    assert any(module.path == path for inventory in inventories for module in inventory.modules)
    assert _declared_module_name(path, root, "sample") is None


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


@pytest.mark.parametrize(
    ("path", "roots", "expected"),
    [
        ("lib/planned.dart", ("lib",), "sample.planned"),
        ("custom/nested/a-b.dart", ("custom",), "sample.nested.a_b"),
        ("lib/planned.dart", (".",), "sample.lib.planned"),
        ("lib/planned.dart", ("lib/nested",), None),
        ("lib/planned.py", ("lib",), None),
        ("lib/planned.dart", (".", "lib"), None),
    ],
)
def test_dart_target_uses_the_collectors_active_root(
    path: str, roots: tuple[str, ...], expected: str | None
) -> None:
    assert _declared_module_name(path, roots, "sample", "dart") == expected


def test_dart_target_renders_under_its_owning_component(tmp_path: Path) -> None:
    contract = _contract()
    contract["components"][0].pop("inside")
    contract["declarations"] = {"modules": [_module("lib/planned.dart")]}
    result, _, payload, _ = _report(
        tmp_path,
        contract,
        extra_files={"lib/main.dart": "void main() {}\n", "pubspec.yaml": "name: sample\n"},
        config=ScanConfig(
            ("lib",), "sample", "architecture-contract.json", "0" * 64, language="dart"
        ),
    )
    assert result.exit_code == 0
    assert payload is not None
    report = parse_report(payload)
    assert report.target is not None
    inventories = report.target.module_inventories
    assert any(
        module.path == "lib/planned.dart"
        for inventory in inventories
        for module in inventory.modules
    )
    assert _declared_module_name("lib/planned.dart", ("lib",), "sample", "dart") == "sample.planned"


@pytest.mark.parametrize("observed", [False, True])
def test_dart_target_collision_cannot_associate_different_file_spellings(
    tmp_path: Path, observed: bool
) -> None:
    contract = _contract()
    contract["components"][0].pop("inside")
    paths = ["lib/a-b.dart"] if observed else ["lib/a-b.dart", "lib/a_b.dart"]
    contract["declarations"] = {"modules": [_module(path) for path in paths]}
    _, html, payload, actual = _report(
        tmp_path,
        contract,
        extra_files={
            "lib/main.dart": "void main() {}\n",
            "pubspec.yaml": "name: sample\n",
            **({"lib/a_b.dart": "class Existing {}\n"} if observed else {}),
        },
        config=ScanConfig(
            ("lib",), "sample", "architecture-contract.json", "0" * 64, language="dart"
        ),
    )
    assert payload is not None
    assert ("sample.a_b" in actual) is observed
    report = parse_report(payload)
    assert report.target is not None
    inventories = report.target.module_inventories
    assert {module.path for inventory in inventories for module in inventory.modules} == set(paths)
    observed_paths = {
        item.file_path
        for item in report.observed.entities
        if item.kind == "module" and item.presence == "defined"
    }
    assert "lib/a-b.dart" not in observed_paths
    assert "different source paths share Dart module identity sample.a_b" in html


def test_empty_inventory_ids_are_unique_across_root_and_component_named_root(
    tmp_path: Path,
) -> None:
    contract = _contract()
    contract["components"][0]["label"] = "root"
    contract["components"][0]["inside"] = "contracts/inside.json"
    contract["declarations"] = {"modules": []}
    _, _, payload, _ = _report(tmp_path, contract, inside_modules=[])
    assert payload is not None
    report = parse_report(payload)
    assert report.target is not None
    inventories = report.target.module_inventories
    assert len(inventories) == 2 and len({item.id for item in inventories}) == 2
    assert all(not item.modules for item in inventories)
    assert {item.component_id is None for item in inventories} == {True, False}


def test_nested_unresolved_target_stays_in_its_declaring_scope(tmp_path: Path) -> None:
    contract = _contract()
    contract["components"][0]["inside"] = "contracts/inside.json"
    _, _, payload, _ = _report(
        tmp_path,
        contract,
        inside_modules=[_module("elsewhere/api.py", "Retain unresolved scope.")],
    )
    assert payload is not None
    report = parse_report(payload)
    assert report.target is not None
    inventories = report.target.module_inventories
    inventory = next(item for item in inventories if "contracts/inside.json" in item.provenance)
    assert inventory.component_id == "COMP-APP"
    assert [(item.path, item.responsibility) for item in inventory.modules] == [
        ("elsewhere/api.py", "Retain unresolved scope.")
    ]


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
    report = parse_report(payload)
    assert report.target is not None
    inventories = report.target.module_inventories
    inventory = next(item for item in inventories if "contracts/inside.json" in item.provenance)
    assert inventory.component_id == "COMP-APP"
    assert [item.path for item in inventory.modules] == ["sample/core/api.py"]


def test_nested_empty_inventory_stays_at_its_declaring_scope(tmp_path: Path) -> None:
    contract = _contract()
    contract["components"][0]["inside"] = "contracts/inside.json"
    _, _, payload, _ = _report(tmp_path, contract, inside_modules=[])
    assert payload is not None
    report = parse_report(payload)
    assert report.target is not None
    inventories = report.target.module_inventories
    inventory = next(item for item in inventories if "contracts/inside.json" in item.provenance)
    assert inventory.component_id == "COMP-APP" and inventory.modules == ()


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
    report = parse_report(payload)
    assert report.target is not None
    inventories = report.target.module_inventories
    assert len(inventories) == 1 and inventories[0].component_id is None
    assert [item.path for item in inventories[0].modules] == [path]


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
    report = parse_report(payload)
    assert report.target is not None
    inventories = report.target.module_inventories
    assert len(inventories) == 1 and inventories[0].component_id is None
    assert [item.path for item in inventories[0].modules] == ["sample/core/api.py"]
