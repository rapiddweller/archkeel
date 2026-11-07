# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Find the unresolved imports that no collector gap already names."""

from .facts import Record, SourceFacts, SourceSectionName, UnresolvedTarget


def _named_by_gap(gaps: tuple[Record, ...], record: Record) -> bool:
    """Return whether a collector gap already identifies the import site of the record."""
    return any(
        gap.data.get("resolution_dimension") == SourceSectionName.IMPORTS
        and gap.data.get("module") == record.data.get("source_module")
        and gap.evidence_ids == record.evidence_ids
        for gap in gaps
    )


def derived_unresolved_imports(facts: SourceFacts) -> frozenset[str]:
    """Return the id of each unresolved import that needs a failure derived by Core."""
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
        and not _named_by_gap(facts.coverage.gaps, records[target.import_id])
    )
