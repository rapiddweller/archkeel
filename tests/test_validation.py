# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
import json
from collections.abc import Callable
from pathlib import Path
from typing import get_args, get_origin, get_type_hints
from unittest.mock import Mock

import pytest
from test_analyzer import _component
from test_architecture_demo import CONFIG as SHOP_CONFIG
from test_architecture_demo import _prepare_repo
from test_delta import _model, _record

from archkeel.analyzer import observe
from archkeel.check.onboarding import architecture_document
from archkeel.check.ports import ScanConfig
from archkeel.check.report import observe_repository
from archkeel.check.validation import (
    COMPONENT_GRAPH_MARKER,
    TARGET_GRAPH_MARKER,
    _resolved_public_entries,
    graph_diagnostics,
    inside_diagnostics,
    interface_diagnostics,
    public_api_diagnostics,
    reference_diagnostics,
    rewrite_component_graph,
    run_validate,
)
from archkeel.cli.config import load_config
from archkeel.ir.baseline import KnownViolation, ViolationFingerprint
from archkeel.ir.codec import (
    CONTRACT_SCHEMA_VERSION,
    baseline_bytes,
    decode_canonical_model,
    decode_json,
    parse_contract,
    parse_observation,
)
from archkeel.ir.model import ArchitectureContract, Observation, ObservationResult, Record
from fixtures.architecture_demo import CATALOG
from fixtures.demo_catalog_support import FIXTURE_DIR

ROOT = Path(__file__).parents[1]
CONFIG = ScanConfig(("sample",), "sample", "contract.json", "0" * 64)


def test_an_inside_may_not_grant_what_requires_never_named(tmp_path: Path) -> None:
    """AD-32 decides pairs by absence, so absence has to reach the inside as a prohibition.

    Archkeel's own top level holds no `forbidden_dependency` for check, so a check that reads
    only those rules would pass anything the inside granted itself.
    """
    outer = json.loads((ROOT / "architecture-contract.json").read_text())
    inner = json.loads((ROOT / "src/archkeel/check/architecture-contract.json").read_text())
    analyzer_inner = json.loads(
        (ROOT / "src/archkeel/analyzer/architecture-contract.json").read_text()
    )
    root = tmp_path / "repository"
    inside = root / "src/archkeel/check/architecture-contract.json"
    inside.parent.mkdir(parents=True)
    analyzer_inside = root / "src/archkeel/analyzer/architecture-contract.json"
    analyzer_inside.parent.mkdir(parents=True)
    (root / "architecture-contract.json").write_text(json.dumps(outer))
    inside.write_text(json.dumps(inner))
    analyzer_inside.write_text(json.dumps(analyzer_inner))

    inside_config = ScanConfig(("src",), "archkeel", "architecture-contract.json", "0" * 64)
    assert inside_diagnostics(root, parse_contract(outer), inside_config) == ()

    inner["rules"].append(
        {
            "id": "DEP-ENTRY-ALLOWS-RENDER",
            "kind": "allowed_dependency",
            "source": "archkeel.check.run",
            "target": "archkeel.render",
            "rationale": "The inside grants an edge the level above never named in requires.",
            "provenance": ["docs/architecture/archkeel.md"],
            "decided_by": "architect",
        }
    )
    inside.write_text(json.dumps(inner))

    diagnostics = inside_diagnostics(root, parse_contract(outer), inside_config)

    assert [item.code for item in diagnostics] == ["inside.forbidden_import"]
    assert "REQUIRES-COMPLETE" in diagnostics[0].unknown_claim


def test_validate_accepts_archkeel_self_contract() -> None:
    result, _ = run_validate(
        ROOT, load_config(ROOT), observe, baseline=ROOT / "architecture-baseline.json"
    )
    assert result.exit_code == 0
    assert result.observation_complete == "PASS"
    # AD-72: declaring boundary_types for check and render leaves 16 positions the checker
    # cannot read (15 a union, 1 an unentered generic), so the verdict says so -- exit 0.
    assert result.declared_rules == "UNKNOWN"
    assert result.expectation_fulfilled == "n/a"


def test_validate_reports_no_check_types_declared_violation_against_this_repository() -> None:
    """AD-68's Limit (issue #59): `check.run_init` and `check.run_validate` both return
    `tuple[RunResult, dict[str, bytes]]`, and a bare `dict[str, bytes]` is exactly the
    untyped container CHECK-TYPES-DECLARED (AD-58) exists to reject. Declaring `boundary_types`
    for `check` must not leave its own two facade functions violating the rule they now carry.
    """
    result, _ = run_validate(
        ROOT, load_config(ROOT), observe, baseline=ROOT / "architecture-baseline.json"
    )
    subjects = {diagnostic.subject for diagnostic in result.diagnostics}
    assert "CHECK-TYPES-DECLARED" not in subjects
    assert result.exit_code == 0


def _as_path_bytes(files: object) -> dict[str, bytes]:
    """Normalize `run_validate`'s written-files result into path -> bytes.

    Works whether that value is the bare `dict[str, bytes]` AD-68's Limit flags, or the typed
    model that replaces it: the pin below is about which paths a run writes and what bytes it
    writes into them, not about the container shape carrying that answer.
    """
    if isinstance(files, dict):
        return files
    if hasattr(files, "items"):
        return dict(files.items())
    return dict(files)  # type: ignore[call-overload]


def _second_return_type(func: Callable[..., object]) -> type:
    """The declared type of a 2-tuple return's second element, as CHECK-TYPES-DECLARED reads it.

    `boundary_types` (AD-58/AD-63) judges the annotation itself, not a runtime value: a bare
    `dict`/`Dict`/`object`, or a `dict[...]`/`Dict[...]` generic, is the violation regardless of
    what a particular call happens to return. Reading it through `get_type_hints`/`get_origin`
    mirrors that same judgement instead of asserting on one call's runtime type.
    """
    (_, files_type) = get_args(get_type_hints(func)["return"])
    return get_origin(files_type) or files_type


