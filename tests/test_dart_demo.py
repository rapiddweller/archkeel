# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""`make demo-dart` prints what the Dart rows' real runs answer, grouped as AD-97's story."""

import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
_TOUR_RULES = (
    "ASSIGNMENT-COMPLETE, COMPONENT-NO-CYCLES, DEP-DOMAIN-NO-DART-IO, EXTERNAL-HTTP-DATA, "
    "INTERFACE-BOUNDARY, REQUIRES-COMPLETE, ROOT-LAYOUT"
)


@pytest.fixture(scope="module")
def printed() -> list[str]:
    # Under a parent `make` (as in `make check`) a nested make announces its directory.
    run = subprocess.run(
        ["make", "--no-print-directory", "demo-dart"], cwd=ROOT, capture_output=True, text=True
    )
    assert run.returncode == 0, (run.stdout, run.stderr)
    return run.stdout.splitlines()


def test_the_story_separates_violations_unknowns_and_refusals(printed: list[str]) -> None:
    assert printed == [
        "measured violations",
        "  dart-forbidden-dart-io   FAIL  rules: DEP-DOMAIN-NO-DART-IO  "
        "unknown rules: COMPONENT-NO-CYCLES",
        "  dart-complete-requires   FAIL  rules: REQUIRES-COMPLETE  "
        "unknown rules: COMPONENT-NO-CYCLES",
        "  dart-component-cycle     FAIL  rules: COMPONENT-NO-CYCLES, REQUIRES-COMPLETE",
        "  dart-complete-assignment FAIL  rules: ASSIGNMENT-COMPLETE, ROOT-LAYOUT  "
        "unknown rules: COMPONENT-NO-CYCLES, INTERFACE-BOUNDARY, REQUIRES-COMPLETE",
        "  dart-external-scope      FAIL  rules: EXTERNAL-HTTP-DATA  "
        "unknown rules: COMPONENT-NO-CYCLES",
        "  dart-interface-show      FAIL  rules: INTERFACE-BOUNDARY  "
        "unknown rules: COMPONENT-NO-CYCLES",
        "  dart-nested-interface-mixed FAIL  rules: domain:core:INTERFACE  "
        "unknown rules: COMPONENT-NO-CYCLES  "
        "unknown: interface_symbol_limit",
        f"  dart-tour                FAIL  rules: {_TOUR_RULES}  unknown: interface_symbol_limit",
        "incomplete rule proof -> UNKNOWN",
        "  dart-clean               UNKNOWN  unknown rules: COMPONENT-NO-CYCLES",
        "  dart-interface-unknown   UNKNOWN  unknown rules: COMPONENT-NO-CYCLES, "
        "INTERFACE-BOUNDARY  "
        "unknown: interface_symbol_limit",
        "  dart-nested-interface-unknown UNKNOWN  unknown rules: COMPONENT-NO-CYCLES, "
        "domain:core:INTERFACE  unknown: interface_symbol_limit",
        "  dart-nested-interface-show UNKNOWN  unknown rules: COMPONENT-NO-CYCLES, "
        "domain:core:INTERFACE",
        "  dart-nested-forbidden-symbol-unknown UNKNOWN  unknown rules: COMPONENT-NO-CYCLES, "
        "domain:core:NO-DRAFT  unknown: dependency_symbol_limit",
        "unsupported or unreadable -> refused with exit 2",
        "  dart-unsupported-rule    exit 2 rule_unsupported_by_profile",
        "  dart-unsupported-budget  exit 2 rule_unsupported_by_profile",
        "  dart-unreadable-header   exit 2 parse_error",
        "",
        "No violation is different from a complete PASS: unproven scope stays UNKNOWN.",
    ]


def test_an_unknown_beside_violations_is_still_listed(printed: list[str]) -> None:
    """A violation decides the verdict, and the undecided position does not vanish behind it."""
    (tour,) = [line for line in printed if line.lstrip().startswith("dart-tour ")]
    assert "FAIL" in tour
    assert tour.endswith("unknown: interface_symbol_limit")
