# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Find the unresolved imports that no collector gap already names."""

from .facts import JsonValue, Record, SourceFacts, SourceSectionName, UnresolvedTarget


def _site(record: Record, module_key: str) -> tuple[JsonValue, tuple[str, ...]]:
    """Return the module and the evidence ids that identify the import site of a record."""
    return record.data.get(module_key), record.evidence_ids


def derived_unresolved_imports(facts: SourceFacts) -> frozenset[str]:
    """Return the id of each unresolved import that needs a failure derived by Core."""
    records = {
        record.id: record
        for section in facts.sections
        if section.name is SourceSectionName.IMPORTS
        for record in section.records
    }
    named = {
        _site(gap, "module")
        for gap in facts.coverage.gaps
        if gap.data.get("resolution_dimension") == SourceSectionName.IMPORTS
    }
    return frozenset(
        target.import_id
        for target in facts.imports
        if isinstance(target, UnresolvedTarget)
        and _site(records[target.import_id], "source_module") not in named
    )
