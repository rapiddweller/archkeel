# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Keep every unproved CPython site in a counted condition class."""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from pathlib import Path

import pytest
from python_compile_classes import PROOFS, classification, condition_class
from python_compile_grammar_families import family, seeds
from python_compile_review_families import outcome
from python_compile_sites import message_pattern
from test_collector_native_python_parse import _minor, _native, _write
from test_collector_native_python_survey import _native as survey
from test_collector_native_python_survey import _request

ROOT = Path(__file__).parents[1]
PINS = json.loads((ROOT / "tests/python_compile_messages.json").read_text())
TABLE = json.loads((ROOT / "tests/python_compile_sites.json").read_text())
SUMMARY = json.loads((ROOT / "tests/python_compile_completeness.json").read_text())
SITES = {site["id"]: site for pin in PINS.values() for site in pin["sites"]}
CLASSIFIED = sorted(
    (row["site"], *classification(SITES[row["site"]]))
    for row in TABLE["rows"]
    if row["status"] == "UNPROVED"
)


def test_all_unproved_sites_have_a_counted_class() -> None:
    sites = {site["id"]: site for pin in PINS.values() for site in pin["sites"]}
    counts = Counter(
        condition_class(sites[row["site"]]) for row in TABLE["rows"] if row["status"] == "UNPROVED"
    )
    assert counts == {
        "grammar": 445,
        "resource-allocation": 139,
        "ast-validation": 133,
        "Parser/lexer/lexer.c": 74,
        "Python/compile.c": 55,
        "Parser/pegen_errors.c": 54,
        "Python/symtable.c": 43,
        "Parser/action_helpers.c": 30,
        "Parser/string_parser.c": 29,
        "Parser/pegen.c": 21,
        "Python/codegen.c": 14,
        "Parser/tokenizer.c": 11,
        "Python/flowgraph.c": 11,
        "Parser/tokenizer/helpers.c": 8,
        "Python/ast_opt.c": 6,
        "Parser/tokenizer/file_tokenizer.c": 2,
        "Parser/tokenizer/readline_tokenizer.c": 2,
    }
    assert sum(counts.values()) == TABLE["unwitnessed"] == SUMMARY["initial_unproved"] == 1077


def test_condition_proofs_close_sites_without_erasing_the_witness_inventory() -> None:
    sites = {site["id"]: site for pin in PINS.values() for site in pin["sites"]}
    counts = Counter(
        classification(sites[row["site"]])[0]
        for row in TABLE["rows"]
        if row["status"] == "UNPROVED"
    )
    assert counts == {"A": 150, "B": 433, "D": 494}
    assert counts == {
        "A": SUMMARY["unreachable"],
        "B": SUMMARY["family_refused"],
        "D": SUMMARY["unproved"],
    }
    assert counts["D"] == TABLE["unproved"] > 0
    assert SUMMARY["complete"] is TABLE["complete"] is False
    digest = hashlib.sha256(json.dumps(CLASSIFIED, sort_keys=True).encode()).hexdigest()
    assert digest == SUMMARY["membership_sha256"]
    assert Counter(name for _, kind, name in CLASSIFIED if kind == "A") == SUMMARY["source_proofs"]
    assert set(PROOFS) == set(SUMMARY["source_proofs"])
    assert Counter(name for _, kind, name in CLASSIFIED if kind == "D") == {
        name: count for name, (count, reason) in SUMMARY["remaining"].items() if reason
    }


@pytest.fixture(scope="module")
def grammar_results(python_dump_binary: Path, tmp_path_factory: pytest.TempPathFactory):
    sources = {name: source for rule in seeds() for name, source in family(rule).items()}
    root = tmp_path_factory.mktemp("compiler-grammar-families")
    native = _native(
        python_dump_binary, root, _write(root, {f"{n}.py": s for n, s in sources.items()})
    )
    compiler = {name: outcome(source) for name, source in sources.items()}
    assert len(sources) == SUMMARY["family_cases"]
    digest = hashlib.sha256(
        json.dumps(compiler, sort_keys=True, ensure_ascii=True).encode()
    ).hexdigest()
    assert digest == SUMMARY["compiler_outcomes_sha256"][f"3.{_minor()}"]
    return sources, compiler, native


@pytest.mark.parametrize("rule", seeds())
def test_each_grammar_condition_refuses_in_each_source_position(rule: str, grammar_results) -> None:
    _, compiler, native = grammar_results
    for name, source in family(rule).items():
        found = native[f"{name}.py"]
        if compiler[name] is not None:
            assert found is not None, (rule, name, compiler[name], source)
        else:
            assert found is None, (rule, "unlisted false refusal", name, found, source)
    messages = [compiler[name][1] for name in family(rule) if compiler[name] is not None]
    for site, kind, name in CLASSIFIED:
        if kind != "B" or name != rule or SITES[site] not in PINS[f"3.{_minor()}"]["sites"]:
            continue
        for template in SITES[site]["messages"]:
            assert any(re.fullmatch(message_pattern(template), message) for message in messages), (
                site,
                rule,
                template,
            )


def test_a_proof_does_not_turn_resource_or_identifier_checks_into_unreachable_sites() -> None:
    for site in SITES.values():
        if site["call"] == "PyErr_NoMemory":
            assert classification(site)[0] == "D"
        if site["file"] == "Python/ast.c" and site["function"] == "validate_name":
            assert classification(site) == ("D", "ast-validation")


def test_each_refused_family_source_has_a_named_gap_and_no_facts(
    grammar_results, python_dump_binary: Path, tmp_path: Path
) -> None:
    sources, compiler, _ = grammar_results
    refused = {
        f"r{index}.py": sources[name]
        for index, name in enumerate(sources)
        if compiler[name] is not None
    }
    _write(tmp_path, refused)
    found = survey(python_dump_binary, _request(tmp_path, (".",), "probe", False))
    assert found["coverage"]["full_scope"] is False
    assert not found["files"] and not found["imports"] and not found["evidence"]
    gaps = found["coverage"]["gaps"]
    assert {gap["data"]["file"] for gap in gaps} == set(refused)
    assert all(gap["data"]["message"] for gap in gaps)
