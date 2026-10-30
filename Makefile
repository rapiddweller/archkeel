.DEFAULT_GOAL := check
UV ?= uv
DART_EXECUTABLE ?= dart
FLUTTER_EXECUTABLE ?= flutter

.PHONY: demos against gate full-test ci ci-check ci-core-check ci-pr-check ci-pr-static ci-pr-report-check pr-test pr-report-test ci-typescript ci-artifacts-clean mermaid check test collector-safety python-compat typescript-native typescript-compiler-check dart-test lint typecheck self-validate self-observation demo demo-onboarding demo-dart demo-typescript demo-architecture demo-uml demo-screenshots browser-install report-browser-tests report-pages plugin plugin-release build smoke release-check architecture-graph-schema report-timing flutter-demo-check browser-runtime-install browser-runtime-generate browser-runtime-check typescript-libs-check browser-graph-generate browser-graph-check browser-architecture-check

# SKIP_TESTS=1: skip the test suite here; Full verification runs it in area jobs (make full-test).
check: lint typecheck browser-architecture-check $(if $(strip $(SKIP_TESTS)),,test)

# These stages consume the previous stage's success, even with make -j.
.NOTPARALLEL: gate full-test release-check ci ci-check ci-core-check ci-pr-check ci-pr-static ci-pr-report-check

gate: $(if $(strip $(BASE)),against,self-validate) release-check

release-check: check build smoke

ci: ci-check mermaid

ci-check: ci-artifacts-clean ci-core-check report-timing

ci-core-check: PYTEST_STOP := --maxfail=1
ci-core-check: gate typescript-compiler-check browser-graph-check ci-typescript browser-runtime-check typescript-libs-check

# One area of the full suite (tests/areas.py); Full verification runs every area in parallel.
full-test: TEST_WORKERS = 4
full-test: browser-runtime-install test

ci-pr-check: ci-pr-static pr-test

ci-pr-static: $(if $(strip $(BASE)),against,self-validate) lint typecheck browser-architecture-check

ci-pr-report-check: browser-runtime-check browser-graph-check pr-report-test

