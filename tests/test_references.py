# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-26: the unreferenced-symbol claim needs its signal and never guesses without it."""

import json
from dataclasses import replace
from pathlib import Path

import pytest
from test_analyzer import _observe

from archkeel.ir.codec import decode_canonical_model, parse_observation
from archkeel.ir.references import unreferenced_symbols

ROOT = Path(__file__).resolve().parents[1]


def _self_observation():
    artifact = (ROOT / "fixtures/D-self/architecture.json").read_bytes()
    return parse_observation(decode_canonical_model(json.loads(artifact)))


def test_the_claim_is_unknown_without_the_reference_signal() -> None:
    observation = _self_observation()
    without = replace(
        observation,
        sections=tuple(item for item in observation.sections if item.name != "references"),
    )

    result = unreferenced_symbols(without)

    assert result.status == "UNKNOWN"
    assert result.candidates == ()
    assert result.symbols == 0


def test_a_function_used_only_as_a_value_is_not_a_candidate() -> None:
    """The parser functions live in a dispatch table; no call site names them."""
    result = unreferenced_symbols(_self_observation())
    names = {candidate.name for candidate in result.candidates}

    assert result.status == "SUPPORTED"
    assert "archkeel.ir.codec._parse_sibling_isolation" not in names
    assert "archkeel.ir.codec._parse_forbidden_dependency" not in names
    assert "archkeel.cli._sha" not in names


def test_runtime_dispatch_and_declared_interfaces_are_set_aside() -> None:
    """Visitor methods and dunder methods are called by the runtime, not by the code."""
    result = unreferenced_symbols(_self_observation())
    names = [candidate.name for candidate in result.candidates]

    assert result.exempt > 0
    assert not [name for name in names if name.rsplit(".", 1)[-1].startswith("visit_")]
    assert not [
        name
        for name in names
        if name.rsplit(".", 1)[-1].startswith("__") and name.rsplit(".", 1)[-1].endswith("__")
    ]


def test_the_claim_stays_small_enough_to_read() -> None:
    """A review claim is only useful while a person can still check every candidate."""
    result = unreferenced_symbols(_self_observation())

    assert result.symbols > 400
    assert len(result.candidates) < 10


def test_enum_members_in_field_annotations_and_defaults_reference_their_class(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "sample.py"
    source.write_text(
        "from enum import Enum\n"
        "from typing import Literal\n\n"
        "class IntentRepairKind(str, Enum):\n"
        "    REPLACE_FIELD = 'replace_field'\n\n"
        "class ScaffoldParameter(str, Enum):\n"
        "    MAX_COUNT = 'max_count'\n\n"
        "class Unused(Enum):\n"
        "    ITEM = 'item'\n\n"
        "class Request:\n"
        "    repair: Literal[IntentRepairKind.REPLACE_FIELD]\n"
        "    limit: str = ScaffoldParameter.MAX_COUNT\n"
    )

    monkeypatch.setenv("PYTHONPATH", str(ROOT / "src"))
    observed = _observe(tmp_path)
    assert observed.observation is not None
    result = unreferenced_symbols(observed.observation)
    candidates = {candidate.name for candidate in result.candidates}

    assert "sample.IntentRepairKind" not in candidates
    assert "sample.ScaffoldParameter" not in candidates
    assert "sample.Unused" in candidates


def test_enum_member_evidence_requires_a_proven_unshadowed_member(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "sample.py"
    source.write_text(
        "from enum import Enum\n"
        "from typing import Literal\n\n"
        "class State(Enum):\n"
        "    READY = 'ready'\n\n"
        "class Other:\n"
        "    READY = 'ready'\n\n"
        "class Unused(Enum):\n"
        "    IDLE = 'idle'\n\n"
        "class Payload:\n"
        "    status: Literal[State.MISSING]\n"
        "    other: Literal[Other.READY]\n\n"
        "class Shadowed:\n"
        "    State = Other\n"
        "    status: Literal[State.READY]\n\n"
        "def dynamic():\n"
        "    return make_state().READY\n\n"
        "def shadowed(State):\n"
        "    return State.READY\n\n"
        "def build():\n"
        "    return Payload(State.READY)\n"
    )

    monkeypatch.setenv("PYTHONPATH", str(ROOT / "src"))
    observed = _observe(tmp_path)
    assert observed.observation is not None
    references = observed.observation.records("references") or ()
    member_references = [
        item for item in references if item.data.get("expression") == "State.READY"
    ]

    assert [item.data.get("source_scope") for item in member_references] == ["sample.build"]
    assert member_references[0].data.get("targets") == ("sample.State",)


def test_shadowed_import_does_not_create_enum_member_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "sample").mkdir()
    (tmp_path / "sample/types.py").write_text(
        "from enum import Enum\nclass State(Enum):\n    READY = 'ready'\n"
    )
    (tmp_path / "sample/facade.py").write_text(
        "from typing import Literal\n"
        "from sample.types import State\n\n"
        "class Payload:\n"
        "    State = object\n"
        "    status: Literal[State.READY]\n"
    )

    monkeypatch.setenv("PYTHONPATH", str(ROOT / "src"))
    observed = _observe(tmp_path)
    assert observed.observation is not None
    member_references = [
        item
        for item in observed.observation.records("references") or ()
        if item.data.get("expression") == "State.READY"
    ]

    assert all(item.data.get("targets") != ("sample.types.State",) for item in member_references)
