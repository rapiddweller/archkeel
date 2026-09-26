# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""A requires target is local to the contract that declares it."""

import json
import subprocess
from hashlib import sha256
from pathlib import Path
from unittest.mock import patch

import pytest
from test_delta import _model
from test_expectation import _expectation_payload
from test_git_lock import _lock

from archkeel.analyzer import observe
from archkeel.check.ports import ScanConfig
from archkeel.check.report import run_report
from archkeel.check.run import _authenticate_inputs, materialize_declarations
from archkeel.check.validation import run_validate
from archkeel.ir.codec import ContractInputError, declaration_paths, parse_contract
from archkeel.ir.lock import LOCK_PATH, LockError


def _component(
    label: str,
    *,
    packages: list[str],
    requires: list[str] | None = None,
    inside: str | None = None,
) -> dict[str, object]:
    component: dict[str, object] = {
        "id": f"COMP-{label.upper()}",
        "label": label,
        "role": "component",
        "packages": packages,
        "responsibilities": [],
        "forbidden_responsibilities": [],
        "provenance": ["docs/architecture/sample.md"],
        "requires": [
            {"component": target, "rationale": "The caller needs this component."}
            for target in requires or []
        ],
    }
    if inside is not None:
        component["inside"] = inside
    return component


def _write_contract(path: Path, components: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"schema_version": "2.1.0", "components": components, "rules": []}),
        encoding="utf-8",
    )


def _setup(root: Path) -> ScanConfig:
    (root / "pyproject.toml").write_text('[project]\nrequires-python = ">=3.11"\n')
    (root / "sample").mkdir()
    (root / "sample/__init__.py").write_text("")
    (root / "sample/core.py").write_text("VALUE = 1\n")
    (root / "docs/architecture").mkdir(parents=True)
    (root / "docs/architecture/sample.md").write_text("Architecture notes.\n")
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    subprocess.run(["git", "-C", str(root), "config", "user.name", "Test"], check=True)
    subprocess.run(["git", "-C", str(root), "config", "user.email", "test@example.com"], check=True)
    subprocess.run(["git", "-C", str(root), "add", "."], check=True)
    subprocess.run(["git", "-C", str(root), "commit", "-qm", "fixture"], check=True)
    return ScanConfig(("sample",), "sample", "contract.json", "0" * 64)


def test_requires_target_must_name_a_component_in_the_same_contract() -> None:
    valid = {
        "schema_version": "2.1.0",
        "components": [
            _component("api", packages=["sample.api"], requires=["core"]),
            _component("core", packages=["sample.core"]),
        ],
        "rules": [],
    }
    assert parse_contract(valid).components[0].requires[0].component == "core"

    invalid = json.loads(json.dumps(valid))
    invalid["components"][0]["requires"][0]["component"] = "missing"
    with pytest.raises(ContractInputError) as caught:
        parse_contract(invalid)
    assert caught.value.pointer == "/components/0/requires/0/component"
    assert caught.value.subject == "missing"


def test_component_labels_must_be_unique_within_one_contract() -> None:
    raw = {
        "schema_version": "2.1.0",
        "components": [
            _component("shared", packages=["sample.a"]),
            _component("shared", packages=["sample.b"]),
        ],
        "rules": [],
    }
    with pytest.raises(ContractInputError) as caught:
        parse_contract(raw)
    assert caught.value.pointer == "/components/1/label"
    assert caught.value.subject == "shared"


def test_validate_and_report_reject_root_reference_before_writes(tmp_path: Path) -> None:
    config = _setup(tmp_path)
    _write_contract(
        tmp_path / "contract.json",
        [
            _component("api", packages=["sample"], requires=["missing"]),
            _component("core", packages=["sample.core"]),
        ],
    )
    baseline = tmp_path / "architecture-baseline.json"

    result, files = run_validate(
        tmp_path,
        config,
        observe,
        baseline=baseline,
        write_baseline=True,
        write_graph=True,
    )
    assert result.exit_code == 2
    assert len(result.diagnostics) == 1
    assert result.diagnostics[0].code == "contract.invalid"
    assert result.diagnostics[0].pointer == "/components/0/requires/0/component"
    assert result.diagnostics[0].subject == "missing"
    assert not files
    assert not baseline.exists()

    report, architecture = run_report(tmp_path, config=config, analyzer=observe)
    assert report.exit_code == 2
    assert report.diagnostics[0].pointer == "/components/0/requires/0/component"
    assert report.diagnostics[0].subject == "missing"
    assert architecture is None


