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


def test_the_story_runs_clean_then_measured_then_unknown_then_refused(printed: list[str]) -> None:
    assert printed == [
        "clean: every rule decided every import",
        "  dart-clean               PASS",
        "measured violations",
        "  dart-forbidden-dart-io   FAIL  rules: DEP-DOMAIN-NO-DART-IO",
        "  dart-complete-requires   FAIL  rules: REQUIRES-COMPLETE",
        "  dart-component-cycle     FAIL  rules: COMPONENT-NO-CYCLES, REQUIRES-COMPLETE",
        "  dart-complete-assignment FAIL  rules: ASSIGNMENT-COMPLETE, ROOT-LAYOUT",
        "  dart-external-scope      FAIL  rules: EXTERNAL-HTTP-DATA",
        "  dart-interface-show      FAIL  rules: INTERFACE-BOUNDARY",
        f"  dart-tour                FAIL  rules: {_TOUR_RULES}  unknown: interface_symbol_limit",
        "not measurable -> UNKNOWN, counted, never PASS",
        "  dart-interface-unknown   UNKNOWN  unknown: interface_symbol_limit",
        "unsupported or unreadable -> refused with exit 2",
        "  dart-unsupported-rule    exit 2 rule_unsupported_by_profile",
        "  dart-unsupported-budget  exit 2 rule_unsupported_by_profile",
        "  dart-unreadable-header   exit 2 parse_error",
        "",
        "What the directives decide is PASS or FAIL. The rest is UNKNOWN or refused.",
    ]


def test_an_unknown_beside_violations_is_still_listed(printed: list[str]) -> None:
    """A violation decides the verdict, and the undecided position does not vanish behind it."""
    (tour,) = [line for line in printed if line.lstrip().startswith("dart-tour ")]
    assert "FAIL" in tour
    assert tour.endswith("unknown: interface_symbol_limit")
