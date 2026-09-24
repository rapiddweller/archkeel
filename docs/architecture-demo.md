# Architecture demo catalog

Generated from `fixtures/architecture_demo.py`'s `CATALOG`. Every checkable item in the decision
records under `docs/architecture/decisions/` (indexed by `docs/architecture/archkeel.md`, AD-11) has
one row below: a named variant, the rule ids and diagnostic codes (AD-12) it must produce, and
either the shop sample files it changes or the existing evidence that demonstrates it instead.
Regenerate with `python -m fixtures.architecture_demo --markdown`.

The `showcase` row below (`tour`) is the default demo view: it applies many overlays at once so one
run shows many violations together; every other row isolates one item.

Rows whose item starts with `dart:` run on `fixtures/G-dart`, a Flutter-style package scanned with
`language = "dart"` (AD-97); `dart-tour` is their showcase. Replay them as one story with `make
demo-dart`.

| Section | Item | Variant | Demo | Rule ids | Diagnostic codes | Evidence / files |
|---|---|---|---|---|---|---|
| showcase | tour | tour | validate/report run | APP-TYPES-NOT-DICT, ASSIGNMENT-COMPLETE, COMPONENT-NO-CYCLES, CONSTRUCT-NO-ANY, CONSTRUCT-NO-ASSERT, CONSTRUCT-NO-BROAD-EXCEPT, CONSTRUCT-NO-DYNAMIC, CONSTRUCT-NO-DYNAMIC, DEP-APP-NO-STORE-BACKEND, DEP-APP-NO-STORE-SQLITE, DEP-MODEL-NO-RENDER, DEP-RENDER-NO-STORE, DEP-STORE-NO-MONEY, EXTERNAL-COMPLETE, EXTERNAL-JSON-STORE, INTERFACE-BOUNDARY, MODEL-TYPES-IN-ENTITIES, ROOT-LAYOUT, STORE-PEERS-ISOLATED, store:STORE-REQUIRES-COMPLETE | closed_world.observed_forbidden, closed_world.observed_forbidden, graph.drift, rule.violated, rule.violated, rule.violated, rule.violated, rule.violated, rule.violated, rule.violated, rule.violated, rule.violated, rule.violated, rule.violated, rule.violated, rule.violated, rule.violated, rule.violated, rule.violated, rule.violated, rule.violated, rule.violated, rule.violated | shop/app/analytics.py, shop/app/maintenance.py, shop/app/orders.py, shop/cli/main.py, shop/extra.py, shop/model/entities.py, shop/model/promotions.py, shop/render/text.py, shop/store/architecture-contract.json, shop/store/repository.py, shop/store/sqlite.py |
| clean | shop sample | clean | validate/report run | - | - | clean sample |
| clean | compatibility:clean | class-a-compatibility-clean | validate/report run | - | - | architecture-contract.json, shop/model/legacy.py |
| class_a | compatibility:migration-work | class-a-compatibility-migration | validate/report run | - | - | architecture-contract.json, shop/model/legacy.py |
| class_a | compatibility:effectful-shim | class-a-compatibility-effectful | validate/report run | - | compatibility.invalid, compatibility.invalid | architecture-contract.json, shop/model/legacy.py |
| class_a | compatibility:product-import | class-a-compatibility-product-import | validate/report run | - | compatibility.invalid | architecture-contract.json, shop/model/legacy.py, shop/model/legacy_user.py |
| class_a | compatibility:wrong-export | class-a-compatibility-wrong-export | validate/report run | - | compatibility.invalid | architecture-contract.json, shop/model/legacy.py, shop/model/other.py |
| validation | against:compatibility-added | against-compatibility-added | validate --against run | - | - | architecture-contract.json, shop/model/legacy.py |
| validation | against:compatibility-promoted | against-compatibility-promoted | validate --against run | - | - | architecture-contract.json, shop/model/legacy.py |
| class_a | forbidden_construct:getattr | class-a-construct-getattr | validate/report run | CONSTRUCT-NO-DYNAMIC | rule.violated | shop/model/probe_getattr.py |
| class_a | forbidden_construct:hasattr | class-a-construct-hasattr | validate/report run | CONSTRUCT-NO-DYNAMIC | rule.violated | shop/model/probe_hasattr.py |
| class_a | forbidden_construct:cast | class-a-construct-cast | validate/report run | CONSTRUCT-NO-DYNAMIC | rule.violated | shop/model/probe_cast.py |
| class_a | forbidden_construct:eval | class-a-construct-eval | validate/report run | CONSTRUCT-NO-DYNAMIC | rule.violated | shop/model/probe_eval.py |
| class_a | forbidden_construct:exec | class-a-construct-exec | validate/report run | CONSTRUCT-NO-DYNAMIC | rule.violated | shop/model/probe_exec.py |
| class_a | forbidden_construct:dynamic_import | class-a-construct-dynamic_import | validate/report run | CONSTRUCT-NO-DYNAMIC | rule.violated | shop/model/probe_dynamic_import.py |
| class_a | forbidden_construct:type_ignore | class-a-construct-type_ignore | validate/report run | CONSTRUCT-NO-DYNAMIC | rule.violated | shop/model/probe_type_ignore.py |
| class_a | forbidden_construct:any_annotation | class-a-construct-any_annotation | validate/report run | CONSTRUCT-NO-ANY, CONSTRUCT-NO-ANY | rule.violated, rule.violated | shop/model/probe_any_annotation.py |
| class_a | forbidden_construct:placeholder_body | class-a-construct-placeholder_body | validate/report run | CONSTRUCT-NO-PLACEHOLDER | rule.violated | shop/model/probe_placeholder_body.py |
| class_a | forbidden_construct:assert | class-a-construct-assert | validate/report run | CONSTRUCT-NO-ASSERT | rule.violated | shop/model/probe_assert.py |
| class_a | forbidden_construct:broad_except | class-a-construct-broad_except | validate/report run | CONSTRUCT-NO-BROAD-EXCEPT | rule.violated | shop/model/probe_broad_except.py |
| class_a | forbidden_construct:setattr | class-a-construct-setattr | validate/report run | CONSTRUCT-NO-DYNAMIC | rule.violated | shop/model/probe_setattr.py |
| class_a | forbidden_construct:delattr | class-a-construct-delattr | validate/report run | CONSTRUCT-NO-DYNAMIC | rule.violated | shop/model/probe_delattr.py |
| class_a | forbidden_construct:vars | class-a-construct-vars | validate/report run | CONSTRUCT-NO-DYNAMIC | rule.violated | shop/model/probe_vars.py |
| class_a | forbidden_construct:dunder_dict | class-a-construct-dunder_dict | validate/report run | CONSTRUCT-NO-DYNAMIC | rule.violated | shop/model/probe_dunder_dict.py |
| class_a | forbidden_construct:string_literal_compare | class-a-construct-string_literal_compare | validate/report run | CONSTRUCT-NO-STRING-LITERAL-COMPARE, CONSTRUCT-NO-STRING-LITERAL-COMPARE, CONSTRUCT-NO-STRING-LITERAL-COMPARE | rule.violated, rule.violated, rule.violated | shop/model/probe_string_literal_compare.py |
| class_a | forbidden_construct:exact_sources | class-a-broad-except-exact | validate/report run | CONSTRUCT-NO-BROAD-EXCEPT | rule.violated | shop/cli/main.py |
| class_a | forbidden_construct:allowed_sources | class-a-broad-except-prefix | validate/report run | - | - | architecture-contract.json, shop/cli/main.py |
| class_a | complete_requires | class-a-complete-requires | validate/report run | REQUIRES-COMPLETE | rule.violated | architecture-contract.json |
| class_a | complete_requires:include_type_checking | class-a-complete-requires-type-checking | validate/report run | REQUIRES-COMPLETE, REQUIRES-COMPLETE, REQUIRES-COMPLETE, REQUIRES-COMPLETE | rule.violated, rule.violated, rule.violated, rule.violated | architecture-contract.json |
| class_a | complete_requires:inside | class-a-complete-requires-inside | validate/report run | store:STORE-REQUIRES-COMPLETE, store:STORE-REQUIRES-COMPLETE, store:STORE-REQUIRES-COMPLETE | rule.violated, rule.violated, rule.violated | shop/store/architecture-contract.json |
| class_a | complete_external_scope | class-a-complete-external-scope | validate/report run | EXTERNAL-COMPLETE | rule.violated | shop/app/analytics.py |
| class_a | forbidden_dependency:pair | class-a-forbidden-dependency-pair | validate/report run | DEP-RENDER-NO-STORE | closed_world.observed_forbidden, graph.drift, rule.violated | shop/render/text.py |
| class_a | forbidden_dependency:target_symbol | class-a-forbidden-dependency-target-symbol | validate/report run | DEP-STORE-NO-MONEY | rule.violated | shop/store/repository.py |
| class_a | forbidden_dependency:include_type_checking | class-a-forbidden-dependency-include-type-checking | validate/report run | DEP-APP-NO-STORE-SQLITE | rule.violated | architecture-contract.json |
| class_a | forbidden_dependency:allowed_sources | class-a-forbidden-dependency-allowed-sources | validate/report run | DEP-APP-NO-STORE-SQLITE, DEP-APP-NO-STORE-SQLITE | rule.violated, rule.violated | architecture-contract.json |
| class_a | external_dependency_scope | class-a-external-dependency-scope | validate/report run | EXTERNAL-JSON-STORE | rule.violated | shop/app/reporting.py |
| class_a | complete_assignment | class-a-complete-assignment | validate/report run | ASSIGNMENT-COMPLETE, ROOT-LAYOUT | rule.violated, rule.violated | shop/extra.py |
| class_a | no_component_cycles | class-a-no-component-cycles | validate/report run | COMPONENT-NO-CYCLES | rule.violated | architecture-contract.json, docs/architecture/shop.md, shop/model/uses_render.py |
| class_a | no_component_cycles:module_hidden | class-a-no-component-cycles-module-hidden | validate/report run | - | - | shop/model/alpha.py, shop/model/beta.py |
| class_a | no_component_cycles:module | class-a-no-component-cycles-module | validate/report run | MODEL-MODULES-ACYCLIC | rule.violated | architecture-contract.json, shop/model/alpha.py, shop/model/beta.py |
| class_a | no_component_cycles:package_rollup_only | class-a-package-cycle-rollup-only | validate/report run | COMPONENT-NO-CYCLES | rule.violated | architecture-contract.json, docs/architecture/shop.md, shop/model/uses_render.py |
| class_a | no_component_cycles:package_backed | class-a-package-cycle-backed | validate/report run | COMPONENT-NO-CYCLES | rule.violated | architecture-contract.json, docs/architecture/shop.md, shop/model/entities.py |
| class_a | decision:open | class-a-decision-open | validate/report run | - | decision.open | architecture-contract.json |
| class_a | closed_world:duplicate | class-a-closed-world-duplicate | validate/report run | - | closed_world.duplicate | architecture-contract.json |
| class_a | allowed_dependency:duplicate | class-a-allowed-dependency-duplicate | validate/report run | - | closed_world.duplicate | architecture-contract.json |
| class_a | decision:conflict | class-a-decision-conflict | validate/report run | DEP-STORE-NO-MODEL-CONFLICT, DEP-STORE-NO-MODEL-CONFLICT, DEP-STORE-NO-MODEL-CONFLICT | closed_world.observed_forbidden, decision.conflict, rule.violated, rule.violated, rule.violated | architecture-contract.json |
| class_a | sibling_isolation:peer import | class-a-sibling-isolation | validate/report run | STORE-PEERS-ISOLATED | rule.violated | shop/store/architecture-contract.json, shop/store/sqlite.py |
| class_a | interface_boundary:underscore | class-a-interface-boundary-underscore | validate/report run | INTERFACE-BOUNDARY | rule.violated | shop/cli/main.py |
| class_a | interface_boundary:undeclared symbol | class-a-interface-boundary-undeclared-symbol | validate/report run | INTERFACE-BOUNDARY | rule.violated | shop/cli/main.py |
| class_a | interface_boundary:whole-module import | class-a-interface-boundary-whole-module | validate/report run | INTERFACE-BOUNDARY | rule.violated | shop/app/maintenance_report.py |
| class_a | interface_boundary:__all__ gate | class-a-interface-boundary-all-gate | validate/report run | INTERFACE-BOUNDARY | rule.violated | shop/render/discount_probe.py |
| class_a | interface_boundary:accepted re-export | class-a-interface-boundary-accepted-reexport | validate/report run | - | - | shop/app/accepted_reexport.py |
| class_d | interface_profile:declared barrel | class-d-interface-profile-barrel | validate/report run | - | - | architecture-contract.json, shop/store/__init__.py, shop/store/architecture-contract.json |
| class_a | interface_boundary:package attribute over submodule | class-a-interface-boundary-package-attribute-over-submodule | validate/report run | INTERFACE-BOUNDARY | rule.violated | shop/app/sqlite_probe.py, shop/store/__init__.py |
| class_a | private_access:untyped parameter | class-a-private-attribute-untyped | validate/report run | - | - | shop/app/untyped_private.py |
| class_a | private_access:top-level Any owner | class-a-private-attribute-any-owner | validate/report run | - | - | architecture-contract.json, shop/app/any_private.py |
| clean | root_layout:clean | class-a-root-layout-clean | validate/report run | - | - | clean sample |
| clean | root_layout:nested-root | class-a-root-layout-nested-root | validate/report run | - | - | architecture-contract.json |
| validation | root_layout:invalid-contract | validation-root-layout-invalid-child | validate/report run | - | contract.invalid | architecture-contract.json |
| class_a | root_layout:unexpected-child | class-a-root-layout-violation | validate/report run | ASSIGNMENT-COMPLETE, ROOT-LAYOUT | rule.violated, rule.violated | shop/rogue.py |
| class_a | symbol_placement:exact_sources | class-a-symbol-placement | validate/report run | MODEL-TYPES-IN-ENTITIES | rule.violated | shop/model/promotions.py |
| class_a | boundary_types:dict | class-a-boundary-types | validate/report run | APP-TYPES-NOT-DICT | rule.violated | architecture-contract.json, shop/app/reports.py, shop/cli/main.py |
| class_a | boundary_types:declared_type | class-a-boundary-types-declared-type | validate/report run | APP-TYPES-NOT-DICT | rule.violated | architecture-contract.json, shop/app/discounts.py, shop/cli/main.py |
| class_a | boundary_types:collection_element | class-a-boundary-types-in-collection | validate/report run | APP-TYPES-NOT-DICT | rule.violated | architecture-contract.json, shop/app/batches.py, shop/cli/main.py |
| class_a | boundary_types:reexport | class-a-boundary-types-reexport | validate/report run | RENDER-TYPES-NOT-DICT | rule.violated | architecture-contract.json, shop/cli/main.py, shop/render/__init__.py, shop/render/text.py |
| class_a | boundary_types:reexport_aliases | class-a-boundary-types-reexport-aliases | validate/report run | RENDER-TYPES-NOT-DICT | rule.violated | architecture-contract.json, shop/cli/main.py, shop/render/__init__.py, shop/render/text.py |
| class_a | boundary_types:model_field | class-a-boundary-types-model-field | validate/report run | APP-TYPES-NOT-DICT | rule.violated | architecture-contract.json, shop/app/requests.py, shop/cli/main.py |
| validation | module.placement:clean | validation-module-placement-clean | validate/report run | - | - | shop/model/catalog.py |
| validation | module.placement | validation-module-placement | validate/report run | COMP-MODEL, ROOT-LAYOUT | rule.violated, rule.violated | architecture-contract.json, shop/model_rules.py |
| validation | interface.undeclared | validation-interface-undeclared | validate/report run | - | interface.undeclared | architecture-contract.json |
| validation | interface.unused | validation-interface-unused | validate/report run | - | interface.unused | architecture-contract.json |
| validation | interface.missing | validation-interface-missing | validate/report run | - | interface.missing | architecture-contract.json |
| validation | api_surface.missing | validation-api-surface-missing | validate/report run | - | api_surface.missing | architecture-contract.json |
| validation | api_surface.missing:not_in_all | validation-api-surface-not-exported | validate/report run | - | api_surface.missing | architecture-contract.json |
| validation | interface.planned_built:not yet built | validation-interface-planned-not-built | validate/report run | - | - | architecture-contract.json |
| validation | interface.planned_built:target work | validation-interface-planned-built | validate/report run | - | - | architecture-contract.json |
| validation | interface.planned_built:reached | validation-interface-planned-built-reached | tested only | - | interface.planned_built | tests/test_validation.py |
| validation | agent_decisions:agent-attributed | validation-agent-decisions-attributed | validate/report run | - | - | architecture-contract.json |
| validation | rationale.placeholder | validation-rationale-placeholder | validate/report run | - | rationale.placeholder | architecture-contract.json |
| validation | rationale.repeated | validation-rationale-repeated | validate/report run | - | rationale.repeated | architecture-contract.json |
| validation | graph.count | validation-graph-count | validate/report run | - | graph.count | docs/architecture/shop.md |
| validation | graph.drift:write-graph | validation-graph-drift-write-graph | validate/report run | - | graph.drift, graph.drift | architecture-contract.json |
| validation | graph.drift:subgraph | validation-graph-drift-subgraph | validate/report run | - | graph.drift, graph.drift | architecture-contract.json, docs/architecture/shop.md |
| validation | graph.drift:target-write-graph | validation-target-graph-drift-write-graph | validate/report run | - | graph.drift | architecture-contract.json |
| validation | graph.drift:target-subgraph | validation-target-graph-drift-subgraph | validate/report run | - | graph.drift | architecture-contract.json, docs/architecture/shop.md |
| validation | reference.namespace | validation-reference-namespace | validate/report run | - | reference.namespace | architecture-contract.json |
| validation | reference.public_owner | validation-reference-public-owner | validate/report run | - | reference.public_owner | architecture-contract.json |
| validation | reference.public_underscore | validation-reference-public-underscore | validate/report run | - | reference.public_underscore | architecture-contract.json |
| validation | reference.provenance | validation-reference-provenance | validate/report run | - | reference.provenance | architecture-contract.json |
| validation | reference.package_unscanned | validation-reference-package-unscanned | validate/report run | - | reference.package_unscanned | architecture-contract.json |
| validation | contract.schema_version | validation-contract-schema-version | validate/report run | - | contract.schema_version | architecture-contract.json |
| validation | contract.invalid | validation-contract-invalid | validate/report run | - | contract.invalid | architecture-contract.json |
| validation | observation.incomplete | validation-observation-incomplete | tested only | - | - | tests/test_trace.py |
| class_c | ContractDeclarations.measurement_budgets | validation-measurement-budget-clean | validate/report run | - | - | architecture-baseline.json, architecture-contract.json |
| validation | measurement_budget:cycle_edges | validation-measurement-budget-rise | validate/report run | - | - | architecture-baseline.json, architecture-contract.json, shop/model/alpha.py, shop/model/beta.py |
| class_c | ContractDeclarations.facade_budgets | validation-facade-budget-clean | validate/report run | - | - | architecture-contract.json |
| class_c | ContractDeclarations.coupling_budgets | validation-coupling-budget-clean | validate/report run | - | - | architecture-contract.json |
| validation | budget.exceeded | validation-facade-budget-exceeded | validate/report run | - | budget.exceeded | architecture-contract.json, shop/model/entities.py |
| validation | budget.exceeded:coupling | validation-coupling-budget-exceeded | validate/report run | - | budget.exceeded | architecture-contract.json, shop/app/export.py |
| validation | budget.unknown | validation-facade-budget-unknown | validate/report run | - | budget.unknown | architecture-contract.json |
| validation | budget.target_first | validation-facade-budget-target-first | validate/report run | - | - | architecture-baseline.json, architecture-contract.json |
| validation | budget.ratchet | validation-facade-budget-ratchet | validate/report run | - | - | architecture-baseline.json, architecture-contract.json, shop/model/entities.py |
| validation | baseline.invalid | validation-baseline-invalid | tested only | - | - | tests/test_baseline.py |
| validation | baseline.accept_new | validation-baseline-accept-new | tested only | - | - | tests/test_cli.py |
| validation | baseline.roles | validation-baseline-roles | tested only | - | - | tests/test_baseline.py |
| validation | baseline.role_evidence | validation-baseline-role-evidence | tested only | - | - | tests/test_widening.py |
| validation | baseline.interface_narrowing | validation-baseline-interface-narrowing | validate/report run | - | - | architecture-contract.json, known-violations.json |
| validation | against.invalid | validation-against-invalid | tested only | - | - | tests/test_widening.py |
| validation | amendment.invalid | validation-amendment-invalid | tested only | - | - | tests/test_widening.py |
| validation | inside.public_mismatch | validation-inside-public-mismatch | validate/report run | - | inside.public_mismatch | shop/store/architecture-contract.json |
| validation | inside.forbidden_import | validation-inside-forbidden-import | validate/report run | - | inside.forbidden_import | shop/store/architecture-contract.json |
| validation | contract.invalid:inside | validation-inside-contract-missing | validate/report run | - | contract.invalid | shop/store/architecture-contract.json |
| validation | api_surface_unknown | validation-api-surface-unknown | validate/report run | - | - | architecture-contract.json |
| validation | rule_without_subjects | validation-rule-without-subjects | validate/report run | - | - | architecture-contract.json |
| validation | parse_error | validation-parse-error | validate/report run | - | - | shop/model/broken_syntax.py |
| validation | scope_empty | validation-scope-empty | validate/report run | - | - | architecture-contract.json, shop/app/maintenance.py, shop/app/orders.py, shop/cli/main.py, shop/model/entities.py, shop/render/text.py, shop/store/__init__.py, shop/store/backend/__init__.py, shop/store/backend/files.py, shop/store/backend/paths.py, shop/store/codec.py, shop/store/repository.py, shop/store/sqlite.py |
| validation | runtime_mismatch | validation-runtime-mismatch | validate/report run | - | - | pyproject.toml |
| validation | missing_tool | validation-missing-tool | tested only | - | - | tests/test_analyzer.py |
| validation | timeout | validation-timeout | tested only | - | - | tests/test_analyzer.py |
| validation | incomparable_runtime | validation-incomparable-runtime | tested only | - | - | tests/test_runtime_delta.py |
| validation | rule_unsupported_by_profile | validation-rule-unsupported-by-profile | tested only | - | - | tests/test_dart_profile.py |
| validation | existing_files | validation-existing-files | tested only | - | - | tests/test_onboarding.py |
| validation | filter_unknown | validation-filter-unknown | tested only | - | - | tests/test_report_filter.py |
| validation | against:widened_unamended | against-widened-unamended | validate --against run | - | - | architecture-contract.json |
| validation | against:widened_amended | against-widened-amended | validate --against run | - | - | architecture-contract.json |
| validation | against:narrowed_only | against-narrowed-only | validate --against run | - | - | architecture-contract.json |
| validation | against:boundary_types_added | against-boundary-types-added | validate --against run | - | - | architecture-contract.json |
| validation | against:symbol_placement_added | against-symbol-placement-added | validate --against run | - | - | architecture-contract.json |
| validation | against:boundary_types_removed | against-boundary-types-removed | validate --against run | - | - | architecture-contract.json |
| validation | against:symbol_placement_removed | against-symbol-placement-removed | validate --against run | - | - | architecture-contract.json |
| validation | against:budget_raised | against-facade-budget-raised | validate --against run | - | - | architecture-contract.json |
| validation | against:cycle_rule_scoped | against-cycle-rule-scoped | validate --against run | - | - | architecture-contract.json |
| protocol | ordered | protocol-ordered | check run | - | - | shop/render/order_summary.py |
| protocol | host_order | protocol-published-after-candidate | check run | - | - | shop/render/order_summary.py |
| protocol | git_order | protocol-candidate-changed-expectation | check run | - | - | shop/render/order_summary.py |
| protocol | empty_declaration | protocol-empty-declaration | check run | - | - | shop/model/entities.py |
| class_b | SCALARS:violations | class-b-check-scalar-violations | check run | - | - | shop/render/text.py |
| class_b | GUARDRAIL_DIMENSIONS:violations | class-b-check-guardrail-violations | check run | - | - | shop/render/text.py |
| class_b | SCALARS:private_crossings | class-b-scalar-private-crossings | check run | - | - | shop/cli/main.py |
| class_b | GUARDRAIL_DIMENSIONS:private_crossings | class-b-guardrail-private-crossings | check run | - | - | shop/cli/main.py |
| class_b | SCALARS:untyped_private_accesses | class-b-scalar-private-attribute-access | check run | - | - | shop/app/untyped_private.py |
| class_b | GUARDRAIL_DIMENSIONS:unknowns:untyped attribute | class-b-guardrail-private-attribute-access | check run | - | - | shop/app/untyped_private.py |
| class_b | SCALARS:unknown_positions | class-b-scalar-unknown-positions | check run | - | - | shop/app/orders.py |
| class_b | SCALARS:cycle_edges | class-b-scalar-cycle-edges | check run | - | - | shop/model/uses_render.py |
| class_b | GUARDRAIL_DIMENSIONS:cycles | class-b-check-guardrail-cycles | check run | - | - | shop/model/uses_render.py |
| class_b | SCALARS:typing_positions | class-b-scalar-typing-positions | check run | - | - | shop/model/probe_type_ignore.py |
| class_b | GUARDRAIL_DIMENSIONS:typing_signals | class-b-guardrail-typing-signals | check run | - | - | shop/model/probe_type_ignore.py |
| class_b | SCALARS:calls_unresolved | class-b-scalar-calls-unresolved | check run | - | - | shop/app/probe_unresolved.py |
| class_b | unresolved_ratio | class-b-check-unresolved-ratio | check run | - | - | shop/app/probe_unresolved.py |
| class_b | SCALARS:coverage_failures | class-b-scalar-coverage-failures | tested only | - | - | tests/test_ratchets.py |
| class_b | GUARDRAIL_DIMENSIONS:unknowns | class-b-guardrail-unknowns | tested only | - | - | tests/test_expectation.py |
| class_b | GUARDRAIL_DIMENSIONS:dependency_edges | class-b-guardrail-dependency-edges | tested only | - | - | tests/test_expectation.py |
| class_b | coverage_must_pass | class-b-coverage-must-pass | tested only | - | - | tests/test_expectation.py |
| class_c | ContractDeclarations.capabilities | class-c-capabilities | tested only | - | - | fixtures/F-architecture/architecture-contract.json |
| class_c | ContractDeclarations.review_scopes | class-c-review-scopes | tested only | - | - | fixtures/F-architecture/architecture-contract.json |
| class_c | ContractDeclarations.public_api | class-c-public-api | tested only | - | - | fixtures/F-architecture/architecture-contract.json |
| class_c | ContractDeclarations.public_api_provenance | class-c-public-api-provenance | tested only | - | - | fixtures/F-architecture/architecture-contract.json |
| class_c | ContractDeclarations.public_commands | class-c-public-commands | tested only | - | - | fixtures/F-architecture/architecture-contract.json |
| class_c | ContractDeclarations.context_roots | class-c-context-roots | tested only | - | - | fixtures/F-architecture/architecture-contract.json |
| class_c | ContractDeclarations.context_roots_provenance | class-c-context-roots-provenance | tested only | - | - | fixtures/F-architecture/architecture-contract.json |
| class_c | ContractDeclarations.paths | class-c-paths | tested only | - | - | fixtures/F-architecture/architecture-contract.json |
| class_c | ContractDeclarations.spot_owners | class-c-spot-owners | tested only | - | - | fixtures/F-architecture/architecture-contract.json |
| class_c | ContractDeclarations.compat | class-c-compat | tested only | - | - | fixtures/F-architecture/architecture-contract.json |
| class_d | review_claims | class-d-review-claims | tested only | - | - | docs/rules.md |
| class_d | oversized_inside | class-d-oversized-inside | tested only | - | - | docs/rules.md |
| class_d | type_fanin | class-d-type-fanin | tested only | - | - | docs/rules.md |
| clean | dart:clean | dart-clean | validate/report run | - | - | G-dart: clean sample |
| class_a | dart:forbidden_dependency | dart-forbidden-dart-io | validate/report run | DEP-DOMAIN-NO-DART-IO | rule.violated | G-dart: lib/domain/repository.dart |
| class_a | dart:complete_requires | dart-complete-requires | validate/report run | REQUIRES-COMPLETE | graph.drift, rule.violated | G-dart: lib/data/http_order_repository.dart |
| class_a | dart:no_component_cycles | dart-component-cycle | validate/report run | COMPONENT-NO-CYCLES, REQUIRES-COMPLETE | graph.drift, rule.violated, rule.violated | G-dart: lib/domain/repository.dart |
| class_a | dart:complete_assignment | dart-complete-assignment | validate/report run | ASSIGNMENT-COMPLETE, ROOT-LAYOUT | rule.violated, rule.violated | G-dart: lib/util/strings.dart |
| class_a | dart:external_dependency_scope | dart-external-scope | validate/report run | EXTERNAL-HTTP-DATA | rule.violated | G-dart: lib/presentation/order_tile.dart |
| class_a | dart:interface_boundary:show | dart-interface-show | validate/report run | INTERFACE-BOUNDARY | rule.violated | G-dart: lib/presentation/order_tile.dart |
| class_a | dart:interface_boundary:unknown | dart-interface-unknown | validate/report run | - | - | G-dart: lib/presentation/order_tile.dart |
| validation | dart:rule_unsupported_by_profile:rule | dart-unsupported-rule | validate/report run | - | - | G-dart: architecture-contract.json |
| validation | dart:rule_unsupported_by_profile:measurement_budget | dart-unsupported-budget | validate/report run | - | - | G-dart: architecture-baseline.json, architecture-contract.json |
| validation | dart:parse_error | dart-unreadable-header | validate/report run | - | - | G-dart: lib/presentation/order_badge.dart |
| showcase | dart:tour | dart-tour | validate/report run | ASSIGNMENT-COMPLETE, COMPONENT-NO-CYCLES, DEP-DOMAIN-NO-DART-IO, EXTERNAL-HTTP-DATA, INTERFACE-BOUNDARY, REQUIRES-COMPLETE, REQUIRES-COMPLETE, ROOT-LAYOUT | graph.drift, rule.violated, rule.violated, rule.violated, rule.violated, rule.violated, rule.violated, rule.violated, rule.violated | G-dart: lib/data/http_order_repository.dart, lib/domain/repository.dart, lib/presentation/order_tile.dart, lib/util/strings.dart |
