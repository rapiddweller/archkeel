# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The closed code lists of the report v2 payload (AD-361).

A code is the position of a value in its list. A new value is appended and never inserted.
`schema/report-2.0.schema.json` holds the same lists as `x-codes`; a test checks that both agree.
"""

from __future__ import annotations

from typing import Final

SCHEMA_VERSION: Final = "2.0.0"
MAX_BYTES: Final = 8_000_000
CROSSING_CAP: Final = 200
CARRIER_CAP: Final = 6
DECL_CHARS: Final = 72
HUB_ABSOLUTE: Final = 10
HUB_RELATIVE_PERMILLE: Final = 200
ABSENT: Final = -1

LEVEL: Final = ("system", "package", "component", "module")
KIND: Final = (
    "struct",
    "enum",
    "trait",
    "class",
    "interface",
    "type_alias",
    "constant",
    "function",
    "method",
    "macro",
    "variable",
    "component",
    "static",
    "module",
    "unknown",
)
VIS: Final = ("public", "package", "private", "unknown")
MEASURE_STATE: Final = ("measured", "unknown", "undeclared", "not_applicable")
VERDICT: Final = ("none", "within", "over")
EDGE_TARGET: Final = ("no_target", "declared", "undeclared", "forbidden")
FINDING_KIND: Final = (
    "fan_in_hub",
    "fan_out_hub",
    "cycle",
    "violation",
    "api_outside_list",
    "over_budget",
    "unused_requires",
)
DISPOSITION: Final = ("ranked", "declared", "context")
REASON: Final = (
    "open_question",
    "kernel",
    "orchestrator",
    "crate_facade",
    "test_only",
    "rule_passes",
    "left_declaration",
)
MEASURE: Final = (
    "R.clear",
    "R.owned",
    "R.stated",
    "R.size",
    "I.declared",
    "I.api",
    "I.surface",
    "D.resolved",
    "D.types",
    "D.signatures",
    "D.declared",
    "E.known",
    "E.parsed",
    "E.excluded",
)
GAP: Final = (
    "G-CODE-LINES",
    "G-SIGNATURES",
    "G-ORIGIN",
    "G-USES",
    "G-PUBLIC-API",
    "G-BOUNDARY-TYPES",
    "G-BUDGETS",
    "G-TREND",
    "G-EXCLUDED",
    "G-NO-CONTRACT",
    "G-CONTRACT-LINES",
    "G-ROLES",
)
RELATION: Final = (
    "imports",
    "reexports",
    "variants",
    "calls",
    "references",
    "implements",
    "uses_type",
    "fields",
    "signatures",
    "code_lines",
    "contract_lines",
)
# The relations that this payload version does not carry. The page shows each one as
# "not collected yet". A producer that adds a table removes its relation from this list.
NOT_CARRIED: Final = (
    "calls",
    "references",
    "implements",
    "uses_type",
    "fields",
    "signatures",
    "code_lines",
    "contract_lines",
)
RULE_VERDICT: Final = ("PASS", "FAIL", "UNKNOWN", "DECLARATION")
RULE_REASON: Final = (
    "evaluated",
    "violations",
    "scope_incomplete",
    "no_receipt",
    "undecided",
    "declaration",
    "ownership_blocker",
)
PERMISSION: Final = ("allowed", "forbidden", "undecided")
UNKNOWN_SOURCE: Final = ("record", "diagnostic", "run")
# The record kinds of the unknowns section, then the diagnostic kinds of the run result, then
# `no_target` for a run without Target. `other` keeps a kind outside this list visible.
UNKNOWN_REASON: Final = (
    "collection_gap",
    "source_resolution_gap",
    "SyntaxError",
    "TooDeepError",
    "UnicodeDecodeError",
    "UnsupportedDeclaration",
    "boundary_type_limit",
    "boundary_type_position",
    "call_argument_limit",
    "call_owner_limit",
    "context_alias_limit",
    "dynamic_call_limit",
    "dynamic_dependency_limit",
    "dynamic_import_limit",
    "interface_symbol_limit",
    "private_attribute_access_limit",
    "uml_assessment_unavailable",
    "uml_conformance",
    "missing_tool",
    "timeout",
    "parse_error",
    "unresolved_import",
    "not_examined",
    "incomplete_scan",
    "scope_empty",
    "rule_without_subjects",
    "rule_unsupported_by_profile",
    "runtime_mismatch",
    "incomparable_runtime",
    "contract_invalid",
    "existing_files",
    "filter_unknown",
    "no_target",
    "other",
)
# A diagnostic of these kinds revokes the proofs, so a violation of an incomplete run is no FAIL.
REVOKING: Final = frozenset({"runtime_mismatch", "incomparable_runtime", "contract_invalid"})
LANGUAGE_OF: Final = {
    "archkeel-python-analyzer": "python",
    "archkeel-dart-analyzer": "dart",
    "archkeel-typescript-imports": "typescript",
    "archkeel-rust-imports": "rust",
}
DATA_KINDS: Final = frozenset({"struct", "enum", "type_alias", "constant"})


def code(values: tuple[str, ...], value: str) -> int:
    """Return the code of one value of a closed list."""
    return values.index(value)


def reason_code(kind: str) -> int:
    """Return the unknown reason code of a kind; a kind outside the list is `other`."""
    return code(UNKNOWN_REASON, kind if kind in UNKNOWN_REASON else "other")
