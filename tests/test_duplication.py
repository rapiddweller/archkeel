# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-30: the repeated-logic claim needs a signal and a declared owner to contradict."""

import json
from dataclasses import replace
from pathlib import Path

from test_architecture_demo import CONFIG, _prepare_repo

from archkeel.check.report import run_report
from archkeel.cli.observe import observe
from archkeel.ir.codec import decode_canonical_model, parse_observation
from archkeel.ir.duplication import MINIMUM_SHAPE_NODES, repeated_logic
from archkeel.ir.facts_codec import freeze_data, thaw_data
from archkeel.ir.model import Observation
from fixtures.architecture_demo import CATALOG

_TOUR = next(variant for variant in CATALOG if variant.id == "tour")


def test_the_claim_is_unknown_without_the_shape_signal(self_observation: Observation) -> None:
    observation = self_observation
    without = replace(
        observation,
        sections=tuple(item for item in observation.sections if item.name != "symbols"),
    )

    result = repeated_logic(without)

    assert result.status == "UNKNOWN"
    assert result.candidates == ()
    assert result.functions == 0


def test_archkeel_repeats_nothing_its_declared_owner_holds(self_observation: Observation) -> None:
    """Declared vocabulary and identity owners retain their independent logic.

    This claim found its own repository on the first run: the analyzer carried a second
    copy of `stable_id`, the fingerprint every record id is built from. It was removed,
    and this test is what keeps it removed.
    """
    result = repeated_logic(self_observation)

    assert result.status == "SUPPORTED"
    assert result.owners == 2
    assert result.functions > 400
    assert result.candidates == ()


def test_copying_the_current_identity_owner_is_reported(self_observation: Observation) -> None:
    symbols = self_observation.records("symbols")
    assert symbols is not None
    owner = "archkeel.ir.facts.stable_id"
    original = next(item for item in symbols if item.data.get("qualified_name") == owner)
    data = thaw_data(original.data)
    data["qualified_name"] = "archkeel.analyzer.python.identity_copy"
    copied = replace(original, id="COPIED-STABLE-IDENTITY", data=freeze_data(data))
    changed = replace(
        self_observation,
        sections=tuple(
            replace(section, records=(*symbols, copied)) if section.name == "symbols" else section
            for section in self_observation.sections
        ),
    )
    assert (owner, data["qualified_name"]) in {
        (item.inside, item.outside) for item in repeated_logic(changed).candidates
    }


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
