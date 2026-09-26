# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Keep explicit inside-contract trees closed across observation and revision checks."""

from __future__ import annotations

import json
import subprocess
from contextlib import nullcontext
from hashlib import sha256
from pathlib import Path
from unittest.mock import patch

import pytest
from test_analyzer import _component, _observe
from test_delta import _model
from test_expectation import _expectation_payload
from test_git_lock import _lock

from archkeel.analyzer import observe
from archkeel.check.git import GitError
from archkeel.check.ports import ScanConfig
from archkeel.check.run import _authenticate_inputs, materialize_declarations
from archkeel.check.validation import (
    COMPONENT_GRAPH_MARKER,
    _inside_contract_tree,
    inside_diagnostics,
    run_validate,
)
from archkeel.ir.codec import (
    amendment_bytes,
    canonical_report_bytes,
    contract_digest,
    declaration_paths,
    load_inside_contract_tree,
    parse_contract,
)
from archkeel.ir.levels import inside_levels
from archkeel.ir.lock import LOCK_PATH, LockError
from archkeel.ir.model import ArchitectureContract, RunResult
from archkeel.ir.widening import Amendment
from archkeel.render.html import render_html

_PROVENANCE = ["docs/architecture/sample.md"]
_COMPLETE_REQUIRES = {
    "id": "REQUIRES-COMPLETE",
    "kind": "complete_requires",
    "rationale": "Probe.",
    "provenance": _PROVENANCE,
    "decided_by": "architect",
}


def _component_at(label: str, package: str, *, inside: str | None = None) -> dict[str, object]:
    component = _component(label, packages=[package], public=[])
    if inside is not None:
        component["inside"] = inside
    return component


def _contract(
    components: list[dict[str, object]], rules: list[dict[str, object]]
) -> dict[str, object]:
    return {"schema_version": "2.1.0", "components": components, "rules": rules}


def _scan_config() -> ScanConfig:
    return ScanConfig(("sample",), "sample", "contract.json", "0" * 64)


def _load_tree(root: Path, contract: ArchitectureContract):
    return load_inside_contract_tree(
        "contract.json",
        contract,
        contract_digest(contract),
        "contract.json",
        lambda path: ((root / path).read_bytes(), Path(path).as_posix()),
    )


def _write_three_levels(
    root: Path,
    *,
    deep_rules: list[dict[str, object]] | None = None,
    source_import: str = "",
) -> None:
    (root / "pyproject.toml").write_text('[project]\nrequires-python = ">=3.11"\n')
    (root / "contracts").mkdir(parents=True)
    (root / "sample/layer/source").mkdir(parents=True)
    (root / "sample/layer/target").mkdir(parents=True)
    (root / "sample/__init__.py").write_text("")
    (root / "sample/layer/__init__.py").write_text("")
    (root / "sample/layer/source/__init__.py").write_text("")
    (root / "sample/layer/target/__init__.py").write_text("")
    (root / "sample/layer/source/api.py").write_text(source_import)
    (root / "sample/layer/target/api.py").write_text("VALUE = 1\n")
    docs = root / "docs/architecture"
    docs.mkdir(parents=True)
    (docs / "sample.md").write_text(f"{COMPONENT_GRAPH_MARKER}\n```mermaid\ngraph TD\n```\n")

    (root / "contract.json").write_text(
        json.dumps(
            _contract(
                [_component_at("app", "sample", inside="contracts/one.json")],
                [dict(_COMPLETE_REQUIRES)],
            )
        )
    )
    (root / "contracts/one.json").write_text(
        json.dumps(
            _contract(
                [_component_at("app", "sample.layer", inside="contracts/two.json")],
                [dict(_COMPLETE_REQUIRES)],
            )
        )
    )
    (root / "contracts/two.json").write_text(
        json.dumps(
            _contract(
                [
                    _component_at("source", "sample.layer.source"),
                    _component_at("target", "sample.layer.target"),
                ],
                [dict(_COMPLETE_REQUIRES), *(deep_rules or [])],
            )
        )
    )


def _forbidden_edge() -> dict[str, object]:
    return {
        "id": "DEEP-NO-EDGE",
        "kind": "forbidden_dependency",
        "source": "sample.layer.source",
        "target": "sample.layer.target",
        "include_type_checking": True,
        "rationale": "Probe.",
        "provenance": _PROVENANCE,
        "decided_by": "architect",
    }


