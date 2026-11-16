# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-616: one core run checks each part of a system document.

Each part is the scan of one configuration. The status of the system comes from the status rule of
the core: a part that FAILs fails the system. A rule id that two parts use, a rule between parts,
and a baseline for a system run refuse the run: UNKNOWN, never a PASS.
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
    root: Path,
    core: Path,
    parts: dict[str, tuple[dict[str, Any], ...]],
    rules: list[Any],
    interfaces: list[Any] | None = None,
) -> Path:
    """A Rust fixture with one configuration and contract for each part, and the system document."""
    repository(root, core)
    components = [component("base", "base_crate"), component("app", "app", ("base",))]
    listed = []
    for name, part_rules in parts.items():
        contract = {"schema_version": "2.1.0", "components": components, "rules": part_rules}
        (root / f"{name}-contract.json").write_text(json.dumps(contract, indent=2))
        (root / f"{name}.toml").write_text(SCAN.format(f"{name}-contract.json"))
        listed.append(
            {
                "id": name,
                "title": f"Part {name}",
                "config": f"{name}.toml",
                "responsibilities": [f"Part {name} checks its crate."],
                "forbidden_responsibilities": ["Checking another part."],
                "provides": [f"The result of {name}."],
            }
        )
    document = {
        "schema_version": "archkeel-system-contract-1",
        "kind": "system",
        "title": "Fixture",
        "parts": listed,
        "interfaces": interfaces or [],
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
        ({"one": PASSING}, [], ("--baseline", "baseline.json"), "no baseline"),
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


def _report(root: Path, core: Path, name: str) -> tuple[int, str | None]:
    target = root / name
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(core_only, "locate_core", lambda: core)
        code, _ = run(
            "report", "--root", str(root), "--config", "system.json", "--output", str(target)
        )
    return code, target.read_text() if target.exists() else None


def test_the_report_of_a_system_is_one_page_with_the_part_as_a_top_component(
    tmp_path: Path, core_binary: Path
) -> None:
    root = _system(tmp_path, core_binary, {"one": PASSING}, [])
    code, page = _report(root, core_binary, "page.html")

    assert page is not None
    data = json.loads(
        page.split('id="flow-data" type="application/json">')[1].split("</script>")[0]
    )
    tops = [c for c in data["atlas"]["components"] if c["parent_id"] is None]
    assert code == 0
    assert [(c["id"], c["label"], c["language"]) for c in tops] == [
        ("PART:one", "Part one", "rust")
    ]
    assert "<h1>Verdict: PASS</h1>" in page


def test_the_report_of_two_parts_that_name_one_component_is_refused(
    tmp_path: Path, core_binary: Path
) -> None:
    root = _system(tmp_path, core_binary, {"one": PASSING, "two": ()}, [])
    code, page = _report(root, core_binary, "page.html")

    # The fixture gives both parts the same components, so no id names one thing: no page is
    # written, and the exit is not a PASS.
    assert code != 0
    assert page is None


def test_an_interface_names_two_parts_and_a_schema_file_that_exists(
    tmp_path: Path, core_binary: Path
) -> None:
    (tmp_path / "wire.schema.json").write_text("{}")
    good = {
        "id": "wire",
        "source": "one",
        "target": "two",
        "title": "A wire",
        "schema": "wire.schema.json",
    }
    for name, change, cause in (
        ("lost", {"schema": "none.schema.json"}, "is no file"),
        ("self", {"target": "one"}, "joins a part to itself"),
        ("far", {"target": "ghost"}, "names no part ghost"),
    ):
        root = _system(
            tmp_path / name, core_binary, {"one": PASSING, "two": ()}, [], [{**good, **change}]
        )
        (root / "wire.schema.json").write_text("{}")
        commit_tree(root)
        code, result = _validate(root, core_binary)
        assert code != 0 and result["status"] == "UNKNOWN", result
        assert cause in json.dumps(result), result


def test_a_part_that_the_core_cannot_run_leaves_the_system_unknown(
    tmp_path: Path, core_binary: Path
) -> None:
    root = _system(tmp_path, core_binary, {"one": PASSING}, [])
    document = json.loads((root / "system.json").read_text())
    lost = {
        "id": "lost",
        "title": "Lost part",
        "config": "lost.toml",
        "responsibilities": ["Nothing runs."],
        "forbidden_responsibilities": ["Anything."],
        "provides": ["Nothing."],
    }
    document["parts"].append(lost)
    (root / "system.json").write_text(json.dumps(document))
    commit_tree(root)
    exit_code, result = _validate(root, core_binary)

    assert (exit_code, result["status"]) == (2, "UNKNOWN"), result.get("refusal")
    rows = {part["id"]: part["status"] for part in result["frame"]["system"]["parts"]}
    assert rows == {"one": "PASS", "lost": "UNKNOWN"}