def test_run_validate_declares_a_files_type_that_is_not_a_bare_dict(
    tmp_path: Path,
) -> None:
    """AD-68's Limit (issue #59): pin `--write-graph`'s written file through `run_validate`
    itself, the way `test_architecture_demo.py`'s graph-drift tests already do, but also
    require the declared files type to stop being a bare `dict[str, bytes]` - the exact shape
    CHECK-TYPES-DECLARED rejects. A refactor may change what carries the answer; it must not
    change which file is rewritten, or leave it unrewritten.
    """
    assert _second_return_type(run_validate) is not dict

    rows = {variant.item: variant for variant in CATALOG}
    stale = _prepare_repo(tmp_path, dict(rows["graph.drift:write-graph"].files))
    page = stale / "docs/architecture/shop.md"
    original = page.read_bytes()

    result, files = run_validate(stale, SHOP_CONFIG, observe, write_graph=True)

    assert result.exit_code == 0
    written = _as_path_bytes(files)
    assert set(written) == {"docs/architecture/shop.md"}
    assert written["docs/architecture/shop.md"] != original

    # The bytes returned must be exactly what a clean, regenerated graph looks like: writing
    # them and validating again must find nothing left to rewrite and no graph drift.
    page.write_bytes(written["docs/architecture/shop.md"])
    revalidated, rerun_files = run_validate(stale, SHOP_CONFIG, observe, write_graph=True)
    assert revalidated.exit_code == 0
    assert revalidated.diagnostics == ()
    assert _as_path_bytes(rerun_files) == {}


def test_validate_rejects_contract_1_1_with_exact_pointer(tmp_path: Path) -> None:
    (tmp_path / "contract.json").write_text('{"schema_version":"1.1.0","components":[],"rules":[]}')
    analyzer = Mock()
    result, _ = run_validate(tmp_path, CONFIG, analyzer)
    analyzer.assert_not_called()
    assert result.exit_code == 2
    assert result.diagnostics[0].pointer == "/schema_version"
    assert result.diagnostics[0].unknown_claim == (
        "Contract schema 1.1.0 cannot be validated as 2.1.0."
    )


def test_validate_gives_every_contract_invalid_diagnostic_a_code(tmp_path: Path) -> None:
    broken = (ROOT / "tests/contracts/invalid/wrong-type.json").read_bytes()
    (tmp_path / "contract.json").write_bytes(broken)
    result, _ = run_validate(tmp_path, CONFIG, Mock())
    assert result.diagnostics
    assert all(item.code == "contract.invalid" for item in result.diagnostics)


def test_validate_rejects_a_non_immediate_root_layout_child(tmp_path: Path) -> None:
    contract = json.loads((ROOT / "tests/contracts/valid/minimal.json").read_bytes())
    contract["rules"] = [
        {
            "id": "ROOT-LAYOUT",
            "kind": "root_layout",
            "root": "sample",
            "allowed_children": ["sample.core.nested"],
            "rationale": "Probe.",
            "provenance": ["docs/architecture/sample.md"],
            "decided_by": "architect",
        }
    ]
    (tmp_path / "contract.json").write_text(json.dumps(contract))
    analyzer = Mock()
    result, _ = run_validate(tmp_path, CONFIG, analyzer)
    analyzer.assert_not_called()
    assert result.exit_code == 2
    assert result.diagnostics[0].code == "contract.invalid"
    assert "exactly one immediate child" in result.diagnostics[0].unknown_claim


def test_validate_sorts_namespace_and_provenance_diagnostics(tmp_path: Path) -> None:
    contract = json.loads((ROOT / "tests/contracts/valid/minimal.json").read_bytes())
    contract["components"][0]["packages"] = ["outside.x"]
    contract["components"][0]["provenance"] = ["missing.md"]
    contract["components"] = contract["components"][:1]
    contract["rules"] = []
    (tmp_path / "contract.json").write_text(json.dumps(contract))
    result, _ = run_validate(tmp_path, CONFIG, Mock())
    assert [item.pointer for item in result.diagnostics] == [
        "/components/0/packages/0",
        "/components/0/provenance/0",
    ]


def test_reference_check_rejects_a_component_without_scanned_modules() -> None:
    raw = json.loads((ROOT / "tests/contracts/valid/minimal.json").read_bytes())
    contract = parse_contract(raw)
    observation = parse_observation(
        decode_canonical_model(
            json.loads((ROOT / "fixtures/D-self/architecture.json").read_bytes())
        )
    )
    diagnostics = reference_diagnostics(ROOT, CONFIG, contract, observation)
    assert any(item.pointer == "/components/0/packages/0" for item in diagnostics)


def test_public_entry_outside_namespace_is_a_diagnostic() -> None:
    contract = parse_contract(
        {
            "schema_version": "2.1.0",
            "components": [_component("core", public=["other.module"])],
            "rules": [],
        }
    )
    diagnostics = reference_diagnostics(ROOT, CONFIG, contract)
    assert any(
        item.pointer == "/components/0/public/0" and "outside namespace" in item.unknown_claim
        for item in diagnostics
    )


def test_exact_source_outside_namespace_is_a_diagnostic() -> None:
    """AD-49: an exact source is a module name like a prefix one, held to the same namespace."""
    rule = {
        "id": "EXTERNAL-JSON",
        "kind": "external_dependency_scope",
        "dependency": "json",
        "exact_sources": ["other"],
        "rationale": "Probe.",
        "provenance": ["docs/architecture/sample.md"],
        "decided_by": "architect",
    }
    contract = parse_contract({"schema_version": "2.1.0", "components": [], "rules": [rule]})
    diagnostics = reference_diagnostics(ROOT, CONFIG, contract)
    assert "/rules/0/exact_sources/0" in [item.pointer for item in diagnostics]


def test_public_entry_owned_by_another_component_is_a_diagnostic() -> None:
    contract = parse_contract(
        {
            "schema_version": "2.1.0",
            "components": [
                _component("core", public=["sample.cli"]),
                _component("cli"),
            ],
            "rules": [],
        }
    )
    diagnostics = reference_diagnostics(ROOT, CONFIG, contract)
    assert any(
        item.pointer == "/components/0/public/0"
        and "not owned by this component" in item.unknown_claim
        for item in diagnostics
    )


def test_public_entry_with_underscore_name_is_a_diagnostic() -> None:
    contract = parse_contract(
        {
            "schema_version": "2.1.0",
            "components": [_component("core", public=["sample.core:_Hidden"])],
            "rules": [],
        }
    )
    diagnostics = reference_diagnostics(ROOT, CONFIG, contract)
    assert any(
        item.pointer == "/components/0/public/0" and "Underscore" in item.unknown_claim
        for item in diagnostics
    )


