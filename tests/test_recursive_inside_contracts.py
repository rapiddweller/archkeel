# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Explicit inside mounts remain scoped and revision-bound at every depth."""

import json
import subprocess
from pathlib import Path

import pytest
from test_analyzer import _component, _observe

from archkeel.analyzer import observe
from archkeel.check.ports import ScanConfig
from archkeel.check.validation import (
    COMPONENT_GRAPH_MARKER,
    TARGET_GRAPH_MARKER,
    run_validate,
)
from archkeel.ir.codec import load_inside_contract_tree, observation_payload, parse_contract
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
        "provenance": ["docs/sample.md"],
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
