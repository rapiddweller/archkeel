# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Profile statements release no actual source gap and make no PASS proof."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest
from core_support import SUFFIX
from corpus_support import case as corpus_case
from corpus_support import commit_tree, materialized

CASES = (
    "s4/a-symbol-selector-is-a-limit-of-some-profiles",
    "s4/an-interface-boundary-is-a-limit-of-some-profiles",
    "s5/requires-symbol-port-is-judged-with-the-symbol-feature",
    "probe/full-test-a-changed-reply-gives-no-pass-for-each-rule-family-inte",
)
MAIN = "shop.src.main_x2e_ts"
PRIVATE = "import outside the public interface"


def scan(built: Path, root: Path) -> dict[str, Any]:
    request = {
        "protocol": "archkeel-core-scan-1",
        "root": str(root.resolve()),
        "config": "archkeel.toml",
    }
    done = subprocess.run(
        [str(built / f"archkeel-core{SUFFIX}"), "scan"],
        input=json.dumps(request),
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    assert done.returncode in (0, 3), done.stderr
    frame: dict[str, Any] = json.loads(done.stdout)
    assert "refused" not in frame["self_test"]["collect"], frame
    frame["rules"] = {key: value[1] for key, value in frame["rules"].items()}
    return frame


@pytest.mark.parametrize("fixture_dirty", [False, True])
@pytest.mark.parametrize("checkout_dirty", [False, True])
def test_scan_derives_fixture_state_not_the_callers_checkout(
    built: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fixture_dirty: bool,
    checkout_dirty: bool,
) -> None:
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    (checkout / "tracked").write_text("base")
    commit_tree(checkout)
    if checkout_dirty:
        (checkout / "untracked").write_text("build output")
    monkeypatch.chdir(checkout)
    with materialized(corpus_case(CASES[0])) as root:
        (root / "tracked-state.txt").write_text("committed fixture")
        commit_tree(root)
        if fixture_dirty:
            (root / "untracked").write_text("fixture change")
        frame = scan(built, root)
        snapshot = frame["self_test"]["collect"]["request"]["snapshot"]
        assert snapshot["root"] == str(root.resolve())
        assert snapshot["dirty"] is fixture_dirty


@pytest.mark.parametrize("case_id", CASES)
def test_a_known_profile_limit_does_not_hold_an_unrelated_rule(built: Path, case_id: str) -> None:
    case = corpus_case(case_id)
    with materialized(case) as root:
        frame = scan(built, root)
    assert frame["rules"].get("ASSIGNMENT") == "PASS", frame["unsupported"]
    assert frame["rules"].get("DOMAIN-NO-DATA") == "PASS", frame["unsupported"]
    assert frame["rules"].get("LAYOUT") == "PASS", frame["unsupported"]
    assert "limit of some profiles" not in json.dumps(frame["unsupported"])
    if case_id.startswith("s4/a-symbol"):
        assert frame["rules"]["SYMBOL"] == "PASS"
    # AD-428 keeps the private imports FAIL; AD-434 proves the named type publications.
    if "interface" in case_id:
        assert frame["rules"]["BOUNDARY"] == "FAIL", frame
        assert "BOUNDARY" not in frame["unsupported"]["rules"]
        assert {
            (row["source"], row["target"], row["cause"]) for row in frame["details"]["BOUNDARY"]
        } == {
            (MAIN, "shop.src.data.local_x2e_ts:local", PRIVATE),
            (MAIN, "shop.src.presentation.page_x2e_ts:page", PRIVATE),
        }
    if case_id.startswith("probe/"):
        assert frame["rules"]["PROBE"] == "PASS", frame
        assert "PROBE" not in frame["unsupported"]["rules"]
        assert "PROBE" not in frame["explained"], frame
        assert "PROBE" not in frame["details"], frame


@pytest.mark.parametrize("case_id", CASES)
def test_a_profile_statement_cannot_hide_a_dynamic_forbidden_edge(
    built: Path, case_id: str
) -> None:
    case = corpus_case(case_id)
    with materialized(case) as root:
        before = scan(built, root)
        assert before["rules"].get("DOMAIN-NO-DATA") == "PASS", before["unsupported"]
        source = root / "src/domain/order.ts"
        source.write_text(source.read_text() + '\nimport(globalThis["forbiddenModule"]);\n')
        planted = scan(built, root)
    assert planted["rules"].get("DOMAIN-NO-DATA") in {"UNKNOWN", "FAIL"}, planted
    assert planted["status"] != "PASS"


def test_an_unread_symbol_position_stays_unknown(built: Path) -> None:
    case_id = "s5/forbidden-symbol-rule-leaves-a-position-undecided"
    case = corpus_case(case_id)
    with materialized(case) as root:
        frame = scan(built, root)
    assert frame["rules"].get("ASSIGNMENT") == "PASS", frame["unsupported"]
    assert frame["rules"].get("SYMBOL") == "UNKNOWN", frame
    assert "undecided" in frame["explained"]["SYMBOL"], frame


def test_a_namespace_import_has_a_named_unknown_row_not_a_profile_refusal(built: Path) -> None:
    case_id = "s4/a-symbol-selector-is-a-limit-of-some-profiles"
    case = corpus_case(case_id)
    with materialized(case) as root:
        source = root / "src/presentation/page.ts"
        source.write_text(source.read_text() + '\nimport * as domain from "../domain";\n')
        frame = scan(built, root)
    assert frame["rules"]["SYMBOL"] == "UNKNOWN", frame
    assert frame["explained"]["SYMBOL"] == "incomplete scope: the rule left 1 imports undecided"
    assert frame["scope"] == "complete", frame["scope"]
    assert "limit of some profiles" not in json.dumps(frame["unsupported"])


def test_a_symbol_public_interface_releases_no_actual_gap(built: Path) -> None:
    case = corpus_case("fixture/H-typescript")
    with materialized(case) as root:
        path = root / "architecture-contract.json"
        contract = json.loads(path.read_text())
        component = next(c for c in contract["components"] if c["label"] == "data")
        component["public"] = ["shop.src.data.local_x2e_ts:local"]
        contract["declarations"] = {}
        # AD-466: `complete_requires` decides each pair; without it 4.0.1 names open decisions.
        kept = {"DOMAIN-NO-DATA", "REQUIRES"}
        contract["rules"] = [r for r in contract["rules"] if r["id"] in kept]
        path.write_text(json.dumps(contract))
        before = scan(built, root)
        assert before["rules"] == {"DOMAIN-NO-DATA": "PASS", "REQUIRES": "PASS"}, before
        assert before["status"] == "PASS", before
        source = root / "src/domain/order.ts"
        source.write_text(source.read_text() + '\nimport(globalThis["forbiddenModule"]);\n')
        planted = scan(built, root)
    assert planted["rules"]["DOMAIN-NO-DATA"] in {"UNKNOWN", "FAIL"}, planted
    assert planted["status"] != "PASS"
