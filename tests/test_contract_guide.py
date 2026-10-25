# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Verify the contract guide renderer and the `archkeel guide` command."""

import json
import re
from pathlib import Path
from typing import Any

import pytest

from archkeel.cli import main
from archkeel.ir.architecture_graph import ArchitectureRuleKind
from archkeel.render.guide import RULE_KIND_EXPLANATIONS, render_guide

ROOT = Path(__file__).parents[1]
NO_DYNAMIC = "CONSTRUCT-NO-DYNAMIC"
DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
COMMIT = re.compile(r"\b[0-9a-f]{40}\b")
REQUIRES_NOT_DECLARED = (
    "No `requires` entries, no `allowed_dependency` or `forbidden_dependency` rule and no "
    "`complete_requires` rule: dependency permissions are not declared. A missing entry "
    "does not mean a dependency is allowed or forbidden."
)


def _component(label: str, packages: list[str], **extra: Any) -> dict[str, Any]:
    return {
        "id": f"COMP-{label.upper()}",
        "label": label,
        "role": "component",
        "packages": packages,
        "responsibilities": [f"Own the {label} package."],
        "forbidden_responsibilities": [],
        "provenance": ["docs/architecture/sample.md"],
        **extra,
    }


def _rule(rule_id: str, kind: str, **extra: Any) -> dict[str, Any]:
    return {
        "id": rule_id,
        "kind": kind,
        "rationale": f"Rule {rule_id} keeps the sample honest.",
        "provenance": ["docs/architecture/sample.md"],
        "decided_by": "architect",
        **extra,
    }


def _contract(components: list[dict[str, Any]], rules: list[dict[str, Any]]) -> dict[str, Any]:
    return {"schema_version": "2.1.0", "components": components, "rules": rules}


def _payload(raw: dict[str, Any]) -> bytes:
    return json.dumps(raw).encode("utf-8")


def _render(raw: dict[str, Any]) -> str:
    return render_guide(_payload(raw), repository="sample", contract_path="contract.json")


def _without_requires() -> dict[str, Any]:
    return _contract(
        [_component("core", ["sample.core"]), _component("cli", ["sample.cli"])],
        [
            _rule("ASSIGNMENT", "complete_assignment", source="sample"),
            _rule("NO-CYCLES", "no_component_cycles"),
            _rule(NO_DYNAMIC, "forbidden_construct", source="sample", constructs=["getattr"]),
        ],
    )


def _with_requires() -> dict[str, Any]:
    return _contract(
        [
            _component(
                "core",
                ["sample.core"],
                public=["sample.core"],
                decided_by="architect",
            ),
            _component(
                "cli",
                ["sample.cli"],
                decided_by="architect",
                requires=[
                    {
                        "component": "core",
                        "rationale": "The composition root builds the core model.",
                        "decided_by": "agent",
                    },
                    {"component": "core", "rationale": "Second edge, same owner."},
                ],
            ),
        ],
        [_rule("REQUIRES-COMPLETE", "complete_requires")],
    )


def _shuffled_keys(value: Any) -> Any:
    """Reverse object key order at every depth; lists keep their order."""
    if isinstance(value, dict):
        return {key: _shuffled_keys(value[key]) for key in reversed(list(value))}
    if isinstance(value, list):
        return [_shuffled_keys(item) for item in value]
    return value


def test_contract_without_requires_says_permissions_are_not_declared() -> None:
    text = _render(_without_requires())

    assert REQUIRES_NOT_DECLARED in text
    assert "mermaid" not in text.lower()


def test_contract_with_requires_says_the_set_is_closed_and_counts_deciders() -> None:
    text = _render(_with_requires())

    assert "The permission set is closed" in text
    # Entry one is the agent's; entry two inherits cli's architect; core's public list and
    # the complete_requires rule are architect decisions too.
    assert "Decided by: 1 agent, 3 architect, 0 not recorded" in text


def test_an_allowed_dependency_rule_is_a_declared_permission() -> None:
    raw = _without_requires()
    raw["rules"].append(_rule("ALLOW", "allowed_dependency", source="core", target="cli"))
    text = _render(raw)

    assert "dependency permissions are not declared" not in text
    assert "Dependency permissions are not declared. Decide them" not in text
    assert "allowed_dependency rules: 1" in text
    assert "The permission set is open" in text


