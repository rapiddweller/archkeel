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
EDGE_TARGET: Final = ("no_target", "declared", "undeclared")
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
)
RULE_VERDICT: Final = ("PASS", "FAIL", "UNKNOWN", "DECLARATION")
DATA_KINDS: Final = frozenset({"struct", "enum", "type_alias", "constant"})
CODE_LISTS: Final = {
    "Level": LEVEL,
    "Kind": KIND,
    "Vis": VIS,
    "MeasureState": MEASURE_STATE,
    "Verdict": VERDICT,
    "EdgeTarget": EDGE_TARGET,
    "FindingKind": FINDING_KIND,
    "Disposition": DISPOSITION,
    "Reason": REASON,
    "Measure": MEASURE,
    "Gap": GAP,
    "Relation": RELATION,
}


def code(values: tuple[str, ...], value: str) -> int:
    """Return the code of one value of a closed list."""
    return values.index(value)