def test_nested_and_deep_references_are_validated_in_their_own_contracts(
    tmp_path: Path,
) -> None:
    config = _setup(tmp_path)
    _write_contract(
        tmp_path / "contract.json",
        [_component("outer", packages=["sample"], inside="contracts/one.json")],
    )
    _write_contract(
        tmp_path / "contracts/one.json",
        [_component("middle", packages=["sample"], inside="contracts/two.json")],
    )
    _write_contract(
        tmp_path / "contracts/two.json",
        [
            _component("leaf", packages=["sample"], requires=["middle"]),
            _component("other", packages=["sample.core"]),
        ],
    )

    observed = observe(
        tmp_path,
        roots=config.roots,
        namespace=config.namespace,
        contract=config.contract,
        git_head="a" * 40,
        dirty=False,
        contract_root=tmp_path,
    )
    assert observed.observation is None
    assert observed.exit_code == 2
    assert observed.diagnostics[0].pointer == (
        "/components/0/inside/components/0/inside/components/0/requires/0/component"
    )
    assert observed.diagnostics[0].subject == "middle"

    report, architecture = run_report(tmp_path, config=config, analyzer=observe)
    assert report.exit_code == 2
    assert report.diagnostics[0].pointer == observed.diagnostics[0].pointer
    assert report.diagnostics[0].subject == "middle"
    assert architecture is None

    with pytest.raises(ContractInputError) as caught:
        declaration_paths(
            (tmp_path / "contract.json").read_bytes(),
            "contract.json",
            read_contract=lambda path: ((tmp_path / path).read_bytes(), path),
        )
    assert caught.value.pointer == observed.diagnostics[0].pointer
    assert caught.value.subject == "middle"


def test_nested_reference_may_not_borrow_a_parent_label(tmp_path: Path) -> None:
    config = _setup(tmp_path)
    _write_contract(
        tmp_path / "contract.json",
        [
            _component(
                "outer",
                packages=["sample"],
                requires=["root-target"],
                inside="inside.json",
            ),
            _component("root-target", packages=["sample.core"]),
        ],
    )
    _write_contract(
        tmp_path / "inside.json",
        [_component("child", packages=["sample"], requires=["root-target"])],
    )

    result, files = run_validate(tmp_path, config, observe, write_graph=True)
    assert result.exit_code == 2
    assert result.diagnostics[0].pointer == (
        "/components/0/inside/components/0/requires/0/component"
    )
    assert result.diagnostics[0].subject == "root-target"
    assert not files


def test_revision_materialization_and_check_auth_keep_nested_pointer(tmp_path: Path) -> None:
    _setup(tmp_path)
    _write_contract(
        tmp_path / "contract.json",
        [_component("outer", packages=["sample"], inside="inside.json")],
    )
    _write_contract(
        tmp_path / "inside.json",
        [_component("child", packages=["sample"], requires=["missing"])],
    )
    subprocess.run(["git", "-C", str(tmp_path), "add", "."], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "commit", "-qm", "invalid reference"], check=True)
    revision = subprocess.check_output(
        ["git", "-C", str(tmp_path), "rev-parse", "HEAD"], text=True
    ).strip()
    expected_pointer = "/components/0/inside/components/0/requires/0/component"

    with pytest.raises(ContractInputError) as caught:
        materialize_declarations(
            tmp_path,
            revision,
            ScanConfig(("sample",), "sample", "contract.json", "0" * 64),
            tmp_path / "snapshot",
        )
    assert caught.value.pointer == expected_pointer
    assert not (tmp_path / "snapshot/contract.json").exists()

    lock_bytes = _lock(_model(git_head="a" * 40))
    expected = _expectation_payload()
    expected.update(accepted_digest=sha256(lock_bytes).hexdigest(), baseline_commit="b" * 40)
    expected_bytes = json.dumps(expected).encode()

    def read_blob(_root: Path, _commit: str, path: str) -> bytes:
        if path == LOCK_PATH:
            return lock_bytes
        if path == "expectation.json":
            return expected_bytes
        return (tmp_path / path).read_bytes()

    with (
        patch("archkeel.check.run.remote_tip", return_value="b" * 40),
        patch("archkeel.check.run.read_blob", side_effect=read_blob),
        patch("archkeel.check.run.parents", return_value=["a" * 40]),
        patch("archkeel.check.run.changed_paths", return_value={LOCK_PATH}),
        patch("archkeel.check.run.package_digest", return_value="c" * 64),
        pytest.raises(LockError) as auth_error,
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
    assert auth_error.value.diagnostic.pointer == expected_pointer
    assert auth_error.value.diagnostic.subject == "missing"