def test_planned_entry_owned_by_another_component_is_a_diagnostic() -> None:
    """AD-56: a planned entry is held to the same ownership check as a public one."""
    contract = parse_contract(
        {
            "schema_version": "2.1.0",
            "components": [
                _component("core", planned=["sample.cli"]),
                _component("cli"),
            ],
            "rules": [],
        }
    )
    diagnostics = reference_diagnostics(ROOT, CONFIG, contract)
    assert any(
        item.pointer == "/components/0/planned/0"
        and "not owned by this component" in item.unknown_claim
        for item in diagnostics
    )


def test_planned_entry_with_underscore_name_is_a_diagnostic() -> None:
    contract = parse_contract(
        {
            "schema_version": "2.1.0",
            "components": [_component("core", planned=["sample.core:_Hidden"])],
            "rules": [],
        }
    )
    diagnostics = reference_diagnostics(ROOT, CONFIG, contract)
    assert any(
        item.pointer == "/components/0/planned/0" and "Underscore" in item.unknown_claim
        for item in diagnostics
    )


def test_planned_entry_outside_namespace_is_a_diagnostic() -> None:
    contract = parse_contract(
        {
            "schema_version": "2.1.0",
            "components": [_component("core", planned=["other.module"])],
            "rules": [],
        }
    )
    diagnostics = reference_diagnostics(ROOT, CONFIG, contract)
    assert any(
        item.pointer == "/components/0/planned/0" and "outside namespace" in item.unknown_claim
        for item in diagnostics
    )


_INTERFACE_RULE = {
    "id": "INTERFACE",
    "kind": "interface_boundary",
    "rationale": "Probe.",
    "provenance": ["docs/architecture/sample.md"],
    "decided_by": "architect",
}


def _contract_with_allowed_dependency(source: str, target: str) -> dict[str, object]:
    """A two-component contract whose only decision permits `source` to depend on `target`."""
    return {
        "schema_version": "2.1.0",
        "components": [_component(source), _component(target)],
        "rules": [
            {
                "id": "DEP-ALLOW",
                "kind": "allowed_dependency",
                "source": f"sample.{source}",
                "target": f"sample.{target}",
                "rationale": "Probe.",
                "provenance": ["docs/architecture/sample.md"],
                "decided_by": "architect",
            }
        ],
    }


def _cross_import(target_module: str, **data: object) -> dict[str, object]:
    return _record(
        "IMPORT-1",
        kind="import",
        data={"source_module": "sample.cli", "target_module": target_module, **data},
    )


def _module(qualified_name: str, all_exports: list[str] | None = None) -> dict[str, object]:
    data: dict[str, object] = {"qualified_name": qualified_name}
    if all_exports is not None:
        data["all_exports"] = all_exports
    return _record(f"MOD-{qualified_name}", kind="module", data=data)


def _symbol(module: str, name: str, kind: str = "function") -> dict[str, object]:
    """A top-level, public class/function `symbols` record (AD-56's own evidence for `public`)."""
    return _record(
        f"SYM-{module}.{name}",
        kind=kind,
        data={
            "qualified_name": f"{module}.{name}",
            "module": module,
            "name": name,
            "parent": None,
            "visibility": "public_name",
        },
    )


def test_undeclared_interface_is_a_diagnostic_when_a_rule_is_present() -> None:
    contract = parse_contract(
        {
            "schema_version": "2.1.0",
            "components": [_component("core"), _component("cli")],
            "rules": [_INTERFACE_RULE],
        }
    )
    observation = parse_observation(
        _model(git_head="a" * 40, imports=[_cross_import("sample.core")])
    )
    diagnostics = interface_diagnostics(contract, observation)
    assert [item.pointer for item in diagnostics] == ["/components/0"]


def test_declared_public_interface_has_no_undeclared_diagnostic() -> None:
    contract = parse_contract(
        {
            "schema_version": "2.1.0",
            "components": [_component("core", public=["sample.core"]), _component("cli")],
            "rules": [_INTERFACE_RULE],
        }
    )
    observation = parse_observation(
        _model(git_head="a" * 40, imports=[_cross_import("sample.core")])
    )
    assert interface_diagnostics(contract, observation) == ()


def test_unused_public_entry_is_a_diagnostic() -> None:
    contract = parse_contract(
        {
            "schema_version": "2.1.0",
            "components": [_component("core", public=["sample.core:Widget"]), _component("cli")],
            "rules": [_INTERFACE_RULE],
        }
    )
    observation = parse_observation(
        _model(git_head="a" * 40, modules=[_module("sample.core")], imports=[])
    )
    diagnostics = interface_diagnostics(contract, observation)
    assert [item.pointer for item in diagnostics] == ["/components/0/public/0"]
    assert diagnostics[0].code == "interface.unused"


@pytest.mark.parametrize(
    ("subjects", "target", "entry"),
    [
        (("sample.cli", "sample.core"), "sample.core", "sample.core"),
        (("sample.cli", "sample.core.api.run"), "sample.core.api", "sample.core.api:run"),
    ],
)
def test_baseline_roles_prove_the_public_entry_that_lost_its_importer(
    subjects: tuple[str, str], target: str, entry: str
) -> None:
    contract = parse_contract(
        {
            "schema_version": "2.1.0",
            "components": [
                _component("core", public=[entry]),
                _component("cli"),
            ],
            "rules": [_INTERFACE_RULE],
        }
    )
    known = (
        KnownViolation(
            ViolationFingerprint(("DEP-IMPORT",), subjects),
            1,
            (("sample.cli", target),),
        ),
    )

    assert _resolved_public_entries(contract, known, ()) == (("core", entry),)


def test_unrelated_resolved_role_does_not_suppress_public_entry() -> None:
    contract = parse_contract(
        {
            "schema_version": "2.1.0",
            "components": [
                _component("core", public=["sample.core.api"]),
                _component("cli"),
            ],
            "rules": [_INTERFACE_RULE],
        }
    )
    known = (
        KnownViolation(
            ViolationFingerprint(("DEP-IMPORT",), ("sample.cli", "sample.other")),
            1,
            (("sample.cli", "sample.other"),),
        ),
    )

    assert _resolved_public_entries(contract, known, ()) == ()


def test_mismatched_target_subject_does_not_suppress_public_entry() -> None:
    contract = parse_contract(
        {
            "schema_version": "2.1.0",
            "components": [
                _component("core", public=["sample.core.api:run"]),
                _component("cli"),
            ],
            "rules": [_INTERFACE_RULE],
        }
    )
    known = (
        KnownViolation(
            ViolationFingerprint(("DEP-IMPORT",), ("sample.cli", "sample.other.run")),
            1,
            (("sample.cli", "sample.core.api"),),
        ),
    )

    assert _resolved_public_entries(contract, known, ()) == ()


