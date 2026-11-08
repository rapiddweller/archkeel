# The fixed set of tests that `make pr-test` runs on each PR. Full verification runs every area
# (`make full-test`) and never this list, so Full does not watch this file. Add a test here
# without a change to the Makefile.
PR_TEST_FILES := \
	tests/test_make_gate.py tests/test_native_ci.py tests/test_browser_markers.py tests/test_publish_release.py tests/test_repository_hygiene.py \
	tests/test_responsibility_validation.py tests/test_target_architecture.py tests/test_self.py tests/test_ir_owners.py tests/test_contract_maintenance.py tests/test_skill.py \
	tests/test_contract_model.py tests/test_contract_version_types.py tests/test_dependency_selectors.py tests/test_requires_symbol_ports.py tests/test_typed_dependency_api.py tests/test_dependency_api_target.py tests/test_module_object_grants.py tests/test_dependency_typed_control.py tests/test_typed_state_protocol.py tests/test_typed_python_bindings.py tests/test_typed_python_receivers.py tests/test_typed_method_descriptors.py tests/test_typed_graph_vocabulary.py tests/test_typed_diagnostic_owner.py tests/test_state_facts.py tests/test_boundary_type_nested_mapping.py tests/test_typed_dict_bound_aliases.py tests/test_decisions.py tests/test_typed_python_properties.py tests/test_typed_contract_rule_grammar.py tests/test_typed_contract_rule_native.py tests/test_core_command_result.py tests/test_typed_measurement_controls.py tests/test_typed_parameter_kinds.py tests/test_atlas_deviation_target.py tests/test_definition_context_types.py tests/test_permission_status_types.py tests/test_snapshot_language_types.py tests/test_source_resolution_types.py tests/test_known_delta_action_types.py tests/test_typed_symbol_class_kinds.py tests/test_source_name_visibility.py tests/test_git_blob_types.py tests/test_typed_structure_levels.py tests/test_classifier_projections.py tests/test_unresolved_call_change_types.py \
	tests/test_target_graph.py::test_contract_corpus_preserves_version_and_uml_presence \
	tests/test_report_exploration_reuse.py tests/test_explore.py \
	tests/test_collection_protocol.py tests/test_typed_collector_protocol.py tests/test_typed_collector_native.py tests/test_collector_native_wheel.py tests/test_source_trust_boundary.py tests/test_shared_runtime_bootstrap.py \
	tests/test_python_class_value_proofs.py tests/test_local_inherited_methods.py tests/test_inherited_generic_facade_negative.py tests/test_python_provider_sources.py tests/test_python_contextmanager_signatures.py tests/test_boundary_types_contextmanager.py \
	'tests/test_architecture_demo.py::test_variant_produces_the_catalogued_findings[class-a-inherited-generic-return]' \
	'tests/test_architecture_demo.py::test_variant_produces_the_catalogued_findings[class-a-inherited-generic-undeclared-return]' \
	'tests/test_architecture_demo.py::test_variant_produces_the_catalogued_findings[class-a-inherited-generic-undeclared-batch]' \
	'tests/test_architecture_demo.py::test_variant_produces_the_catalogued_findings[class-a-boundary-types-ordinary-reexport-chain-unknown]' \
	'tests/test_architecture_demo.py::test_variant_produces_the_catalogued_findings[public-api-alias-missing]' \
	'tests/test_architecture_demo.py::test_variant_produces_the_catalogued_findings[public-api-alias-declared]' \
	tests/test_architecture_demo.py::test_stable_ordinary_reexport_proves_source_violation_in_cli_json \
	tests/test_report_rule_evidence_oracle.py::test_unknown_position_is_associated_with_its_rule_not_every_boundary_rule \
	tests/test_typescript_script_globals.py tests/test_typescript_standard_globals.py tests/test_typescript_umd_providers.py tests/test_browser_architecture.py tests/test_source_graph.py tests/test_binding_proof_reuse.py tests/test_shared_lexical_index.py tests/test_namespace_scan_cost.py \
	tests/test_member_escape_prefix_index.py tests/test_collection_boundary_regressions.py tests/test_recursive_boundary_index_work.py tests/test_lexical_resolution.py tests/test_static_instances.py tests/test_module_explore.py tests/test_architecture_owner_characterization.py tests/test_architecture_coverage_characterization.py tests/test_projection_ownership_reuse.py tests/test_dependency_profile_selection.py tests/test_python_crossing_policy.py tests/test_duplication.py tests/test_duplication_call_evidence.py \
	tests/test_boundary_types_chain_proof.py tests/test_boundary_types_reexport_proofs.py tests/test_boundary_types_facades.py tests/test_boundary_types_aliases.py tests/test_boundary_type_recursive_aliases.py \
	tests/test_callable_boundaries.py tests/test_boundary_type_literal_mapping_arms.py tests/test_boundary_type_native_payloads.py tests/test_boundary_types_mappings.py tests/test_boundary_type_native_open_maps.py tests/test_boundary_type_enum_literals.py \
	tests/test_boundary_type_bound_aliases.py::test_opaque_alias_transfer_keeps_source_identity_without_an_exact_permission \
	tests/test_boundary_type_bound_aliases.py::test_redirected_metadata_class_cannot_grant_an_exact_alias_permission \
	tests/test_boundary_type_bound_aliases.py::test_alias_body_separates_source_identity_from_runtime_member_proof \
	tests/test_boundary_type_bound_aliases.py::test_literal_outer_and_sibling_survive_uncertain_alias \
	tests/test_boundary_type_bound_aliases.py::test_uncertain_inner_alias_does_not_erase_exact_literal_outer_map_permission \
	tests/test_boundary_type_bound_aliases.py::test_uncertain_alias_ordinary_permission_is_independent_of_union_order \
	tests/test_typescript_owned_types.py tests/test_typescript_syntax_types.py tests/test_typescript_syntax_compatibility.py tests/test_typescript_json_fields.py tests/test_typescript_control_target.py tests/test_typescript_source_input.py tests/test_typescript_string_constructs.py \
	tests/test_python_source_evidence_lines.py tests/test_definition_source_owners.py tests/test_analyzer.py tests/test_typescript_config.py tests/test_typescript_resolve.py tests/test_typescript_bundler.py tests/test_type_shapes.py \
	tests/test_typescript_array_constants.py \
	tests/test_typescript_decorated_inventory.py \
	tests/test_typescript_parameter_properties.py \
	tests/test_uml_comparison.py tests/test_saved_report.py tests/test_architecture_projection.py tests/test_cli.py tests/test_cli_view.py tests/test_cli_view_show.py tests/test_cli_story.py tests/test_studio.py tests/test_studio_chat.py tests/test_studio_launcher.py tests/test_cli_typed_inputs.py tests/test_cli_input_target.py \
	tests/test_member_inventory.py tests/test_partial_member_inventory.py \
	tests/test_report_recorded_unknowns.py \
	tests/test_report_agent_json.py \
	tests/test_native_violation_filter.py \
	tests/test_scoped_dependency_proof.py \
	tests/test_call_owner_policy.py tests/test_call_owner_source_facts.py tests/test_call_owner_wire_compatibility.py tests/test_call_scope_receipt_identity.py \
	tests/test_call_owner_scan_completeness.py tests/test_call_argument_scan_completeness.py \
	tests/test_call_argument_policy.py tests/test_call_argument_binding.py \
	tests/test_call_owner_native_proof_regressions.py \
	tests/test_numeric_operand_rule.py tests/test_numeric_operand_observation.py tests/test_protocol_declarations.py \
	tests/test_source_ownership_policy.py \
	tests/test_catalog_policy_native.py tests/test_catalog_policy_scan_completeness.py \
	tests/test_guard_paths.py tests/test_guarded_effect_contract.py tests/test_guarded_effect_evaluation.py \
	tests/test_guarded_effect_facts.py tests/test_guarded_effect_saved_report.py tests/test_guarded_effect_source.py \
	tests/test_guarded_effect_wire_compatibility.py tests/test_guarded_effect_source_validation.py \
	tests/test_guarded_effect_scan_completeness.py \
	tests/test_protocol_conditional_identity.py \
	tests/test_typescript_namespace_identities.py \
	tests/test_result_schema.py \
	tests/test_construct_selectors.py \
	tests/test_source_facts_columnar.py \
	tests/test_selector_validation_performance.py \
	tests/test_dart_parse.py tests/test_dart_snapshot.py tests/test_dart_resolve.py \
	tests/test_dart_typed_controls.py tests/test_dart_local_callable_shadowing.py \
	tests/test_dart_sdk_free.py tests/test_dart_inner_collect.py tests/test_dart_target.py \
	tests/test_dart_uml_acceptance.py::test_checkout_cli_report_fulfills_independent_target \
	tests/test_dart_unknowns.py::test_no_show_import_hiding_a_real_crossing_is_unknown_not_pass \
	tests/test_flutter_demo.py::test_flutter_target_has_agent_owned_responsibilities_and_closed_permissions \
	tests/test_flutter_demo.py::test_flutter_mutations_keep_target_identical_and_change_only_dart_sources \
	tests/test_flutter_demo.py::test_flutter_variant_reports_keep_pass_fail_unknown_and_coverage_distinct \
	tests/test_flutter_demo.py::test_flutter_target_owns_three_meaningful_component_levels_and_all_modules \
	tests/test_flutter_demo.py::test_flutter_target_pins_journey_signatures_member_scopes_and_flutter_inheritance \
	tests/test_runtime.py \
	tests/test_codec.py tests/test_codec_compatibility.py tests/test_source_provenance_acceptance.py \
	tests/test_collection_process.py tests/test_collection_conformance.py tests/test_schema_drift.py \
	tests/test_runtime_delta.py tests/test_delta_version_types.py tests/test_comparison_support_types.py tests/test_nullable_profile_measurements.py tests/test_source_section_types.py tests/test_graph_topology_level_types.py \
	tests/test_collection_runtime_gate.py tests/test_ratchets.py tests/test_model.py tests/test_trace.py tests/test_violations.py \
	tests/test_typescript_demo.py tests/test_onboarding_guidance.py \
	tests/test_references.py tests/test_levels.py tests/test_recursive_inside_contracts.py tests/test_widening.py tests/test_measurement_budgets.py tests/test_typed_amendment_artifact.py \
	tests/test_onboarding.py tests/test_terminal.py tests/test_summary_badge_types.py tests/test_summary_badge_target.py \
	tests/test_onboarding_demo.py tests/test_pypi_description.py tests/test_typescript_onboarding.py \
	tests/test_unknown_positions.py tests/test_inside_rule_coverage.py tests/test_inside_rule_parity.py tests/test_report_rule_evidence.py \
	tests/test_target_navigation_graph.py \
	tests/test_annotation_carriers.py \
	tests/test_absent_import_namespace.py tests/test_dynamic_dependency_policy.py tests/test_string_comparison_observation.py tests/test_local_string_comparisons.py tests/test_string_predicate_observation.py tests/test_python_string_predicate_target.py tests/test_typed_host_events.py \
	tests/test_empty_literal_all.py tests/test_review_workflow_fixture.py tests/test_contract_edits.py tests/test_collector_real_world_shapes.py tests/test_rule_driven_collection.py tests/test_findings.py tests/test_contract_provenance.py
