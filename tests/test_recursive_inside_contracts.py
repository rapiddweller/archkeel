# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Explicit inside mounts remain scoped and revision-bound at every depth."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest
from test_analyzer import _component, _observe

from archkeel.check.ports import ScanConfig
from archkeel.check.validation import COMPONENT_GRAPH_MARKER, run_validate
from archkeel.check.validation.graphs import TARGET_GRAPH_MARKER
from archkeel.cli.observe import observe
from archkeel.ir.codec import load_inside_contract_tree, observation_payload, parse_contract
from archkeel.ir.model import ContractChangeDirection
from archkeel.ir.trace import trace_valid_violations


def _write(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _inside_component(label: str, package: str, *, inside: str | None = None) -> dict[str, object]:
    component: dict[str, object] = {
        "id": f"COMP-{label.upper()}",
        "label": label,
        "role": "component",
        "packages": [package],
        "responsibilities": [],
        "forbidden_responsibilities": [],
        "provenance": ["docs/architecture/sample.md"],
    }
    if inside is not None:
        component["inside"] = inside
    return component


def _three_level_contract(root: Path, *, deepest_rule: bool) -> None:
    _write(
        root / "contract.json",
        {
            "schema_version": "2.1.0",
            "components": [_component("sample", packages=["sample"]) | {"inside": "one.json"}],
            "rules": [],
        },
    )
    _write(
        root / "one.json",
        {
            "schema_version": "2.1.0",
            "components": [_inside_component("core", "sample.core", inside="two.json")],
            "rules": [],
        },
    )
    _write(
        root / "two.json",
        {
            "schema_version": "2.1.0",
            "components": [
                _inside_component("a", "sample.core.a"),
                _inside_component("b", "sample.core.b"),
            ],
            "rules": (
                [
                    {
                        "id": "NO-PRIVATE-CROSSING",
                        "kind": "forbidden_dependency",
                        "source": "sample.core.a",
                        "target": "sample.core.b",
                        "include_type_checking": True,
                        "rationale": "Keep this deep edge private.",
                        "provenance": ["docs/sample.md"],
                        "decided_by": "architect",
                    }
                ]
                if deepest_rule
                else []
            ),
        },
    )


def test_deep_inside_rule_is_observed_and_ids_include_each_mount(tmp_path: Path) -> None:
    (tmp_path / "docs/architecture").mkdir(parents=True)
    (tmp_path / "docs/architecture/sample.md").write_text(
        f"{COMPONENT_GRAPH_MARKER}\n```mermaid\ngraph TD\n```\n"
        f"{TARGET_GRAPH_MARKER}\n```mermaid\ngraph TD\n```\n"
    )
    (tmp_path / "pyproject.toml").write_text('[project]\nrequires-python = ">=3.11"\n')
    (tmp_path / "sample/core/a.py").parent.mkdir(parents=True)
    (tmp_path / "sample/__init__.py").write_text("")
    (tmp_path / "sample/core/__init__.py").write_text("")
    (tmp_path / "sample/core/a.py").write_text("from sample.core.b import _hidden\n")
    (tmp_path / "sample/core/b.py").write_text("_hidden = 1\n")
    _three_level_contract(tmp_path, deepest_rule=True)

    result = _observe(tmp_path)

    assert result.observation is not None, result.diagnostics
    findings = trace_valid_violations(result.observation)
    assert len(findings) == 1
    assert findings[0].rule_ids == ("sample:core:NO-PRIVATE-CROSSING",)
    assert result.observation.contract.digest


def test_deep_contract_bytes_change_digest_deterministically(tmp_path: Path) -> None:
    (tmp_path / "sample/core").mkdir(parents=True)
    (tmp_path / "sample/__init__.py").write_text("")
    (tmp_path / "sample/core/__init__.py").write_text("")
    (tmp_path / "sample/core/a.py").write_text("VALUE = 1\n")
    _three_level_contract(tmp_path, deepest_rule=False)
    first = _observe(tmp_path).observation
    again = _observe(tmp_path).observation
    assert first is not None and again is not None
    assert first.contract.digest == again.contract.digest
    assert observation_payload(first) == observation_payload(again)

    _three_level_contract(tmp_path, deepest_rule=True)
    changed = _observe(tmp_path).observation
    assert changed is not None
    assert changed.contract.digest != first.contract.digest


def test_amendment_digest_is_canonical_while_observation_digest_keeps_source_bytes(
    tmp_path: Path,
) -> None:
    root = parse_contract(
        {
            "schema_version": "2.1.0",
            "components": [_component("sample", packages=["sample"]) | {"inside": "one.json"}],
            "rules": [],
        }
    )
    payloads = [
        b'{"schema_version":"2.1.0","components":[],"rules":[]}',
        b'{\n  "schema_version": "2.1.0",\n  "components": [],\n  "rules": []\n}\n',
    ]

    def tree(payload: bytes):
        return load_inside_contract_tree(
            "contract.json",
            root,
            "root-source-digest",
            "contract.json",
            lambda path: (payload, path),
        )

    compact, formatted = map(tree, payloads)

    assert compact.digest != formatted.digest
    assert compact.comparison_digest == formatted.comparison_digest


def _git(root: Path, *args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=root, text=True).strip()


def test_against_checks_a_rule_removed_only_in_deepest_contract(tmp_path: Path) -> None:
    (tmp_path / "docs/architecture").mkdir(parents=True)
    (tmp_path / "docs/architecture/sample.md").write_text(
        f"{COMPONENT_GRAPH_MARKER}\n```mermaid\ngraph TD\n```\n"
        f"{TARGET_GRAPH_MARKER}\n```mermaid\ngraph TD\n```\n"
    )
    (tmp_path / "pyproject.toml").write_text('[project]\nrequires-python = ">=3.11"\n')
    (tmp_path / "sample/core").mkdir(parents=True)
    (tmp_path / "sample/__init__.py").write_text("")
    (tmp_path / "sample/core/__init__.py").write_text("")
    (tmp_path / "sample/core/a.py").write_text("from sample.core.b import _hidden\n")
    (tmp_path / "sample/core/b.py").write_text("_hidden = 1\n")
    _three_level_contract(tmp_path, deepest_rule=True)
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "arch@example.invalid")
    _git(tmp_path, "config", "user.name", "Archkeel test")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-q", "-m", "deep contract with rule")
    before = _git(tmp_path, "rev-parse", "HEAD")

    _three_level_contract(tmp_path, deepest_rule=False)
    _git(tmp_path, "add", "two.json")
    _git(tmp_path, "commit", "-q", "-m", "remove deep rule")
    config = ScanConfig(("sample",), "sample", "contract.json", "0" * 64)

    result, _ = run_validate(tmp_path, config, observe, against=before, write_graph=True)

    assert result.exit_code == 1
    assert any("NO-PRIVATE-CROSSING" in failure for failure in result.failures)


