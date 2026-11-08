# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Find original import sites, their Core findings and the module membership in a report."""

import json
import subprocess
from pathlib import Path

from archkeel.check.ports import ScanConfig
from archkeel.check.report import run_report
from archkeel.cli.observe import observe
from archkeel.ir.architecture_graph import ArchitectureReport, Relationship, ReportFinding
from archkeel.ir.codec import decode_canonical_model, parse_observation
from archkeel.ir.ownership import scope_names
from archkeel.ir.report_graph import architecture_report


def scan_config() -> ScanConfig:
    return ScanConfig(("sample",), "sample", "contract.json", "0" * 64)


def commit_tree(root: Path) -> str:
    for args in (
        ["git", "init", "-q", "-b", "main"],
        ["git", "config", "user.email", "qa@example.invalid"],
        ["git", "config", "user.name", "QA"],
        ["git", "add", "-A"],
        ["git", "-c", "commit.gpgsign=false", "commit", "-q", "-m", "base"],
    ):
        subprocess.run(args, cwd=root, check=True, capture_output=True)
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()


def committed_report(root: Path) -> ArchitectureReport:
    """Commit the tree, run the report as the CLI does and return the report graph."""
    commit_tree(root)
    _, encoded = run_report(root, config=scan_config(), analyzer=observe)
    assert encoded is not None
    return architecture_report(parse_observation(decode_canonical_model(json.loads(encoded))))


def member_modules(report: ArchitectureReport) -> dict[str, tuple[str, ...]]:
    """Map the scope key of each component to the sorted names of the modules it owns."""
    assert report.target is not None and report.observed is not None
    names = {item.id: item.qualified_name for item in report.observed.entities}
    keys = scope_names(report.target.component_intents)
    return {
        keys[item.component_id]: tuple(sorted(names[identity] for identity in item.module_ids))
        for item in report.memberships
    }


def unassigned_modules(report: ArchitectureReport) -> dict[str, tuple[str, ...]]:
    """Map each component with children to its modules that no child owns."""
    assert report.target is not None
    keys = scope_names(report.target.component_intents)
    members = member_modules(report)
    result: dict[str, tuple[str, ...]] = {}
    for parent in {item.parent_id for item in report.target.component_intents if item.parent_id}:
        owned = {
            module
            for item in report.target.component_intents
            if item.parent_id == parent
            for module in members[keys[item.component_id]]
        }
        result[keys[parent]] = tuple(
            module for module in members[keys[parent]] if module not in owned
        )
    return result


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
