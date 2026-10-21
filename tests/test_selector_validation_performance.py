# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Selector proof checks avoid repeated scans of global inventories."""

from collections.abc import Iterator, Mapping
from types import SimpleNamespace

from archkeel.ir.facts import (
    CallBinding,
    CallBindingOrigin,
    Evidence,
    EvidenceClass,
    FactSection,
    Record,
    RecordData,
    SourceSectionName,
)
from archkeel.ir.facts_validation import (
    _selector_direct_receiver_proof,
    _selector_receiver_proof,
)


class _LookupOnlyEvidence(Mapping[str, Evidence]):
    def __init__(self, rows: dict[str, Evidence]) -> None:
        self.rows = rows
        self.lookups: list[str] = []

    def __getitem__(self, key: str) -> Evidence:
        self.lookups.append(key)
        return self.rows[key]

    def __iter__(self) -> Iterator[str]:
        raise AssertionError("selector proof must not iterate the full evidence inventory")

    def __len__(self) -> int:
        return len(self.rows)

    def __contains__(self, key: object) -> bool:
        self.lookups.append(str(key))
        return key in self.rows


class _UnscannableImports:
    def __iter__(self) -> Iterator[Record]:
        raise AssertionError("local selector proof must not scan imports")


def _record(
    identifier: str,
    *,
    kind: str,
    evidence_ids: tuple[str, ...],
    data: RecordData,
) -> Record:
    return Record(
        identifier,
        EvidenceClass.FACT,
        "symbols",
        kind,
        identifier,
        (),
        evidence_ids,
        (),
        (),
        (),
        data,
    )


def test_selector_receiver_validation_looks_up_only_its_proof_evidence():
    selector = _record(
        "SELECTOR",
        kind="construct_selector",
        evidence_ids=("SELECTOR-EVD", "CLASS-EVD"),
        data=RecordData(
            (
                ("owner", "sample.route"),
                ("receiver_type", "sample.Connection"),
                ("selector_role", "constructor"),
            )
        ),
    )
    binding = CallBinding(CallBindingOrigin.DIRECT, "sample.Connection", ("CLASS-EVD",))
    class_declaration = _record(
        "CLASS",
        kind="class",
        evidence_ids=("CLASS-EVD",),
        data=RecordData((("module", "sample"), ("source_binding_unique", True))),
    )
    evidence = _LookupOnlyEvidence(
        {
            "SELECTOR-EVD": Evidence("SELECTOR-EVD", "sample.py", 1, 1, 0, "Connection()"),
            "CLASS-EVD": Evidence("CLASS-EVD", "sample.py", 3, 3, 0, "class Connection:"),
        }
    )

    _selector_receiver_proof(
        SimpleNamespace(
            sections=(FactSection(SourceSectionName.IMPORTS, ()),),
        ),
        selector,
        binding,
        None,
        {"sample.Connection": [class_declaration]},
        evidence,
    )

    assert "CLASS-EVD" in evidence.lookups


def test_local_selector_class_proof_does_not_scan_imports():
    class_declaration = _record(
        "CLASS",
        kind="class",
        evidence_ids=(),
        data=RecordData((("module", "sample"), ("source_binding_unique", True))),
    )

    _selector_direct_receiver_proof(
        CallBinding(CallBindingOrigin.DIRECT, "sample.Connection", ("CLASS-EVD",)),
        None,
        [class_declaration],
        _UnscannableImports(),
    )