pr-test: browser-runtime-install
	$(UV) run --locked python -m pytest -n 4 --dist=loadgroup --max-worker-restart=0 \
		-q --durations=10 --junitxml=test-artifacts/pytest/pr-core.xml $(if $(AREA),--area="$(AREA)",) \
		tests/test_make_gate.py tests/test_browser_markers.py tests/test_publish_release.py tests/test_repository_hygiene.py \
		tests/test_responsibility_validation.py tests/test_target_architecture.py tests/test_self.py tests/test_contract_maintenance.py tests/test_skill.py \
		tests/test_contract_model.py tests/test_contract_version_types.py tests/test_dependency_selectors.py tests/test_requires_symbol_ports.py tests/test_typed_dependency_api.py tests/test_dependency_api_target.py tests/test_module_object_grants.py tests/test_dependency_typed_control.py tests/test_typed_state_protocol.py tests/test_typed_python_bindings.py tests/test_typed_python_receivers.py tests/test_typed_method_descriptors.py tests/test_typed_graph_vocabulary.py tests/test_typed_diagnostic_owner.py tests/test_state_facts.py tests/test_boundary_type_nested_mapping.py tests/test_typed_dict_bound_aliases.py tests/test_decisions.py tests/test_typed_python_properties.py tests/test_typed_contract_rule_grammar.py tests/test_typed_contract_rule_native.py tests/test_core_command_result.py tests/test_typed_measurement_controls.py tests/test_typed_parameter_kinds.py tests/test_atlas_deviation_target.py tests/test_definition_context_types.py tests/test_permission_status_types.py tests/test_snapshot_language_types.py tests/test_source_resolution_types.py tests/test_known_delta_action_types.py tests/test_typed_symbol_class_kinds.py tests/test_source_name_visibility.py tests/test_git_blob_types.py tests/test_typed_structure_levels.py tests/test_classifier_projections.py tests/test_unresolved_call_change_types.py \
		tests/test_target_graph.py::test_contract_corpus_preserves_version_and_uml_presence \
		tests/test_report_exploration_reuse.py \
		tests/test_collection_protocol.py tests/test_typed_collector_protocol.py tests/test_typed_collector_native.py tests/test_source_trust_boundary.py tests/test_shared_runtime_bootstrap.py \
		tests/test_python_class_value_proofs.py tests/test_local_inherited_methods.py tests/test_inherited_generic_facade_negative.py tests/test_python_provider_sources.py tests/test_python_contextmanager_signatures.py tests/test_boundary_types_contextmanager.py \
		'tests/test_architecture_demo.py::test_variant_produces_the_catalogued_findings[class-a-inherited-generic-return]' \
		'tests/test_architecture_demo.py::test_variant_produces_the_catalogued_findings[class-a-inherited-generic-undeclared-return]' \
		'tests/test_architecture_demo.py::test_variant_produces_the_catalogued_findings[class-a-inherited-generic-undeclared-batch]' \
		'tests/test_architecture_demo.py::test_variant_produces_the_catalogued_findings[class-a-boundary-types-ordinary-reexport-chain-unknown]' \
		'tests/test_architecture_demo.py::test_variant_produces_the_catalogued_findings[public-api-alias-missing]' \
		'tests/test_architecture_demo.py::test_variant_produces_the_catalogued_findings[public-api-alias-declared]' \
		tests/test_architecture_demo.py::test_stable_ordinary_reexport_proves_source_violation_in_cli_json \
		tests/test_report_159_160_e2e_oracle.py::test_unknown_position_is_associated_with_its_rule_not_every_boundary_rule \
		tests/test_typescript_script_globals.py tests/test_typescript_standard_globals.py tests/test_typescript_umd_providers.py tests/test_browser_architecture.py tests/test_source_graph.py tests/test_binding_proof_reuse.py tests/test_shared_lexical_index.py tests/test_namespace_scan_cost.py \
		tests/test_member_escape_prefix_index.py tests/test_collection_boundary_regressions.py tests/test_recursive_boundary_index_work.py tests/test_lexical_resolution.py tests/test_static_instances.py tests/test_module_explore.py tests/test_projection_ownership_reuse.py tests/test_dependency_profile_selection.py tests/test_python_crossing_policy.py tests/test_duplication.py tests/test_duplication_call_evidence.py \
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
		tests/test_uml_comparison.py tests/test_saved_report.py tests/test_architecture_projection.py tests/test_cli.py tests/test_cli_typed_inputs.py tests/test_cli_input_target.py \
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
		tests/test_unknown_positions.py tests/test_inside_rule_coverage.py tests/test_inside_rule_parity.py tests/test_report_159_160.py \
		tests/test_target_navigation_graph.py \
		tests/test_annotation_carriers.py \
		tests/test_absent_import_namespace.py tests/test_dynamic_dependency_policy.py tests/test_string_comparison_observation.py tests/test_local_string_comparisons.py tests/test_string_predicate_observation.py tests/test_python_string_predicate_target.py tests/test_typed_host_events.py \
		tests/test_empty_literal_all.py tests/test_review_workflow_fixture.py tests/test_contract_edits.py tests/test_collector_real_world_shapes.py tests/test_rule_driven_collection.py tests/test_findings.py tests/test_contract_provenance.py

pr-report-test:
	$(UV) run --locked python -m pytest -n 2 --dist=loadfile --max-worker-restart=0 -q \
		--junitxml=test-artifacts/pytest/pr-report.xml \
		tests/test_graph_scene_protocol.py tests/test_atlas_deviation_boundary.py tests/test_report_renderer_units.py

ci-typescript: OUTPUT := test-artifacts/typescript-demo
ci-typescript: demo-typescript

ci-artifacts-clean:
	rm -rf test-artifacts/typescript-demo test-artifacts/report-browser test-artifacts/report-timing

