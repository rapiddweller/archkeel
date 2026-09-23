# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-11 class_b rows: real `check` demos of each demonstrable ratchet scalar and guardrail
dimension, run through `fixtures.demo_catalog_check.build_and_run_check`.

A scalar and its paired guardrail dimension usually regress from the same event (a violation
also regresses the violations dimension, an underscore reach also regresses private_crossings),
so one overlay backs two catalog rows; see `tests/test_architecture_demo.py` for the dedupe.
"""

from __future__ import annotations

from collections.abc import Mapping

from fixtures.demo_catalog_constructs import VARIANTS as _CONSTRUCT_VARIANTS
from fixtures.demo_catalog_dependencies import VARIANTS as _DEPENDENCY_VARIANTS
from fixtures.demo_catalog_interfaces import VARIANTS as _INTERFACE_VARIANTS
from fixtures.demo_catalog_support import FIXTURE_DIR, HEADER, CheckExpectation, Variant


def _files_of(variants: tuple[Variant, ...], variant_id: str) -> Mapping[str, str | None]:
    """Reuse one class_a variant's overlay content instead of duplicating a probe module."""
    return next(variant for variant in variants if variant.id == variant_id).files


_VIOLATION_FILES = _files_of(_DEPENDENCY_VARIANTS, "class-a-forbidden-dependency-pair")
_VIOLATION = CheckExpectation(
    scenario="ordered",
    exit_code=1,
    expectation_fulfilled="FAIL",
    git_predicate="PASS",
    host_order="PASS",
    regressed_scalars=("violations",),
    # The new import is also a new module-level dependency_edges entry (AD-44), declared
    # alongside the violation itself.
    regressed_dimensions=("violations", "dependency_edges"),
)

_PRIVATE_CROSSING_FILES = _files_of(_INTERFACE_VARIANTS, "class-a-interface-boundary-underscore")
_PRIVATE_CROSSING = CheckExpectation(
    scenario="ordered",
    exit_code=1,
    expectation_fulfilled="FAIL",
    git_predicate="PASS",
    host_order="PASS",
    regressed_scalars=("violations", "private_crossings"),
    regressed_dimensions=("violations", "private_crossings"),
)
_PRIVATE_ATTRIBUTE_FILES = _files_of(_INTERFACE_VARIANTS, "class-a-private-attribute-untyped")
_PRIVATE_ATTRIBUTE = CheckExpectation(
    scenario="ordered",
    exit_code=1,
    expectation_fulfilled="FAIL",
    git_predicate="PASS",
    host_order="PASS",
    regressed_scalars=("untyped_private_accesses",),
    regressed_dimensions=("unknowns",),
)

# AD-92: widening a boundary parameter to a union leaves APP-TYPES-NOT-DICT one more position it
# cannot decide. The contract is an accepted policy input `check` refuses to see changed, so the
# regression has to come from code; a union adds no typing signal, so unknown_positions is the
# only measurement that moves.
_CLEAN_ORDERS = (FIXTURE_DIR / "shop/app/orders.py").read_text()
_UNDECIDED_FILES: Mapping[str, str | None] = {
    "shop/app/orders.py": _CLEAN_ORDERS.replace(
        "    description: str,\n", "    description: str | None,\n"
    ).replace("Line(description=description,", "Line(description=description or order_id,")
}
_UNDECIDED = CheckExpectation(
    scenario="ordered",
    exit_code=1,
    expectation_fulfilled="FAIL",
    git_predicate="PASS",
    host_order="PASS",
    regressed_scalars=("unknown_positions",),
    regressed_dimensions=(),
)

_CYCLE_FILES: Mapping[str, str | None] = {
    "shop/model/uses_render.py": HEADER
    + (
        '"""Cycle probe: model reaching into render, without touching the contract."""\n\n'
        "from __future__ import annotations\n\n"
        "from shop.render.text import render_order\n\n"
        "describe_order = render_order\n"
    )
}
_CYCLE = CheckExpectation(
    scenario="ordered",
    exit_code=1,
    expectation_fulfilled="FAIL",
    git_predicate="PASS",
    host_order="PASS",
    regressed_scalars=("violations", "cycle_edges"),
    # The new back-edge is also a new module-level dependency_edges entry (AD-44).
    regressed_dimensions=("violations", "cycles", "dependency_edges"),
)

_TYPING_FILES = _files_of(_CONSTRUCT_VARIANTS, "class-a-construct-type_ignore")
_TYPING = CheckExpectation(
    scenario="ordered",
    exit_code=1,
    expectation_fulfilled="FAIL",
    git_predicate="PASS",
    host_order="PASS",
    regressed_scalars=("violations", "typing_positions"),
    regressed_dimensions=("violations", "typing_signals"),
)

_UNRESOLVED_FILES: Mapping[str, str | None] = {
    "shop/app/probe_unresolved.py": HEADER
    + (
        '"""Unresolved-call probe: an isolated regression, no rule fires."""\n\n'
        "from __future__ import annotations\n\n\n"
        "def probe() -> None:\n"
        "    _totally_unbound_shop_demo_symbol()\n"
    )
}
_UNRESOLVED = CheckExpectation(
    scenario="ordered",
    exit_code=1,
    expectation_fulfilled="FAIL",
    git_predicate="PASS",
    host_order="PASS",
    regressed_scalars=("calls_unresolved", "unresolved_ratio"),
    regressed_dimensions=(),
)