def test_multiple_gone_roles_fail_closed() -> None:
    contract = parse_contract(
        {
            "schema_version": "2.1.0",
            "components": [
                _component(
                    "core",
                    public=["sample.core.api:run", "sample.core.other:run"],
                ),
                _component("cli"),
            ],
            "rules": [_INTERFACE_RULE],
        }
    )
    known = (
        KnownViolation(
            ViolationFingerprint(("DEP-IMPORT",), ("sample.cli", "sample.core.api.run")),
            1,
            (
                ("sample.cli", "sample.core.api"),
                ("sample.cli", "sample.core.other"),
            ),
        ),
    )

    assert _resolved_public_entries(contract, known, ()) == ()


def test_remaining_importer_role_does_not_resolve_public_entry() -> None:
    contract = parse_contract(
        {
            "schema_version": "2.1.0",
            "components": [_component("core", public=["sample.core.api:run"]), _component("cli")],
            "rules": [_INTERFACE_RULE],
        }
    )
    fingerprint = ViolationFingerprint(("DEP-IMPORT",), ("sample.cli", "sample.core.api.run"))
    known = (
        KnownViolation(
            fingerprint,
            1,
            (
                ("sample.cli", "sample.core.api"),
                ("sample.cli", "sample.core.api.extra"),
            ),
        ),
    )
    observed = (KnownViolation(fingerprint, 1, (("sample.cli", "sample.core.api.extra"),)),)

    assert _resolved_public_entries(contract, known, observed) == ()


def test_old_baseline_without_roles_cannot_suppress_public_entry() -> None:
    contract = parse_contract(
        {
            "schema_version": "2.1.0",
            "components": [
                _component("core", public=["sample.core.api"]),
                _component("cli"),
            ],
            "rules": [_INTERFACE_RULE],
        }
    )
    known = (
        KnownViolation(ViolationFingerprint(("DEP-IMPORT",), ("sample.cli", "sample.core.api")), 1),
    )

    assert _resolved_public_entries(contract, known, ()) == ()


def test_only_the_proven_public_entry_is_suppressed() -> None:
    contract = parse_contract(
        {
            "schema_version": "2.1.0",
            "components": [
                _component("core", public=["sample.core.api", "sample.core.other"]),
                _component("cli"),
            ],
            "rules": [_INTERFACE_RULE],
        }
    )
    observation = parse_observation(
        _model(
            git_head="a" * 40,
            modules=[_module("sample.core.api"), _module("sample.core.other")],
            imports=[],
        )
    )

    diagnostics = interface_diagnostics(
        contract, observation, frozenset({("core", "sample.core.api")})
    )

    assert [(item.code, item.subject) for item in diagnostics] == [
        ("interface.unused", "sample.core.other")
    ]


def test_validate_reports_the_resolved_import_and_exact_interface_narrowing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    contract = {
        "schema_version": "2.1.0",
        "components": [
            _component("core", public=["sample.core.api:run"]),
            _component("cli"),
        ],
        "rules": [_INTERFACE_RULE],
    }
    (tmp_path / "contract.json").write_text(json.dumps(contract))
    docs = tmp_path / "docs/architecture"
    docs.mkdir(parents=True)
    (docs / "sample.md").write_text(f"{COMPONENT_GRAPH_MARKER}\n```mermaid\n```\n")

    raw = _model(
        git_head="a" * 40,
        modules=[_module("sample.core.api"), _module("sample.cli")],
    )
    raw["imports"] = []
    raw["violations"] = []
    after = parse_observation(raw)
    before = KnownViolation(
        ViolationFingerprint(("DEP-IMPORT",), ("sample.cli", "sample.core.api.run")),
        1,
        (("sample.cli", "sample.core.api"),),
    )
    baseline = tmp_path / "known.json"
    baseline.write_bytes(baseline_bytes((before,)))
    monkeypatch.setattr(
        "archkeel.check.validation.observe_repository",
        lambda *_args, **_kwargs: ObservationResult(after, after.coverage, ()),
    )

    result, _ = run_validate(
        tmp_path,
        ScanConfig(("sample",), "sample", "contract.json", "0" * 64),
        observe,
        baseline=baseline,
    )

    assert result.exit_code == 1
    assert result.diagnostics == ()
    assert result.failures == (
        "resolved violation: DEP-IMPORT | sample.cli sample.core.api.run "
        "(0 observed, 1 in the baseline); rewrite the baseline with --write-baseline",
        "resolved public entry: sample.core.api:run is no longer reached; remove it from "
        "core.public",
    )


def test_resolved_import_with_allowed_current_import_does_not_narrow_public_entry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    contract = {
        "schema_version": "2.1.0",
        "components": [
            _component("core", public=["sample.core.api:run"]),
            _component("cli"),
        ],
        "rules": [_INTERFACE_RULE],
    }
    (tmp_path / "contract.json").write_text(json.dumps(contract))
    docs = tmp_path / "docs/architecture"
    docs.mkdir(parents=True)
    (docs / "sample.md").write_text(
        f"{COMPONENT_GRAPH_MARKER}\n```mermaid\ngraph TD\n  cli --> core\n```\n"
    )

    raw = _model(
        git_head="a" * 40,
        modules=[_module("sample.core.api"), _module("sample.cli")],
        imports=[
            _cross_import(
                "sample.core.api",
                symbol="run",
                reexport_chain=["sample.core.api.run"],
                source_package="sample.cli",
                target_package="sample.core",
            )
        ],
    )
    raw["violations"] = []
    after = parse_observation(raw)
    before = KnownViolation(
        ViolationFingerprint(("DEP-IMPORT",), ("sample.cli", "sample.core.api.run")),
        1,
        (("sample.cli", "sample.core.api"),),
    )
    baseline = tmp_path / "known.json"
    baseline.write_bytes(baseline_bytes((before,)))
    monkeypatch.setattr(
        "archkeel.check.validation.observe_repository",
        lambda *_args, **_kwargs: ObservationResult(after, after.coverage, ()),
    )

    result, _ = run_validate(
        tmp_path,
        ScanConfig(("sample",), "sample", "contract.json", "0" * 64),
        observe,
        baseline=baseline,
    )

    assert result.exit_code == 1
    assert result.diagnostics == ()
    assert result.failures == (
        "resolved violation: DEP-IMPORT | sample.cli sample.core.api.run "
        "(0 observed, 1 in the baseline); rewrite the baseline with --write-baseline",
    )