mermaid:
	@set -eu; mermaid_dir=$$(mktemp -d); \
		trap 'rm -rf "$$mermaid_dir"' 0; \
		python3 tools/mermaid_blocks.py --write "$$mermaid_dir"; \
		printf '{"args": ["--no-sandbox"]}\n' > "$$mermaid_dir/puppeteer-config.json"; \
		fail=0; \
		for mmd in "$$mermaid_dir"/*.mmd; do \
			[ -f "$$mmd" ] || continue; \
			number=$$(basename "$$mmd" .mmd); \
			location=$$(awk -F'\t' -v n="$$number" '$$1 == n { print $$2 }' "$$mermaid_dir/index.txt"); \
			if ! npx --yes @mermaid-js/mermaid-cli@11.17.0 -p "$$mermaid_dir/puppeteer-config.json" -i "$$mmd" -o "$$mmd.svg"; then \
				echo "::error::$$location: mermaid-cli failed to render this block"; \
				fail=1; \
			fi; \
		done; \
		exit "$$fail"

against: BASE ?= origin/main
against:
	$(UV) run --locked python -m tools.against --base "$(BASE)"

self-validate:
	@mkdir -p test-artifacts/validation
	@$(UV) run --locked archkeel validate --root . --baseline architecture-baseline.json --json > test-artifacts/validation/result.json || { cat test-artifacts/validation/result.json; exit 1; }
	@python3 -c 'import json; d=json.load(open("test-artifacts/validation/result.json")); print("Architecture rules: %s; diagnostics: %s; full result: test-artifacts/validation/result.json" % (d["declared_rules"], len(d["diagnostics"])))'

TEST_WORKERS ?= 2

test:
	$(UV) run --locked $(PYTEST_EXTRA) python -m pytest -n $(TEST_WORKERS) --dist=loadgroup --max-worker-restart=0 \
		-q $(PYTEST_STOP) --durations=20 --junitxml=test-artifacts/pytest/results.xml \
		$(if $(AREA),--area="$(AREA)",)

# The Python analyzer reads source with the `ast` of the running interpreter: these files cover what
# differs between Python versions. The nightly job runs them on the newest versions (#724).
PYTHON_COMPAT_TESTS = tests/test_analyzer.py tests/test_python_provider_sources.py \
	tests/test_python_contextmanager_signatures.py tests/test_boundary_types_contextmanager.py \
	tests/test_python_source_evidence_lines.py tests/test_typed_python_receivers.py \
	tests/test_python_class_value_proofs.py tests/test_numeric_operand_observation.py \
	tests/test_architecture_projection.py tests/test_validation.py

python-compat:
	$(UV) run --locked python -m pytest -n $(TEST_WORKERS) --dist=loadfile --max-worker-restart=0 \
		-q --durations=10 $(PYTHON_COMPAT_TESTS)

collector-safety:
	$(UV) run --locked python -m pytest -q tests/test_collection_protocol.py tests/test_typed_collector_protocol.py tests/test_typed_collector_native.py \
		tests/test_collection_process.py tests/test_collection_runtime_gate.py \
		tests/test_runtime.py tests/test_source_trust_boundary.py \
		tests/test_collector_interrupt.py tests/test_windows_launcher_startup.py \
		tests/test_collector_safety_acceptance.py tests/test_collector_liveness_observer.py \
		tests/test_inheritance_proof_transport.py
typescript-compiler-check:
	npx --yes --package typescript@5.9.3 tsc --noEmit --project fixtures/H-uml-typescript/tsconfig.json

# Python implementation architecture is covered by make test, once on Linux in CI.
typescript-native: browser-runtime-install
	$(UV) run --locked python -m pytest -n $(TEST_WORKERS) --dist=loadfile --max-worker-restart=0 \
		-q --durations=10 tests/test_typescript_parse.py \
		tests/test_typescript_inner.py tests/test_typescript_uml_acceptance.py \
		tests/test_typescript_namespace_identities.py \
		tests/test_typescript_collect.py tests/test_typescript_owned_types.py tests/test_typescript_syntax_types.py tests/test_typescript_syntax_compatibility.py tests/test_typescript_source_input.py \
		tests/test_typescript_script_globals.py tests/test_typescript_standard_globals.py tests/test_typescript_umd_providers.py \
		tests/test_browser_architecture.py::test_browser_runner_serializes_windows_config_as_a_posix_port \
		tests/test_typescript_json_fields.py tests/test_typescript_config.py tests/test_typescript_string_constructs.py \
		tests/test_typescript_config_reference.py \
		tests/test_typescript_resolve.py tests/test_typescript_bundler.py tests/test_typescript_provenance.py \
		tests/test_typescript_init_acceptance.py tests/test_typescript_demo.py

dart-test:
	$(UV) run --locked python -m pytest -n $(TEST_WORKERS) --dist=worksteal --max-worker-restart=0 \
		-q --durations=10 tests/test_dart_*.py \
		tests/test_uml_source_facts.py tests/test_language_collectors.py \
		tests/test_flutter_demo.py::test_flutter_variant_reports_keep_pass_fail_unknown_and_coverage_distinct

LINT_PATHS := src tests tools/mermaid_blocks.py \
	tools/report_pages.py tools/package_plugin.py tools/against.py \
	fixtures/reproduce_milestone1.py fixtures/reproduce_onboarding.py \
	fixtures/reproduce_dart.py fixtures/reproduce_snapshot_check.py fixtures/consume_result.py \
	fixtures/reproduce_typescript.py \
	fixtures/architecture_demo.py fixtures/demo_catalog_*.py \
	tools/architecture_graph_schema.py tools/report_timing.py tools/browser_runtime.py tools/browser_graph_protocol.py tools/browser_architecture.py tools/publish_release.py tools/typescript_libs.py

# The same commit measured 80-96s on hosted runners; allow for runner noise.
REPORT_MAX_SECONDS ?= 190
report-timing:
	$(UV) run --locked python -m tools.report_timing --max-seconds "$(REPORT_MAX_SECONDS)"

# Builds the demo gallery in test-artifacts/pages; Full publishes this same build.
demos:
	rm -rf test-artifacts/pages
	$(UV) run --locked python -m tools.report_pages

report-pages: report-timing demos
	cp test-artifacts/report-timing/architecture.json test-artifacts/report-timing/architecture.report.html \
		test-artifacts/report-timing/architecture.detail*.html test-artifacts/pages/

architecture-graph-schema:
	$(UV) run --locked python -m tools.architecture_graph_schema schema/architecture-graph.schema.json --contract schema/architecture-contract.schema.json --contract schema/architecture-contract-3.0.schema.json --contract schema/architecture-contract-3.1.schema.json --contract schema/architecture-contract-3.2.schema.json --contract schema/architecture-contract-3.3.schema.json --contract schema/architecture-contract-3.4.schema.json --contract schema/architecture-contract-3.5.schema.json --contract schema/architecture-contract-3.6.schema.json --contract schema/architecture-contract-3.7.schema.json --contract schema/architecture-contract-3.8.schema.json --contract schema/architecture-contract-3.9.schema.json --contract schema/architecture-contract-3.10.schema.json --contract schema/architecture-contract-3.11.schema.json --contract schema/architecture-contract-3.12.schema.json --contract schema/architecture-contract-3.13.schema.json --contract schema/architecture-contract-3.14.schema.json --comparison schema/architecture-comparison.schema.json --report schema/architecture-report.schema.json --source-inventory schema/source-member-inventory.schema.json --source-profile schema/architecture-ir-python-decoded.schema.json --projection schema/architecture-projection.schema.json --command schema/architecture-command-2.0.schema.json

lint:
	$(UV) run --locked ruff format --check $(LINT_PATHS)
	$(UV) run --locked ruff check $(LINT_PATHS)

typecheck:
	$(UV) run --locked mypy src/archkeel tools/against.py tools/architecture_graph_schema.py tools/report_timing.py tools/browser_architecture.py tools/publish_release.py

self-observation:
	$(UV) run --locked archkeel report --root . --output test-artifacts/self-observation/architecture.json

demo:
	@$(UV) run --locked python fixtures/reproduce_milestone1.py $(if $(OUTPUT),--output "$(OUTPUT)") --summary

demo-onboarding:
	@$(UV) run --locked python -m fixtures.reproduce_onboarding

demo-dart:
	@$(UV) run --locked python -m fixtures.reproduce_dart

flutter-demo-check:
	@command -v "$(FLUTTER_EXECUTABLE)" >/dev/null 2>&1 || test -x "$(FLUTTER_EXECUTABLE)" || { echo "Flutter SDK not found: $(FLUTTER_EXECUTABLE)"; exit 2; }
	@command -v "$(DART_EXECUTABLE)" >/dev/null 2>&1 || test -x "$(DART_EXECUTABLE)" || { echo "Dart SDK not found: $(DART_EXECUTABLE)"; exit 2; }
	"$(FLUTTER_EXECUTABLE)" --version --machine
	"$(DART_EXECUTABLE)" --version
	cd fixtures/I-flutter-shop && "$(FLUTTER_EXECUTABLE)" pub get
	"$(DART_EXECUTABLE)" format --output=none --set-exit-if-changed fixtures/I-flutter-shop/lib fixtures/I-flutter-shop/test
	cd fixtures/I-flutter-shop && "$(FLUTTER_EXECUTABLE)" analyze
	cd fixtures/I-flutter-shop && "$(FLUTTER_EXECUTABLE)" test
	cd fixtures/I-flutter-shop && "$(FLUTTER_EXECUTABLE)" build web --output "$(abspath test-artifacts/flutter-demo/web)"

demo-typescript:
	@$(UV) run --locked python -m fixtures.reproduce_typescript $(if $(OUTPUT),--output "$(OUTPUT)")

demo-architecture:
	@test -n "$(VARIANT)" || { echo "VARIANT is required"; exit 2; }
	@test -n "$(OUTPUT)" || { echo "OUTPUT is required"; exit 2; }
	@$(UV) run --locked python -m fixtures.architecture_demo --replay "$(VARIANT)" --output "$(OUTPUT)"

demo-uml: typescript-compiler-check
	@test -n "$(OUTPUT)" || { echo "OUTPUT is required"; exit 2; }
	@$(UV) run --locked python -m fixtures.architecture_demo --uml-suite --output "$(OUTPUT)"

demo-screenshots:
	@test -n "$(OUTPUT)" || { echo "OUTPUT is required"; exit 2; }
	@$(MAKE) demo OUTPUT="$(OUTPUT)"
	@set -e; for case in A B C; do \
		firefox --headless --no-remote --window-size 1440,1000 \
		  --screenshot "$(OUTPUT)/$$case-check-1440x1000.png" \
		  "file://$(abspath $(OUTPUT))/$$case-check.stdout.check.html"; \
	done
	@firefox --headless --no-remote --window-size 375,2400 \
	  --screenshot "$(OUTPUT)/A-check-375x2400.png" \
	  "file://$(abspath $(OUTPUT))/A-check.stdout.check.html"
	@printf 'Screenshots: %s\n' "$(abspath $(OUTPUT))"

PLAYWRIGHT_VERSION ?= 1.62.0

browser-install:
	$(UV) run --locked --with playwright==$(PLAYWRIGHT_VERSION) python -m playwright install --with-deps chromium

plugin:
	@test -n "$(OUTPUT)" || { echo "OUTPUT is required"; exit 2; }
	$(UV) run --locked python -m tools.package_plugin "$(OUTPUT)"

plugin-release:
	@test -n "$(VERSION)" || { echo "VERSION is required"; exit 2; }
	$(UV) run --locked python -m tools.package_plugin --release-version "$(VERSION)" --expected-version "$(VERSION)" "build/plugin-release/archkeel-plugin-$(VERSION)"
	$(UV) run --locked python -m tools.package_plugin --check --release-version "$(VERSION)" --expected-version "$(VERSION)" "build/plugin-release/archkeel-plugin-$(VERSION).zip"

report-browser-tests: browser-install
	$(UV) run --locked --with playwright==$(PLAYWRIGHT_VERSION) python -m pytest -m browser -n 2 --dist=loadfile --max-worker-restart=0 -q

# Twine validates PyPI metadata; it is a build-only tool.
build:
	$(UV) build --no-sources --clear
	$(UV) tool run --from twine==7.0.0 twine check --strict dist/*

smoke:
	$(UV) run --isolated --no-project --with dist/*.whl tests/smoke_test.py
	$(UV) run --isolated --no-project --with dist/*.tar.gz tests/smoke_test.py

# Development publication only; reports and Python package builds load committed assets.
browser-runtime-install:
	npm ci --prefix tools/browser-runtime --ignore-scripts --no-audit --no-fund
	$(UV) run --locked python -m tools.browser_runtime --prepare-dependencies

browser-runtime-generate: browser-runtime-install
	uv run --locked python -m tools.browser_runtime

browser-runtime-check: browser-runtime-install
	uv run --locked mypy --strict tools/browser_runtime.py
	uv run --locked python -m tools.browser_runtime --check
	uv run --locked python -m pytest -q tests/test_flow_runtime_publication.py

typescript-libs-check: browser-runtime-install
	$(UV) run --locked mypy --strict tools/typescript_libs.py
	$(UV) run --locked python -m tools.typescript_libs --check

browser-architecture-check: browser-runtime-install
	$(UV) run --locked python -m tools.browser_architecture

BROWSER_GRAPH_PROTOCOL := src/archkeel/render/assets/report-graph-vocabulary.ts src/archkeel/render/assets/report-graph-schema.ts
BROWSER_GRAPH_COMPILER := node tools/browser-runtime/node_modules/typescript/bin/tsc --strict --target ES2022 --module none --newLine lf

browser-graph-generate: browser-runtime-install
	$(UV) run --locked python -m tools.browser_graph_protocol
	$(BROWSER_GRAPH_COMPILER) --outFile src/archkeel/render/assets/report-graph-protocol.js $(BROWSER_GRAPH_PROTOCOL)
	cat tools/browser-runtime/protocol-exports.js >> src/archkeel/render/assets/report-graph-protocol.js
	$(BROWSER_GRAPH_COMPILER) --declaration --emitDeclarationOnly --outFile src/archkeel/render/assets/report-graph-protocol.types.d.ts $(BROWSER_GRAPH_PROTOCOL)
	cat tools/browser-runtime/protocol-exports.types.d.ts >> src/archkeel/render/assets/report-graph-protocol.types.d.ts

browser-graph-check: browser-runtime-install
	$(UV) run --locked mypy --strict tools/browser_graph_protocol.py
	$(UV) run --locked python -m tools.browser_graph_protocol --check
	@set -e; browser_graph_stage=$$(mktemp -d); \
		trap 'rm -rf "$$browser_graph_stage"' EXIT; \
		$(BROWSER_GRAPH_COMPILER) --outFile "$$browser_graph_stage/protocol.js" $(BROWSER_GRAPH_PROTOCOL); \
		cat tools/browser-runtime/protocol-exports.js >> "$$browser_graph_stage/protocol.js"; \
		cmp src/archkeel/render/assets/report-graph-protocol.js "$$browser_graph_stage/protocol.js"; \
		$(BROWSER_GRAPH_COMPILER) --declaration --emitDeclarationOnly --outFile "$$browser_graph_stage/protocol.types.d.ts" $(BROWSER_GRAPH_PROTOCOL); \
		cat tools/browser-runtime/protocol-exports.types.d.ts >> "$$browser_graph_stage/protocol.types.d.ts"; \
		cmp src/archkeel/render/assets/report-graph-protocol.types.d.ts "$$browser_graph_stage/protocol.types.d.ts"
	$(BROWSER_GRAPH_COMPILER) --module esnext --moduleResolution node --moduleSuffixes .types, --allowJs --checkJs --noEmit src/archkeel/render/assets/report-graph-scene.js tests/browser_graph_scene_target.ts src/archkeel/render/assets/report-atlas-deviations.js
