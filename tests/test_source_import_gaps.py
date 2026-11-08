# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""derived_unresolved_imports reads the collector gaps once, not once for each import."""

from __future__ import annotations

import random
from collections.abc import Sequence
from types import SimpleNamespace
from typing import cast

import pytest

from archkeel.ir.facts import (
    CollectionCoverage,
    EvidenceClass,
    FactSection,
    LocalTarget,
    Record,
    RecordData,
    SourceFacts,
    SourceSectionName,
    UnresolvedTarget,
)
from archkeel.ir.import_gaps import derived_unresolved_imports


def _record(identity: str, evidence: tuple[str, ...], **data: object) -> Record:
    return Record(
        identity,
        EvidenceClass.FACT,
        "source",
        "import",
        identity,
        (),
        evidence,
        (),
        (),
        (),
        RecordData(tuple(sorted(data.items()))),  # type: ignore[arg-type]
    )


def _facts(
    sections: list[FactSection], imports: Sequence[object], gaps: list[Record]
) -> SourceFacts:
    coverage = CollectionCoverage((), 0, 0, True, tuple(gaps))
    return cast(
        SourceFacts,
        SimpleNamespace(sections=tuple(sections), imports=tuple(imports), coverage=coverage),
    )


def _quadratic_scan(facts: SourceFacts) -> frozenset[str]:
    """The earlier definition: scan every collector gap for each unresolved import."""

    def named_by_gap(gaps: tuple[Record, ...], record: Record) -> bool:
        return any(
            gap.data.get("resolution_dimension") == SourceSectionName.IMPORTS
            and gap.data.get("module") == record.data.get("source_module")
            and gap.evidence_ids == record.evidence_ids
            for gap in gaps
        )

    records = {
        record.id: record
        for section in facts.sections
        if section.name is SourceSectionName.IMPORTS
        for record in section.records
    }
    return frozenset(
        target.import_id
        for target in facts.imports
        if isinstance(target, UnresolvedTarget)
        and not named_by_gap(facts.coverage.gaps, records[target.import_id])
    )


def _generated(seed: int, size: int | None = None) -> SourceFacts:
    rng = random.Random(seed)
    count = size if size is not None else rng.randint(0, 25)
    modules = [f"m{index}" for index in range(max(2, count // 3))]
    evidence: list[tuple[str, ...]] = [(f"e{index}",) for index in range(max(2, count // 2))]
    evidence.append(())
    evidence.append(("e0", "e1"))
    imports: list[object] = []
    records: list[Record] = []
    for index in range(count):
        identity = f"i{index}"
        fields: dict[str, object] = {}
        if rng.random() < 0.9:
            fields["source_module"] = rng.choice(modules)
        records.append(_record(identity, rng.choice(evidence), **fields))
        if rng.random() < 0.7:
            imports.append(UnresolvedTarget(identity, f"x{index}", "missing"))
        else:
            imports.append(LocalTarget(identity, "m0", "m0.py"))
    gaps: list[Record] = []
    for index in range(rng.randint(0, 2 * count)):
        fields = {}
        if rng.random() < 0.85:
            fields["resolution_dimension"] = rng.choice(["imports", "imports", "symbols", "calls"])
        if rng.random() < 0.9:
            fields["module"] = rng.choice(modules)
        gaps.append(_record(f"g{index}", rng.choice(evidence), **fields))
    sections = [
        FactSection(SourceSectionName.IMPORTS, tuple(records)),
        FactSection(SourceSectionName.SYMBOLS, (_record("s0", ("e0",), source_module="m0"),)),
    ]
    return _facts(sections, imports, gaps)


@pytest.mark.parametrize("seed", range(400))
def test_derived_unresolved_imports_equal_the_quadratic_scan(seed: int) -> None:
    facts = _generated(seed)
    assert derived_unresolved_imports(facts) == _quadratic_scan(facts)


def test_a_gap_names_an_import_by_its_module_and_evidence() -> None:
    imports = [UnresolvedTarget(f"i{n}", f"x{n}", "missing") for n in range(4)]
    records = [
        _record("i0", ("e0",), source_module="a"),  # named by a gap
        _record("i1", ("e1",), source_module="a"),  # same module, other evidence
        _record("i2", ("e0",), source_module="b"),  # same evidence, other module
        _record("i3", ("e0",)),  # no module: a gap without module names it
    ]
    gaps = [
        _record("g0", ("e0",), resolution_dimension="imports", module="a"),
        _record("g1", ("e1",), resolution_dimension="symbols", module="a"),  # wrong dimension
        _record("g2", ("e0",), resolution_dimension="imports"),
    ]
    facts = _facts([FactSection(SourceSectionName.IMPORTS, tuple(records))], imports, gaps)
    assert derived_unresolved_imports(facts) == {"i1", "i2"}
    assert derived_unresolved_imports(facts) == _quadratic_scan(facts)


def test_derived_unresolved_imports_read_each_gap_a_constant_number_of_times(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reads = 0
    real = RecordData.get

    def counted(self: RecordData, key: str, default: object = None) -> object:
        nonlocal reads
        reads += 1
        return real(self, key, default)  # type: ignore[arg-type]

    facts = _generated(7, size=300)
    expected = _quadratic_scan(facts)
    monkeypatch.setattr(RecordData, "get", counted)
    assert derived_unresolved_imports(facts) == expected
    imports = len(facts.imports)
    gaps = len(facts.coverage.gaps)
    assert reads <= 2 * (imports + gaps)