@pytest.mark.parametrize(
    ("references", "expected"),
    [
        (["missing.json"], "missing"),
        (["../outside.json"], "unsafe repository path"),
        (["inner.json", "inner.json"], "duplicate mount"),
    ],
)
def test_inside_tree_rejects_missing_unsafe_and_duplicate_mounts(
    tmp_path: Path, references: list[str], expected: str
) -> None:
    root = parse_contract(
        {
            "schema_version": "2.1.0",
            "components": [
                _component(f"c{index}", packages=[f"sample.c{index}"]) | {"inside": path}
                for index, path in enumerate(references)
            ],
            "rules": [],
        }
    )
    child = {"schema_version": "2.1.0", "components": [], "rules": []}
    (tmp_path / "inner.json").write_text(json.dumps(child), encoding="utf-8")

    def read(path: str) -> tuple[bytes, str]:
        target = (tmp_path / path).resolve()
        if not target.is_relative_to(tmp_path.resolve()) or not target.is_file():
            raise ValueError("missing or outside")
        return target.read_bytes(), target.relative_to(tmp_path.resolve()).as_posix()

    tree = load_inside_contract_tree("contract.json", root, "root-digest", "contract.json", read)

    assert any(expected in issue.reason for issue in tree.issues)


def test_inside_tree_rejects_cycles_and_symlink_escapes(tmp_path: Path) -> None:
    outer = parse_contract(
        {
            "schema_version": "2.1.0",
            "components": [_component("outer", packages=["sample"]) | {"inside": "inner.json"}],
            "rules": [],
        }
    )
    cyclic = {"schema_version": "2.1.0", "components": [], "rules": []}
    cyclic["components"] = [_component("loop", packages=["sample"]) | {"inside": "contract.json"}]
    (tmp_path / "inner.json").write_text(json.dumps(cyclic), encoding="utf-8")
    root_payload = {
        "schema_version": "2.1.0",
        "components": [_component("outer", packages=["sample"]) | {"inside": "inner.json"}],
        "rules": [],
    }
    (tmp_path / "contract.json").write_text(json.dumps(root_payload), encoding="utf-8")
    outside = tmp_path.parent / f"{tmp_path.name}-outside.json"
    outside.write_text('{"schema_version":"2.1.0","components":[],"rules":[]}')
    (tmp_path / "escape.json").symlink_to(outside)
    outer_with_escape = parse_contract(
        {
            "schema_version": "2.1.0",
            "components": [_component("escape", packages=["sample"]) | {"inside": "escape.json"}],
            "rules": [],
        }
    )

    def read(path: str) -> tuple[bytes, str]:
        target = (tmp_path / path).resolve()
        if not target.is_relative_to(tmp_path.resolve()) or not target.is_file():
            raise ValueError("outside repository")
        return target.read_bytes(), target.relative_to(tmp_path.resolve()).as_posix()

    cycle_tree = load_inside_contract_tree(
        "contract.json", outer, "root-digest", "contract.json", read
    )
    escape_tree = load_inside_contract_tree(
        "contract.json", outer_with_escape, "root-digest", "contract.json", read
    )

    assert any(issue.reason == "reference cycle" for issue in cycle_tree.issues)
    assert any("outside repository" in issue.reason for issue in escape_tree.issues)


