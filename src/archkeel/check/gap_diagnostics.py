# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Name the real cause of a coverage gap (AD-336). The kind never changes an exit code."""

from typing import Final

from archkeel.ir.facts import SOURCE_RESOLUTION_GAP_KIND, Record
from archkeel.ir.model import DiagnosticKind
from archkeel.ir.profiles import Language
from archkeel.ir.protocol import GapTitle

_UNRESOLVED_TITLES: Final = (GapTitle.NO_MODULE, GapTitle.UNIDENTIFIED_PACKAGE)

# The Dart collector names the gap by a structured kind (`ResolutionProblemKind`, `ConcernKind`).
_DART_KINDS: Final[dict[str, DiagnosticKind]] = {
    "SyntaxError": DiagnosticKind.PARSE_ERROR,
    "syntax_error": DiagnosticKind.PARSE_ERROR,
    "invalid_encoding": DiagnosticKind.PARSE_ERROR,
    "ImportError": DiagnosticKind.UNRESOLVED_IMPORT,
    "UnsupportedDeclaration": DiagnosticKind.NOT_EXAMINED,
    "UnsupportedMember": DiagnosticKind.NOT_EXAMINED,
    "UnsupportedParameter": DiagnosticKind.NOT_EXAMINED,
}

_SYNTAX_REMEDY: Final[dict[Language, str]] = {
    Language.PYTHON: "Inspect the reported failure using the declared target runtime; "
    "rerun after resolving its cause.",
    Language.TYPESCRIPT: "Correct the syntax of the reported TypeScript file and retry.",
    Language.DART: "Correct the syntax or the encoding of the reported Dart file and retry.",
    Language.RUST: "Correct the syntax of the reported Rust file and retry.",
}
_REMEDY: Final[dict[DiagnosticKind, str]] = {
    DiagnosticKind.UNRESOLVED_IMPORT: "Install the missing package, or correct the relative path, "
    "the file name or the path mapping, and scan again.",
    DiagnosticKind.NOT_EXAMINED: "The collector does not prove this fact yet, and a change in the "
    "project may not help; the scan stays incomplete.",
    DiagnosticKind.INCOMPLETE_SCAN: "Read the reported gap; the scan stays incomplete until the "
    "collector can prove this fact.",
}
_UNREADABLE_REMEDY: Final = (
    "Check that the file can be read, is UTF-8 text and is not too large; then scan again."
)


def gap_diagnostic(failure: Record, language: Language) -> tuple[DiagnosticKind, str]:
    """Return the diagnostic kind and the remedy for one coverage failure."""
    kind: str = failure.kind
    title: str = failure.title
    if title.startswith(GapTitle.UNREADABLE_SOURCE):
        return DiagnosticKind.INCOMPLETE_SCAN, _UNREADABLE_REMEDY
    found = _DART_KINDS.get(kind) if language == Language.DART else _by_title(failure, language)
    result = found or DiagnosticKind.INCOMPLETE_SCAN
    if result is DiagnosticKind.PARSE_ERROR:
        return result, _SYNTAX_REMEDY[language]
    return result, _REMEDY[result]


def _by_title(failure: Record, language: Language) -> DiagnosticKind | None:
    kind: str = failure.kind
    title: str = failure.title
    if title.startswith(GapTitle.SYNTAX_ERROR) or (
        language == Language.PYTHON
        and failure.area == "analysis_coverage"
        and title.endswith(GapTitle.FILE_FAILURE)
    ):
        return DiagnosticKind.PARSE_ERROR
    if kind != SOURCE_RESOLUTION_GAP_KIND:
        return None
    if title.startswith(_UNRESOLVED_TITLES):
        return DiagnosticKind.UNRESOLVED_IMPORT
    if title == GapTitle.SCRIPT_GLOBALS_UNEXAMINED or GapTitle.UNPUBLISHED_GLOBAL in title:
        return DiagnosticKind.NOT_EXAMINED
    return None
