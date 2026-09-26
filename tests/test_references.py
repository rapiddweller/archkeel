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


def test_enum_member_constructor_argument_references_its_class(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "sample.py").write_text(
        "from enum import Enum\n"
        "class State(Enum):\n"
        "    READY = 'ready'\n"
        "class Payload: pass\n"
        "def build():\n"
        "    return Payload(State.READY)\n"
    )

    monkeypatch.setenv("PYTHONPATH", str(ROOT / "src"))
    observed = _observe(tmp_path)
    assert observed.observation is not None
    member_references = [
        item
        for item in observed.observation.records("references") or ()
        if item.data.get("expression") == "State.READY"
    ]

    assert len(member_references) == 1
    assert member_references[0].data.get("targets") == ("sample.State",)


@pytest.mark.parametrize(
    "body",
    [
        "class Payload: status = State.MISSING",
        "class Other: READY = 'ready'\nvalue = Other.READY",
        "class Shadowed:\n    State = object\n    status = State.READY",
        "value = make_state().READY",
        "def shadowed(State):\n    return State.READY",
        "def State(): pass\nvalue = State.READY",
        "State = object()\nvalue = State.READY",
        "def shadowed():\n    State = object()\n    return State.READY",
        "value = lambda State: State.READY",
        "values = [State.READY for State in items]",
        "try: raise ValueError\nexcept ValueError as State:\n    value = State.READY",
        "match value:\n    case {'state': State}: result = State.READY",
        "match value:\n    case [*State]: result = State.READY",
        "match value:\n    case {**State}: result = State.READY",
        "del State\nvalue = State.READY",
        "def shadowed():\n    global State\n    return State.READY",
    ],
)
def test_ambiguous_enum_member_roots_do_not_add_enum_evidence(tmp_path: Path, body: str) -> None:
    (tmp_path / "sample.py").write_text(
        "from enum import Enum\nclass State(Enum):\n    READY = 'ready'\n" + body + "\n"
    )
    observed = _observe(tmp_path)
    assert observed.observation is not None
    assert not any(
        item.data.get("use") == "attribute" and item.data.get("targets") == ("sample.State",)
        for item in observed.observation.records("references") or ()
    )


@pytest.mark.parametrize(
    ("owner_suffix", "writer", "expected"),
    [
        ("", "", True),
        ("State = object()\n", "", False),
        ("", "import sample.types as t\nt.State = object()\n", False),
        ("", "import sample.types as t\ndel t.State\n", False),
        ("", "import sample.types as t\nt.State.READY = 'new'\n", False),
        ("", "import sample as s\ns.types = object()\n", False),
        ("", "import sample.types as t\nimport other as t\nt.State = object()\n", False),
        ("", "from sample import *\ntypes.State = object()\n", False),
        ("", "import external\nexternal.choice = object()\n", True),
        ("", "class Service:\n    def __init__(self): self.value = 1\n", True),
    ],
)
def test_enum_member_evidence_checks_owner_and_scanned_attribute_writes(
    tmp_path: Path, owner_suffix: str, writer: str, expected: bool
) -> None:
    package = tmp_path / "sample"
    package.mkdir()
    (package / "__init__.py").write_text("from . import types\n__all__ = ['types']\n")
    (package / "types.py").write_text(
        "from enum import Enum\nclass State(Enum):\n    READY = 'ready'\n" + owner_suffix
    )
    (package / "writer.py").write_text(writer)
    (package / "consumer.py").write_text(
        "import sample.writer\nimport sample.types as types\nvalue = types.State.READY\n"
    )
    observed = _observe(tmp_path)
    assert observed.observation is not None
    references = [
        item
        for item in observed.observation.records("references") or ()
        if item.data.get("expression") == "types.State.READY"
    ]
    assert (
        any(item.data.get("targets") == ("sample.types.State",) for item in references) is expected
    )


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


def test_wildcard_import_disables_enum_member_evidence_for_the_module(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "sample.py").write_text(
        "from enum import Enum\n"
        "from other import *\n"
        "class State(Enum):\n"
        "    READY = 'ready'\n"
        "class Payload:\n"
        "    status: State.READY\n"
    )

    monkeypatch.setenv("PYTHONPATH", str(ROOT / "src"))
    observed = _observe(tmp_path)
    assert observed.observation is not None
    member_references = [
        item
        for item in observed.observation.records("references") or ()
        if item.data.get("expression") == "State.READY"
    ]

    assert all(item.data.get("targets") != ("sample.State",) for item in member_references)