def test_inside_tree_rejects_generated_parent_and_record_id_collisions(tmp_path: Path) -> None:
    root_payload = {
        "schema_version": "2.1.0",
        "components": [
            _component("a:b", packages=["sample.ab"]) | {"inside": "ab.json"},
            _component("a", packages=["sample.a"]) | {"inside": "a.json"},
        ],
        "rules": [],
    }
    (tmp_path / "ab.json").write_text(
        json.dumps({"schema_version": "2.1.0", "components": [], "rules": []})
    )
    (tmp_path / "a.json").write_text(
        json.dumps(
            {
                "schema_version": "2.1.0",
                "components": [_inside_component("b", "sample.a.b", inside="leaf.json")],
                "rules": [],
            }
        )
    )
    (tmp_path / "leaf.json").write_text(
        json.dumps({"schema_version": "2.1.0", "components": [], "rules": []})
    )
    root = parse_contract(root_payload)
    tree = load_inside_contract_tree(
        "contract.json",
        root,
        "root-digest",
        "contract.json",
        lambda path: ((tmp_path / path).read_bytes(), path),
    )

    assert any("generated inside parent ID collision" in issue.reason for issue in tree.issues)

    root_component = _component("app", packages=["sample"]) | {"inside": "child.json"}
    root_component["id"] = "app:COMP-CHILD"
    id_root = parse_contract(
        {"schema_version": "2.1.0", "components": [root_component], "rules": []}
    )
    (tmp_path / "child.json").write_text(
        json.dumps(
            {
                "schema_version": "2.1.0",
                "components": [_inside_component("child", "sample.child")],
                "rules": [],
            }
        )
    )
    id_tree = load_inside_contract_tree(
        "contract.json",
        id_root,
        "root-digest",
        "contract.json",
        lambda path: ((tmp_path / path).read_bytes(), path),
    )

    assert any("generated declaration ID collision" in issue.reason for issue in id_tree.issues)