def _api_import() -> dict[str, object]:
    """One cross-component import that reaches `sample.core.api:run` the old way."""
    return _cross_import("sample.core.api", symbol="run", reexport_chain=["sample.core.api.run"])


def _function(qualified_name: str, *facade_types: str) -> dict[str, object]:
    """One symbol record, carrying the types its signature exposes when it is a facade."""
    module, _, name = qualified_name.rpartition(".")
    data: dict[str, object] = {
        "qualified_name": qualified_name,
        "module": module,
        "name": name,
        "symbol_category": "function",
    }
    if facade_types:
        data["facade_types"] = list(facade_types)
    return _record(f"SYM-{qualified_name}", kind="function", data=data)


def test_public_entry_a_declared_facade_signature_exposes_is_used() -> None:
    """AD-65: `sample.core.ports:Widget` is reached, although nothing imports it.

    `core`'s own declared facade `sample.core.api:run` takes it as a parameter, so the type is
    exposed to every consumer of that signature. Reporting it `interface.unused` made the entry
    `boundary_types` asks for (AD-63) impossible to declare, issue #57.
    """
    contract = parse_contract(
        {
            "schema_version": "2.1.0",
            "components": [
                _component("core", public=["sample.core.api:run", "sample.core.ports:Widget"]),
                _component("cli"),
            ],
            "rules": [_INTERFACE_RULE],
        }
    )
    observation = parse_observation(
        _model(
            git_head="a" * 40,
            modules=[_module("sample.core.api"), _module("sample.core.ports")],
            imports=[_api_import()],
            symbols=[_function("sample.core.api.run", "sample.core.ports.Widget")],
        )
    )
    assert interface_diagnostics(contract, observation) == ()


def test_public_entry_only_an_internal_signature_names_is_still_unused() -> None:
    """AD-65's limit: only a *declared facade* signature reaches an entry. `internal` is not
    covered by `core`'s public list, so the analyzer records no facade type for it and
    `sample.core.ports:Widget` stays `interface.unused`."""
    contract = parse_contract(
        {
            "schema_version": "2.1.0",
            "components": [
                _component("core", public=["sample.core.api:run", "sample.core.ports:Widget"]),
                _component("cli"),
            ],
            "rules": [_INTERFACE_RULE],
        }
    )
    observation = parse_observation(
        _model(
            git_head="a" * 40,
            modules=[_module("sample.core.api"), _module("sample.core.ports")],
            imports=[_api_import()],
            symbols=[_function("sample.core.api.internal")],
        )
    )
    diagnostics = interface_diagnostics(contract, observation)
    assert [(item.code, item.pointer) for item in diagnostics] == [
        ("interface.unused", "/components/0/public/1")
    ]


def test_missing_public_entry_is_a_diagnostic() -> None:
    """AD-56: a public entry whose module the scan never saw is missing, not merely unused."""
    contract = parse_contract(
        {
            "schema_version": "2.1.0",
            "components": [_component("core", public=["sample.core:Widget"]), _component("cli")],
            "rules": [_INTERFACE_RULE],
        }
    )
    observation = parse_observation(_model(git_head="a" * 40, imports=[]))
    diagnostics = interface_diagnostics(contract, observation)
    assert [item.pointer for item in diagnostics] == ["/components/0/public/0"]
    assert diagnostics[0].code == "interface.missing"


def test_resolved_entry_suppression_does_not_hide_missing_module() -> None:
    contract = parse_contract(
        {
            "schema_version": "2.1.0",
            "components": [_component("core", public=["sample.core:Widget"]), _component("cli")],
            "rules": [_INTERFACE_RULE],
        }
    )
    observation = parse_observation(_model(git_head="a" * 40, imports=[]))

    diagnostics = interface_diagnostics(
        contract, observation, frozenset({("core", "sample.core:Widget")})
    )

    assert [(item.code, item.subject) for item in diagnostics] == [
        ("interface.missing", "sample.core:Widget")
    ]


def test_missing_public_api_entry_is_a_diagnostic() -> None:
    """AD-66: a `declarations.public_api` entry the scan never saw is missing, the one signal
    an external surface has, since nothing inside the scan crosses into it to leave it unused."""
    contract = parse_contract(
        {
            "schema_version": "2.1.0",
            "components": [],
            "rules": [],
            "declarations": {"public_api": ["sample.core:Widget"]},
        }
    )
    observation = parse_observation(_model(git_head="a" * 40, imports=[]))
    diagnostics = public_api_diagnostics(contract, observation)
    assert [item.pointer for item in diagnostics] == ["/declarations/public_api/0"]
    assert diagnostics[0].code == "api_surface.missing"


def test_built_public_api_entry_has_no_diagnostic() -> None:
    """AD-66: a `declarations.public_api` entry whose module the scan saw is not missing.

    `Widget` is recorded as a scanned class (AD-72) so this stays about AD-66's own module-only
    existence check, undisturbed by whether the module's own `__all__` or its `symbols` prove
    the name -- both of which are exercised by their own tests below.
    """
    contract = parse_contract(
        {
            "schema_version": "2.1.0",
            "components": [],
            "rules": [],
            "declarations": {"public_api": ["sample.core:Widget"]},
        }
    )
    raw = _model(git_head="a" * 40, modules=[_module("sample.core")], imports=[])
    raw["symbols"] = [_symbol("sample.core", "Widget", kind="class")]
    observation = parse_observation(raw)
    assert public_api_diagnostics(contract, observation) == ()


def test_public_api_name_outside_declared_all_is_missing() -> None:
    """AD-71: a module with `__all__` states its surface, so a name outside it is proven absent."""
    contract = parse_contract(
        {
            "schema_version": "2.1.0",
            "components": [],
            "rules": [],
            "declarations": {"public_api": ["sample.core:Widget"]},
        }
    )
    observation = parse_observation(
        _model(
            git_head="a" * 40,
            modules=[_module("sample.core", all_exports=["Gadget"])],
            imports=[],
        )
    )
    diagnostics = public_api_diagnostics(contract, observation)
    assert [item.pointer for item in diagnostics] == ["/declarations/public_api/0"]
    assert diagnostics[0].code == "api_surface.missing"


def test_public_api_name_inside_declared_all_has_no_diagnostic() -> None:
    """AD-71: a name the module's own `__all__` lists is proven present, so nothing is flagged."""
    contract = parse_contract(
        {
            "schema_version": "2.1.0",
            "components": [],
            "rules": [],
            "declarations": {"public_api": ["sample.core:Widget"]},
        }
    )
    observation = parse_observation(
        _model(
            git_head="a" * 40,
            modules=[_module("sample.core", all_exports=["Widget"])],
            imports=[],
        )
    )
    assert public_api_diagnostics(contract, observation) == ()


