# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-26: the unread-binding claim needs its signal and never guesses without it."""

from archkeel.ir.bindings import BindingReads, UnreadBinding
from archkeel.render.html import _binding_claim_body


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
