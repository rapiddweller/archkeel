# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-11 architecture demo catalog: the single source read by the test and by markdown().

Every named `Variant` maps a copy of the clean `fixtures/F-architecture` shop sample to the
exact rule ids, `DiagnosticCode` and `DiagnosticKind` values `validate` and `report` must
produce. Rows that run on the sample apply file overlays; rows that compare two observations
or record a declaration Archkeel never enforces cite existing evidence instead.

Regenerate `docs/architecture-demo.md` from the repository root with:

    python -m fixtures.architecture_demo --markdown
"""

from __future__ import annotations

import sys
import textwrap
from pathlib import Path

from fixtures.demo_catalog_check import VARIANTS as _CHECK_PROTOCOL_VARIANTS
from fixtures.demo_catalog_check_regressions import VARIANTS as _CHECK_REGRESSION_VARIANTS
from fixtures.demo_catalog_constructs import VARIANTS as _CONSTRUCT_VARIANTS
from fixtures.demo_catalog_dependencies import VARIANTS as _DEPENDENCY_VARIANTS
from fixtures.demo_catalog_evidence import VARIANTS as _EVIDENCE_VARIANTS
from fixtures.demo_catalog_interfaces import VARIANTS as _INTERFACE_VARIANTS
from fixtures.demo_catalog_showcase import VARIANTS as _SHOWCASE_VARIANTS
from fixtures.demo_catalog_support import Variant
from fixtures.demo_catalog_types import VARIANTS as _TYPE_VARIANTS
from fixtures.demo_catalog_validation import VARIANTS as _VALIDATION_VARIANTS

CATALOG: tuple[Variant, ...] = (
    *_SHOWCASE_VARIANTS,
    *_CONSTRUCT_VARIANTS,
    *_DEPENDENCY_VARIANTS,
    *_INTERFACE_VARIANTS,
    *_TYPE_VARIANTS,
    *_VALIDATION_VARIANTS,
    *_CHECK_PROTOCOL_VARIANTS,
    *_CHECK_REGRESSION_VARIANTS,
    *_EVIDENCE_VARIANTS,
)

_INTRO = (
    "Generated from `fixtures/architecture_demo.py`'s `CATALOG`. Every checkable item in the "
    "decision records under `docs/architecture/decisions/` (indexed by "
    "`docs/architecture/archkeel.md`, AD-11) has one row below: a named variant, the "
    "rule ids and diagnostic codes (AD-12) it must produce, and either the shop sample "
    "files it changes or the existing evidence that demonstrates it instead. Regenerate "
    "with `python -m fixtures.architecture_demo --markdown`."
)
_SHOWCASE_NOTE = (
    "The `showcase` row below (`tour`) is the default demo view: it applies many overlays "
    "at once so one run shows many violations together; every other row isolates one item."
)


def _demo_type(variant: Variant) -> str:
    """Name each row's demo kind: what it runs, not what it changes."""
    if variant.check is not None:
        return "check run"
    if variant.evidence is not None:
        return "tested only"
    return "validate/report run"


def markdown() -> str:
    """Render docs/architecture-demo.md from CATALOG."""
    lines = [
        "# Architecture demo catalog",
        "",
        *textwrap.wrap(_INTRO, width=100, break_long_words=False, break_on_hyphens=False),
        "",
        *textwrap.wrap(_SHOWCASE_NOTE, width=100, break_long_words=False, break_on_hyphens=False),
        "",
        "| Section | Item | Variant | Demo | Rule ids | Diagnostic codes | Evidence / files |",
        "|---|---|---|---|---|---|---|",
    ]
    for variant in CATALOG:
        violations = ", ".join(variant.expected_violations) or "-"
        codes = ", ".join(variant.expected_codes) or "-"
        reference = variant.evidence or ", ".join(sorted(variant.files)) or "clean sample"
        lines.append(
            f"| {variant.section} | {variant.item} | {variant.id} | {_demo_type(variant)} | "
            f"{violations} | {codes} | {reference} |"
        )
    return "\n".join(lines) + "\n"


def main(argv: list[str]) -> int:
    if argv != ["--markdown"]:
        print("usage: python -m fixtures.architecture_demo --markdown", file=sys.stderr)
        return 2
    text = markdown()
    (Path(__file__).resolve().parent.parent / "docs/architecture-demo.md").write_text(text)
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
