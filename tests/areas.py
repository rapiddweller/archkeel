# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Test areas and selections. Each CI test job runs one area; a Make target names a selection."""

from fnmatch import fnmatchcase

# The first area with a matching pattern owns a file, so a specific name comes before its prefix.
# A PR job must take at most about 7 minutes on the slowest runner (AD-341). The same tests took
# up to 2 times as long on one runner as on another, so the summed test time of an area on such a
# runner must stay below about 24 minutes for 4 workers.
AREAS: dict[str, tuple[str, ...]] = {
    "demo catalog": (
        "test_architecture_demo.py",
        "test_demo_catalog_studio.py",
        "test_dual_run.py",
        "test_dual_run_commits.py",
        "test_dual_run_shell.py",
        "test_dual_run_supported_profiles.py",
    ),
    "boundary types": ("test_boundary_*.py",),
    "Python analysis": (
        "test_python_*.py",
        "test_typed_python_*.py",
        "test_inherit*.py",
        "test_analyzer.py",
        "test_binding_*.py",
        "test_classifier_projections.py",
        "test_*member*.py",
        "test_static_*.py",
        "test_absent_import_namespace.py",
        "test_empty_literal_all.py",
        "test_enum_*.py",
        "test_unresolved_call_sites.py",
        "test_native_violation_filter.py",
    ),
    "CLI and Studio": (
        "test_cli_native_profile_limits.py",
        "test_cli_native_core_scan_rust.py",
        "test_cli*.py",
        "test_onboarding*.py",
        "test_init_first_hour.py",
        "test_explore.py",
        "test_studio*.py",
        "test_command_view.py",
        "test_core_command_result.py",
        "test_project_demo_snapshots.py",
    ),
    "contracts and dependency rules": (
        "test_contract_*.py",
        "test_typed_amendment_artifact.py",
        "test_delta*.py",
        "test_known_delta_action_types.py",
        "test_baseline.py",
        "test_bound_amendments.py",
        "test_widening.py",
        "test_ratchets.py",
        "test_rename*.py",
        "test_profile_comparison*.py",
        "test_nullable_profile_measurements.py",
        "test_config.py",
        "test_expectation.py",
        "test_compatibility.py",
        "test_ordering.py",
        "test_diagnostics.py",
        "test_check_diagnostics.py",
        "test_gap_diagnostics.py",
        "test_against_introduction.py",
        "test_review_*.py",
        "test_host_gitlab.py",
        "test_inside_*.py",
        "test_recursive_*.py",
        "test_requires_*.py",
        "test_dependency_*.py",
        "test_exact_*.py",
        "test_public_api_boundary.py",
        "test_module_object_grants.py",
        "test_declared_module_targets.py",
        "test_layers.py",
        "test_cycle_levels.py",
        "test_interfaces.py",
        "test_facade_budgets.py",
        "test_measurement_budgets.py",
        "test_nested_*.py",
        "test_duplication*.py",
        "test_scoped_dependency_proof.py",
        "test_selector_validation_performance.py",
        "test_responsibility_validation.py",
        "test_unknown_positions.py",
    ),
    "typed guards": ("test_typed_*.py",),
    "type and wire guards": (
        "test_*_types.py",
        "test_codec*.py",
        "test_host_memory.py",
    ),
    "native TypeScript collector": ("test_collector_native_*.py",),
    "collectors": (
        "test_collection_capabilities.py",
        "test_typescript_*.py",
        "test_dart_*.py",
        "test_flutter_*.py",
        "test_collector_*.py",
        "test_collection_*.py",
        "test_runtime*.py",
        "test_source_*.py",
        "test_snapshot*.py",
        "test_git_*.py",
        "test_language_collectors.py",
        "test_parallel_execution.py",
        "test_windows_launcher_startup.py",
        "test_file_evidence.py",
        "test_extraction_boundaries.py",
        "test_phase_timings.py",
        "test_state_facts.py",
        "test_model.py",
        "test_identity.py",
        "test_identity_memo.py",
        "test_compute_once_per_run.py",
        "test_bindings.py",
    ),
    "call and catalog rules": (
        "test_call_*.py",
        "test_catalog_*.py",
        "test_guard*.py",
        "test_numeric_*.py",
        "test_*string_*.py",
        "test_construct_*.py",
        "test_protocol_*.py",
        "test_rule_*.py",
    ),
    "reports": (
        "test_report*.py",
        "test_html_report.py",
        "test_atlas_*.py",
        "test_graph_*.py",
        "test_flow*.py",
        "test_uml_*.py",
        "test_terminal*.py",
        "test_findings*.py",
        "test_compass_*.py",
        "test_nest_*.py",
        "test_architecture_*.py",
        "test_module_explore.py",
        "test_structure*.py",
        "test_target_*.py",
        "test_projection_ownership_reuse.py",
        "test_saved_report.py",
        "test_own_uml_target.py",
        "test_ownership.py",
        "test_coverage.py",
        "test_excerpt_parsers.py",
        "test_violations.py",
        "test_trace.py",
    ),
    "self-check and CI": (
        "test_self*.py",
        "test_validation.py",
        "test_schema_drift.py",
        "test_schema_drift_profiles.py",
        "test_result_schema.py",
        "test_decisions.py",
        "test_repository_hygiene.py",
        "test_ir_owners.py",
        "test_make_gate.py",
        "test_ci_budget.py",
        "test_ci_daily.py",
        "test_merge_check.py",
        "test_native_ci.py",
        "test_native_contract_rules.py",
        "test_native_core.py",
        "test_native_forbidden_construct.py",
        "test_native_report.py",
        "test_native_expected_gaps.py",
        "test_native_self_rules.py",
        "test_native_self_contract.py",
        "test_native_self_core_rows.py",
        "test_native_standard_library.py",
        # AD-402: the real compiler of each minor checks the refusal witnesses.
        "test_collector_native_python_compile_sites.py",
        "test_collector_native_python_compiler.py",
        "test_collector_native_python_review.py",
        "test_collector_native_python_review_families.py",
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


PYTHON_COMPAT = "python-compat"

# An entry is a test file or a test id in tests/. Each entry must select a test.
SELECTIONS: dict[str, tuple[str, ...]] = {
    # Each test marked requires_python, plus these files: the analyzer reads source with the `ast`
    # of the running interpreter, and these files cover what differs between versions (#724).
    PYTHON_COMPAT: (
        "test_collector_native_python_bindings.py",
        "test_analyzer.py",
        "test_architecture_projection.py",
        "test_python_provider_sources.py",
        "test_validation.py",
        # AD-388: the pinned standard library equals `sys.stdlib_module_names` of each minor.
        "test_native_standard_library.py",
    ),
}


def selects(entry: str, test_id: str) -> bool:
    """`test_id` is the node id below tests/, for example `test_x.py::test_y[case]`."""
    return test_id == entry or test_id.startswith((f"{entry}::", f"{entry}["))
