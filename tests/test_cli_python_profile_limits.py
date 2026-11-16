# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-644: a profile limit holds only what reads the part that it limits, through the release core.

Consumer: a CI job that reads the row of each rule. The Python collector examines no construct,
decides no `symbol_placement` rule and measures no `private_crossings` budget. Each such limit
keeps its own rule (or, for a budget, the run) UNKNOWN; the rules on the import edges and the
files decide. A violation that the scan sees stays FAIL, and a hidden construct never passes:
Python runs the truth of each plant.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any, NamedTuple

import pytest
from test_cli_native_python_imports import RULE, project, rows, verdict
from test_cli_python_gap_effects import FILES, RULES

CONSTRUCT = {
    **RULE,
    "id": "NO-GETATTR",
    "kind": "forbidden_construct",
    "source": "app",
    "constructs": ["getattr"],
    "allowed_sources": [],
    "exact_sources": [],
}
PLACEMENT = {
    **RULE,
    "id": "PROTOCOLS-IN-SERVICE",
    "kind": "symbol_placement",
    "source": "app",
    "class_kinds": ["protocol"],
    "allowed_sources": ["app.service"],
}
BUDGET = {"name": "private_crossings", "provenance": ["p"]}
# Prints `True` when `app.client.page` really calls the builtin `getattr` (the hidden construct).
CALLS_GETATTR = (
    "import ast, pathlib; tree = ast.parse(pathlib.Path('src/app/client/page.py').read_text()); "
    "print(any(isinstance(n, ast.Call) and getattr(n.func, 'id', '') == 'getattr' "
    "for n in ast.walk(tree)))"
)
# Prints `True` when importing `app.client.page` loads `app.service.secret` (the seen violation).
LOADS_SECRET = "import sys, app.client.page; print('app.service.secret' in sys.modules)"


class Plant(NamedTuple):
    files: dict[str, str]
    # The limited rules that the contract adds, and its measurement budgets.
    extra: list[dict[str, Any]]
    budgets: list[dict[str, Any]]
    # The rows that are not PASS, with their status. Each other rule is PASS.
    open: dict[str, str]
    # The text that the row of each held rule names.
    why: dict[str, str]
    # Python code that prints `True` when the hidden or seen fact is real.
    truth: str = ""


GETATTR_PAGE = "import app.service.model as model\nVALUE = getattr(model, 'VALUE')\n"
PLANTS = {
    # Before AD-644 the construct limit held every rule of the run.
    "construct": Plant(
        {"src/app/client/page.py": GETATTR_PAGE},
        [CONSTRUCT],
        [],
        {"NO-GETATTR": "UNKNOWN"},
        {"NO-GETATTR": "the profile cannot decide NO-GETATTR: the collector examines no getattr"},
        truth=CALLS_GETATTR,
    ),
    "construct beside a seen violation": Plant(
        {"src/app/client/page.py": "import app.service.secret\n" + GETATTR_PAGE},
        [CONSTRUCT],
        [],
        {"NO-GETATTR": "UNKNOWN", "CLIENT-NO-SECRET": "FAIL"},
        {"NO-GETATTR": "the collector examines no getattr"},
        truth=LOADS_SECRET,
    ),
    # An unported rule kind is an unsupported row; it holds no rule on the edges.
    "symbol placement": Plant({}, [PLACEMENT], [], {}, {}),
    # A budget that no profile measures holds the run, and no rule.
    "budget": Plant({}, [], [BUDGET], {}, {}),
}


def scanned(binary: Path, root: Path, plant: Plant) -> dict[str, Any]:
    path = project(root, {**FILES, **plant.files}, contract_rules=[*RULES, *plant.extra])
    if plant.budgets:
        contract_path = path / "architecture-contract.json"
        contract = json.loads(contract_path.read_text())
        contract["declarations"] = {"measurement_budgets": plant.budgets}
        contract_path.write_text(json.dumps(contract))
    return verdict(binary, path)


@pytest.mark.parametrize("name", sorted(PLANTS))
def test_a_profile_limit_holds_only_what_reads_it(
    release_core: Path, tmp_path: Path, name: str
) -> None:
    plant = PLANTS[name]
    result = scanned(release_core, tmp_path, plant)
    frame = result["frame"]
    decided = [rule["id"] for rule in [*RULES, *plant.extra] if rule["kind"] != "symbol_placement"]
    expected = {rule: plant.open.get(rule, "PASS") for rule in decided}
    assert rows(result) == expected, frame["explained"]
    for rule, text in plant.why.items():
        assert text in frame["explained"][rule], frame["explained"][rule]
    # A limited part never lets the run pass.
    assert result["status"] == ("FAIL" if "FAIL" in plant.open.values() else "UNKNOWN"), result
    if plant.truth:
        done = subprocess.run(
            [sys.executable, "-I", "-c", f"import sys; sys.path.insert(0, 'src'); {plant.truth}"],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            check=True,
        )
        assert done.stdout.strip() == "True", done


def test_an_unported_kind_and_an_unmeasured_budget_name_their_own_rows(
    release_core: Path, tmp_path: Path
) -> None:
    placement = scanned(release_core, tmp_path / "placement", PLANTS["symbol placement"])
    unsupported = placement["frame"]["unsupported"]["rules"]
    assert "rule kind SymbolPlacement" in unsupported["PROTOCOLS-IN-SERVICE"], unsupported
    budget = scanned(release_core, tmp_path / "budget", PLANTS["budget"])["frame"]
    assert "declarations.measurement_budgets.private_crossings" in budget["scope"], budget["scope"]