def _commit_tree(root: Path) -> str:
    for args in (
        ["git", "init", "-q", "-b", "main"],
        ["git", "config", "user.email", "qa@example.invalid"],
        ["git", "config", "user.name", "QA"],
        ["git", "add", "-A"],
        ["git", "-c", "commit.gpgsign=false", "commit", "-q", "-m", "base"],
    ):
        subprocess.run(args, cwd=root, check=True, capture_output=True)
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()


def test_one_level_explicit_inside_remains_a_supported_positive_control(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text('[project]\nrequires-python = ">=3.11"\n')
    (tmp_path / "contracts").mkdir()
    (tmp_path / "sample").mkdir()
    (tmp_path / "sample/__init__.py").write_text("")
    outer = _contract([_component_at("app", "sample", inside="contracts/inside.json")], [])
    inside = _contract([_component_at("child", "sample.child")], [])
    (tmp_path / "contract.json").write_text(json.dumps(outer))
    (tmp_path / "contracts/inside.json").write_text(json.dumps(inside))

    result = _observe(tmp_path)

    assert result.observation is not None
    assert any(
        item.kind == "inside_component_responsibility"
        for item in result.observation.records("declarations") or ()
    )
    assert "contracts/inside.json" in declaration_paths(
        (tmp_path / "contract.json").read_bytes(),
        "contract.json",
        read_contract=lambda path: (
            (tmp_path / path).read_bytes(),
            Path(path).as_posix(),
        ),
    )


def test_three_level_requires_only_tree_enforces_the_leaf_edge_with_unique_record_ids(
    tmp_path: Path,
) -> None:
    _write_three_levels(
        tmp_path,
        source_import="from sample.layer.target.api import VALUE\n",
    )

    result = _observe(tmp_path)

    assert result.observation is not None
    violations = [
        item
        for item in result.observation.records("violations") or ()
        if item.kind == "complete_requires"
    ]
    assert any(
        item.data.get("source_module") == "sample.layer.source.api"
        and item.data.get("target_module") == "sample.layer.target.api"
        for item in violations
    )
    declarations = result.observation.records("declarations") or ()
    record_ids = [item.id for item in declarations if item.kind == "complete_requires"]
    assert len(record_ids) == 3
    assert len(record_ids) == len(set(record_ids))


def test_same_local_rule_ids_at_different_depths_have_distinct_record_ids(tmp_path: Path) -> None:
    _write_three_levels(tmp_path)

    result = _observe(tmp_path)

    assert result.observation is not None
    record_ids = [
        item.id
        for item in result.observation.records("declarations") or ()
        if item.kind == "complete_requires"
    ]
    assert len(record_ids) == 3
    assert len(record_ids) == len(set(record_ids))


def test_deepest_forbidden_dependency_reaches_the_report(tmp_path: Path) -> None:
    _write_three_levels(
        tmp_path,
        deep_rules=[_forbidden_edge()],
        source_import="from sample.layer.target.api import VALUE\n",
    )

    result = _observe(tmp_path)

    assert result.observation is not None
    findings = [
        item
        for item in result.observation.records("violations") or ()
        if item.kind == "forbidden_dependency"
    ]
    assert len(findings) == 1
    assert findings[0].data.get("source_module") == "sample.layer.source.api"
    assert findings[0].data.get("target_module") == "sample.layer.target.api"


def test_deep_inside_level_owns_its_modules_and_crossing(tmp_path: Path) -> None:
    _write_three_levels(
        tmp_path,
        deep_rules=[_forbidden_edge()],
        source_import="from sample.layer.target.api import VALUE\n",
    )
    result = _observe(tmp_path)
    assert result.observation is not None

    deep = next(level for level in inside_levels(result.observation) if level.parent == "app:app")
    components = {item.label: item for item in deep.components}
    assert components["source"].modules == (
        "sample.layer.source",
        "sample.layer.source.api",
    )
    assert components["target"].modules == (
        "sample.layer.target",
        "sample.layer.target.api",
    )
    assert [(edge.source, edge.target, edge.import_sites) for edge in deep.edges] == [
        ("source", "target", 1)
    ]


def test_deep_inside_violation_is_reachable_in_rendered_flow_data(tmp_path: Path) -> None:
    _write_three_levels(
        tmp_path,
        deep_rules=[_forbidden_edge()],
        source_import="from sample.layer.target.api import VALUE\n",
    )
    observation = _observe(tmp_path).observation
    assert observation is not None
    result = RunResult(
        "report",
        0,
        observation_complete="PASS",
        declared_rules="FAIL",
        expectation_fulfilled="n/a",
        coverage=observation.coverage,
    )
    page = render_html(
        result,
        observation,
        repository="sample",
        architecture_href="architecture.json",
    ).decode()
    data_start = page.index('id="flow-data"')
    data_start = page.index(">", data_start) + 1
    data_end = page.index("</script>", data_start)
    flow = json.loads(page[data_start:data_end])
    app = next(item for item in flow["components"] if item["label"] == "app")
    first_level_app = next(item for item in app["inside"]["components"] if item["label"] == "app")

    assert first_level_app.get("inside") is not None
    deep_inside = first_level_app["inside"]
    assert {item["label"] for item in deep_inside["components"]} == {"source", "target"}
    assert any(
        edge["source"] == "source"
        and edge["target"] == "target"
        and edge["state"] == "violation"
        and "app:app:DEEP-NO-EDGE" in edge["rule_ids"]
        for edge in deep_inside["edges"]
    )


def test_colon_labels_cannot_alias_recursive_parent_and_component_ids(tmp_path: Path) -> None:
    _write_three_levels(tmp_path)
    root = json.loads((tmp_path / "contract.json").read_text())
    root["components"][0]["packages"] = ["sample.layer"]
    root["components"].append(
        _component_at("app:app", "sample.other", inside="contracts/side.json")
    )
    (tmp_path / "contract.json").write_text(json.dumps(root))
    (tmp_path / "contracts/side.json").write_text(
        json.dumps(_contract([_component_at("source", "sample.other.source")], []))
    )
    contract = parse_contract(root)

    tree = _load_tree(tmp_path, contract)

    component_ids = [
        component.id for mount in tree.mounts for component in mount.contract.components
    ]
    assert tree.issues or len(component_ids) == len(set(component_ids))


def test_root_rule_id_cannot_alias_a_scoped_inside_rule_id(tmp_path: Path) -> None:
    _write_three_levels(tmp_path, deep_rules=[_forbidden_edge()])
    root = json.loads((tmp_path / "contract.json").read_text())
    root["rules"].append({**_forbidden_edge(), "id": "app:app:DEEP-NO-EDGE"})
    (tmp_path / "contract.json").write_text(json.dumps(root))

    tree = _load_tree(tmp_path, parse_contract(root))

    rule_ids = [item.id for item in tree.comparison_contract.rules]
    assert tree.issues or len(rule_ids) == len(set(rule_ids))


def test_contract_digests_keep_legacy_root_bytes_without_insides(tmp_path: Path) -> None:
    payload = b'{"schema_version":"2.1.0","components":[],"rules":[]}\n'
    (tmp_path / "contract.json").write_bytes(payload)

    result = _observe(tmp_path)

    assert result.observation is not None
    assert result.observation.contract.digest == sha256(payload).hexdigest()
    assert contract_digest(parse_contract(json.loads(payload))) != sha256(payload).hexdigest()


def test_one_level_report_and_validation_digests_keep_their_distinct_inputs(
    tmp_path: Path,
) -> None:
    (tmp_path / "pyproject.toml").write_text('[project]\nrequires-python = ">=3.11"\n')
    (tmp_path / "contracts").mkdir()
    (tmp_path / "sample").mkdir()
    (tmp_path / "sample/__init__.py").write_text("")
    root_payload = (
        json.dumps(
            _contract(
                [_component_at("app", "sample", inside="contracts/inside.json")],
                [],
            ),
            separators=(",", ":"),
        )
        + "\n"
    ).encode()
    child_payload = (
        json.dumps(_contract([_component_at("child", "sample.child")], []), separators=(",", ":"))
        + "\n"
    ).encode()
    (tmp_path / "contract.json").write_bytes(root_payload)
    (tmp_path / "contracts/inside.json").write_bytes(child_payload)
    root_contract = parse_contract(json.loads(root_payload))
    child_contract = parse_contract(json.loads(child_payload))

    observed = _observe(tmp_path).observation
    validated = _inside_contract_tree(tmp_path, "contract.json", root_contract)

    assert observed is not None and validated is not None
    expected_observation = sha256(
        (sha256(root_payload).hexdigest() + sha256(child_payload).hexdigest()).encode()
    ).hexdigest()
    expected_validation = sha256(
        (contract_digest(root_contract) + contract_digest(child_contract)).encode()
    ).hexdigest()
    assert observed.contract.digest == expected_observation
    assert validated.digest == expected_validation
    assert observed.contract.digest != validated.digest


def test_validation_digest_ignores_child_json_formatting(tmp_path: Path) -> None:
    _write_three_levels(tmp_path)
    root_contract = parse_contract(json.loads((tmp_path / "contract.json").read_text()))
    original = _inside_contract_tree(tmp_path, "contract.json", root_contract)
    assert original is not None

    leaf = tmp_path / "contracts/two.json"
    leaf.write_text(json.dumps(json.loads(leaf.read_text()), indent=2))
    reformatted_contract = parse_contract(json.loads((tmp_path / "contract.json").read_text()))
    reformatted = _inside_contract_tree(tmp_path, "contract.json", reformatted_contract)
    assert reformatted is not None

    assert original.digest == reformatted.digest


def test_pre_inside_root_only_amendment_is_refused_for_recursive_policy(tmp_path: Path) -> None:
    _write_three_levels(tmp_path, deep_rules=[_forbidden_edge()])
    base = _commit_tree(tmp_path)
    config = _scan_config()
    leaf = tmp_path / "contracts/two.json"
    leaf_payload = json.loads(leaf.read_text())
    leaf_payload["rules"] = [_COMPLETE_REQUIRES]
    leaf.write_text(json.dumps(leaf_payload))
    root_contract = parse_contract(json.loads((tmp_path / "contract.json").read_text()))
    root_only_digest = contract_digest(root_contract)
    amendment = tmp_path / "legacy-root-only-amendment.json"
    amendment.write_bytes(
        amendment_bytes(
            Amendment(
                root_only_digest,
                root_only_digest,
                "QA architect",
                "Legacy amendment binds only the root contract.",
            )
        )
    )

    result, _ = run_validate(tmp_path, config, observe, against=base, amendment=amendment)

    assert result.exit_code == 1
    assert any("DEEP-NO-EDGE" in failure for failure in result.failures)


def test_revision_declarations_snapshot_copies_the_deepest_contract(tmp_path: Path) -> None:
    _write_three_levels(tmp_path)
    leaf_path = tmp_path / "contracts/two.json"
    leaf = json.loads(leaf_path.read_bytes())
    leaf["components"][0]["provenance"] = ["docs/architecture/leaf.md"]
    leaf_path.write_text(json.dumps(leaf))
    leaf_document = tmp_path / "docs/architecture/leaf.md"
    accepted_provenance = b"The deepest component's decision.\n"
    leaf_document.write_bytes(accepted_provenance)
    revision = _commit_tree(tmp_path)
    leaf_document.write_text("Candidate documentation must not replace accepted evidence.\n")
    snapshot = tmp_path / "snapshot"

    materialize_declarations(
        tmp_path,
        revision,
        ScanConfig(("sample",), "sample", "contract.json", "0" * 64),
        snapshot,
    )

    assert (snapshot / "contracts/one.json").read_bytes() == (
        tmp_path / "contracts/one.json"
    ).read_bytes()
    assert (snapshot / "contracts/two.json").read_bytes() == (
        tmp_path / "contracts/two.json"
    ).read_bytes()
    assert (snapshot / "docs/architecture/leaf.md").read_bytes() == accepted_provenance


def test_snapshot_refuses_missing_accepted_deep_provenance(tmp_path: Path) -> None:
    _write_three_levels(tmp_path)
    leaf_path = tmp_path / "contracts/two.json"
    leaf = json.loads(leaf_path.read_bytes())
    leaf["components"][0]["provenance"] = ["docs/architecture/missing.md"]
    leaf_path.write_text(json.dumps(leaf))
    revision = _commit_tree(tmp_path)

    with pytest.raises(GitError):
        materialize_declarations(
            tmp_path,
            revision,
            ScanConfig(("sample",), "sample", "contract.json", "0" * 64),
            tmp_path / "snapshot",
        )


def test_deep_contract_edit_changes_repeatable_report_digest(tmp_path: Path) -> None:
    _write_three_levels(tmp_path)
    before = _observe(tmp_path).observation
    assert before is not None
    repeated = _observe(tmp_path).observation
    assert repeated is not None
    assert canonical_report_bytes(before) == canonical_report_bytes(repeated)

    leaf_path = tmp_path / "contracts/two.json"
    leaf = json.loads(leaf_path.read_bytes())
    leaf["rules"][0]["rationale"] = "Changed only at the deepest level."
    leaf_path.write_text(json.dumps(leaf))
    after = _observe(tmp_path).observation

    assert after is not None
    assert before.contract.digest != after.contract.digest
    assert canonical_report_bytes(before) != canonical_report_bytes(after)


def test_validate_against_detects_a_deepest_level_rule_removal(tmp_path: Path) -> None:
    _write_three_levels(tmp_path, deep_rules=[_forbidden_edge()])
    base = _commit_tree(tmp_path)
    config = ScanConfig(("sample",), "sample", "contract.json", "0" * 64)

    unchanged, _ = run_validate(tmp_path, config, observe, against=base)
    assert unchanged.exit_code == 0, unchanged.failures

    leaf_path = tmp_path / "contracts/two.json"
    leaf = json.loads(leaf_path.read_bytes())
    leaf["rules"] = [_COMPLETE_REQUIRES]
    leaf_path.write_text(json.dumps(leaf))
    widened, _ = run_validate(tmp_path, config, observe, against=base)

    assert widened.exit_code == 1
    assert widened.failures


def test_amendment_is_bound_to_the_exact_recursive_contract_tree(tmp_path: Path) -> None:
    _write_three_levels(tmp_path, deep_rules=[_forbidden_edge()])
    base = _commit_tree(tmp_path)
    config = ScanConfig(("sample",), "sample", "contract.json", "0" * 64)
    leaf_path = tmp_path / "contracts/two.json"
    leaf = json.loads(leaf_path.read_bytes())
    leaf["rules"] = [_COMPLETE_REQUIRES]
    leaf_path.write_text(json.dumps(leaf))
    amendment = tmp_path / "amendment.json"

    written, artifacts = run_validate(
        tmp_path,
        config,
        observe,
        against=base,
        amendment=amendment,
        write_amendment=True,
        decided_by="QA architect",
        rationale="Approve this exact leaf-only widening.",
    )
    assert written.exit_code == 0, written.diagnostics
    assert str(amendment) in artifacts
    amendment.write_bytes(artifacts[str(amendment)])
    accepted, _ = run_validate(tmp_path, config, observe, against=base, amendment=amendment)
    assert accepted.exit_code == 0, accepted.diagnostics

    leaf["rules"] = []
    leaf_path.write_text(json.dumps(leaf))
    stale, _ = run_validate(tmp_path, config, observe, against=base, amendment=amendment)
    assert stale.exit_code == 1
    assert stale.failures, "The amendment must not authorize a second leaf-only widening"


@pytest.mark.parametrize(
    ("leaf_path", "external_file"),
    [
        ("contracts/missing.json", None),
        ("../outside.json", "outside.json"),
        ("contracts/external.json", "outside.json"),
    ],
)
def test_nested_missing_or_escaping_contract_fails_validation(
    tmp_path: Path, leaf_path: str, external_file: str | None
) -> None:
    _write_three_levels(tmp_path)
    if external_file is not None:
        outside = tmp_path.parent / f"{tmp_path.name}-{external_file}"
        outside.write_text(json.dumps(_contract([], [])))
        if leaf_path == "contracts/external.json":
            (tmp_path / leaf_path).symlink_to(outside)
        else:
            leaf_path = f"../{outside.name}"
    (tmp_path / "contracts/two.json").write_text(
        json.dumps(
            _contract([_component_at("source", "sample.layer.source", inside=leaf_path)], [])
        )
    )
    root_contract = parse_contract(json.loads((tmp_path / "contract.json").read_bytes()))

    diagnostics = inside_diagnostics(tmp_path, root_contract, _scan_config())

    assert diagnostics
    _commit_tree(tmp_path)
    validation, _ = run_validate(
        tmp_path,
        ScanConfig(("sample",), "sample", "contract.json", "0" * 64),
        observe,
    )
    assert validation.exit_code == 2
    assert _observe(tmp_path).diagnostics


@pytest.mark.parametrize("invalid_graph", ["cycle", "duplicate_mount"])
def test_nested_reference_cycles_and_duplicate_mounts_fail_validation(
    tmp_path: Path, invalid_graph: str
) -> None:
    contracts = tmp_path / "contracts"
    contracts.mkdir()
    if invalid_graph == "cycle":
        one = _contract([_component_at("app", "sample.app", inside="contracts/two.json")], [])
        two = _contract([_component_at("app", "sample.app", inside="contracts/one.json")], [])
        root_components = [_component_at("app", "sample", inside="contracts/one.json")]
        (contracts / "one.json").write_text(json.dumps(one))
        (contracts / "two.json").write_text(json.dumps(two))
    else:
        one = _contract([], [])
        root_components = [
            _component_at("left", "sample.left", inside="contracts/one.json"),
            _component_at("right", "sample.right", inside="contracts/one.json"),
        ]
        (contracts / "one.json").write_text(json.dumps(one))
    root_contract = parse_contract(_contract(root_components, []))
    (tmp_path / "contract.json").write_text(json.dumps(_contract(root_components, [])))

    diagnostics = inside_diagnostics(tmp_path, root_contract, _scan_config())

    assert diagnostics
    reason = "reference cycle" if invalid_graph == "cycle" else "duplicate mount"
    assert any(
        item.code == "contract.invalid" and reason in item.unknown_claim for item in diagnostics
    )


@pytest.mark.parametrize(
    ("changed_path", "must_reject"),
    [(None, False), ("contracts/two.json", True), ("docs/architecture/leaf.md", False)],
)
def test_check_locks_transitive_policy_but_allows_candidate_documentation_edits(
    tmp_path: Path, changed_path: str | None, must_reject: bool
) -> None:
    _write_three_levels(tmp_path)
    leaf = tmp_path / "contracts/two.json"
    payload = json.loads(leaf.read_bytes())
    payload["components"][0]["provenance"] = ["docs/architecture/leaf.md"]
    leaf.write_text(json.dumps(payload))
    (tmp_path / "docs/architecture/leaf.md").write_text("Accepted leaf decision.\n")
    inputs = {
        path: (tmp_path / path).read_bytes()
        for path in (
            "contract.json",
            "contracts/one.json",
            "contracts/two.json",
            "docs/architecture/sample.md",
            "docs/architecture/leaf.md",
        )
    }
    lock_bytes = _lock(_model(git_head="a" * 40))
    expected = _expectation_payload()
    expected.update(accepted_digest=sha256(lock_bytes).hexdigest(), baseline_commit="b" * 40)
    expected_bytes = json.dumps(expected).encode()

    def read_blob(root: Path, commit: str, path: str) -> bytes:
        if path == LOCK_PATH:
            return lock_bytes
        if path == "expectation.json":
            return expected_bytes
        accepted = inputs[path]
        return accepted + b"\n" if commit == "f" * 40 and path == changed_path else accepted

    with (
        patch("archkeel.check.run.remote_tip", return_value="b" * 40),
        patch("archkeel.check.run.read_blob", side_effect=read_blob),
        patch("archkeel.check.run.parents", return_value=["a" * 40]),
        patch("archkeel.check.run.changed_paths", return_value={LOCK_PATH}),
        patch("archkeel.check.run.package_digest", return_value="c" * 64),
        pytest.raises(LockError, match="candidate changed accepted policy input")
        if must_reject
        else nullcontext(),
    ):
        _authenticate_inputs(
            tmp_path,
            config=ScanConfig(("sample",), "sample", "contract.json", "b" * 64),
            baseline="b" * 40,
            expectation_commit="e" * 40,
            head="f" * 40,
            expected_path="expectation.json",
            expected_digest=sha256(expected_bytes).hexdigest(),
            accepted_branch="main",
        )
