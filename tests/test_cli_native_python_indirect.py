# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-1085: `indirect` on `forbidden_dependency` proves a chain of imports through other modules.

The default stays direct, so a rule without the key gives the result of before. A chain gives FAIL
with the shortest path, tied by module name, and the file and line of each hop. No chain gives
PASS only when each import of the scan is resolved: an import by a computed name in any module
gives UNKNOWN.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from test_cli_core_only_scan import command
from test_cli_native_python_imports import RULE, project, rows, verdict

BASE = {
    "src/app/__init__.py": "",
    "src/app/client.py": "import app.mid\n",
    "src/app/mid.py": "import os\nimport app.service\n",
    "src/app/service.py": "VALUE = 1\n",
}


def forbid(**fields: Any) -> list[dict[str, Any]]:
    rule = {"id": "FORBID", "kind": "forbidden_dependency", **RULE}
    rule |= {"source": "app.client", "target": "app.service", "include_type_checking": True}
    return [rule | fields]


def scan(release_core: Path, root: Path, rules: list[dict[str, Any]], files: dict[str, str]) -> Any:
    project(root, files, contract_rules=rules)
    contract = root / "architecture-contract.json"
    contract.write_text(contract.read_text().replace('"2.2.0"', '"3.21.0"'))
    identity = ["-c", "user.name=t", "-c", "user.email=t@t"]
    subprocess.run(["git", "-C", str(root), *identity, "commit", "-qam", "3.21"], check=True)
    return verdict(release_core, root)


def hops(result: dict[str, Any]) -> list[tuple[str, str, str, int]]:
    frame = result["frame"]
    (row,) = frame["details"]["FORBID"]
    sites = [frame["locations"][step["evidence"]] for step in row["path"]]
    return [
        (step["from"], step["to"], site["path"], site["line"])
        for step, site in zip(row["path"], sites, strict=True)
    ]


def test_two_hops_fail_with_the_chain_and_a_site_for_each_hop(
    release_core: Path, tmp_path: Path
) -> None:
    result = scan(release_core, tmp_path, forbid(indirect=True), BASE)
    assert rows(result)["FORBID"] == "FAIL" and result["exit_code"] == 1
    assert hops(result) == [
        ("app.client", "app.mid", "src/app/client.py", 1),
        ("app.mid", "app.service", "src/app/mid.py", 2),
    ]


def test_the_default_and_false_judge_a_direct_import_only(
    release_core: Path, tmp_path: Path
) -> None:
    for name, fields in (("absent", {}), ("false", {"indirect": False})):
        result = scan(release_core, tmp_path / name, forbid(**fields), BASE)
        assert rows(result)["FORBID"] == "PASS", (name, result)


def test_a_computed_import_in_the_middle_module_is_unknown_not_pass(
    release_core: Path, tmp_path: Path
) -> None:
    middle = (
        "import importlib\n\n\ndef load(name):\n    return importlib.import_module(f'app.{name}')\n"
    )
    files = {**BASE, "src/app/mid.py": middle}
    result = scan(release_core, tmp_path / "indirect", forbid(indirect=True), files)
    assert rows(result)["FORBID"] == "UNKNOWN" and result["exit_code"] == 2, result


def test_a_tie_goes_to_the_smaller_module_name_and_a_rerun_gives_the_same_bytes(
    release_core: Path, tmp_path: Path
) -> None:
    files = {
        **BASE,
        "src/app/client.py": "import app.zeta\nimport app.alpha\n",
        "src/app/alpha.py": "import app.service\n",
        "src/app/zeta.py": "import app.service\n",
    }
    first = scan(release_core, tmp_path, forbid(indirect=True), files)
    assert [(a, b) for a, b, _, _ in hops(first)] == [
        ("app.client", "app.alpha"),
        ("app.alpha", "app.service"),
    ]
    again = verdict(release_core, tmp_path)
    assert json.dumps(first["frame"], sort_keys=True) == json.dumps(again["frame"], sort_keys=True)


def test_the_shortest_chain_wins_over_a_longer_one(release_core: Path, tmp_path: Path) -> None:
    files = {
        **BASE,
        "src/app/client.py": "import app.long1\nimport app.mid\n",
        "src/app/long1.py": "import app.long2\n",
        "src/app/long2.py": "import app.service\n",
    }
    result = scan(release_core, tmp_path, forbid(indirect=True), files)
    assert [(a, b) for a, b, _, _ in hops(result)] == [
        ("app.client", "app.mid"),
        ("app.mid", "app.service"),
    ]


def test_allowed_sources_exempts_the_first_module_of_a_chain_only(
    release_core: Path, tmp_path: Path
) -> None:
    rules = forbid(indirect=True, source="app.cli", allowed_sources=["app.cli.legacy"])
    files = {
        **BASE,
        "src/app/cli/__init__.py": "",
        "src/app/cli/main.py": "import os\n",
        "src/app/cli/legacy.py": "import app.mid\n",
        "src/app/mid.py": "import app.service\n",
    }
    # The exempt module `legacy` starts a chain: no violation.
    assert rows(scan(release_core, tmp_path / "start", rules, files))["FORBID"] == "PASS"
    # The same module in the middle of the chain of `main` is no exception.
    through = {**files, "src/app/cli/main.py": "import app.cli.legacy\n"}
    result = scan(release_core, tmp_path / "through", rules, through)
    assert rows(result)["FORBID"] == "FAIL"
    assert [hop[:2] for hop in hops(result)] == [
        ("app.cli.main", "app.cli.legacy"),
        ("app.cli.legacy", "app.mid"),
        ("app.mid", "app.service"),
    ]


def test_a_type_checking_hop_follows_include_type_checking(
    release_core: Path, tmp_path: Path
) -> None:
    middle = "from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    import app.service\n"
    files = {**BASE, "src/app/mid.py": middle}
    kept = scan(release_core, tmp_path / "kept", forbid(indirect=True), files)
    assert rows(kept)["FORBID"] == "FAIL"
    left_out = forbid(indirect=True, include_type_checking=False)
    assert rows(scan(release_core, tmp_path / "out", left_out, files))["FORBID"] == "PASS"


def test_the_text_and_the_report_show_the_chain_with_a_site_for_each_hop(
    release_core: Path, tmp_path: Path
) -> None:
    scan(release_core, tmp_path, forbid(indirect=True), BASE)
    text = command(release_core, tmp_path, "--text").stdout
    assert "FORBID: indirect forbidden dependency: app.client -> app.mid -> app.service" in text
    assert "(src/app/client.py:1, src/app/mid.py:2)" in text
    # The report page reads the same violation rows: a chain has a `path` and no `members`.
    done = command(release_core, tmp_path, "--json", verb="report")
    result = json.loads(done.stdout)
    assert result["exit_code"] == 1 and "refusal" not in result, done.stderr
    assert [(a, b) for a, b, _, _ in hops(result)] == [
        ("app.client", "app.mid"),
        ("app.mid", "app.service"),
    ]