def _unknowns_naming(observation: Observation, entry: str) -> list[Record]:
    """Every `unknowns` record whose `subjects` name one `declarations.public_api` entry."""
    unknowns = observation.records("unknowns") or ()
    return [item for item in unknowns if entry in item.subjects]


def test_public_api_diagnostics_never_flags_an_entry_the_analyzer_already_marked_unknown() -> None:
    """AD-72: an `unknowns` record is the analyzer's verdict, not a draft for `check` to gate on.

    Built by hand so this holds regardless of how the analyzer eventually decides
    `sample.core:WIDGET_LIMIT` is undecidable: whatever `kind` or `data` an `api_surface_limit`
    (or similarly named) `unknowns` record carries, `public_api_diagnostics` must stay silent
    for the entry it names -- an undecidable position is a limit of the scan, not a proven
    defect (AD-67's own boundary for `dynamic_call_limit`/`context_alias_limit`), so it must
    never move `validate`'s exit code. This guard is what stops a later change from folding an
    `unknowns` entry back into a coded or uncoded diagnostic.
    """
    contract = parse_contract(
        {
            "schema_version": "2.1.0",
            "components": [],
            "rules": [],
            "declarations": {"public_api": ["sample.core:WIDGET_LIMIT"]},
        }
    )
    raw = _model(git_head="a" * 40, modules=[_module("sample.core")], imports=[])
    unknown_record = _record(
        "UNKNOWN-API-SURFACE-WIDGET-LIMIT",
        kind="api_surface_limit",
        evidence_class="UNKNOWN",
        data={
            "module": "sample.core",
            "name": "WIDGET_LIMIT",
            "reason": "The module declares no __all__ and the scan records no class or "
            "function of this name.",
        },
    )
    unknown_record["subjects"] = ["sample.core:WIDGET_LIMIT"]
    raw["unknowns"] = [unknown_record]
    observation = parse_observation(raw)
    assert _unknowns_naming(observation, "sample.core:WIDGET_LIMIT") != []
    assert public_api_diagnostics(contract, observation) == ()


def test_public_api_name_without_all_is_unknown_to_the_analyzer_only_when_unprovable(
    tmp_path: Path,
) -> None:
    """AD-72: the analyzer, not `check`, decides a `public_api` name `__all__` never declared.

    `shop.app.orders:place_order` is a real scanned function, so the scan itself proves the
    promise kept; `shop.app.orders:TypoThatIsNotReal` is the reviewer's own example -- its
    module declares no `__all__` and `symbols` records no such name -- so neither the module nor
    the scan can prove or disprove it. Only the second is recorded as `unknowns`; `validate`
    reports it there, not as a diagnostic (coded or not) of any kind, and `public_api_diagnostics`
    stays silent for both -- so the exit code, and `declared_rules`, are exactly what the clean
    sample already gives, unmoved by an entry nothing could settle.
    """
    # The clean sample already declares shop.app.orders:place_order as public_api (a real
    # scanned function); only the reviewer's unprovable name needs adding.
    shop_contract = json.loads((FIXTURE_DIR / "architecture-contract.json").read_text())
    assert "shop.app.orders:place_order" in shop_contract["declarations"]["public_api"]
    shop_contract["declarations"]["public_api"] = [
        *shop_contract["declarations"]["public_api"],
        "shop.app.orders:TypoThatIsNotReal",
    ]
    root = _prepare_repo(
        tmp_path,
        {"architecture-contract.json": json.dumps(shop_contract, indent=2) + "\n"},
    )
    observed = observe_repository(root, SHOP_CONFIG, observe)
    assert observed.diagnostics == ()
    observation = observed.observation
    assert observation is not None
    contract = parse_contract(decode_json((root / "architecture-contract.json").read_bytes()))

    assert public_api_diagnostics(contract, observation) == ()
    assert _unknowns_naming(observation, "shop.app.orders:place_order") == []
    unresolved = _unknowns_naming(observation, "shop.app.orders:TypoThatIsNotReal")
    assert len(unresolved) == 1, unresolved
    unknown = unresolved[0]
    assert unknown.data.get("module") == "shop.app.orders"
    assert unknown.data.get("name") == "TypoThatIsNotReal"

    result, _ = run_validate(root, SHOP_CONFIG, observe)
    assert result.exit_code == 0
    assert result.diagnostics == ()
    # AD-72: the entry is what the contract declared and nothing could settle, so the run is
    # honest about it -- and says so without gating, which the two assertions above hold.
    assert result.declared_rules == "UNKNOWN"


def test_planned_entry_not_yet_built_has_no_diagnostic() -> None:
    """AD-56: a planned entry the scan never saw is target work, not a finding."""
    contract = parse_contract(
        {
            "schema_version": "2.1.0",
            "components": [
                _component("core", planned=["sample.core:Widget"]),
                _component("cli"),
            ],
            "rules": [_INTERFACE_RULE],
        }
    )
    observation = parse_observation(_model(git_head="a" * 40, imports=[]))
    assert interface_diagnostics(contract, observation) == ()


def test_planned_entry_built_but_unused_is_target_work() -> None:
    """AD-56/#79: a built planned entry stays target work until code reaches it."""
    contract = parse_contract(
        {
            "schema_version": "2.1.0",
            "components": [
                _component("core", planned=["sample.core:Widget"]),
                _component("cli"),
            ],
            "rules": [_INTERFACE_RULE],
        }
    )
    observation = parse_observation(
        _model(git_head="a" * 40, modules=[_module("sample.core")], imports=[])
    )
    assert interface_diagnostics(contract, observation) == ()


def test_built_planned_entry_reached_by_import_needs_promotion() -> None:
    """#79: reaching a planned entry is the point at which promotion becomes required."""
    contract = parse_contract(
        {
            "schema_version": "2.1.0",
            "components": [
                _component("core", public=[], planned=["sample.core:Widget"]),
                _component("cli"),
            ],
            "rules": [_INTERFACE_RULE],
        }
    )
    observation = parse_observation(
        _model(
            git_head="a" * 40,
            modules=[_module("sample.core")],
            imports=[
                _cross_import(
                    "sample.core",
                    imported_names=["Widget"],
                    reexport_chain=["sample.core.Widget"],
                )
            ],
        )
    )
    diagnostics = interface_diagnostics(contract, observation)
    assert [item.pointer for item in diagnostics] == ["/components/0/planned/0"]
    assert diagnostics[0].code == "interface.planned_built"


