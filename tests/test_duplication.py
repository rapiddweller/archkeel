# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-30: the repeated-logic claim needs a signal and a declared owner to contradict."""

import json
from dataclasses import replace
from pathlib import Path

from test_architecture_demo import CONFIG, _prepare_repo

from archkeel.analyzer import observe
from archkeel.check.report import run_report
from archkeel.ir.codec import decode_canonical_model, parse_observation
from archkeel.ir.duplication import MINIMUM_SHAPE_NODES, repeated_logic
from fixtures.architecture_demo import CATALOG

ROOT = Path(__file__).resolve().parents[1]
_TOUR = next(variant for variant in CATALOG if variant.id == "tour")


def _self_observation():
    artifact = (ROOT / "fixtures/D-self/architecture.json").read_bytes()
    return parse_observation(decode_canonical_model(json.loads(artifact)))


def test_the_claim_is_unknown_without_the_shape_signal() -> None:
    observation = _self_observation()
    without = replace(
        observation,
        sections=tuple(item for item in observation.sections if item.name != "symbols"),
    )

    result = repeated_logic(without)

    assert result.status == "UNKNOWN"
    assert result.candidates == ()
    assert result.functions == 0


def test_archkeel_repeats_nothing_its_declared_owner_holds() -> None:
    """One owner is declared, and no function outside it repeats one inside it.

    This claim found its own repository on the first run: the analyzer carried a second
    copy of `stable_id`, the fingerprint every record id is built from. It was removed,
    and this test is what keeps it removed.
    """
    result = repeated_logic(_self_observation())

    assert result.status == "SUPPORTED"
    assert result.owners == 1
    assert result.functions > 400
    assert result.candidates == ()


def test_a_copy_of_owned_arithmetic_is_named(tmp_path: Path) -> None:
    """The tour copies Order.total into shop.app, which shop.model is declared to own."""
    root = _prepare_repo(tmp_path, dict(_TOUR.files))
    _, architecture = run_report(root, config=CONFIG, analyzer=observe)
    assert architecture is not None
    observation = parse_observation(decode_canonical_model(json.loads(architecture)))

    result = repeated_logic(observation)

    assert result.owners == 1
    assert [(item.outside, item.inside) for item in result.candidates] == [
        ("shop.app.orders.restate_total", "shop.model.entities.Order.total")
    ]
    assert all(item.shape_nodes >= MINIMUM_SHAPE_NODES for item in result.candidates)
