# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-11 class_b, class_c and class_d rows that cannot run on the sample.

The remaining class_b rows are genuinely undemonstrable, not merely uncatalogued: raising
coverage_failures or unknowns makes `Measurements.__post_init__` or `evaluate_expectation`
raise instead of returning a typed FAIL, and coverage_must_pass is a fixed guardrail key, never
a comparable dimension. See `fixtures/demo_catalog_check.py` for every scalar and guardrail
dimension that a `check` demo can fire, and its protocol rows for `git_order`/`host_order`.
class_c (declarations Archkeel decodes but never enforces) and class_d (not implemented) each
cite the existing test or fixture that demonstrates them instead.
"""

from __future__ import annotations

from dataclasses import fields as dataclass_fields

from archkeel.ir.model import ContractDeclarations
from fixtures.demo_catalog_support import Variant

_CLASS_B_ROWS: tuple[Variant, ...] = (
    Variant(
        id="class-b-scalar-coverage-failures",
        section="class_b",
        item="SCALARS:coverage_failures",
        summary="A scan failure that would raise coverage_failures also fails "
        'Measurements.__post_init__ ("scan must be complete"), so check never returns a '
        "typed FAIL for it; only a crash. Exercised by the measurement tests instead.",
        files={},
        expected_violations=(),
        expected_codes=(),
        evidence="tests/test_ratchets.py",
    ),
    Variant(
        id="class-b-guardrail-unknowns",
        section="class_b",
        item="GUARDRAIL_DIMENSIONS:unknowns",
        summary="The two structural analysis-limit records are fixed in kind and subjects, so "
        "code-only changes can only change their data, never add a new one; a genuinely new "
        "unknowns record needs a scan failure or a rule losing every subject, both of which "
        "fail coverage and crash measurement before the guardrail is compared. Exercised by "
        "the expectation tests instead.",
        files={},
        expected_violations=(),
        expected_codes=(),
        evidence="tests/test_expectation.py",
    ),
    Variant(
        id="class-b-guardrail-dependency-edges",
        section="class_b",
        item="GUARDRAIL_DIMENSIONS:dependency_edges",
        summary="Every check demo in this catalog declares its whole observed delta, so none "
        "of them can show an *undeclared* added edge failing; that needs a declaration built "
        "to omit one, which only the expectation tests construct. The check-run rows still "
        "exercise the dimension itself: adding any import creates a new module-level edge, "
        "declared like the rest of that row's delta (AD-44).",
        files={},
        expected_violations=(),
        expected_codes=(),
        evidence="tests/test_expectation.py",
    ),
    Variant(
        id="class-b-coverage-must-pass",
        section="class_b",
        item="coverage_must_pass",
        summary="coverage_must_pass is a fixed guardrail key, not a comparable dimension: a "
        "failing scan makes evaluate_expectation raise before any guardrail is compared. "
        "Exercised only by the expectation tests.",
        files={},
        expected_violations=(),
        expected_codes=(),
        evidence="tests/test_expectation.py",
    ),
)

_SUPERSEDED_DECLARATIONS = {"public_api", "public_api_provenance"}
_CLASS_C_ROWS: tuple[Variant, ...] = tuple(
    Variant(
        id=f"class-c-{field.name.replace('_', '-')}",
        section="class_c",
        item=f"ContractDeclarations.{field.name}",
        summary=(
            "AD-9 supersedes public_api with per-component public interfaces, so the clean "
            "sample intentionally leaves this field empty; see docs/rules.md."
            if field.name in _SUPERSEDED_DECLARATIONS
            else f"The clean sample contract populates declarations.{field.name}."
        ),
        files={},
        expected_violations=(),
        expected_codes=(),
        evidence=(
            "docs/rules.md"
            if field.name in _SUPERSEDED_DECLARATIONS
            else "fixtures/F-architecture/architecture-contract.json"
        ),
    )
    for field in dataclass_fields(ContractDeclarations)
)

_CLASS_D_ROWS: tuple[Variant, ...] = (
    Variant(
        id="class-d-review-claims",
        section="class_d",
        item="review_claims",
        summary="Class D review claims are planned but not implemented: no contract field or "
        "diagnostic binds a review verdict to an evidence digest yet, so no overlay changes "
        "the clean sample's findings.",
        files={},
        expected_violations=(),
        expected_codes=(),
        evidence="docs/rules.md",
    ),
    Variant(
        id="class-d-oversized-inside",
        section="class_d",
        item="oversized_inside",
        summary="A component larger than its own level is named in the report and never gated "
        "on, so no overlay changes the clean sample's findings; the claim is measured on "
        "Archkeel itself, where it names analyzer, check and ir.",
        files={},
        expected_violations=(),
        expected_codes=(),
        evidence="docs/rules.md",
    ),
    Variant(
        id="class-d-type-fanin",
        section="class_d",
        item="type_fanin",
        summary="Which types cross the most component boundaries is named in the report and "
        "never gated on, so no overlay changes the clean sample's findings; measured on the "
        "clean shop sample itself, the claim names Order and str crossing two component pairs "
        "each, and on Archkeel itself, object (ir.codec's own JSON boundary) crosses four.",
        files={},
        expected_violations=(),
        expected_codes=(),
        evidence="docs/rules.md",
    ),
)

VARIANTS: tuple[Variant, ...] = (
    *_CLASS_B_ROWS,
    *_CLASS_C_ROWS,
    *_CLASS_D_ROWS,
)
