# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Test areas. Each CI test job runs one area."""

from fnmatch import fnmatchcase

# The first area with a matching pattern owns a file, so a specific name comes before its prefix.
# A PR job must take at most about 7 minutes on the slowest runner (AD-341). The same tests took
# up to 2 times as long on one runner as on another, so the summed test time of an area on such a
# runner must stay below about 24 minutes for 4 workers.
AREAS: dict[str, tuple[str, ...]] = {
    "CLI and core": (
        "test_cli*.py",
        "test_native_core.py",
        "test_native_interface_boundary.py",
        "test_native_expected_gaps.py",
        "test_native_self_rules.py",
        "test_native_self_contract.py",
        "test_native_self_core_rows.py",
        "test_project_demo_snapshots.py",
    ),
    "native collectors": ("test_collector_native_*.py",),
    "collectors": (
        "test_typescript_*.py",
        "test_collector_*.py",
        "test_parallel_execution.py",
    ),
    "reports": ("test_report*.py", "test_flow*.py"),
    "self-check and CI": (
        "test_repository_hygiene.py",
        "test_ir_owners.py",
        "test_make_gate.py",
        "test_ci_budget.py",
        "test_ci_daily.py",
        "test_merge_check.py",
        "test_native_ci.py",
        "test_native_contract_rules.py",
        "test_native_report.py",
        "test_native_standard_library.py",
        "test_pr_test_node_ids.py",
        "test_native_versions.py",
        "test_rust_*.py",
        "test_browser_*.py",
        "test_mermaid.py",
        "test_publish_release.py",
        "test_pypi_description.py",
        "test_skill.py",
    ),
}


def area_of(file_name: str) -> str | None:
    return next(
        (area for area, patterns in AREAS.items() for p in patterns if fnmatchcase(file_name, p)),
        None,
    )
