# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-512: the core compares the symbol part of a UML target on TypeScript plants.

The plants and their release rows are in `uml_symbol_plants.py`. A core PASS where 4.0.1 gives FAIL
or UNKNOWN is a bug. A core UNKNOWN where 4.0.1 passes is stricter; where the release PASS is wrong
(`WRONG_RELEASE_PASS`) the core is right.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from test_cli_core_only_scan import command
from test_cli_core_uml_compare import ONE, module, project, scope
from uml_symbol_patterns import PATTERN_CAUSES, PATTERN_PLANTS, WRONG_RELEASE_PATTERNS
from uml_symbol_plants import CAUSES as BASE_CAUSES
from uml_symbol_plants import PLANTS as BASE_PLANTS
from uml_symbol_plants import ROW, edge, referenced, sym, target
from uml_symbol_review import COUNTS, REVIEW_CAUSES, REVIEW_PLANTS, STRICTER, WRONG_RELEASE_PASS

PLANTS = {**BASE_PLANTS, **REVIEW_PLANTS, **PATTERN_PLANTS}
CAUSES = {**BASE_CAUSES, **REVIEW_CAUSES, **PATTERN_CAUSES}


@pytest.mark.parametrize("name", sorted(PLANTS))
def test_the_core_row_is_never_weaker_than_the_release_row(name: str) -> None:
    _, _, release, core = PLANTS[name]
    assert release == core or (release, core) in STRICTER


def test_the_difference_between_the_release_rows_and_the_core_rows_is_counted() -> None:
    rows = [(release, core) for _, _, release, core in PLANTS.values()]
    equal = sum(release == core for release, core in rows)
    passes = {n for n, p in PLANTS.items() if (p[2], p[3]) == ("PASS", "UNKNOWN")}
    fails = {n for n, p in PLANTS.items() if (p[2], p[3]) == ("FAIL", "UNKNOWN")}
    assert (equal, len(passes), len(fails), len(PLANTS)) == COUNTS
    assert (WRONG_RELEASE_PASS | WRONG_RELEASE_PATTERNS) <= passes


@pytest.mark.parametrize(("callee", "expected"), [("request", "PASS"), ("handler", "UNKNOWN")])
def test_a_const_arrow_call_reaches_the_model_but_jsx_registration_does_not(
    core_binary: Path, tmp_path: Path, callee: str, expected: str
) -> None:
    module = "app.src.a.one_x2e_tsx"
    entities = [
        {**referenced(name, "function", name), "qualified_name": f"{module}.{name}"}
        for name in ("Button", callee)
    ]
    uml = target(entities, relationships=[edge("calls", "Button", callee)])
    files = {
        "src/a/one.tsx": (
            "function request() {}\n"
            "function handler() { request(); }\n"
            "export const Button = () => { request(); return <button onClick={handler} />; };\n"
        )
    }
    done = command(core_binary, project(tmp_path, files, uml, None), "--json")
    result = json.loads(done.stdout)
    assert "refusal" not in result, result
    assert result["frame"]["rules"][ROW] == ["uml_target", expected], result["frame"]


@pytest.mark.parametrize("listed", [True, False])
def test_a_direct_anonymous_default_is_a_written_function(
    release_core: Path, tmp_path: Path, listed: bool
) -> None:
    entities = [module("one", ONE)]
    if listed:
        entities.append(sym("default-export", "function", "default"))
    uml = target(
        entities,
        relationships=[],
        scopes=[] if listed else [scope("one", ["function"], [])],
    )
    files = {
        "src/a/one.ts": "export default\nfunction (): number { return 1; }\n",
        "src/b/t.ts": "export const t = 1;\n",
    }
    done = command(release_core, project(tmp_path, files, uml, None), "--json")
    frame = json.loads(done.stdout)["frame"]
    assert frame["scope"] == "complete" and frame["collection_gaps"] == []
    assert frame["rules"][ROW] == ["uml_target", "PASS" if listed else "FAIL"]
    assert done.returncode == (0 if listed else 1)
    if not listed:
        [detail] = frame["details"][ROW]
        assert (detail["source"], detail["target"], detail["cause"]) == (
            "one",
            f"{ONE}.default",
            "closed scope holds an unlisted definition",
        )
        assert {"path": "src/a/one.ts", "line": 2} in [
            frame["locations"][identity] for identity in detail["evidence"]
        ]


@pytest.mark.parametrize("name", sorted(PLANTS))
def test_the_symbol_row_is_the_pinned_row(release_core: Path, tmp_path: Path, name: str) -> None:
    files, uml, _, expected = PLANTS[name]
    done = command(release_core, project(tmp_path, files, uml, None), "--json")
    result = json.loads(done.stdout)
    assert "refusal" not in result, result
    assert result["frame"]["rules"][ROW] == ["uml_target", expected], result["frame"]["explained"]
    causes = CAUSES.get(name, "")
    causes = (causes,) if isinstance(causes, str) else causes
    if expected == "FAIL":
        found = {item["cause"] for item in result["frame"]["details"][ROW]}
        assert found == set(causes), found
        assert done.returncode == 1
    if expected == "PASS":
        assert result["status"] == "PASS" and done.returncode == 0, result["frame"]
        assert name not in CAUSES
    if expected == "UNKNOWN":
        assert causes[0] in result["frame"]["explained"][ROW], result["frame"]["explained"][ROW]
        assert result["frame"]["unknown_kinds"][ROW] == "no_receipt"
        assert done.returncode == 2