VARIANTS: tuple[Variant, ...] = (
    Variant(
        id="class-b-check-scalar-violations",
        section="class_b",
        item="SCALARS:violations",
        summary="shop.render imports shop.store's declared OrderRepository, a new "
        "rule.violated: the violations ratchet scalar regresses.",
        files=_VIOLATION_FILES,
        expected_violations=(),
        expected_codes=(),
        check=_VIOLATION,
    ),
    Variant(
        id="class-b-check-guardrail-violations",
        section="class_b",
        item="GUARDRAIL_DIMENSIONS:violations",
        summary="The same new rule.violated regresses the violations delta dimension the "
        "no_new_violations guardrail compares.",
        files=_VIOLATION_FILES,
        expected_violations=(),
        expected_codes=(),
        check=_VIOLATION,
    ),
    Variant(
        id="class-b-scalar-private-crossings",
        section="class_b",
        item="SCALARS:private_crossings",
        summary="shop.cli imports shop.render.text's private _indent; the private_crossings "
        "ratchet scalar regresses alongside the interface_boundary violation it also fires.",
        files=_PRIVATE_CROSSING_FILES,
        expected_violations=(),
        expected_codes=(),
        check=_PRIVATE_CROSSING,
    ),
    Variant(
        id="class-b-guardrail-private-crossings",
        section="class_b",
        item="GUARDRAIL_DIMENSIONS:private_crossings",
        summary="The same underscore reach regresses the private_crossings delta dimension "
        "the no_new_private_crossings guardrail compares.",
        files=_PRIVATE_CROSSING_FILES,
        expected_violations=(),
        expected_codes=(),
        check=_PRIVATE_CROSSING,
    ),
    Variant(
        id="class-b-scalar-private-attribute-access",
        section="class_b",
        item="SCALARS:untyped_private_accesses",
        summary="An untyped parameter reaches a private attribute; the UNKNOWN record still "
        "counts as a separate untyped_private_accesses ratchet position.",
        files=_PRIVATE_ATTRIBUTE_FILES,
        expected_violations=(),
        expected_codes=(),
        check=_PRIVATE_ATTRIBUTE,
    ),
    Variant(
        id="class-b-guardrail-private-attribute-access",
        section="class_b",
        item="GUARDRAIL_DIMENSIONS:unknowns:untyped attribute",
        summary="The same UNKNOWN record regresses the unknowns delta dimension, so the "
        "guardrail sees the measured risk without relabelling it as a private crossing.",
        files=_PRIVATE_ATTRIBUTE_FILES,
        expected_violations=(),
        expected_codes=(),
        check=_PRIVATE_ATTRIBUTE,
    ),
    Variant(
        id="class-b-scalar-unknown-positions",
        section="class_b",
        item="SCALARS:unknown_positions",
        summary="place_order's description parameter widens to str | None; APP-TYPES-NOT-DICT "
        "cannot decide a union, so the unknown_positions ratchet scalar regresses in isolation.",
        files=_UNDECIDED_FILES,
        expected_violations=(),
        expected_codes=(),
        check=_UNDECIDED,
    ),
    Variant(
        id="class-b-scalar-cycle-edges",
        section="class_b",
        item="SCALARS:cycle_edges",
        summary="shop.model reaches into shop.render, closing a two-component cycle; the "
        "cycle_edges ratchet scalar regresses alongside the forbidden-dependency violation.",
        files=_CYCLE_FILES,
        expected_violations=(),
        expected_codes=(),
        check=_CYCLE,
    ),
    Variant(
        id="class-b-check-guardrail-cycles",
        section="class_b",
        item="GUARDRAIL_DIMENSIONS:cycles",
        summary="The same new back-edge regresses the cycles delta dimension the "
        "no_new_cycles guardrail compares.",
        files=_CYCLE_FILES,
        expected_violations=(),
        expected_codes=(),
        check=_CYCLE,
    ),
    Variant(
        id="class-b-scalar-typing-positions",
        section="class_b",
        item="SCALARS:typing_positions",
        summary="A new shop.model probe module uses a type: ignore comment; the "
        "typing_positions ratchet scalar regresses alongside the forbidden-construct violation.",
        files=_TYPING_FILES,
        expected_violations=(),
        expected_codes=(),
        check=_TYPING,
    ),
    Variant(
        id="class-b-guardrail-typing-signals",
        section="class_b",
        item="GUARDRAIL_DIMENSIONS:typing_signals",
        summary="The same type: ignore comment regresses the typing_signals delta dimension "
        "the no_new_typing_signals guardrail compares.",
        files=_TYPING_FILES,
        expected_violations=(),
        expected_codes=(),
        check=_TYPING,
    ),
    Variant(
        id="class-b-scalar-calls-unresolved",
        section="class_b",
        item="SCALARS:calls_unresolved",
        summary="A new call to an unbound name resolves to nothing; the calls_unresolved "
        "ratchet scalar regresses in isolation, firing no rule.",
        files=_UNRESOLVED_FILES,
        expected_violations=(),
        expected_codes=(),
        check=_UNRESOLVED,
    ),
    Variant(
        id="class-b-check-unresolved-ratio",
        section="class_b",
        item="unresolved_ratio",
        summary="The same unresolved call cross-multiplies against a shrinking calls_total "
        "share, regressing the unresolved-call ratio.",
        files=_UNRESOLVED_FILES,
        expected_violations=(),
        expected_codes=(),
        check=_UNRESOLVED,
    ),
)
