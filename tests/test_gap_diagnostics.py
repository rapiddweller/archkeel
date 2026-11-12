# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-336: a coverage gap gives a diagnostic kind that names its real cause."""

import contextlib
import io
import json
import subprocess
from pathlib import Path
from typing import Any

import pytest
from command_result_12 import render
from jsonschema import Draft202012Validator
from test_result_schema import _validator

from archkeel.check.evaluation.unknown_imports import unknown_import_failure
from archkeel.check.gap_diagnostics import gap_diagnostic
from archkeel.cli import main
from archkeel.ir.facts import Record
from archkeel.ir.facts_codec import classified, parse_record
from archkeel.ir.model import DiagnosticKind, EvidenceClass
from archkeel.ir.profiles import Language, is_test_source
from archkeel.ir.protocol import GapTitle

ROOT = Path(__file__).parents[1]
# The titles are written in the loop of the imports and in the search of the target of an import.
_RUST = tuple(ROOT / "native/typescript/src" / name for name in ("imports.rs", "import_target.rs"))
TS, PY, DART = Language.TYPESCRIPT, Language.PYTHON, Language.DART
PARSE, UNRESOLVED = DiagnosticKind.PARSE_ERROR, DiagnosticKind.UNRESOLVED_IMPORT
NOT_EXAMINED, INCOMPLETE = DiagnosticKind.NOT_EXAMINED, DiagnosticKind.INCOMPLETE_SCAN


def _gap(kind: str, title: str, area: str = "source") -> Record:
    return parse_record(
        classified(
            item_id=f"UNKNOWN-{abs(hash((kind, title)))}",
            evidence_class=EvidenceClass.UNKNOWN,
            area=area,
            kind=kind,
            title=title,
            subjects=["app.main"],
            data={},
        )
    )


RES, COLLECT, COV = "source_resolution_gap", "collection_gap", "analysis_coverage"

# Every gap title template that a producer emits, shaped as the producer emits it.
# The native TypeScript collector (imports.rs):
_TYPESCRIPT = [
    (TS, RES, f"{GapTitle.NO_MODULE}react", "source", UNRESOLVED),
    (TS, RES, f"{GapTitle.UNIDENTIFIED_PACKAGE}lodash", "source", UNRESOLVED),
    (
        TS,
        RES,
        f"Script global console{GapTitle.UNPUBLISHED_GLOBAL}",
        "source",
        NOT_EXAMINED,
    ),
    (TS, RES, GapTitle.SCRIPT_GLOBALS_UNEXAMINED, "source", NOT_EXAMINED),
    (TS, RES, "Local alias runtime conditions are not proven: @app/common", "source", INCOMPLETE),
    (TS, RES, "Bundler mode requires moduleResolution bundler", "source", INCOMPLETE),
    (TS, RES, "Computed import cannot be resolved", "source", INCOMPLETE),
    (TS, RES, "Unproven or shadowed require call", "source", INCOMPLETE),
    (TS, RES, "Resolution mode override is not observed: ./a", "source", INCOMPLETE),
    (TS, RES, "Local dependency outside selected source scope: a.ts", "source", INCOMPLETE),
    (TS, RES, "Production import targets excluded test source: a.test.ts", "source", INCOMPLETE),
    (TS, RES, "Script namespace effects are not statically bounded", "source", INCOMPLETE),
    (TS, RES, "Script namespace member a.b is not statically published", "source", INCOMPLETE),
    (
        TS,
        RES,
        "Escaped or computed global host dependency is not statically bounded",
        "source",
        INCOMPLETE,
    ),
    (TS, RES, "Factory result uses are not statically bounded", "source", INCOMPLETE),
    (TS, COLLECT, f"{GapTitle.SYNTAX_ERROR}a.ts: unparseable construct at line 3", "source", PARSE),
    (TS, COLLECT, f"{GapTitle.UNREADABLE_SOURCE}: a.ts", "source", INCOMPLETE),
    (TS, COLLECT, "Source path has no module identity: a.ts", "source", INCOMPLETE),
    (TS, COLLECT, "Unproven require member use", "source", INCOMPLETE),
]
# Python collector (analyzer/python/source.py, explore_scope.py): the kind of a file failure is
# the name of the exception class.
_PYTHON = [
    (PY, "SyntaxError", f"a.py:3{GapTitle.FILE_FAILURE}", COV, PARSE),
    (PY, "UnicodeDecodeError", f"a.py:1{GapTitle.FILE_FAILURE}", COV, PARSE),
    (PY, "OSError", f"a.py:1{GapTitle.FILE_FAILURE}", COV, PARSE),
    (PY, RES, "Production import targets excluded test source a.b", "source", INCOMPLETE),
    (PY, COLLECT, "No production source in the configured scope", "source", INCOMPLETE),
]
# Dart collector (analyzer/dart/collect.py, resolve.py, snapshot.py): a structured kind.
_DART = [
    (DART, "SyntaxError", f"a.dart:1{GapTitle.FILE_FAILURE}: syntax errors", COV, PARSE),
    (DART, "invalid_encoding", f"a.dart:1{GapTitle.FILE_FAILURE}: bad bytes", COV, PARSE),
    (DART, "ImportError", f"a.dart:1{GapTitle.FILE_FAILURE}: unreadable URI 'x'", COV, UNRESOLVED),
    (DART, "UnsupportedDeclaration", f"a.dart:1{GapTitle.FILE_FAILURE}: x", COV, NOT_EXAMINED),
    (DART, "UnsupportedMember", f"a.dart:1{GapTitle.FILE_FAILURE}: x", COV, NOT_EXAMINED),
    (DART, "UnsupportedParameter", f"a.dart:1{GapTitle.FILE_FAILURE}: x", COV, NOT_EXAMINED),
    (DART, "DirectiveError", f"a.dart:1{GapTitle.FILE_FAILURE}: import 'x' fails", COV, INCOMPLETE),
    (DART, "PartError", f"a.dart:1{GapTitle.FILE_FAILURE}: no owner", COV, INCOMPLETE),
    (DART, "PartOwnershipConflict", f"a.dart:1{GapTitle.FILE_FAILURE}: x", COV, INCOMPLETE),
    (DART, "SdkConstraintError", f"pubspec.yaml:1{GapTitle.FILE_FAILURE}: x", COV, INCOMPLETE),
    (DART, "LanguageVersionError", f"a.dart:1{GapTitle.FILE_FAILURE}: x", COV, INCOMPLETE),
    (DART, "DuplicateDeclaration", f"a.dart:1{GapTitle.FILE_FAILURE}: x", COV, INCOMPLETE),
    (
        DART,
        RES,
        f"a.dart:1{GapTitle.FILE_FAILURE}: constructor owner is unresolved",
        COV,
        INCOMPLETE,
    ),
    (DART, "DartModuleCollision", f"a.dart{GapTitle.FILE_FAILURE}: x", COV, INCOMPLETE),
    (DART, "PubspecMissing", f"pubspec.yaml{GapTitle.FILE_FAILURE}: x", COV, INCOMPLETE),
]
# Host (check/observation.py, check/evaluation): gaps without a language.
_HOST = [
    (language, kind, title, COV, INCOMPLETE)
    for language in (TS, PY, DART)
    for kind, title in (
        ("git_metadata_failure", "Git metadata could not be read"),
        ("inside_contract_incomplete", "Inside contract is incomplete"),
        ("declaration_source_unavailable", "Declaration source is unavailable"),
        ("construct_selector_unknown", "Construct selector is unknown"),
        ("protocol_declaration_limit", "Protocol declaration limit"),
    )
]
_CASES = [
    *_TYPESCRIPT,
    *_PYTHON,
    *_DART,
    *_HOST,
]