def test_public_entry_used_through_a_reexport_chain_has_no_diagnostic() -> None:
    contract = parse_contract(
        {
            "schema_version": "2.1.0",
            "components": [
                _component("core", public=["sample.core.impl:Widget"]),
                _component("cli"),
            ],
            "rules": [_INTERFACE_RULE],
        }
    )
    observation = parse_observation(
        _model(
            git_head="a" * 40,
            imports=[
                _cross_import(
                    "sample.core",
                    reexport_chain=["sample.core.Widget", "sample.core.impl.Widget"],
                )
            ],
        )
    )
    assert interface_diagnostics(contract, observation) == ()


@pytest.mark.parametrize(
    ("public", "pointers"),
    [("sample.core.impl", []), ("sample.core:impl", ["/components/0/public/0"])],
)
def test_a_submodule_import_uses_the_module_entry_and_never_the_name_entry(
    public: str, pointers: list[str]
) -> None:
    """`from sample.core import impl` records the module `sample.core.impl` and no symbol."""
    contract = parse_contract(
        {
            "schema_version": "2.1.0",
            "components": [_component("core", public=[public]), _component("cli")],
            "rules": [_INTERFACE_RULE],
        }
    )
    observation = parse_observation(
        _model(
            git_head="a" * 40,
            modules=[_module("sample.core")],
            imports=[_cross_import("sample.core.impl", symbol=None, reexport_chain=[])],
        )
    )
    diagnostics = interface_diagnostics(contract, observation)
    assert [item.pointer for item in diagnostics] == pointers


def test_no_interface_rule_means_neither_diagnostic() -> None:
    contract = parse_contract(
        {
            "schema_version": "2.1.0",
            "components": [_component("core"), _component("cli")],
            "rules": [],
        }
    )
    observation = parse_observation(
        _model(git_head="a" * 40, imports=[_cross_import("sample.core")])
    )
    assert interface_diagnostics(contract, observation) == ()


def test_a_violated_inside_rule_points_at_the_component_that_declares_the_level(
    tmp_path: Path,
) -> None:
    """AD-36: the rule is in no `rules` array here, so `/rules/0` would blame another rule."""
    variant = next(item for item in CATALOG if item.id == "class-a-complete-requires-inside")
    root = _prepare_repo(tmp_path, dict(variant.files))

    diagnostics = run_validate(root, SHOP_CONFIG, observe)[0].diagnostics

    assert {item.pointer for item in diagnostics} == {"/components/1/inside"}
    assert {item.subject for item in diagnostics} == {"store:STORE-REQUIRES-COMPLETE"}


def test_write_graph_writes_the_graph_init_writes() -> None:
    """AD-46: one edge format for both writers, and a current graph is left alone."""
    empty = ArchitectureContract(CONTRACT_SCHEMA_VERSION, (), ())
    edges = frozenset({("cli", "app"), ("app", "model")})
    drafted = architecture_document("shop", empty, frozenset({("cli", "model")}), ())
    current = architecture_document("shop", empty, edges, ())

    assert rewrite_component_graph((("shop.md", drafted),), edges, frozenset()) == (
        ("shop.md", current),
    )
    assert rewrite_component_graph((("shop.md", current),), edges, frozenset()) == ()
    # A block without a diagram line gets the one `init` writes.
    block = f"{COMPONENT_GRAPH_MARKER}\n```mermaid\n```\n"
    assert rewrite_component_graph((("shop.md", block),), edges, frozenset()) == (
        (
            "shop.md",
            block.replace("```\n", "graph TD\n    app --> model\n    cli --> app\n```\n"),
        ),
    )


def test_write_graph_changes_nothing_without_exactly_one_marked_graph() -> None:
    """AD-46: which graph to rewrite is ambiguous there, so `graph.count` is the answer."""
    edges = frozenset({("cli", "app")})
    page = f"# Shop\n\n{COMPONENT_GRAPH_MARKER}\n```mermaid\ngraph TD\n```\n"
    assert (
        rewrite_component_graph(
            (("a.md", "# Shop\n```mermaid\ngraph TD\n```\n"),), edges, frozenset()
        )
        == ()
    )
    assert rewrite_component_graph((("a.md", page), ("b.md", page)), edges, frozenset()) == ()
    assert rewrite_component_graph((("a.md", page + page),), edges, frozenset()) == ()


def test_write_graph_adds_the_declaration_a_block_lacks() -> None:
    """AD-46: a `%%` comment is kept, but it is no diagram declaration and cannot stand in."""
    block = (
        f"{COMPONENT_GRAPH_MARKER}\n```mermaid\n%% generated component graph\ncli --> core\n```\n"
    )
    assert rewrite_component_graph(
        (("a.md", block),), frozenset({("cli", "core")}), frozenset()
    ) == (
        (
            "a.md",
            f"{COMPONENT_GRAPH_MARKER}\n```mermaid\ngraph TD\n%% generated component graph\n"
            "    cli --> core\n```\n",
        ),
    )


@pytest.mark.parametrize(
    ("body", "structure"),
    [
        ("flowchart LR\n    subgraph core\n    cli --> core\n    end\n", "subgraph core"),
        ("flowchart LR\n    cli -->|uses| core\n    core --> ir\n", "cli -->|uses| core"),
        ("flowchart LR\n    cli --> core\n    classDef hot fill:#f96\n", "classDef hot fill:#f96"),
    ],
    ids=["subgraph", "labeled-edge", "style"],
)
def test_write_graph_leaves_a_block_it_cannot_read_to_the_architect(
    body: str, structure: str
) -> None:
    """AD-46: only a declaration, `%%` comments and plain edges are known to survive a rewrite."""
    documents = (("a.md", f"{COMPONENT_GRAPH_MARKER}\n```mermaid\n{body}```\n"),)
    assert rewrite_component_graph(documents, frozenset({("core", "ir")}), frozenset()) == ()

    contract = parse_contract({"schema_version": "2.1.0", "components": [], "rules": []})
    observation = parse_observation(_model(git_head="a" * 40))
    (drift,) = graph_diagnostics(contract, observation, documents)
    assert drift.code == "graph.drift"
    assert f"`{structure}`" in drift.remedy
    assert "by hand" in drift.remedy