def _dart_revision_fixture(tmp_path: Path):
    from archkeel.cli.config import load_config

    fixture = Path(__file__).parents[1] / "fixtures/H-uml-dart"
    shutil.copytree(fixture, tmp_path, dirs_exist_ok=True)
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "arch@example.invalid")
    _git(tmp_path, "config", "user.name", "Archkeel test")
    _git(tmp_path, "config", "core.autocrlf", "false")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "-c", "commit.gpgsign=false", "commit", "-qm", "nested UML baseline")
    return load_config(tmp_path), _git(tmp_path, "rev-parse", "HEAD")


def test_against_rejects_a_public_method_renamed_only_in_nested_uml(tmp_path: Path) -> None:
    config, before = _dart_revision_fixture(tmp_path)
    for relative in (
        "lib/ordering/ports/order_repository.dart",
        "lib/adapters/memory/in_memory_order_repository.dart",
        "contracts/ordering.json",
        "contracts/adapters.json",
    ):
        path = tmp_path / relative
        assert "findById" in path.read_text()
        path.write_text(path.read_text().replace("findById", "find"))

    result, _ = run_validate(tmp_path, config, observe, against=before)

    assert result.diagnostics == ()
    assert result.exit_code == 1
    assert {finding.subject for finding in result.widenings} == {
        "inside 'ordering'.contract.declarations",
        "inside 'adapters'.contract.declarations",
    }


def _commit_current_fixture(root: Path) -> str:
    _git(root, "add", ".")
    _git(root, "-c", "commit.gpgsign=false", "commit", "-qm", "declaration baseline")
    return _git(root, "rev-parse", "HEAD")


@pytest.mark.parametrize(
    "change", ["remove_entity", "module_changed", "module_removed", "uml_version", "remove_scope"]
)
def test_against_compares_deep_module_and_uml_declarations(tmp_path: Path, change: str) -> None:
    config, before = _dart_revision_fixture(tmp_path)
    path = tmp_path / "contracts/domain.json"
    raw = json.loads(path.read_text())
    if change.startswith("module_"):
        raw["declarations"]["modules"] = [
            {
                "path": "lib/ordering/domain/pricing/discount_policy.dart",
                "responsibility": "Own deterministic discount policy.",
            }
        ]
        _write(path, raw)
        before = _commit_current_fixture(tmp_path)
    elif change == "uml_version":
        parent = tmp_path / "contracts/ordering.json"
        parent_raw = json.loads(parent.read_text())
        parent_raw["declarations"]["uml"]["schema_version"] = "1.2.0"
        parent_raw["declarations"]["uml"]["entities"].append(
            {
                "id": "duplicate-qualified-reference",
                "kind": "module",
                "qualified_name": "commerce.ordering.domain.orders.order",
                "language": "dart",
                "presence": "referenced",
                "provenance": ["docs/target.md"],
            }
        )
        _write(parent, parent_raw)
        before = _commit_current_fixture(tmp_path)
    if change == "remove_entity":
        uml = raw["declarations"]["uml"]
        uml["entities"] = [row for row in uml["entities"] if row["id"] != "discount-cap"]
    elif change == "module_changed":
        raw["declarations"]["modules"][0]["responsibility"] = "Own bounded percent pricing."
    elif change == "module_removed":
        raw["declarations"]["modules"] = []
    elif change == "uml_version":
        raw["declarations"]["uml"]["schema_version"] = "1.2.0"
    else:
        assert raw["declarations"]["uml"]["scopes"]
        raw["declarations"]["uml"]["scopes"].pop()
    _write(path, raw)

    result, _ = run_validate(tmp_path, config, observe, against=before)

    assert result.diagnostics == ()
    assert result.exit_code == 1
    assert [(row.subject, row.field) for row in result.widenings] == [
        ("inside 'ordering:domain'.contract.declarations", "declarations")
    ]
    # #640 review: the change list carries every change the gate reports.
    assert [(row.direction, row.subject) for row in result.contract_changes or ()] == [
        (ContractChangeDirection.WIDENED, "inside 'ordering:domain'.contract.declarations")
    ]


