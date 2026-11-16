# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-612: one core run checks each part of a system document.

Each part is the scan of one configuration. The status of the system comes from the status rule of
the core: a part that FAILs fails the system. A rule id that two parts use, a rule between parts,
and a page or a baseline for a system run refuse the run: UNKNOWN, never a PASS.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import pytest
from core_support import run
from corpus_support import commit_tree
from rust_repository import CRATE_RULES, component, repository, rule

from archkeel.cli import core_only

pytestmark = pytest.mark.skipif(shutil.which("cargo") is None, reason="rustc is the oracle")

PASSING = tuple({**r, "id": f"P-{r['id']}"} for r in CRATE_RULES)
# `app` imports `base`, so this rule of the second part fails.
FAILING = (
    rule(
        "F-NO-APP-TO-BASE",
        "forbidden_dependency",
        source="native.app",
        target="native.base_crate",
        include_type_checking=True,
    ),
)
SCAN = '[scan]\nlanguage = "rust"\nroots = ["crates"]\nnamespace = "native"\ncontract = "{}"\n'


def _system(
    root: Path, core: Path, parts: dict[str, tuple[dict[str, Any], ...]], rules: list[Any]
) -> Path:
    """A Rust fixture with one configuration and contract for each part, and the system document."""
    repository(root, core)
    components = [component("base", "base_crate"), component("app", "app", ("base",))]
    listed = []
    for name, part_rules in parts.items():
        contract = {"schema_version": "2.1.0", "components": components, "rules": part_rules}
        (root / f"{name}-contract.json").write_text(json.dumps(contract, indent=2))
        (root / f"{name}.toml").write_text(SCAN.format(f"{name}-contract.json"))
        listed.append({"id": name, "title": f"Part {name}", "config": f"{name}.toml"})
    document = {
        "schema_version": "archkeel-system-contract-1",
        "kind": "system",
        "title": "Fixture",
        "parts": listed,
        "rules": rules,
    }
    (root / "system.json").write_text(json.dumps(document, indent=2))
    commit_tree(root)
    return root


def _validate(root: Path, core: Path, *more: str) -> tuple[int, dict[str, Any]]:
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(core_only, "locate_core", lambda: core)
        return run("validate", "--root", str(root), "--config", "system.json", *more)


@pytest.mark.parametrize(
    ("parts", "status", "code"),
    [
        ({"one": PASSING}, "PASS", 0),
        ({"one": PASSING, "two": FAILING}, "FAIL", 1),
        ({"two": FAILING, "one": PASSING}, "FAIL", 1),
    ],
)
def test_the_system_status_is_the_status_rule_over_its_parts(
    tmp_path: Path,
    core_binary: Path,
    parts: dict[str, tuple[dict[str, Any], ...]],
    status: str,
    code: int,
) -> None:
    root = _system(tmp_path, core_binary, parts, [])
    exit_code, result = _validate(root, core_binary)

    assert (exit_code, result["status"]) == (code, status), result.get("refusal")
    frame = result["frame"]
    rows = {part["id"]: part for part in frame["system"]["parts"]}
    assert list(rows) == list(parts)
    for name, part_rules in parts.items():
        assert rows[name]["profile"] == "rust"
        assert rows[name]["config"] == f"{name}.toml"
        assert rows[name]["rules"] == sorted(r["id"] for r in part_rules)
    assert set(frame["rules"]) == {r["id"] for rules in parts.values() for r in rules}
    if "two" in parts:
        assert rows["two"]["status"] == "FAIL"
        assert rows["one"]["status"] == "PASS"


@pytest.mark.parametrize(
    ("parts", "rules", "more", "cause"),
    [
        ({"one": PASSING, "two": PASSING}, [], (), "two parts name the rule"),
        ({"one": PASSING}, [{"id": "X"}], (), "a rule between parts"),
        ({"one": PASSING}, [], ("--baseline", "baseline.json"), "no page, topology or baseline"),
    ],
)
def test_a_system_run_that_the_core_cannot_decide_is_refused(
    tmp_path: Path,
    core_binary: Path,
    parts: dict[str, tuple[dict[str, Any], ...]],
    rules: list[Any],
    more: tuple[str, ...],
    cause: str,
) -> None:
    root = _system(tmp_path, core_binary, parts, rules)
    exit_code, result = _validate(root, core_binary, *more)

    # A refused scan exits 1 with a baseline (AD-546) and 2 without one; it is never a PASS.
    assert exit_code != 0, result
    assert result["status"] == "UNKNOWN"
    assert cause in json.dumps(result), result


def test_a_part_that_the_core_cannot_run_leaves_the_system_unknown(
    tmp_path: Path, core_binary: Path
) -> None:
    root = _system(tmp_path, core_binary, {"one": PASSING}, [])
    document = json.loads((root / "system.json").read_text())
    document["parts"].append({"id": "lost", "title": "Lost part", "config": "lost.toml"})
    (root / "system.json").write_text(json.dumps(document))
    commit_tree(root)
    exit_code, result = _validate(root, core_binary)

    assert (exit_code, result["status"]) == (2, "UNKNOWN"), result.get("refusal")
    rows = {part["id"]: part["status"] for part in result["frame"]["system"]["parts"]}
    assert rows == {"one": "PASS", "lost": "UNKNOWN"}
