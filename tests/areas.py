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
    "core scans": (
        "test_cli_native_core_scan*.py",
        "test_native_core.py",
        "test_native_self_*.py",
    ),
    "CLI and core": (
        "test_cli*.py",
        "test_core_guide.py",
        "test_explorer_*.py",
        "test_native_interface_boundary.py",
        "test_project_demo_snapshots.py",
    ),
    # #2148: the impl oracle (20 summed minutes) has its own job. The PR tier needs one light test
    # in each area, so the three tests of `first_difference` come with it.
    "native impl oracle": (
        "test_collector_native_rust_impl_oracle.py",
        "test_collector_native_python_first_difference.py",
    ),
    "native collector evidence": (
        "test_collector_native_catalog.py",
        "test_collector_native_rust*.py",
        "test_collector_native_scaling_sites.py",
    ),
    "native collectors": ("test_collector_native_*.py",),
    "collectors": (
        "test_typescript_*.py",
        "test_collector_*.py",
        "test_parallel_execution.py",
    ),
    "reports": ("test_report*.py", "test_flow*.py"),
    "self-check and CI": (
        "test_area_selection.py",
        "test_native_touched.py",
        "test_pr_report.py",
        "test_timeout_support.py",
        "test_core_cache.py",
        "test_doc_migration_guide.py",
        "test_fetch_history.py",
        "test_make_gate.py",
        "test_oracle_guard.py",
        "test_main_build.py",
        "test_make_self_check.py",
        "test_self_check_gate.py",
        "test_self_check_summary.py",
        "test_ci_budget.py",
        "test_ci_failure_summary.py",
        "test_phase_timings.py",
        "test_ci_daily.py",
        "test_native_ci.py",
        "test_native_report.py",
        "test_native_standard_library.py",
        "test_native_versions.py",
        "test_rust_*.py",
        "test_browser_*.py",
        "test_publish_release.py",
        "test_system_parts.py",
        "test_pypi_description.py",
        "test_shipped_skills.py",
        "test_skill.py",
        "test_story_install.py",
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
        "test_collector_native_script_scaling.py",
        "test_collector_native_rust_scaling.py",
        "test_cli_native_core_scan_large.py",
        "test_cli_native_core_scan_rust.py",
        "test_cli_phase_timings_reference.py",
        "test_collector_native_rust_impl_oracle.py",
    }
)

# AD-674: files that a PR gate of 3 minutes cannot afford. Each took 8 s or more of summed
# test time in the full run of 2026-11-16, or builds a workspace copy. The main tier runs them;
# the PR tier does not.
HEAVY_FILES = frozenset(
    {
        "test_cli_baseline.py",
        "test_cli_boundary_types.py",
        "test_cli_core_contract_hygiene.py",
        "test_cli_core_inside_trees.py",
        "test_cli_core_ts_config_dropped.py",
        "test_cli_core_uml_symbols.py",
        "test_cli_installed_wheel.py",
        "test_cli_native_core_scan_work.py",
        "test_cli_native_dart_imports.py",
        "test_cli_native_global_code.py",
        "test_cli_native_global_forms.py",
        "test_cli_native_global_writes.py",
        "test_cli_native_python_imports.py",
        "test_cli_native_python_indirect.py",
        "test_cli_string_import.py",
        "test_cli_native_python_reexport.py",
        "test_cli_native_rust_resolved_call.py",
        "test_cli_native_rust_resolved_call_closed.py",
        "test_cli_native_rust_resolved_call_globals.py",
        "test_cli_native_rust_selected_eq_edge.py",
        "test_cli_native_ts_reference_types.py",
        "test_cli_native_type_publication.py",
        "test_cli_python_interface.py",
        "test_cli_python_profile_limits.py",
        "test_cli_python_review_plants.py",
        "test_cli_python_sites.py",
        "test_cli_python_symbols.py",
        "test_cli_python_syspath.py",
        "test_cli_report_output.py",
        "test_cli_report_topology.py",
        # The main tier builds the core and fills the registry for the offline Serde witness.
        "test_collector_false_pass_rust_serde_dispatch.py",
        "test_collector_native_digest.py",
        "test_collector_native_records.py",
        "test_collector_native_rust_definitions_oracle.py",
        "test_collector_native_rust_impl_oracle.py",
        "test_collector_native_rust_module_oracle.py",
        "test_collector_native_rust_oracle.py",
        "test_collector_native_rust_receivers_compiled.py",
        "test_collector_native_rust_unextracted.py",
        "test_native_report.py",
        "test_native_self_core_rows.py",
        "test_parallel_execution.py",
    }
)

