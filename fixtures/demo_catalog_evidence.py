# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-11 class_b, protocol, class_c and class_d rows: evidence-anchored, not run on the sample.

These compare two observations (class_b, protocol) or are declarations Archkeel decodes but
never enforces (class_c) or has not implemented (class_d), so no single-repository overlay
demonstrates them; each row cites the existing test or fixture that does.
"""

from __future__ import annotations

from dataclasses import fields as dataclass_fields

from archkeel.check.expectation import GUARDRAIL_DIMENSIONS
from archkeel.ir.measurements import SCALARS
from archkeel.ir.model import ContractDeclarations
from fixtures.demo_catalog_support import Variant

_SCALAR_EVIDENCE = "tests/test_ratchets.py"
_CLASS_B_ROWS: tuple[Variant, ...] = (
    *(
        Variant(
            id=f"class-b-scalar-{name}",
            section="class_b",
            item=f"SCALARS:{name}",
            summary=f"The {name} ratchet scalar compares an accepted and a candidate "
            "observation; not a single-observation overlay.",
            files={},
            expected_violations=(),
            expected_codes=(),
            evidence="docs/rules.md" if name == "coverage_failures" else _SCALAR_EVIDENCE,
        )
        for name in SCALARS
    ),
    Variant(
        id="class-b-unresolved-ratio",
        section="class_b",
        item="unresolved_ratio",
        summary="The cross-multiplied unresolved-call ratio is demonstrated by demo case A, "
        "whose calls_unresolved rises against calls_total.",
        files={},
        expected_violations=(),
        expected_codes=(),
        evidence="fixtures/reproduce_milestone1.py",
    ),
    *(
        Variant(
            id=f"class-b-guardrail-{name}",
            section="class_b",
            item=f"GUARDRAIL_DIMENSIONS:{name}",
            summary=f"The {name} guardrail dimension compares accepted and candidate "
            "observations; exercised by the expectation tests.",
            files={},
            expected_violations=(),
            expected_codes=(),
            evidence="tests/test_expectation.py",
        )
        for name in GUARDRAIL_DIMENSIONS
    ),
    Variant(
        id="class-b-coverage-must-pass",
        section="class_b",
        item="coverage_must_pass",
        summary="coverage_must_pass is a fixed guardrail key, not a comparable dimension; "
        "exercised only by the expectation tests.",
        files={},
        expected_violations=(),
        expected_codes=(),
        evidence="tests/test_expectation.py",
    ),
)

_PROTOCOL_ROWS: tuple[Variant, ...] = (
    Variant(
        id="protocol-git-order",
        section="protocol",
        item="git_order",
        summary="check_git_order's parent, changed-path and ancestry predicates are "
        "exercised directly against real Git history.",
        files={},
        expected_violations=(),
        expected_codes=(),
        evidence="tests/test_git_lock.py",
    ),
    Variant(
        id="protocol-host-order",
        section="protocol",
        item="host_order",
        summary="Demo case B publishes the expectation only after the first candidate "
        "submission, producing the ordering failure at exit code 1; its companion run "
        "with the host branch missing shows the exit 2 diagnostic path.",
        files={},
        expected_violations=(),
        expected_codes=(),
        evidence="fixtures/reproduce_milestone1.py",
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
)

VARIANTS: tuple[Variant, ...] = (
    *_CLASS_B_ROWS,
    *_PROTOCOL_ROWS,
    *_CLASS_C_ROWS,
    *_CLASS_D_ROWS,
)