@pytest.mark.parametrize(
    ("language", "kind", "title", "area", "expected"),
    _CASES,
    ids=[f"{case[0].value}-{case[1]}-{case[2][:30]}" for case in _CASES],
)
def test_each_producer_template_gives_its_kind(
    language: Language, kind: str, title: str, area: str, expected: DiagnosticKind
) -> None:
    assert gap_diagnostic(_gap(kind, title, area), language)[0] is expected


def test_the_unresolved_import_failure_of_core_is_an_unresolved_import() -> None:
    item = {
        "id": "IMPORT-1",
        "subjects": ["app.main"],
        "evidence_ids": [],
        "data": {"source_module": "app.main"},
    }
    raw = unknown_import_failure(item, f"{GapTitle.NO_MODULE}react")  # type: ignore[arg-type]
    assert gap_diagnostic(parse_record(raw), TS)[0] is UNRESOLVED


_REMEDY_WORDS = {
    PARSE: "syntax",
    UNRESOLVED: "relative path",
    NOT_EXAMINED: "does not prove",
    INCOMPLETE: "stays incomplete",
}


@pytest.mark.parametrize("kind", list(_REMEDY_WORDS))
def test_each_kind_has_its_own_remedy(kind: DiagnosticKind) -> None:
    sample = next(case for case in _CASES if case[4] is kind and case[0] is TS)
    remedy = gap_diagnostic(_gap(sample[1], sample[2], sample[3]), sample[0])[1]
    assert _REMEDY_WORDS[kind].lower() in remedy.lower()
    others = {
        gap_diagnostic(_gap(case[1], case[2], case[3]), case[0])[1]
        for case in _CASES
        if case[4] is not kind and case[4] is not PARSE
    }
    assert remedy not in others


def test_an_unreadable_file_has_a_specific_remedy() -> None:
    kind, remedy = gap_diagnostic(_gap(COLLECT, f"{GapTitle.UNREADABLE_SOURCE}: a.ts"), TS)
    assert kind is INCOMPLETE
    assert "UTF-8" in remedy


def test_an_unknown_reason_uses_the_neutral_fallback() -> None:
    kind, remedy = gap_diagnostic(_gap("future_gap_kind", "A reason no collector emits"), TS)
    assert kind is INCOMPLETE
    assert "stays incomplete" in remedy


