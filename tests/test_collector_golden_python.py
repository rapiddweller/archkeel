# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-343: the golden replies of the Python collector and the interpreter that made them.

Consumer: the phases of epic #880 that replace the Python collector of Python sources (PR 5) and
then delete it (PR 6). The case list, the recorder and the compare are in
`test_collector_golden_replies.py`. This file checks what only Python needs: the coverage of
the record kinds and the handling of the interpreter.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any

import golden_record
import golden_replies
import pytest

from archkeel.analyzer.python import collect, constructs
from archkeel.ir.facts import (
    BASE_RESOLUTION_FEATURES,
    GATED_RESOLUTION_FEATURES,
    SourceResolution,
)
from archkeel.ir.protocol import PYTHON_IMPORT_SURVEY_SECTIONS

ROOT = Path(__file__).parents[1]
ANALYZER = ROOT / "src/archkeel/analyzer/python"
CASES = list(golden_record.cases("python"))
# Fixtures with a Python scan that no case freezes, with the reason.
_STUB = "a policy fixture with one stub file: it adds no collector coverage"
NOT_RECORDED = {
    "E-runtime": "its sample uses PEP 695 syntax: the reply depends on the minor version",
    "planned-component": _STUB,
    "planned-component-policy": _STUB,
}
# Kinds that the collector can emit and that no repository file can freeze, with the reason.
UNREACHABLE = {
    "OSError": "it needs an unreadable file, and the permissions of a checkout change",
    "ValueError": "a null byte gives SyntaxError from Python 3.12, so the kind needs one minor",
}

_REFLECTION = {f"{name}_call" for name in ("getattr", "hasattr", "setattr", "delattr", "vars")}
_CONSTRUCT_KINDS = {
    "assert_statement",
    "placeholder_body",
    "broad_except",
    "string_literal_compare",
}
_SIGNAL_KINDS = {
    "any_annotation",
    "dict_any_annotation",
    "callable_any_annotation",
    "object_annotation",
    "cast_call",
    "getattr_call",
    "hasattr_call",
    "eval_call",
    "exec_call",
    "dynamic_import",
}
_FILE_FAILURES = {"SyntaxError", "UnicodeDecodeError", "TooDeepError", *UNREACHABLE}
# Each place that gives a record its kind, with the section and the kinds it can give. A new place
# fails the test: add it here and add a case that freezes its kinds.
_SITES: dict[tuple[str, str], tuple[str, set[str]]] = {
    ("bindings.py", "f'unused_{binding}'"): ("bindings", {"unused_parameter", "unused_local"}),
    ("calls.py", "f'{status}_call'"): (
        "calls",
        {f"{item.value}_call" for item in SourceResolution},
    ),
    ("constructs.py", "'numeric_operand'"): ("constructs", {"numeric_operand"}),
    ("constructs.py", "'construct_selector'"): ("constructs", {"construct_selector"}),
    ("constructs.py", "'assert_statement'"): ("constructs", {"assert_statement"}),
    ("constructs.py", "'placeholder_body'"): ("constructs", {"placeholder_body"}),
    ("constructs.py", "'broad_except'"): ("constructs", {"broad_except"}),
    ("constructs.py", "'string_literal_compare'"): ("constructs", {"string_literal_compare"}),
    ("constructs.py", "'dunder_dict'"): ("constructs", {"dunder_dict"}),
    ("constructs.py", "_REFLECTION_CALLS[name]"): ("constructs", _REFLECTION),
    ("constructs.py", "kind"): ("constructs", _CONSTRUCT_KINDS | _REFLECTION | {"dunder_dict"}),
    ("explore_scope.py", "SOURCE_RESOLUTION_GAP_KIND"): ("unknowns", {"source_resolution_gap"}),
    ("explore_scope.py", "'collection_gap'"): ("unknowns", {"collection_gap"}),
    ("imports.py", "'import'"): ("imports", {"import"}),
    ("imports.py", "'dynamic_import_limit'"): ("unknowns", {"dynamic_import_limit"}),
    ("private_attributes.py", "'private_attribute_access_limit'"): (
        "unknowns",
        {"private_attribute_access_limit"},
    ),
    ("references.py", "'source_role'"): ("references", {"source_role"}),
    ("references.py", "f'{use}_reference'"): (
        "references",
        {"value_reference", "attribute_reference"},
    ),
    ("source.py", "exc.__class__.__name__"): ("unknowns", _FILE_FAILURES),
    ("symbols.py", "kind"): (
        "symbols",
        {"static_constant", "dynamic_binding", "type_alias"},
    ),
    (
        "symbols.py",
        "'class' if isinstance(node, ast.ClassDef) else 'method' if classifier else 'function'",
    ): ("symbols", {"class", "method", "function"}),
    ("typing_signals.py", "kind"): ("typing_signals", _SIGNAL_KINDS),
    ("typing_signals.py", "'type_ignore'"): ("typing_signals", {"type_ignore"}),
    ("typing_signals.py", "'missing_cross_package_annotation'"): (
        "typing_signals",
        {"missing_cross_package_annotation"},
    ),
}
# These calls pass `kind=` to a record. Other calls with `kind=` build bindings, not records.
_RECORD_CALLS = {"classified", "self._record"}


