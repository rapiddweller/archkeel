# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Find original import sites and their Core findings in a standard report."""

from archkeel.ir.architecture_graph import ArchitectureReport, Relationship, ReportFinding


def import_sites(report: ArchitectureReport, source: str, target: str) -> tuple[Relationship, ...]:
    assert report.observed is not None
    names = {item.id: item.qualified_name for item in report.observed.entities}
    return tuple(
        site
        for site in report.observed.relationships
        if site.kind == "imports"
        and names[site.source_id] == source
        and names.get(site.target_id) == target
    )


def findings_for(
    report: ArchitectureReport, sites: tuple[Relationship, ...]
) -> tuple[ReportFinding, ...]:
    ids = {site.id for site in sites}
    return tuple(item for item in report.findings if ids.intersection(item.graph_subject_ids))