def test_target_graph_matches_the_edges_the_contract_permits() -> None:
    """AD-57: a target marker whose edges equal `target_component_edges` passes cleanly."""
    contract = parse_contract(_contract_with_allowed_dependency("core", "cli"))
    observation = parse_observation(_model(git_head="a" * 40))
    documents = (
        (
            "sample.md",
            f"{COMPONENT_GRAPH_MARKER}\n```mermaid\ngraph TD\n```\n\n"
            f"{TARGET_GRAPH_MARKER}\n```mermaid\ngraph TD\n    core --> cli\n```\n",
        ),
    )
    assert graph_diagnostics(contract, observation, documents) == ()


def test_graph_drift_explains_edges_gone_from_code() -> None:
    """A drawn edge absent from imports is explicitly reported as gone from code."""
    contract = parse_contract(
        {
            "schema_version": "2.1.0",
            "components": [_component("core"), _component("cli")],
            "rules": [],
        }
    )
    observation = parse_observation(_model(git_head="a" * 40))
    documents = (
        ("sample.md", f"{COMPONENT_GRAPH_MARKER}\n```mermaid\ngraph TD\n    core --> cli\n```\n"),
    )

    (drift,) = graph_diagnostics(contract, observation, documents)

    assert drift.unknown_claim == (
        "The marked component graph differs from observed imports; "
        "edges gone from code (drawn, not observed): core->cli; "
        "edges new in code (observed, not drawn): none."
    )


def test_graph_drift_explains_edges_new_in_code() -> None:
    """An import absent from the graph is explicitly reported as new in code."""
    contract = parse_contract(
        {
            "schema_version": "2.1.0",
            "components": [_component("core"), _component("cli")],
            "rules": [],
        }
    )
    observation = parse_observation(
        _model(git_head="a" * 40, imports=[_cross_import("sample.core")])
    )
    documents = (("sample.md", f"{COMPONENT_GRAPH_MARKER}\n```mermaid\ngraph TD\n```\n"),)

    (drift,) = graph_diagnostics(contract, observation, documents)

    assert drift.unknown_claim == (
        "The marked component graph differs from observed imports; "
        "edges gone from code (drawn, not observed): none; "
        "edges new in code (observed, not drawn): cli->core."
    )


def test_target_graph_drift_names_the_target_marker() -> None:
    """AD-57: a stale target marker is graph.drift naming the target graph, not the observed."""
    contract = parse_contract(_contract_with_allowed_dependency("core", "cli"))
    observation = parse_observation(_model(git_head="a" * 40))
    documents = (
        (
            "sample.md",
            f"{COMPONENT_GRAPH_MARKER}\n```mermaid\ngraph TD\n```\n\n"
            f"{TARGET_GRAPH_MARKER}\n```mermaid\ngraph TD\n```\n",
        ),
    )
    (drift,) = graph_diagnostics(contract, observation, documents)
    assert drift.code == "graph.drift"
    assert drift.subject == "sample.md (target graph)"
    assert drift.unknown_claim == (
        "The marked target graph differs from the edges the contract permits; "
        "edges gone from contract (drawn, not permitted): none; "
        "edges new in contract (permitted, not drawn): core->cli."
    )
    assert "archkeel validate --write-graph" in drift.remedy


def test_target_graph_drift_explains_edges_gone_from_contract() -> None:
    """A drawn target edge absent from permissions is reported as gone from contract."""
    contract = parse_contract(
        {
            "schema_version": "2.1.0",
            "components": [_component("core"), _component("cli")],
            "rules": [],
        }
    )
    observation = parse_observation(_model(git_head="a" * 40))
    documents = (
        (
            "sample.md",
            f"{COMPONENT_GRAPH_MARKER}\n```mermaid\ngraph TD\n```\n\n"
            f"{TARGET_GRAPH_MARKER}\n```mermaid\ngraph TD\n    core --> cli\n```\n",
        ),
    )

    (drift,) = graph_diagnostics(contract, observation, documents)

    assert drift.unknown_claim == (
        "The marked target graph differs from the edges the contract permits; "
        "edges gone from contract (drawn, not permitted): core->cli; "
        "edges new in contract (permitted, not drawn): none."
    )


def test_a_page_with_only_the_observed_marker_behaves_exactly_as_before() -> None:
    """AD-57: the target marker is optional; its absence adds no diagnostic and no requirement."""
    contract = parse_contract(_contract_with_allowed_dependency("core", "cli"))
    observation = parse_observation(_model(git_head="a" * 40))
    documents = (("sample.md", f"{COMPONENT_GRAPH_MARKER}\n```mermaid\ngraph TD\n```\n"),)
    assert graph_diagnostics(contract, observation, documents) == ()


def test_write_graph_regenerates_both_marked_graphs_on_one_page() -> None:
    """AD-57: one page carrying both markers comes back once, with both blocks rewritten."""
    documents = (
        (
            "sample.md",
            f"{COMPONENT_GRAPH_MARKER}\n```mermaid\ngraph TD\n```\n\n"
            f"{TARGET_GRAPH_MARKER}\n```mermaid\ngraph TD\n```\n",
        ),
    )
    edits = rewrite_component_graph(
        documents, frozenset({("cli", "app")}), frozenset({("app", "model")})
    )
    assert edits == (
        (
            "sample.md",
            f"{COMPONENT_GRAPH_MARKER}\n```mermaid\ngraph TD\n    cli --> app\n```\n\n"
            f"{TARGET_GRAPH_MARKER}\n```mermaid\ngraph TD\n    app --> model\n```\n",
        ),
    )


def test_write_graph_leaves_a_target_block_it_cannot_read_to_the_architect() -> None:
    """AD-57: the target marker follows AD-46's same allowlist; a subgraph is left to a human."""
    documents = (
        (
            "sample.md",
            f"{COMPONENT_GRAPH_MARKER}\n```mermaid\ngraph TD\n```\n\n"
            f"{TARGET_GRAPH_MARKER}\n```mermaid\nflowchart LR\n    subgraph core\n"
            "    cli --> core\n    end\n```\n",
        ),
    )
    assert rewrite_component_graph(documents, frozenset(), frozenset({("cli", "core")})) == ()

    contract = parse_contract({"schema_version": "2.1.0", "components": [], "rules": []})
    observation = parse_observation(_model(git_head="a" * 40))
    (drift,) = graph_diagnostics(contract, observation, documents)
    assert drift.code == "graph.drift"
    assert drift.subject == "sample.md (target graph)"
    assert "`subgraph core`" in drift.remedy
    assert "by hand" in drift.remedy