@pytest.mark.parametrize("format_only", [False, True])
def test_against_preserves_unchanged_and_format_only_nested_declarations(
    tmp_path: Path, format_only: bool
) -> None:
    config, before = _dart_revision_fixture(tmp_path)
    if format_only:
        path = tmp_path / "contracts/domain.json"
        path.write_text(json.dumps(json.loads(path.read_text()), indent=4, sort_keys=True))

    result, _ = run_validate(tmp_path, config, observe, against=before)

    assert result.diagnostics == ()
    assert result.exit_code == 0
    assert result.widenings == ()


def test_against_preserves_scope_identity_when_a_nested_contract_is_remounted(
    tmp_path: Path,
) -> None:
    config, before = _dart_revision_fixture(tmp_path)
    path = tmp_path / "contracts/ordering.json"
    raw = json.loads(path.read_text())
    domain = next(row for row in raw["components"] if row["label"] == "domain")
    domain["inside"] = "contracts/remounted-domain.json"
    (tmp_path / "contracts/domain.json").rename(tmp_path / domain["inside"])
    _write(path, raw)

    result, _ = run_validate(tmp_path, config, observe, against=before)

    assert result.diagnostics == ()
    assert result.exit_code == 1
    assert result.widenings
    assert all(row.field == "inside" for row in result.widenings)


def test_nested_declaration_amendment_binds_both_scopes_and_rejects_stale_intent(
    tmp_path: Path,
) -> None:
    config, before = _dart_revision_fixture(tmp_path)
    for relative in (
        "lib/ordering/ports/order_repository.dart",
        "lib/adapters/memory/in_memory_order_repository.dart",
        "contracts/ordering.json",
        "contracts/adapters.json",
    ):
        path = tmp_path / relative
        path.write_text(path.read_text().replace("findById", "find"))
    amendment = tmp_path / "amendment.json"
    written, files = run_validate(
        tmp_path,
        config,
        observe,
        against=before,
        amendment=amendment,
        write_amendment=True,
        decided_by="agent",
        rationale="Approve the synthetic nested persistence API transition.",
    )
    assert written.exit_code == 0
    assert written.widenings == ()
    amendment.write_bytes(dict(files.entries)[str(amendment)])
    accepted, _ = run_validate(tmp_path, config, observe, against=before, amendment=amendment)
    assert accepted.exit_code == 0
    assert accepted.widenings == ()
    assert accepted.amendment_status == "valid"

    path = tmp_path / "contracts/domain.json"
    raw = json.loads(path.read_text())
    raw["declarations"]["uml"]["entities"][0]["responsibilities"] = [
        "Own the newly revised order boundary."
    ]
    _write(path, raw)
    stale, _ = run_validate(tmp_path, config, observe, against=before, amendment=amendment)
    assert stale.exit_code == 1
    assert stale.amendment_status == "stale"