# AD-674: the PR tier runs the fast tests of the areas that a change can reach. The first matching
# pattern wins; a changed path that matches no pattern selects every area, so a new directory can
# never run no test. A changed test file always selects its own area (`area_of`).
ALL = "all"
TOUCHES: tuple[tuple[str, tuple[str, ...] | str], ...] = (
    ("tests/test_*.py", ()),
    ("native/report/*", ("core scans", "CLI and core", "reports")),
    ("studio/*", ("core scans", "CLI and core", "reports", "self-check and CI")),
    ("native/*", ALL),
    ("src/archkeel/cli/*", ALL),
    ("src/*", ("core scans", "CLI and core", "self-check and CI")),
    ("schema/*", ("core scans", "CLI and core", "self-check and CI")),
    ("fixtures/*", ("core scans", "CLI and core", "collectors")),
    ("tools/*", ("self-check and CI", "reports")),
    # AD-736: a shared helper of the tests and the area table can change any area.
    ("tests/conftest.py", ALL),
    ("tests/areas.py", ALL),
    ("tools/select_areas.py", ALL),
    (".github/workflows/area-checks.yml", ALL),
    (".github/workflows/ci.yml", ALL),
    (".github/workflows/pr-gate.yml", ALL),
    ("tests/*_support.py", ALL),
    ("tests/*_plants.py", ALL),
    ("tests/*", ("self-check and CI",)),
    (".github/*", ("self-check and CI",)),
    ("docs/*", ("self-check and CI",)),
    ("skills/*", ("self-check and CI",)),
    ("*.md", ("self-check and CI",)),
    ("Makefile", ALL),
    ("pyproject.toml", ALL),
    ("uv.lock", ALL),
    ("*.toml", ("self-check and CI",)),
    ("*.json", ("self-check and CI",)),
)


def is_slow(file_name: str) -> bool:
    return file_name in SLOW_FILES


def is_heavy(file_name: str) -> bool:
    return file_name in HEAVY_FILES


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


GATE_FILES = frozenset(
    {
        "Makefile",
        "tests/areas.py",
        "tools/select_areas.py",
        ".github/workflows/area-checks.yml",
        ".github/workflows/ci.yml",
        ".github/workflows/pr-gate.yml",
    }
)


def rust_checks(paths: list[str]) -> bool:
    return any(path.startswith("native/") or path in GATE_FILES for path in paths)


# AD-1062: a change to these paths can change the result of a real project, so the PR gate fetches
# the pinned sources of the real-project fixtures (`fixtures/matrix.json`). Native Python and Dart
# collectors live under `native/`; no Python collector remains.
FETCH_FILES = frozenset(
    {
        "tools/fixture_source.py",
        "tools/fixture_tree.py",
        "tools/report_gallery.py",
        "tests/test_cli_fixture_matrix.py",
        ".github/workflows/area-checks.yml",
    }
)


def fetch_sources(paths: list[str]) -> bool:
    return any(path.startswith(("native/", "fixtures/")) or path in FETCH_FILES for path in paths)


def parallel_areas(paths: list[str]) -> list[str]:
    return areas_of_change(paths) or ["self-check and CI"]
