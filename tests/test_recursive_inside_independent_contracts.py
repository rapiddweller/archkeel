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
from archkeel.check.validation import COMPONENT_GRAPH_MARKER, inside_diagnostics, run_validate
from archkeel.ir.codec import canonical_report_bytes, declaration_paths, parse_contract
from archkeel.ir.lock import LOCK_PATH, LockError

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
        item.code == "contract.invalid" and reason in item.unknown_claim
        for item in diagnostics
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
