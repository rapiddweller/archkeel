# Architecture demo catalog

Generated from `fixtures/architecture_demo.py`'s `CATALOG`. Every checkable item in
`docs/architecture/archkeel.md` (AD-11) has one row below: a named variant, the rule ids and
diagnostic codes (AD-12) it must produce, and either the shop sample files it changes or the
existing evidence that demonstrates it instead. Regenerate with `python -m
fixtures.architecture_demo --markdown`.

The `showcase` row below (`tour`) is the default demo view: it applies many overlays at once so one
run shows many violations together; every other row isolates one item.

| Section | Item | Variant | Demo | Rule ids | Diagnostic codes | Evidence / files |
|---|---|---|---|---|---|---|
| showcase | tour | tour | validate/report run | ASSIGNMENT-COMPLETE, COMPONENT-NO-CYCLES, CONSTRUCT-NO-ANY, CONSTRUCT-NO-ASSERT, CONSTRUCT-NO-BROAD-EXCEPT, CONSTRUCT-NO-DYNAMIC, CONSTRUCT-NO-DYNAMIC, DEP-APP-NO-STORE-BACKEND, DEP-APP-NO-STORE-SQLITE, DEP-MODEL-NO-RENDER, DEP-RENDER-NO-STORE, DEP-STORE-NO-MONEY, EXTERNAL-JSON-STORE, INTERFACE-BOUNDARY | closed_world.observed_forbidden, closed_world.observed_forbidden, graph.drift, rule.violated, rule.violated, rule.violated, rule.violated, rule.violated, rule.violated, rule.violated, rule.violated, rule.violated, rule.violated, rule.violated, rule.violated, rule.violated, rule.violated | shop/app/maintenance.py, shop/app/orders.py, shop/cli/main.py, shop/extra.py, shop/model/entities.py, shop/render/text.py, shop/store/repository.py |
| clean | shop sample | clean | validate/report run | - | - | clean sample |
| class_a | forbidden_construct:getattr | class-a-construct-getattr | validate/report run | CONSTRUCT-NO-DYNAMIC | rule.violated | shop/model/probe_getattr.py |
| class_a | forbidden_construct:hasattr | class-a-construct-hasattr | validate/report run | CONSTRUCT-NO-DYNAMIC | rule.violated | shop/model/probe_hasattr.py |
| class_a | forbidden_construct:cast | class-a-construct-cast | validate/report run | CONSTRUCT-NO-DYNAMIC | rule.violated | shop/model/probe_cast.py |
| class_a | forbidden_construct:eval | class-a-construct-eval | validate/report run | CONSTRUCT-NO-DYNAMIC | rule.violated | shop/model/probe_eval.py |
| class_a | forbidden_construct:exec | class-a-construct-exec | validate/report run | CONSTRUCT-NO-DYNAMIC | rule.violated | shop/model/probe_exec.py |
| class_a | forbidden_construct:dynamic_import | class-a-construct-dynamic_import | validate/report run | CONSTRUCT-NO-DYNAMIC | rule.violated | shop/model/probe_dynamic_import.py |
| class_a | forbidden_construct:type_ignore | class-a-construct-type_ignore | validate/report run | CONSTRUCT-NO-DYNAMIC | rule.violated | shop/model/probe_type_ignore.py |
| class_a | forbidden_construct:any_annotation | class-a-construct-any_annotation | validate/report run | CONSTRUCT-NO-ANY | rule.violated | shop/model/probe_any_annotation.py |
| class_a | forbidden_construct:placeholder_body | class-a-construct-placeholder_body | validate/report run | CONSTRUCT-NO-PLACEHOLDER | rule.violated | shop/model/probe_placeholder_body.py |
| class_a | forbidden_construct:assert | class-a-construct-assert | validate/report run | CONSTRUCT-NO-ASSERT | rule.violated | shop/model/probe_assert.py |
| class_a | forbidden_construct:broad_except | class-a-construct-broad_except | validate/report run | CONSTRUCT-NO-BROAD-EXCEPT | rule.violated | shop/model/probe_broad_except.py |
| class_a | forbidden_construct:broad_except (allowed source) | class-a-broad-except-allowed | validate/report run | - | - | shop/cli/main.py |
| class_a | complete_requires | class-a-complete-requires | validate/report run | REQUIRES-COMPLETE | rule.violated | architecture-contract.json |
| class_a | complete_requires:include_type_checking | class-a-complete-requires-type-checking | validate/report run | REQUIRES-COMPLETE, REQUIRES-COMPLETE, REQUIRES-COMPLETE, REQUIRES-COMPLETE | rule.violated, rule.violated, rule.violated, rule.violated | architecture-contract.json |
| class_a | complete_inner_decisions | class-a-complete-inner-decisions | validate/report run | - | decision.open, decision.open, decision.open | architecture-contract.json |
| class_a | complete_external_scope | class-a-complete-external-scope | validate/report run | EXTERNAL-COMPLETE | rule.violated | shop/app/analytics.py |
| class_a | forbidden_dependency:pair | class-a-forbidden-dependency-pair | validate/report run | DEP-RENDER-NO-STORE | closed_world.observed_forbidden, graph.drift, rule.violated | shop/render/text.py |
| class_a | forbidden_dependency:target_symbol | class-a-forbidden-dependency-target-symbol | validate/report run | DEP-STORE-NO-MONEY | rule.violated | shop/store/repository.py |
| class_a | forbidden_dependency:include_type_checking | class-a-forbidden-dependency-include-type-checking | validate/report run | DEP-APP-NO-STORE-SQLITE | rule.violated | architecture-contract.json |
| class_a | forbidden_dependency:allowed_sources | class-a-forbidden-dependency-allowed-sources | validate/report run | DEP-APP-NO-STORE-SQLITE, DEP-APP-NO-STORE-SQLITE | rule.violated, rule.violated | architecture-contract.json |
| class_a | external_dependency_scope | class-a-external-dependency-scope | validate/report run | EXTERNAL-JSON-STORE | rule.violated | shop/app/reporting.py |
| class_a | complete_assignment | class-a-complete-assignment | validate/report run | ASSIGNMENT-COMPLETE | rule.violated | shop/extra.py |
| class_a | no_component_cycles | class-a-no-component-cycles | validate/report run | COMPONENT-NO-CYCLES | rule.violated | architecture-contract.json, docs/architecture/shop.md, shop/model/uses_render.py |
| class_a | decision:open | class-a-decision-open | validate/report run | - | decision.open | architecture-contract.json |
| class_a | closed_world:duplicate | class-a-closed-world-duplicate | validate/report run | - | closed_world.duplicate | architecture-contract.json |
| class_a | allowed_dependency:duplicate | class-a-allowed-dependency-duplicate | validate/report run | - | closed_world.duplicate | architecture-contract.json |
| class_a | decision:conflict | class-a-decision-conflict | validate/report run | DEP-STORE-NO-MODEL-CONFLICT, DEP-STORE-NO-MODEL-CONFLICT | closed_world.observed_forbidden, decision.conflict, rule.violated, rule.violated | architecture-contract.json |
| class_a | sibling_isolation:peer import | class-a-sibling-isolation | validate/report run | STORE-PEERS-ISOLATED | rule.violated | architecture-contract.json, shop/store/sqlite.py |
| class_a | interface_boundary:underscore | class-a-interface-boundary-underscore | validate/report run | INTERFACE-BOUNDARY | rule.violated | shop/cli/main.py |
| class_a | interface_boundary:undeclared symbol | class-a-interface-boundary-undeclared-symbol | validate/report run | INTERFACE-BOUNDARY | rule.violated | shop/cli/main.py |
| class_a | interface_boundary:whole-module import | class-a-interface-boundary-whole-module | validate/report run | INTERFACE-BOUNDARY | rule.violated | shop/app/maintenance_report.py |
| class_a | interface_boundary:__all__ gate | class-a-interface-boundary-all-gate | validate/report run | INTERFACE-BOUNDARY | rule.violated | shop/render/discount_probe.py |
| class_a | interface_boundary:accepted re-export | class-a-interface-boundary-accepted-reexport | validate/report run | - | - | shop/app/accepted_reexport.py |
| validation | interface.undeclared | validation-interface-undeclared | validate/report run | - | interface.undeclared | architecture-contract.json |
| validation | interface.unused | validation-interface-unused | validate/report run | - | interface.unused | architecture-contract.json |
| validation | rationale.placeholder | validation-rationale-placeholder | validate/report run | - | rationale.placeholder | architecture-contract.json |
| validation | rationale.repeated | validation-rationale-repeated | validate/report run | - | rationale.repeated | architecture-contract.json |
| validation | graph.count | validation-graph-count | validate/report run | - | graph.count | docs/architecture/shop.md |
| validation | reference.namespace | validation-reference-namespace | validate/report run | - | reference.namespace | architecture-contract.json |
| validation | reference.public_owner | validation-reference-public-owner | validate/report run | - | reference.public_owner | architecture-contract.json |
| validation | reference.public_underscore | validation-reference-public-underscore | validate/report run | - | reference.public_underscore | architecture-contract.json |
| validation | reference.provenance | validation-reference-provenance | validate/report run | - | reference.provenance | architecture-contract.json |
| validation | reference.package_unscanned | validation-reference-package-unscanned | validate/report run | - | reference.package_unscanned | architecture-contract.json |
| validation | contract.schema_version | validation-contract-schema-version | validate/report run | - | contract.schema_version | architecture-contract.json |
| validation | contract.invalid | validation-contract-invalid | validate/report run | - | contract.invalid | architecture-contract.json |
| validation | observation.incomplete | validation-observation-incomplete | tested only | - | - | tests/test_trace.py |
| validation | rule_without_subjects | validation-rule-without-subjects | validate/report run | - | - | architecture-contract.json |
| validation | parse_error | validation-parse-error | validate/report run | - | - | shop/model/broken_syntax.py |
| validation | scope_empty | validation-scope-empty | validate/report run | - | - | architecture-contract.json, shop/app/maintenance.py, shop/app/orders.py, shop/cli/main.py, shop/model/entities.py, shop/render/text.py, shop/store/__init__.py, shop/store/backend/__init__.py, shop/store/backend/files.py, shop/store/repository.py, shop/store/sqlite.py |
| validation | runtime_mismatch | validation-runtime-mismatch | validate/report run | - | - | pyproject.toml |
| validation | missing_tool | validation-missing-tool | tested only | - | - | tests/test_analyzer.py |
| validation | timeout | validation-timeout | tested only | - | - | tests/test_analyzer.py |
| validation | incomparable_runtime | validation-incomparable-runtime | tested only | - | - | tests/test_runtime_delta.py |
| validation | existing_files | validation-existing-files | tested only | - | - | tests/test_onboarding.py |
| protocol | ordered | protocol-ordered | check run | - | - | shop/render/order_summary.py |
| protocol | host_order | protocol-published-after-candidate | check run | - | - | shop/render/order_summary.py |
| protocol | git_order | protocol-candidate-changed-expectation | check run | - | - | shop/render/order_summary.py |
| class_b | SCALARS:violations | class-b-check-scalar-violations | check run | - | - | shop/render/text.py |
| class_b | GUARDRAIL_DIMENSIONS:violations | class-b-check-guardrail-violations | check run | - | - | shop/render/text.py |
| class_b | SCALARS:private_crossings | class-b-scalar-private-crossings | check run | - | - | shop/cli/main.py |
| class_b | GUARDRAIL_DIMENSIONS:private_crossings | class-b-guardrail-private-crossings | check run | - | - | shop/cli/main.py |
| class_b | SCALARS:cycle_edges | class-b-scalar-cycle-edges | check run | - | - | shop/model/uses_render.py |
| class_b | GUARDRAIL_DIMENSIONS:cycles | class-b-check-guardrail-cycles | check run | - | - | shop/model/uses_render.py |
| class_b | SCALARS:typing_positions | class-b-scalar-typing-positions | check run | - | - | shop/model/probe_type_ignore.py |
| class_b | GUARDRAIL_DIMENSIONS:typing_signals | class-b-guardrail-typing-signals | check run | - | - | shop/model/probe_type_ignore.py |
| class_b | SCALARS:calls_unresolved | class-b-scalar-calls-unresolved | check run | - | - | shop/app/probe_unresolved.py |
| class_b | unresolved_ratio | class-b-check-unresolved-ratio | check run | - | - | shop/app/probe_unresolved.py |
| class_b | SCALARS:coverage_failures | class-b-scalar-coverage-failures | tested only | - | - | tests/test_ratchets.py |
| class_b | GUARDRAIL_DIMENSIONS:unknowns | class-b-guardrail-unknowns | tested only | - | - | tests/test_expectation.py |
| class_b | coverage_must_pass | class-b-coverage-must-pass | tested only | - | - | tests/test_expectation.py |
| class_c | ContractDeclarations.capabilities | class-c-capabilities | tested only | - | - | fixtures/F-architecture/architecture-contract.json |
| class_c | ContractDeclarations.review_scopes | class-c-review-scopes | tested only | - | - | fixtures/F-architecture/architecture-contract.json |
| class_c | ContractDeclarations.public_api | class-c-public-api | tested only | - | - | docs/rules.md |
| class_c | ContractDeclarations.public_api_provenance | class-c-public-api-provenance | tested only | - | - | docs/rules.md |
| class_c | ContractDeclarations.public_commands | class-c-public-commands | tested only | - | - | fixtures/F-architecture/architecture-contract.json |
| class_c | ContractDeclarations.context_roots | class-c-context-roots | tested only | - | - | fixtures/F-architecture/architecture-contract.json |
| class_c | ContractDeclarations.context_roots_provenance | class-c-context-roots-provenance | tested only | - | - | fixtures/F-architecture/architecture-contract.json |
| class_c | ContractDeclarations.paths | class-c-paths | tested only | - | - | fixtures/F-architecture/architecture-contract.json |
| class_c | ContractDeclarations.spot_owners | class-c-spot-owners | tested only | - | - | fixtures/F-architecture/architecture-contract.json |
| class_d | review_claims | class-d-review-claims | tested only | - | - | docs/rules.md |