_RUST_TITLES = (
    GapTitle.NO_MODULE,
    GapTitle.UNIDENTIFIED_PACKAGE,
    GapTitle.SYNTAX_ERROR,
)  # The script gap is no longer written (AD-352); the host keeps the mapping for older replies.


@pytest.mark.parametrize("title", _RUST_TITLES)
def test_the_native_collector_emits_the_title_that_the_host_matches(title: str) -> None:
    assert any(title in path.read_text(encoding="utf-8") for path in _RUST)


def test_the_embedded_copies_of_schema_12_equal_a_rebuild_from_the_published_schemas() -> None:
    schema_dir = ROOT / "schema"
    published = (schema_dir / "command-result-12.0.schema.json").read_text(encoding="utf-8")
    assert render(schema_dir) == published


def _diagnostic_validator(name: str) -> Draft202012Validator:
    base = _validator(name)
    anchor = "urn:archkeel:command-result:12.0.0#/$defs/diagnostic"
    return base.evolve(schema={"$ref": anchor if "12.0" in name else _legacy_anchor()})


def _legacy_anchor() -> str:
    return "urn:archkeel:command-result:6.0.0#/$defs/diagnostic"


def _diagnostic(kind: str) -> dict[str, str]:
    return {"kind": kind, "subject": "a", "unknown_claim": "b", "remedy": "c"}


def test_schema_12_lists_the_new_kinds_and_keeps_every_old_kind() -> None:
    new = _diagnostic_validator("command-result-12.0.schema.json")
    old = _diagnostic_validator("command-result.schema.json")
    for kind in ("unresolved_import", "not_examined", "incomplete_scan"):
        assert new.is_valid(_diagnostic(kind))
        assert not old.is_valid(_diagnostic(kind))
    for kind in ("parse_error", "timeout", "missing_tool", "filter_unknown"):
        assert new.is_valid(_diagnostic(kind))
        assert old.is_valid(_diagnostic(kind))


def test_a_result_with_a_new_kind_declares_12_and_an_old_result_keeps_11(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    (root / "src").mkdir(parents=True)
    (root / "tsconfig.json").write_text("{}\n", encoding="utf-8")
    (root / "src" / "a.ts").write_text(
        "import x from 'nonexistent-package';\nexport const a = x;\n", encoding="utf-8"
    )
    for git in (["init", "-q"], ["add", "."], ["commit", "-qm", "x"]):
        subprocess.run(
            ["git", "-c", "user.name=t", "-c", "user.email=t@t", *git], cwd=root, check=True
        )
    out = tmp_path / "out"
    args = ["explore", "--root", str(root), "--language", "typescript", "--source", "src"]
    args += ["--namespace", "app", "--tsconfig", "tsconfig.json", "--output", str(out), "--json"]
    stream = io.StringIO()
    with contextlib.redirect_stdout(stream):
        assert main(args) == 2
    result: dict[str, Any] = json.loads(stream.getvalue())
    kinds = {item["kind"] for item in result["diagnostics"]}
    assert "unresolved_import" in kinds
    assert "parse_error" not in kinds
    assert _validator("command-result-12.0.schema.json").is_valid(result)
    assert not _validator("command-result-11.0.schema.json").is_valid(result)
    old = {
        **result,
        "diagnostics": [{**item, "kind": "parse_error"} for item in result["diagnostics"]],
    }
    assert _validator("command-result-11.0.schema.json").is_valid(old)
    assert _validator("command-result-12.0.schema.json").is_valid(old)


def test_a_dart_import_error_is_unresolved_even_with_a_neutral_title() -> None:
    """The Dart kind decides the diagnostic; the title alone would give incomplete_scan."""
    title = "Dart file has a neutral title"
    assert gap_diagnostic(_gap("ImportError", title, COV), DART)[0] is UNRESOLVED
    assert gap_diagnostic(_gap("other_kind", title, COV), DART)[0] is INCOMPLETE


@pytest.mark.parametrize(
    ("path", "language"), [("pkg/test_a.py", "python"), ("src/a.spec.ts", "typescript")]
)
def test_is_test_source_accepts_the_plain_string_language(path: str, language: str) -> None:
    """The host passes the language by value, so the comparison must use ==, not is."""
    assert is_test_source(path, Language(language))
    assert is_test_source(path, language)  # type: ignore[arg-type]


@pytest.mark.parametrize("language", ["dart", "python", "typescript"])
def test_the_language_can_be_the_plain_string_of_the_profile(language: str) -> None:
    """The host passes the language by value; a Dart syntax error must stay a parse error."""
    kind = "SyntaxError" if language == "dart" else COLLECT
    title = (
        f"a.py:1{GapTitle.FILE_FAILURE}" if language == "python" else f"{GapTitle.SYNTAX_ERROR}a"
    )
    area = COV if language != "typescript" else "source"
    assert gap_diagnostic(_gap(kind, title, area), Language(language))[0] is PARSE
    assert gap_diagnostic(_gap(kind, title, area), language)[0] is PARSE  # type: ignore[arg-type]
