# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-26: the unread-binding claim needs its signal and never guesses without it."""

import json
from dataclasses import replace
from pathlib import Path

from archkeel.ir.bindings import unread_bindings
from archkeel.ir.codec import decode_canonical_model, parse_observation

ROOT = Path(__file__).resolve().parents[1]


def _self_observation():
    artifact = (ROOT / "fixtures/D-self/architecture.json").read_bytes()
    return parse_observation(decode_canonical_model(json.loads(artifact)))


def test_the_claim_is_unknown_without_the_binding_signal() -> None:
    observation = _self_observation()
    without = replace(
        observation,
        sections=tuple(item for item in observation.sections if item.name != "bindings"),
    )

    result = unread_bindings(without)

    assert result.status == "UNKNOWN"
    assert result.candidates == ()
    assert result.functions == 0


def test_a_repository_the_linter_already_guards_names_no_binding() -> None:
    """ARG and RUF059 reject an unread binding at lint time, so the claim stays empty."""
    result = unread_bindings(_self_observation())

    assert result.status == "SUPPORTED"
    assert result.candidates == ()
    assert result.functions > 100
