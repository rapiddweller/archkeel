# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The dependency proof parses only the records that it binds, and binds the same records."""

from __future__ import annotations

import itertools
import random
from types import SimpleNamespace
from typing import Any

import pytest

import archkeel.check.observation as observation
import archkeel.ir.dependency_binding_kinds as binding_kinds
from archkeel.ir.decisions import dependency_binding_id
from archkeel.ir.facts_codec import parse_record
from archkeel.ir.model import CLASSIFIED_SECTIONS, Section

FLAGS = tuple(itertools.product((False, True), repeat=2))
REFERENCE_KINDS = (
    "script_namespace_effect",
    "source_role",
    "value_reference",
    "attribute_reference",
    "plain_reference",
    "annotation_reference",
)


def _raw(name: str, kind: str) -> dict[str, Any]:
    return {
        "id": name,
        "evidence_class": "FACT",
        "area": "dependency",
        "kind": kind,
        "title": name,
        "subjects": [name],
        "evidence_ids": [],
        "rule_ids": [],
        "fact_ids": [],
        "provenance": [],
        "data": {"name": name},
    }


def _scan(seed: int, size: int = 30) -> Any:
    rng = random.Random(seed)

    def section(prefix: str, kinds: tuple[str, ...]) -> list[dict[str, Any]]:
        return [_raw(f"{prefix}{n}", rng.choice(kinds)) for n in range(rng.randint(0, size))]

    return SimpleNamespace(
        modules=section("m", ("module",)),
        imports=section("i", ("import",)),
        symbols=section("s", ("function", "class")),
        references=section("r", REFERENCE_KINDS),
        calls=section("c", ("call",)),
        coverage={"failures": []},
        evidence=[],
    )


def _declarations(seed: int) -> list[dict[str, Any]]:
    kinds = ("complete_requires", "call_owner", "source_ownership", "allowed_dependency")
    return [_raw(f"d{n}", kind) for n, kind in enumerate(kinds * (seed % 3 + 1))]


def _eager_id(scan: Any, declarations: list[dict[str, Any]], calls: bool, ownership: bool) -> str:
    """The earlier definition: parse every record, then let the proof drop the unbound ones."""
    sections = (
        Section(name, tuple(parse_record(item) for item in records))
        for name, records in (
            ("modules", scan.modules),
            ("imports", scan.imports),
            ("symbols", scan.symbols),
            ("references", scan.references),
            ("calls", scan.calls),
            ("declarations", declarations),
        )
    )
    return dependency_binding_id(
        sections, (), (), include_calls=calls, include_source_ownership=ownership
    )


@pytest.mark.parametrize(("calls", "ownership"), FLAGS)
@pytest.mark.parametrize("seed", range(40))
def test_the_filtered_proof_binds_what_the_eager_proof_bound(
    seed: int, calls: bool, ownership: bool
) -> None:
    scan, declarations = _scan(seed), _declarations(seed)
    filtered = observation._dependency_binding_id(
        scan, declarations, include_calls=calls, include_source_ownership=ownership
    )
    assert filtered == _eager_id(scan, declarations, calls, ownership)


def test_the_filter_parses_only_bound_records(monkeypatch: pytest.MonkeyPatch) -> None:
    scan, declarations = _scan(7, size=60), _declarations(7)
    parsed: list[str] = []

    def counting(item: Any, *args: Any) -> Any:
        parsed.append(item["id"])
        return parse_record(item, *args)

    monkeypatch.setattr(binding_kinds, "parse_record", counting)
    observation._dependency_binding_id(scan, declarations)
    dropped = {item["id"] for item in scan.calls}
    dropped |= {item["id"] for item in scan.references if item["kind"] != "script_namespace_effect"}
    assert dropped
    assert not dropped & set(parsed)
    assert {item["id"] for item in scan.modules + scan.imports + scan.symbols} <= set(parsed)


def _poisoned(section: str, kind: str, change: dict[str, Any] | str) -> Any:
    scan = _scan(3)
    bad = _raw("bad", kind)
    if isinstance(change, str):
        bad.pop(change)
    else:
        bad.update(change)
    getattr(scan, section).append(bad)
    return scan


MALFORMED_BOUND = (
    ("references", "script_namespace_effect", {"evidence_class": "NOT-A-CLASS"}),
    ("references", "script_namespace_effect", "title"),
    ("references", "script_namespace_effect", {"extra": 1}),
    ("modules", "module", {"subjects": "not-a-list"}),
    ("imports", "import", "data"),
)


@pytest.mark.parametrize(("section", "kind", "change"), MALFORMED_BOUND)
def test_a_malformed_bound_record_is_still_rejected(section, kind, change) -> None:
    scan = _poisoned(section, kind, change)
    with pytest.raises((ValueError, TypeError)) as eager:
        _eager_id(scan, [], False, False)
    with pytest.raises((ValueError, TypeError)) as filtered:
        observation._dependency_binding_id(scan, [])
    assert str(filtered.value) == str(eager.value)


@pytest.mark.parametrize(
    "change",
    ({"kind": 5}, {"kind": None}, "kind"),
)
def test_a_record_without_a_text_kind_is_rejected_where_the_proof_does_not_bind_it(change) -> None:
    scan = _poisoned("references", "plain_reference", change)
    with pytest.raises((ValueError, TypeError)) as eager:
        _eager_id(scan, [], False, False)
    with pytest.raises((ValueError, TypeError)) as filtered:
        observation._dependency_binding_id(scan, [])
    assert str(filtered.value) == str(eager.value)


@pytest.mark.parametrize(
    ("section", "kind", "change"),
    (
        ("references", "plain_reference", {"evidence_class": "NOT-A-CLASS"}),
        ("calls", "call", {"evidence_class": "NOT-A-CLASS"}),
        ("references", "plain_reference", {"extra": 1}),
    ),
)
def test_a_malformed_record_of_an_unbound_kind_is_rejected_by_the_observation_parse(
    section: str, kind: str, change: dict[str, Any]
) -> None:
    """The proof no longer parses it. `parse_observation` parses the same section later."""
    scan = _poisoned(section, kind, change)
    assert section in CLASSIFIED_SECTIONS
    observation._dependency_binding_id(scan, [])
    with pytest.raises(ValueError, match="evidence_class is invalid|fields mismatch"):
        for item in getattr(scan, section):
            parse_record(item, f"{section}[]")