def _kind_sites() -> set[tuple[str, str]]:
    sites: set[tuple[str, str]] = set()
    for path in sorted(ANALYZER.glob("*.py")):
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.Call) and ast.unparse(node.func) in _RECORD_CALLS:
                sites.update(
                    (path.name, ast.unparse(item.value))
                    for item in node.keywords
                    if item.arg == "kind"
                )
    return sites


def _features(case: str) -> set[str]:
    return set(golden_replies.load("python", case).digest["features"])


def _covered() -> tuple[dict[str, set[str]], set[str], dict[str, int]]:
    kinds: dict[str, set[str]] = {}
    features: set[str] = set()
    counts: dict[str, int] = {}
    for case in CASES:
        digest = golden_replies.load("python", case).digest
        for name, section in digest["sections"].items():
            kinds.setdefault(name, set()).update(section["kinds"])
        features.update(digest["features"])
        for key, count in digest["rest"]["counts"].items():
            counts[key] = counts.get(key, 0) + count
    return kinds, features, counts


def test_every_place_that_gives_a_record_its_kind_is_known() -> None:
    assert _kind_sites() == set(_SITES)
    assert {name for name, _ in _SITES.values()} == {s.value for s in collect._SECTION_NAMES}
    assert _REFLECTION == set(constructs._REFLECTION_CALLS.values())


def test_every_kind_and_feature_that_the_python_collector_emits_has_golden_coverage() -> None:
    emitted: dict[str, set[str]] = {}
    for section, kinds in _SITES.values():
        emitted.setdefault(section, set()).update(kinds)
    kinds, features, _ = _covered()
    missing = {name: sorted(want - kinds.get(name, set())) for name, want in emitted.items()}
    assert {name: gap for name, gap in missing.items() if gap} == {"unknowns": sorted(UNREACHABLE)}
    assert {*BASE_RESOLUTION_FEATURES, *GATED_RESOLUTION_FEATURES} <= features
    alone = [c for c in CASES if _features(c) == set(BASE_RESOLUTION_FEATURES)]
    assert alone, "no case freezes the base features alone"


def test_the_lists_that_the_python_collector_fills_have_golden_coverage() -> None:
    counts = _covered()[2]
    names = ("type_shapes", "uncertain_reexports", "candidate_evidence", "provider_bindings")
    assert [name for name in (*names, "provider_sources", "inputs") if not counts.get(name)] == []


def test_every_python_fixture_is_a_case_or_has_a_reason() -> None:
    scanned = {
        path.parent.name
        for path in (ROOT / "fixtures").glob("*/archkeel.toml")
        if "language" not in path.read_text()
    }
    recorded = {
        golden_record.cases("python")[case].name
        for case in CASES
        if golden_record.cases("python")[case].parent.name == "fixtures"
    }
    assert scanned - recorded == set(NOT_RECORDED)


@pytest.mark.parametrize("case", [name for name in CASES if name.endswith("-survey")])
def test_a_survey_case_freezes_the_import_survey_and_its_provider_sources(case: str) -> None:
    digest = golden_replies.load("python", case).digest
    assert digest["order"] == [section.value for section in PYTHON_IMPORT_SURVEY_SECTIONS]


def test_each_survey_case_has_a_full_case_on_the_same_sources() -> None:
    roots = {name: golden_record.cases("python")[name] for name in CASES}
    for name in CASES:
        if name.endswith("-survey"):
            assert roots[name.removesuffix("-survey")] == roots[name]


def test_every_excerpt_of_the_corpus_has_its_licence_and_its_commit() -> None:
    listing = json.loads((golden_replies.GOLDEN / "python/cases.json").read_text())
    excerpts = [item for item in listing if item["case"].startswith("fastapi-")]
    assert len(excerpts) == 2
    for item in excerpts:
        folder = ROOT / item["root"]
        assert "MIT License" in (folder / "LICENSE").read_text()
        assert "ba47d6d71b3e806900c8471f2f661781b8c43ec4" in (folder / "SOURCE.md").read_text()


