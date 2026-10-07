# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-26: the unread-binding claim needs its signal and never guesses without it."""

from dataclasses import replace

from archkeel.ir.bindings import BindingReads, UnreadBinding, unread_bindings
from archkeel.ir.model import Observation
from archkeel.render.html import _binding_claim_body


def test_the_claim_is_unknown_without_the_binding_signal(self_observation: Observation) -> None:
    observation = self_observation
    without = replace(
        observation,
        sections=tuple(item for item in observation.sections if item.name != "bindings"),
    )

    result = unread_bindings(without)

    assert result.status == "UNKNOWN"
    assert result.candidates == ()
    assert result.functions == 0


def test_a_repository_the_linter_already_guards_names_no_binding(
    self_observation: Observation,
) -> None:
    """ARG and RUF059 reject an unread binding at lint time, so the claim stays empty."""
    result = unread_bindings(self_observation)

    assert result.status == "SUPPORTED"
    assert result.candidates == ()
    assert result.functions > 100


def test_typescript_binding_receipt_does_not_claim_unread_name_coverage(
    self_observation: Observation,
) -> None:
    typescript = replace(
        self_observation,
        analyzer=replace(self_observation.analyzer, name="archkeel-typescript-imports"),
    )

    result = unread_bindings(typescript)

    assert result.status == "UNKNOWN"
    assert result.candidates == ()
    assert result.functions == 0


def test_a_supported_empty_claim_does_not_say_every_parameter_is_read() -> None:
    result = _binding_claim_body(BindingReads("SUPPORTED", functions=4))

    assert "no unread-binding candidates" in result
    assert "every parameter" not in result


def test_an_unread_parameter_candidate_is_not_a_removal_claim() -> None:
    result = _binding_claim_body(
        BindingReads(
            "SUPPORTED",
            functions=4,
            candidates=(UnreadBinding("pkg.Implementation.method", "value", "parameter", "pkg"),),
        )
    )

    assert "Code in these functions does not read the listed names" in result
    assert "required by an interface" in result
    assert "review before removing it" in result