def test_render_is_byte_identical_across_runs_and_key_order() -> None:
    raw = _with_requires()
    first = _render(raw)

    assert _render(raw) == first
    assert _render(_shuffled_keys(raw)) == first


def test_forbidden_construct_rules_are_wrapped_after_ten_rows() -> None:
    raw = json.loads((ROOT / "architecture-contract.json").read_bytes())
    constructs = [rule["id"] for rule in raw["rules"] if rule["kind"] == "forbidden_construct"]
    text = render_guide(
        _payload(raw), repository="archkeel", contract_path="architecture-contract.json"
    )

    heading = f"### Forbidden construct (forbidden_construct, {len(constructs)} rules)"
    section = text[text.index(heading) + len(heading) :]
    section = section.split("\n### ", 1)[0]
    visible, _, hidden = section.partition("<details>")
    assert constructs[9] in visible
    assert constructs[10] not in visible
    assert constructs[10] in hidden
    assert "</details>" in hidden


def test_every_rule_kind_has_an_explanation() -> None:
    for kind in ArchitectureRuleKind:
        assert RULE_KIND_EXPLANATIONS[kind].strip(), kind


def test_own_contract_guide_has_no_dates_or_commit_hashes() -> None:
    raw = json.loads((ROOT / "architecture-contract.json").read_bytes())
    text = render_guide(_payload(raw), repository="archkeel", contract_path="x.json")

    assert DATE.search(text) is None
    assert COMMIT.search(text) is None


def _repository(tmp_path: Path, contract: dict[str, Any]) -> Path:
    (tmp_path / "archkeel.toml").write_text(
        '[scan]\nroots = ["src/sample"]\nnamespace = "sample"\n'
        'contract = "architecture-contract.json"\n',
        encoding="utf-8",
    )
    (tmp_path / "architecture-contract.json").write_text(json.dumps(contract), encoding="utf-8")
    return tmp_path


def test_guide_writes_the_default_file_and_check_follows_the_contract(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _repository(tmp_path, _without_requires())
    guide = root / "docs/architecture/contract-guide.md"

    assert main(["guide", "--root", str(root)]) == 0
    assert guide.read_text(encoding="utf-8") == _render_for_root(root)
    assert main(["guide", "--root", str(root), "--check"]) == 0

    (root / "architecture-contract.json").write_text(json.dumps(_with_requires()), encoding="utf-8")
    capsys.readouterr()
    assert main(["guide", "--root", str(root), "--check"]) == 1
    assert "contract-guide.md" in capsys.readouterr().out

    assert main(["guide", "--root", str(root)]) == 0
    assert main(["guide", "--root", str(root), "--check"]) == 0

    guide.unlink()
    assert main(["guide", "--root", str(root), "--check"]) == 1


def test_guide_never_changes_the_contract_or_other_files(tmp_path: Path) -> None:
    root = _repository(tmp_path, _without_requires())
    before = {path: path.read_bytes() for path in root.rglob("*") if path.is_file()}

    assert main(["guide", "--root", str(root)]) == 0

    after = {path: path.read_bytes() for path in root.rglob("*") if path.is_file()}
    created = set(after) - set(before)
    assert created == {root / "docs/architecture/contract-guide.md"}
    assert all(after[path] == before[path] for path in before)


def test_guide_refuses_to_overwrite_the_contract_or_the_configuration(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _repository(tmp_path, _without_requires())
    (root / "alias.json").symlink_to(root / "architecture-contract.json")
    before = {path: path.read_bytes() for path in root.rglob("*") if path.is_file()}

    for output in ("architecture-contract.json", "archkeel.toml", "alias.json"):
        assert main(["guide", "--root", str(root), "--output", output]) == 2
        assert "Refusing to overwrite" in capsys.readouterr().err

    assert {path: path.read_bytes() for path in root.rglob("*") if path.is_file()} == before


def test_guide_without_a_contract_exits_two_with_the_init_hint(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _repository(tmp_path, _without_requires())
    (root / "architecture-contract.json").unlink()

    assert main(["guide", "--root", str(root)]) == 2
    assert "Run archkeel init first." in capsys.readouterr().err


def test_guide_without_archkeel_toml_exits_two_with_the_init_hint(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["guide", "--root", str(tmp_path)]) == 2
    assert "Run archkeel init first." in capsys.readouterr().err


def _render_for_root(root: Path) -> str:
    return render_guide(
        (root / "architecture-contract.json").read_bytes(),
        repository="sample",
        contract_path="architecture-contract.json",
    )
