# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""#1919 D8: every command of `docs/migration-4-to-5.md` runs, and each fact of its budget and
baseline sections holds on a fixture.

The guide block `migration-check` lists the commands and the exit code of each. A line that
changes in the product, or a command that the guide names wrongly, fails here.
"""

import json
import re
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

from archkeel.cli.init_draft import draft, write_missing

GUIDE = Path(__file__).resolve().parents[1] / "docs" / "migration-4-to-5.md"
LINE = re.compile(r"^(?P<command>.+?)\s+#\s*exit\s+(?P<code>\d+)\s*$")


def _commands() -> list[tuple[list[str], int]]:
    text = GUIDE.read_text(encoding="utf-8")
    block = re.search(r"```migration-check\n(.*?)```", text, re.DOTALL)
    assert block, "the guide has no migration-check block"
    found = []
    for line in block.group(1).splitlines():
        match = LINE.match(line.strip())
        assert match, f"a guide line has no `# exit N` comment: {line!r}"
        words = match.group("command").split()
        assert words[0] == "archkeel", f"a guide line must start with archkeel: {line!r}"
        found.append((words[1:], int(match.group("code"))))
    return found


def _archkeel() -> Path:
    # The console script of the environment that runs the tests.
    return Path(sys.executable).with_name("archkeel")


def _git(root: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(root), "-c", "user.name=t", "-c", "user.email=t@t", *args],
        check=True,
        capture_output=True,
    )


def _project(parent: Path) -> Path:
    """A one-package Python project with a drafted contract, committed (the core needs a commit)."""
    root = parent / "demo"
    (root / "demo").mkdir(parents=True)
    (root / "demo" / "__init__.py").write_text("", encoding="utf-8")
    (root / "demo" / "a.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    write_missing(root, draft(root))
    _git(root, "init", "-q")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "init")
    return root


def _run(root: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(_archkeel()), *arguments],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
        timeout=600,
    )


@pytest.fixture(scope="module")
def guide_run(tmp_path_factory: pytest.TempPathFactory, release_core: Path) -> Iterator[Path]:
    """The commands of the guide, run in order in one fixture folder."""
    root = _project(tmp_path_factory.mktemp("guide"))
    for arguments, expected in _commands():
        done = _run(root, *arguments)
        assert done.returncode == expected, (arguments, done.returncode, done.stdout[-600:])
        assert "Traceback" not in done.stderr, done.stderr
    yield root


def test_the_write_and_compare_keep_the_unknowns_list(guide_run: Path) -> None:
    document = json.loads((guide_run / "known-violations.json").read_text(encoding="utf-8"))
    assert document["schema_version"] == "1.4.0"
    assert isinstance(document["unknowns"], list) and document["unknowns"]
    assert set(document["budgets"]) >= {"calls_unresolved", "typing_positions"}
    done = _run(guide_run, "validate", "--baseline", "known-violations.json", "--json")
    assert json.loads(done.stdout)["baseline"]["state"] == "current"


def test_the_html_and_json_reports_are_written(guide_run: Path) -> None:
    assert (
        (guide_run / "architecture.html").read_text(encoding="utf-8").startswith("<!doctype html")
    )
    assert json.loads((guide_run / "architecture.json").read_text(encoding="utf-8"))[
        "protocol"
    ] == ("archkeel-core-frame-1")


def test_the_refused_input_names_the_command_of_the_guide(guide_run: Path) -> None:
    done = _run(guide_run, "report", "--input", "architecture.json", "--json")
    message = json.loads(done.stdout)["refusal"]["message"]
    assert "use archkeel report --json" in message


def test_a_schema_1_3_file_gives_the_older_schema_gap(guide_run: Path) -> None:
    document = json.loads((guide_run / "known-violations.json").read_text(encoding="utf-8"))
    document["schema_version"] = "1.3.0"
    document.pop("unknowns")
    for name in ("cycle_edges", "private_crossings"):
        document["budgets"].pop(name)
    (guide_run / "old.json").write_text(json.dumps(document), encoding="utf-8")
    done = _run(guide_run, "validate", "--baseline", "old.json", "--json")
    kinds = {gap["kind"] for gap in json.loads(done.stdout)["baseline"]["gaps"]}
    assert "baseline.older_schema" in kinds


@pytest.fixture(scope="module")
def budget_root(tmp_path_factory: pytest.TempPathFactory, release_core: Path) -> Iterator[Path]:
    """A project that declares two budgets, and its written baseline."""
    root = _project(tmp_path_factory.mktemp("budget"))
    contract = root / "architecture-contract.json"
    document = json.loads(contract.read_text(encoding="utf-8"))
    budget = {"provenance": ["docs/architecture/architecture.md"]}
    document["declarations"] = {
        "measurement_budgets": [
            {"name": "calls_unresolved", **budget},
            {"name": "typing_positions", **budget},
        ]
    }
    contract.write_text(json.dumps(document, indent=2), encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "budgets")
    assert _run(root, "validate", "--write-baseline", "known.json").returncode == 2
    yield root


def _budget_rows(root: Path, name: str) -> tuple[int, list[dict[str, object]]]:
    done = _run(root, "validate", "--baseline", name, "--json")
    document = json.loads(done.stdout)
    return done.returncode, document["baseline"]["new"]


def test_a_budget_above_its_file_value_is_budget_exceeded(budget_root: Path) -> None:
    document = json.loads((budget_root / "known.json").read_text(encoding="utf-8"))
    document["budgets"]["typing_positions"] = 0
    (budget_root / "grow.json").write_text(json.dumps(document), encoding="utf-8")
    code, rows = _budget_rows(budget_root, "grow.json")
    assert code == 1
    assert [(row["kind"], row["subject"]) for row in rows] == [
        ("budget.exceeded", "typing_positions")
    ]


def test_a_declared_budget_without_a_file_value_is_budget_unknown(budget_root: Path) -> None:
    document = json.loads((budget_root / "known.json").read_text(encoding="utf-8"))
    document["budgets"].pop("typing_positions")
    (budget_root / "missing.json").write_text(json.dumps(document), encoding="utf-8")
    code, rows = _budget_rows(budget_root, "missing.json")
    assert code == 1
    assert [(row["kind"], row["subject"]) for row in rows] == [
        ("budget.unknown", "typing_positions")
    ]