def _reply(imports: str = "a", evidence: str = "e", calls: str = "c") -> dict[str, Any]:
    names = {"imports": [{"kind": "import", "title": imports}], "calls": [{"title": calls}]}
    return {
        "facts": {
            "adapter": {"name": "x"},
            "capabilities": {"sections": list(names)},
            "sections": [{"name": name, "records": records} for name, records in names.items()],
            "files": [{"path": "<root>/a.py"}],
            "evidence": [{"excerpt": evidence}],
            "inputs": [],
            "imports": [],
            "type_shapes": [],
            "uncertain_reexports": [],
            "candidate_evidence": [],
            "source": {"source_digest": evidence},
        },
        "provider_sources": [{"path": evidence}],
    }


PIN = golden_replies.Pin(
    {"implementation": "cpython", "version": "3.11.12", "builtin_modules": 101},
    ("calls",),
    ("evidence", "source"),
    ("provider_sources",),
    "These parts hold the text of the standard library.",
)


def _golden(small: bool) -> golden_replies.Golden:
    value = _reply()
    return golden_replies.Golden(golden_replies.digest(value, PIN), value if small else None)


def _on(monkeypatch: pytest.MonkeyPatch, version: str, builtins: int = 101) -> None:
    now = {"implementation": "cpython", "version": version, "builtin_modules": builtins}
    monkeypatch.setattr(golden_replies, "interpreter", lambda: now)


@pytest.mark.parametrize("small", [True, False], ids=["full", "digest"])
def test_another_interpreter_changes_only_the_parts_that_the_pin_names(
    small: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    golden = _golden(small)
    _on(monkeypatch, "3.13.15")
    other = _reply(evidence="other", calls="other")
    verdict = golden_replies.compare_on_interpreter(golden, other, None, PIN)
    assert verdict.mismatches == ()
    assert "recorded with cpython 3.11.12" in verdict.unpinned and "3.13.15" in verdict.unpinned
    assert "['calls', 'evidence', 'source', 'provider_sources']" in verdict.unpinned
    changed = golden_replies.compare_on_interpreter(golden, _reply(imports="b"), None, PIN)
    assert [m.split(":")[0] for m in changed.mismatches] == ["imports"]


@pytest.mark.parametrize("small", [True, False], ids=["full", "digest"])
def test_the_recorded_interpreter_compares_the_whole_reply(
    small: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    golden = _golden(small)
    _on(monkeypatch, "3.11.12")
    assert golden_replies.compare_on_interpreter(golden, _reply(), None, PIN).mismatches == ()
    for changed in (_reply(calls="x"), _reply(evidence="x")):
        verdict = golden_replies.compare_on_interpreter(golden, changed, None, PIN)
        assert verdict.mismatches and not verdict.unpinned
    _on(monkeypatch, "3.11.12", builtins=31)
    assert golden_replies.compare_on_interpreter(golden, _reply(calls="x"), None, PIN).unpinned


def test_the_deletion_gate_needs_the_interpreter_of_the_recording(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gate = {"ARCHKEEL_GOLDEN_GATE": "delete"}
    _on(monkeypatch, "3.11.12")
    golden_replies.require_recorded_interpreter(PIN, gate)
    _on(monkeypatch, "3.12.10", builtins=31)
    golden_replies.require_recorded_interpreter(PIN, {})
    golden_replies.require_recorded_interpreter(None, gate)
    with pytest.raises(golden_replies.GoldenError, match="3.11.12 with 101.*not cpython 3.12.10"):
        golden_replies.require_recorded_interpreter(PIN, gate)


def test_the_pin_names_the_interpreter_of_each_recording() -> None:
    pin = golden_replies.pin_for("python")
    assert pin is not None
    runtime = f"({pin.recorded['implementation']} {pin.recorded['version']})"
    log = (golden_replies.GOLDEN / "python/RECORDINGS.md").read_text().splitlines()
    last = {line.split("|")[2].strip(): line for line in log if line.startswith("| 20")}
    assert sorted(last) == sorted(CASES)
    assert all(line.rstrip(" |").endswith(runtime) for line in last.values())
    assert golden_replies.pin_for("typescript") is None


def test_the_portable_part_of_a_golden_reply_does_not_hold_what_the_pin_names() -> None:
    pin = golden_replies.pin_for("python")
    assert pin is not None
    for case in ("python-stdlib-demo", "python-stdlib-demo-survey"):
        golden = golden_replies.load("python", case)
        part = golden.portable(pin)
        assert not set(pin.sections) & set(part.digest["order"])
        assert not set(pin.facts) & set(part.full["facts"] if part.full else ())
        assert part.digest["sections"].keys() <= golden.digest["sections"].keys()


def test_the_pin_names_only_sections_that_the_collector_has() -> None:
    pin = golden_replies.pin_for("python")
    assert pin is not None
    assert set(pin.sections) <= {s.value for s in collect._SECTION_NAMES}
