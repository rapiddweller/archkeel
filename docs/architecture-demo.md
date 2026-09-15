# Architecture demo catalog

Generated from `fixtures/architecture_demo.py`'s `CATALOG`. Every checkable item in
`docs/architecture/archkeel.md` (AD-11) has one row below: a named variant, the rule ids and
diagnostic codes (AD-12) it must produce, and either the shop sample files it changes or the
existing evidence that demonstrates it instead. Regenerate with `python -m
fixtures.architecture_demo --markdown`.

The `showcase` row below (`tour`) is the default demo view: it applies many overlays at once so one
run shows many violations together; every other row isolates one item.

| Section | Item | Variant | Rule ids | Diagnostic codes | Evidence / files |
|---|---|---|---|---|---|
| showcase | tour | tour | ASSIGNMENT-COMPLETE, COMPONENT-NO-CYCLES, CONSTRUCT-NO-ASSERT, CONSTRUCT-NO-BROAD-EXCEPT, CONSTRUCT-NO-DYNAMIC, DEP-APP-NO-STORE-SQLITE, DEP-MODEL-NO-RENDER, DEP-RENDER-NO-STORE, DEP-STORE-NO-MONEY, EXTERNAL-JSON-STORE, INTERFACE-BOUNDARY | closed_world.observed_forbidden, closed_world.observed_forbidden, graph.drift, rule.violated, rule.violated, rule.violated, rule.violated, rule.violated, rule.violated, rule.violated, rule.violated, rule.violated, rule.violated, rule.violated | shop/app/maintenance.py, shop/app/orders.py, shop/cli/main.py, shop/extra.py, shop/model/entities.py, shop/render/text.py, shop/store/repository.py |
| clean | shop sample | clean | - | - | clean sample |
| class_a | forbidden_construct:getattr | class-a-construct-getattr | CONSTRUCT-NO-DYNAMIC | rule.violated | shop/model/probe_getattr.py |
| class_a | forbidden_construct:hasattr | class-a-construct-hasattr | CONSTRUCT-NO-DYNAMIC | rule.violated | shop/model/probe_hasattr.py |
| class_a | forbidden_construct:cast | class-a-construct-cast | CONSTRUCT-NO-DYNAMIC | rule.violated | shop/model/probe_cast.py |
| class_a | forbidden_construct:eval | class-a-construct-eval | CONSTRUCT-NO-DYNAMIC | rule.violated | shop/model/probe_eval.py |
| class_a | forbidden_construct:exec | class-a-construct-exec | CONSTRUCT-NO-DYNAMIC | rule.violated | shop/model/probe_exec.py |
| class_a | forbidden_construct:dynamic_import | class-a-construct-dynamic_import | CONSTRUCT-NO-DYNAMIC | rule.violated | shop/model/probe_dynamic_import.py |
| class_a | forbidden_construct:type_ignore | class-a-construct-type_ignore | CONSTRUCT-NO-DYNAMIC | rule.violated | shop/model/probe_type_ignore.py |
| class_a | forbidden_construct:assert | class-a-construct-assert | CONSTRUCT-NO-ASSERT | rule.violated | shop/model/probe_assert.py |
| class_a | forbidden_construct:broad_except | class-a-construct-broad_except | CONSTRUCT-NO-BROAD-EXCEPT | rule.violated | shop/model/probe_broad_except.py |
| class_a | forbidden_construct:broad_except (allowed source) | class-a-broad-except-allowed | - | - | shop/cli/main.py |
| class_a | forbidden_dependency:pair | class-a-forbidden-dependency-pair | DEP-RENDER-NO-STORE | closed_world.observed_forbidden, graph.drift, rule.violated | shop/render/text.py |
| class_a | forbidden_dependency:target_symbol | class-a-forbidden-dependency-target-symbol | DEP-STORE-NO-MONEY | rule.violated | shop/store/repository.py |
| class_a | forbidden_dependency:include_type_checking | class-a-forbidden-dependency-include-type-checking | DEP-APP-NO-STORE-SQLITE | rule.violated | architecture-contract.json |
| class_a | forbidden_dependency:allowed_sources | class-a-forbidden-dependency-allowed-sources | DEP-APP-NO-STORE-SQLITE, DEP-APP-NO-STORE-SQLITE | rule.violated, rule.violated | architecture-contract.json |
| class_a | external_dependency_scope | class-a-external-dependency-scope | EXTERNAL-JSON-STORE | rule.violated | shop/app/reporting.py |
| class_a | complete_assignment | class-a-complete-assignment | ASSIGNMENT-COMPLETE | rule.violated | shop/extra.py |
| class_a | no_component_cycles | class-a-no-component-cycles | COMPONENT-NO-CYCLES | rule.violated | architecture-contract.json, docs/architecture/shop.md, shop/model/uses_render.py |
| class_a | closed_world:missing | class-a-closed-world-missing | - | closed_world.missing | architecture-contract.json |
| class_a | closed_world:duplicate | class-a-closed-world-duplicate | - | closed_world.duplicate | architecture-contract.json |
| class_a | interface_boundary:underscore | class-a-interface-boundary-underscore | INTERFACE-BOUNDARY | rule.violated | shop/cli/main.py |
| class_a | interface_boundary:undeclared symbol | class-a-interface-boundary-undeclared-symbol | INTERFACE-BOUNDARY | rule.violated | shop/cli/main.py |
| class_a | interface_boundary:whole-module import | class-a-interface-boundary-whole-module | INTERFACE-BOUNDARY | rule.violated | shop/app/maintenance_report.py |
| class_a | interface_boundary:__all__ gate | class-a-interface-boundary-all-gate | INTERFACE-BOUNDARY | rule.violated | shop/render/discount_probe.py |
| class_a | interface_boundary:accepted re-export | class-a-interface-boundary-accepted-reexport | - | - | shop/app/accepted_reexport.py |
| validation | interface.undeclared | validation-interface-undeclared | - | interface.undeclared | architecture-contract.json |
| validation | interface.unused | validation-interface-unused | - | interface.unused | architecture-contract.json |
| validation | rationale.placeholder | validation-rationale-placeholder | - | rationale.placeholder | architecture-contract.json |
| validation | rationale.repeated | validation-rationale-repeated | - | rationale.repeated | architecture-contract.json |
| validation | graph.count | validation-graph-count | - | graph.count | docs/architecture/shop.md |
| validation | reference.namespace | validation-reference-namespace | - | reference.namespace | architecture-contract.json |
| validation | reference.public_owner | validation-reference-public-owner | - | reference.public_owner | architecture-contract.json |
| validation | reference.public_underscore | validation-reference-public-underscore | - | reference.public_underscore | architecture-contract.json |
| validation | reference.provenance | validation-reference-provenance | - | reference.provenance | architecture-contract.json |
| validation | reference.package_unscanned | validation-reference-package-unscanned | - | reference.package_unscanned | architecture-contract.json |
| validation | contract.schema_version | validation-contract-schema-version | - | contract.schema_version | architecture-contract.json |
| validation | contract.invalid | validation-contract-invalid | - | contract.invalid | architecture-contract.json |
| validation | observation.incomplete | validation-observation-incomplete | - | - | tests/test_trace.py |
| validation | rule_without_subjects | validation-rule-without-subjects | - | - | architecture-contract.json |
| validation | parse_error | validation-parse-error | - | - | shop/model/broken_syntax.py |
| validation | scope_empty | validation-scope-empty | - | - | architecture-contract.json, shop/app/maintenance.py, shop/app/orders.py, shop/cli/main.py, shop/model/entities.py, shop/render/text.py, shop/store/__init__.py, shop/store/repository.py, shop/store/sqlite.py |
| validation | runtime_mismatch | validation-runtime-mismatch | - | - | pyproject.toml |
| validation | missing_tool | validation-missing-tool | - | - | tests/test_analyzer.py |
| validation | timeout | validation-timeout | - | - | tests/test_analyzer.py |
| validation | incomparable_runtime | validation-incomparable-runtime | - | - | tests/test_runtime_delta.py |
| validation | existing_files | validation-existing-files | - | - | tests/test_onboarding.py |
| class_b | SCALARS:violations | class-b-scalar-violations | - | - | tests/test_ratchets.py |
| class_b | SCALARS:cycle_edges | class-b-scalar-cycle_edges | - | - | tests/test_ratchets.py |
| class_b | SCALARS:private_crossings | class-b-scalar-private_crossings | - | - | tests/test_ratchets.py |
| class_b | SCALARS:typing_positions | class-b-scalar-typing_positions | - | - | tests/test_ratchets.py |
| class_b | SCALARS:calls_unresolved | class-b-scalar-calls_unresolved | - | - | tests/test_ratchets.py |
| class_b | SCALARS:coverage_failures | class-b-scalar-coverage_failures | - | - | docs/rules.md |
| class_b | unresolved_ratio | class-b-unresolved-ratio | - | - | fixtures/reproduce_milestone1.py |
| class_b | GUARDRAIL_DIMENSIONS:violations | class-b-guardrail-violations | - | - | tests/test_expectation.py |
| class_b | GUARDRAIL_DIMENSIONS:cycles | class-b-guardrail-cycles | - | - | tests/test_expectation.py |
| class_b | GUARDRAIL_DIMENSIONS:private_crossings | class-b-guardrail-private_crossings | - | - | tests/test_expectation.py |
| class_b | GUARDRAIL_DIMENSIONS:typing_signals | class-b-guardrail-typing_signals | - | - | tests/test_expectation.py |
| class_b | GUARDRAIL_DIMENSIONS:unknowns | class-b-guardrail-unknowns | - | - | tests/test_expectation.py |
| class_b | coverage_must_pass | class-b-coverage-must-pass | - | - | tests/test_expectation.py |
| protocol | git_order | protocol-git-order | - | - | tests/test_git_lock.py |
| protocol | host_order | protocol-host-order | - | - | fixtures/reproduce_milestone1.py |
| class_c | ContractDeclarations.capabilities | class-c-capabilities | - | - | fixtures/F-architecture/architecture-contract.json |
| class_c | ContractDeclarations.review_scopes | class-c-review-scopes | - | - | fixtures/F-architecture/architecture-contract.json |
| class_c | ContractDeclarations.public_api | class-c-public-api | - | - | docs/rules.md |
| class_c | ContractDeclarations.public_api_provenance | class-c-public-api-provenance | - | - | docs/rules.md |
| class_c | ContractDeclarations.public_commands | class-c-public-commands | - | - | fixtures/F-architecture/architecture-contract.json |
| class_c | ContractDeclarations.context_roots | class-c-context-roots | - | - | fixtures/F-architecture/architecture-contract.json |
| class_c | ContractDeclarations.context_roots_provenance | class-c-context-roots-provenance | - | - | fixtures/F-architecture/architecture-contract.json |
| class_c | ContractDeclarations.paths | class-c-paths | - | - | fixtures/F-architecture/architecture-contract.json |
| class_c | ContractDeclarations.spot_owners | class-c-spot-owners | - | - | fixtures/F-architecture/architecture-contract.json |
| class_d | review_claims | class-d-review-claims | - | - | docs/rules.md |