@pytest.mark.parametrize("physical_target", [False, True])
def test_recognized_rename_normalizes_nested_names_but_not_unmapped_file_paths(
    tmp_path: Path, physical_target: bool
) -> None:
    from archkeel.ir.codec import contract_bytes
    from archkeel.ir.renames import renamed_contract

    config, before = _dart_revision_fixture(tmp_path)
    path = tmp_path / "contracts/presentation.json"
    if not physical_target:
        raw = json.loads(path.read_text())
        for row in raw["declarations"]["uml"]["entities"]:
            row.pop("file_path", None)
        _write(path, raw)
        before = _commit_current_fixture(tmp_path)
    prefixes = {"commerce.presentation": "commerce.web"}
    for relative in ("architecture-contract.json", "contracts/presentation.json"):
        target = tmp_path / relative
        contract = renamed_contract(parse_contract(json.loads(target.read_text())), prefixes)
        target.write_bytes(contract_bytes(contract))
    (tmp_path / "lib/presentation").rename(tmp_path / "lib/web")
    main = tmp_path / "lib/main.dart"
    main.write_text(main.read_text().replace("presentation/controller.dart", "web/controller.dart"))
    if physical_target:
        raw = json.loads(path.read_text())
        for row in raw["declarations"]["uml"]["entities"]:
            if row.get("file_path") == "lib/presentation/controller.dart":
                row["file_path"] = "lib/web/controller.dart"
        _write(path, raw)

    result, _ = run_validate(tmp_path, config, observe, against=before, against_config=config)

    assert result.diagnostics == ()
    assert result.renames == (("commerce.presentation", "commerce.web"),)
    assert result.exit_code == (1 if physical_target else 0)
    assert [(row.subject, row.field) for row in result.widenings] == (
        [("inside 'presentation'.contract.declarations", "declarations")] if physical_target else []
    )


def test_against_rejects_a_rename_that_collides_in_historical_nested_uml(
    tmp_path: Path,
) -> None:
    from archkeel.ir.codec import contract_bytes
    from archkeel.ir.renames import renamed_contract

    config, _ = _dart_revision_fixture(tmp_path)
    path = tmp_path / "contracts/presentation.json"
    raw = json.loads(path.read_text())
    raw["declarations"]["uml"] = {
        "schema_version": "1.1.0",
        "entities": [
            {
                "id": label,
                "kind": "module",
                "qualified_name": f"commerce.{package}.controller",
                "parent_id": "controller",
                "language": "dart",
                "presence": "planned",
                "responsibilities": ["Own the checkout transport module."],
                "provenance": ["docs/target.md"],
            }
            for label, package in (("old-target", "presentation"), ("future-target", "web"))
        ],
        "relationships": [],
        "scopes": [],
    }
    parse_contract(raw)
    _write(path, raw)
    before = _commit_current_fixture(tmp_path)

    raw["declarations"]["uml"]["entities"].pop(0)
    _write(path, raw)
    for relative in ("architecture-contract.json", "contracts/presentation.json"):
        target = tmp_path / relative
        target.write_bytes(
            contract_bytes(
                renamed_contract(
                    parse_contract(json.loads(target.read_text())),
                    {"commerce.presentation": "commerce.web"},
                )
            )
        )
    (tmp_path / "lib/presentation").rename(tmp_path / "lib/web")
    main = tmp_path / "lib/main.dart"
    main.write_text(main.read_text().replace("presentation/controller.dart", "web/controller.dart"))

    result, _ = run_validate(tmp_path, config, observe, against=before, against_config=config)

    assert result.diagnostics == ()
    assert result.exit_code == 1
    assert result.renames == ()
    assert any(
        row.subject == "inside 'presentation'.contract.declarations" for row in result.widenings
    )
    assert any(row.field == "packages" for row in result.widenings)

    amendment = tmp_path / "amendment.json"
    written, files = run_validate(
        tmp_path,
        config,
        observe,
        against=before,
        against_config=config,
        amendment=amendment,
        write_amendment=True,
        decided_by="agent",
        rationale="Accept the explicit transition between distinct planned module targets.",
    )
    assert written.exit_code == 0
    amendment.write_bytes(dict(files.entries)[str(amendment)])
    accepted, _ = run_validate(
        tmp_path,
        config,
        observe,
        against=before,
        against_config=config,
        amendment=amendment,
    )
    assert accepted.exit_code == 0
    assert accepted.amendment_status == "valid"
    assert accepted.renames == ()
