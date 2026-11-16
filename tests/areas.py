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
        "test_area_selection.py",
        "test_make_gate.py",
        "test_make_self_check.py",
        "test_ci_budget.py",
        "test_ci_daily.py",
        "test_gallery_publication.py",
        "test_merge_check.py",
        "test_native_ci.py",
        "test_native_conventions.py",
        "test_native_targets_have_callers.py",
        "test_doc_references_exist.py",
        "test_native_neutral_crates.py",
        "test_table_overlap.py",
        "test_native_contract_rules.py",
        "test_native_report.py",
        "test_native_standard_library.py",
        "test_pr_test_node_ids.py",
        "test_native_versions.py",
        "test_rust_*.py",
        "test_browser_*.py",
        "test_mermaid.py",
        "test_publish_release.py",
        "test_readme_showcase.py",
        "test_system_parts.py",
        "test_pypi_description.py",
        "test_shipped_skills.py",
        "test_skill.py",
    ),
}


def area_of(file_name: str) -> str | None:
    return next(
        (area for area, patterns in AREAS.items() for p in patterns if fnmatchcase(file_name, p)),
        None,
    )


# AD-674: the nightly tier. These files hold the scaling, memory and large-scan tests: the nine
# files that made 73 % of the summed test time (PIPELINE-TEST-AUDIT.md). The PR and main tiers run
# `-m "not slow"`; the nightly Full run (`make full-test`) runs every test.
SLOW_FILES = frozenset(
    {
        "test_collector_native_scaling.py",
        "test_collector_native_scaling_sites.py",
        "test_collector_native_scaling_real.py",
        "test_collector_native_script_scaling.py",
        "test_collector_native_script_deps_scaling.py",
        "test_collector_native_rust_scaling.py",
        "test_collector_native_syntax_scaling.py",
        "test_cli_native_core_scan_large.py",
        "test_cli_native_core_scan_rust.py",
    }
)

# AD-674: the PR tier runs the fast tests of the areas that a change can reach. The first matching
# pattern wins; a changed path that matches no pattern selects every area, so a new directory can
# never run no test. A changed test file always selects its own area (`area_of`).
ALL = "all"
TOUCHES: tuple[tuple[str, tuple[str, ...] | str], ...] = (
    ("tests/test_*.py", ()),
    ("native/python/*", ("native collectors", "collectors")),
    ("native/typescript/*", ("native collectors", "collectors")),
    ("native/dart*/*", ("native collectors", "collectors")),
    ("native/rust/*", ("native collectors", "collectors")),
    ("native/report/*", ("reports", "CLI and core")),
    ("native/*", ("CLI and core", "self-check and CI")),
    ("src/*", ("CLI and core", "self-check and CI")),
    ("schema/*", ("CLI and core", "self-check and CI")),
    ("fixtures/*", ("CLI and core", "collectors")),
    ("tools/*", ("self-check and CI", "reports")),
    ("tests/*", ("self-check and CI",)),
    (".github/*", ("self-check and CI",)),
    ("docs/*", ("self-check and CI",)),
    ("skills/*", ("self-check and CI",)),
    ("*.md", ("self-check and CI",)),
    ("Makefile", ("self-check and CI",)),
    ("pyproject.toml", ALL),
    ("uv.lock", ALL),
    ("*.toml", ("self-check and CI",)),
    ("*.json", ("self-check and CI",)),
)


def is_slow(file_name: str) -> bool:
    return file_name in SLOW_FILES


def areas_of_change(paths: list[str]) -> list[str]:
    """The areas that the changed paths select, in the order of AREAS (AD-674)."""
    chosen: set[str] = set()
    for path in paths:
        name = path.rsplit("/", 1)[-1]
        if path.startswith("tests/test_") and path.endswith(".py"):
            area = area_of(name)
            if area is None:
                return list(AREAS)
            chosen.add(area)
            continue
        rule = next((areas for pattern, areas in TOUCHES if fnmatchcase(path, pattern)), ALL)
        if rule == ALL:
            return list(AREAS)
        chosen.update(rule)
    return [area for area in AREAS if area in chosen]
