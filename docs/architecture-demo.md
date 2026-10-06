# Architecture demo catalog

Generated from [CATALOG](../fixtures/architecture_demo.py), which owns fixture overlays and expected
outcomes (AD-11). Rows use `fixtures/F-architecture` unless they name another sample or existing
test evidence. Regenerate with `python -m fixtures.architecture_demo --markdown`.

`tour` and `dart-tour` combine violations.

Replay with `make demo-architecture VARIANT=<variant> OUTPUT=<new-path>`. It validates the fixture
and writes report JSON and HTML; the exit is the higher of both command exits. A validation failure
still permits a report with valid inputs. An invalid explicit baseline rejects both commands.
Catalog baselines apply to both; only `deepest_inside_changed` replays `--against`. Check-protocol
and tested-only rows cannot replay as reports. Destination files must not exist.

`make demo-dart` replays the Dart story from `fixtures/G-dart`.

Target frames describe layout; component ownership and permissions remain contract decisions. A null
dependency rank does not identify a cycle. See [Target semantics](target-first.md).

`make report-browser OUTPUT=<fresh-directory>` captures the README views and verifies navigation,
filters and evidence preservation. Browser tests do not prove human usability.

`make demo-uml OUTPUT=<fresh-directory>` generates Python, Dart and TypeScript reports. Python
variants cover matching intent, signature failures, unknown enum literals and closed inventories.
Target stays independent across overlays. Dart and TypeScript inner UML observation remains
unavailable and comparisons stay UNKNOWN. A successful command does not imply `declared_rules` PASS.
See [UML scope](architecture/uml-model-target.md).

| Variant | Demo | Rule ids | Diagnostic codes | Evidence / sample |
|---|---|---|---|---|
| tour | validate/report run | APP-TYPES-NOT-DICT, ASSIGNMENT-COMPLETE, COMPONENT-NO-CYCLES, CONSTRUCT-NO-ANY, CONSTRUCT-NO-ASSERT, CONSTRUCT-NO-BROAD-EXCEPT, CONSTRUCT-NO-DYNAMIC, CONSTRUCT-NO-DYNAMIC, DEP-APP-NO-STORE-BACKEND, DEP-APP-NO-STORE-SQLITE, DEP-MODEL-NO-RENDER, DEP-RENDER-NO-STORE, DEP-STORE-NO-MONEY, EXTERNAL-COMPLETE, EXTERNAL-JSON-STORE, INTERFACE-BOUNDARY, LAYERS-MODEL, MODEL-TYPES-IN-ENTITIES, ROOT-LAYOUT, STORE-PEERS-ISOLATED, store:STORE-REQUIRES-COMPLETE | closed_world.observed_forbidden, closed_world.observed_forbidden, graph.drift, rule.violated, rule.violated, rule.violated, rule.violated, rule.violated, rule.violated, rule.violated, rule.violated, rule.violated, rule.violated, rule.violated, rule.violated, rule.violated, rule.violated, rule.violated, rule.violated, rule.violated, rule.violated, rule.violated, rule.violated, rule.violated | - |
| clean | validate/report run | - | - | - |
| class-a-compatibility-clean | validate/report run | - | - | - |
| class-a-compatibility-migration | validate/report run | - | - | - |
| class-a-compatibility-effectful | validate/report run | - | compatibility.invalid, compatibility.invalid | - |
| class-a-compatibility-product-import | validate/report run | - | compatibility.invalid | - |
| class-a-compatibility-wrong-export | validate/report run | - | compatibility.invalid | - |
| against-compatibility-added | validate --against run | - | - | - |
| against-compatibility-promoted | validate --against run | - | - | - |
| class-a-construct-getattr | validate/report run | CONSTRUCT-NO-DYNAMIC | rule.violated | - |
| class-a-construct-hasattr | validate/report run | CONSTRUCT-NO-DYNAMIC | rule.violated | - |
| class-a-construct-cast | validate/report run | CONSTRUCT-NO-DYNAMIC | rule.violated | - |
| class-a-construct-eval | validate/report run | CONSTRUCT-NO-DYNAMIC | rule.violated | - |
| class-a-construct-exec | validate/report run | CONSTRUCT-NO-DYNAMIC | rule.violated | - |
| class-a-construct-dynamic_import | validate/report run | CONSTRUCT-NO-DYNAMIC | rule.violated | - |
| class-a-construct-type_ignore | validate/report run | CONSTRUCT-NO-DYNAMIC | rule.violated | - |
| class-a-construct-any_annotation | validate/report run | CONSTRUCT-NO-ANY, CONSTRUCT-NO-ANY | rule.violated, rule.violated | - |
| class-a-construct-placeholder_body | validate/report run | CONSTRUCT-NO-PLACEHOLDER | rule.violated | - |
| class-a-construct-assert | validate/report run | CONSTRUCT-NO-ASSERT | rule.violated | - |
| class-a-construct-broad_except | validate/report run | CONSTRUCT-NO-BROAD-EXCEPT | rule.violated | - |
| class-a-construct-setattr | validate/report run | CONSTRUCT-NO-DYNAMIC | rule.violated | - |
| class-a-construct-delattr | validate/report run | CONSTRUCT-NO-DYNAMIC | rule.violated | - |
| class-a-construct-vars | validate/report run | CONSTRUCT-NO-DYNAMIC | rule.violated | - |
| class-a-construct-dunder_dict | validate/report run | CONSTRUCT-NO-DYNAMIC | rule.violated | - |
| class-a-construct-string_literal_compare | validate/report run | CONSTRUCT-NO-STRING-LITERAL-COMPARE, CONSTRUCT-NO-STRING-LITERAL-COMPARE, CONSTRUCT-NO-STRING-LITERAL-COMPARE | rule.violated, rule.violated, rule.violated | - |
| class-a-broad-except-exact | validate/report run | CONSTRUCT-NO-BROAD-EXCEPT | rule.violated | - |
| class-a-broad-except-prefix | validate/report run | - | - | - |
| class-a-type-ignore-exact | validate/report run | - | - | - |
| class-a-type-ignore-neighbors | validate/report run | CONSTRUCT-NO-ANY, CONSTRUCT-NO-DYNAMIC, CONSTRUCT-NO-DYNAMIC, CONSTRUCT-NO-DYNAMIC, CONSTRUCT-NO-DYNAMIC | rule.violated, rule.violated, rule.violated, rule.violated, rule.violated | - |
| class-a-layer-order | validate/report run | LAYERS-MODEL | rule.violated | - |
| class-a-complete-requires | validate/report run | REQUIRES-COMPLETE | rule.violated | - |
| class-a-complete-requires-type-checking | validate/report run | REQUIRES-COMPLETE, REQUIRES-COMPLETE, REQUIRES-COMPLETE, REQUIRES-COMPLETE | rule.violated, rule.violated, rule.violated, rule.violated | - |
| class-a-complete-requires-inside | validate/report run | store:STORE-REQUIRES-COMPLETE, store:STORE-REQUIRES-COMPLETE, store:STORE-REQUIRES-COMPLETE | rule.violated, rule.violated, rule.violated | - |
| class-a-forbidden-construct-inside-clean | validate/report run | - | - | - |
| class-a-forbidden-construct-inside-violation | validate/report run | store:STORE-NO-EVAL | interface.usage_unknown, rule.violated | - |
| class-a-recursive-inside-clean | validate/report run | - | - | - |
| class-a-recursive-inside-violation | validate/report run | store:backend:tasks:DEEP-REQUIRES-COMPLETE | rule.violated | - |
| class-a-recursive-wide-package | validate/report run | - | - | - |
| class-a-recursive-deep-interface | validate/report run | store:backend:tasks:DEEP-INTERFACE | interface.planned_built, rule.violated | - |
| validation-recursive-child-missing | validate/report run | - | contract.invalid | - |
| validation-recursive-child-cycle | validate/report run | - | contract.invalid | - |
| validation-recursive-child-unsupported | validate/report run | - | contract.invalid | - |
| against-recursive-deepest-contract-change | validate --against run | - | - | - |
| validation-recursive-interface-public-unused | validate/report run | - | interface.unused | - |
| validation-recursive-interface-public-used | validate/report run | - | - | - |
| validation-recursive-interface-planned-unused | validate/report run | - | - | - |
| validation-recursive-interface-planned-used | validate/report run | store:backend:tasks:DEEP-INTERFACE | interface.planned_built, rule.violated | - |
| class-a-complete-external-scope | validate/report run | EXTERNAL-COMPLETE | rule.violated | - |
| class-a-forbidden-dependency-pair | validate/report run | DEP-RENDER-NO-STORE | closed_world.observed_forbidden, graph.drift, rule.violated | - |
| class-a-forbidden-dependency-target-symbol | validate/report run | DEP-STORE-NO-MONEY | rule.violated | - |
| class-a-forbidden-dependency-include-type-checking | validate/report run | DEP-APP-NO-STORE-SQLITE | rule.violated | - |
| class-a-forbidden-dependency-allowed-sources | validate/report run | DEP-APP-NO-STORE-SQLITE, DEP-APP-NO-STORE-SQLITE | rule.violated, rule.violated | - |
| class-a-external-dependency-scope | validate/report run | EXTERNAL-JSON-STORE | rule.violated | - |
| class-a-complete-assignment | validate/report run | ASSIGNMENT-COMPLETE, ROOT-LAYOUT | rule.violated, rule.violated | - |
| class-a-no-component-cycles | validate/report run | COMPONENT-NO-CYCLES | rule.violated | - |
| class-a-no-component-cycles-module-hidden | validate/report run | - | - | - |
| class-a-no-component-cycles-module | validate/report run | MODEL-MODULES-ACYCLIC | rule.violated | - |
| report-partial-module-cycle-scan | validate/report run | - | reference.package_unscanned | - |
| class-a-package-cycle-rollup-only | validate/report run | COMPONENT-NO-CYCLES | rule.violated | - |
| class-a-package-cycle-backed | validate/report run | COMPONENT-NO-CYCLES | rule.violated | - |
| class-a-decision-open | validate/report run | - | decision.open | - |
| class-a-closed-world-duplicate | validate/report run | - | closed_world.duplicate | - |
| class-a-allowed-dependency-duplicate | validate/report run | - | closed_world.duplicate | - |
| class-a-decision-conflict | validate/report run | DEP-STORE-NO-MODEL-CONFLICT, DEP-STORE-NO-MODEL-CONFLICT, DEP-STORE-NO-MODEL-CONFLICT | closed_world.observed_forbidden, decision.conflict, rule.violated, rule.violated, rule.violated | - |
| class-a-sibling-isolation | validate/report run | STORE-PEERS-ISOLATED | rule.violated | - |
| class-a-interface-public-method-type | validate/report run | - | - | - |
| class-a-interface-private-method-type | validate/report run | - | interface.unused | - |
| class-a-interface-boundary-underscore | validate/report run | INTERFACE-BOUNDARY | rule.violated | - |
| class-a-interface-boundary-undeclared-symbol | validate/report run | INTERFACE-BOUNDARY | rule.violated | - |
| class-a-interface-boundary-whole-module | validate/report run | INTERFACE-BOUNDARY | rule.violated | - |
| class-a-interface-boundary-all-gate | validate/report run | INTERFACE-BOUNDARY | rule.violated | - |
| class-a-interface-boundary-accepted-reexport | validate/report run | - | - | - |
| class-d-interface-profile-barrel | validate/report run | - | - | - |
| class-a-interface-boundary-package-attribute-over-submodule | validate/report run | INTERFACE-BOUNDARY | rule.violated | - |
| class-a-private-attribute-untyped | validate/report run | - | - | - |
| class-a-private-attribute-any-owner | validate/report run | - | - | - |
| target-module-present | validate/report run | - | - | - |
| target-module-absent | validate/report run | - | - | - |
| target-empty-responsibilities | validate/report run | - | - | - |
| target-hierarchy-positive | validate/report run | - | - | - |
| target-hierarchy-ambiguous | validate/report run | - | - | - |
| target-hierarchy-missing | validate/report run | - | - | - |
| target-hierarchy-cycle | validate/report run | - | - | - |
| class-a-root-layout-clean | validate/report run | - | - | - |
| class-a-root-layout-nested-root | validate/report run | - | - | - |
| validation-root-layout-invalid-child | validate/report run | - | contract.invalid | - |
| class-a-root-layout-violation | validate/report run | ASSIGNMENT-COMPLETE, ROOT-LAYOUT | rule.violated, rule.violated | - |
| class-a-root-layout-empty-package | validate/report run | ROOT-LAYOUT | rule.violated | - |
| class-a-root-layout-blank-first-line | validate/report run | ASSIGNMENT-COMPLETE, ROOT-LAYOUT | rule.violated, rule.violated | - |
| test-scope-clean | validate/report --config archkeel-tests.toml run | - | - | - |
| test-scope-helper-in-unit | validate/report --config archkeel-tests.toml run | TESTS-EXTERNAL-SHOP, TESTS-EXTERNAL-SHOP, TESTS-EXTERNAL-SHOP, TESTS-HELPERS-IN-SUPPORT, TESTS-REQUIRES-COMPLETE | graph.drift, rule.violated, rule.violated, rule.violated, rule.violated, rule.violated | - |
| test-scope-helper-at-root | validate/report --config archkeel-tests.toml run | TESTS-ASSIGNMENT-COMPLETE, TESTS-EXTERNAL-SHOP, TESTS-EXTERNAL-SHOP, TESTS-EXTERNAL-SHOP, TESTS-HELPERS-IN-SUPPORT, TESTS-ROOT-LAYOUT | graph.drift, rule.violated, rule.violated, rule.violated, rule.violated, rule.violated, rule.violated | - |
| test-scope-suite-crossing | validate/report --config archkeel-tests.toml run | TESTS-REQUIRES-COMPLETE | graph.drift, rule.violated | - |
| test-scope-unit-imports-product | validate/report --config archkeel-tests.toml run | TESTS-EXTERNAL-SHOP | rule.violated | - |
| class-a-symbol-placement | validate/report run | MODEL-TYPES-IN-ENTITIES | rule.violated | - |
| class-a-boundary-types | validate/report run | APP-TYPES-NOT-DICT | rule.violated | - |
| class-a-boundary-types-mapping | validate/report run | APP-TYPES-NOT-DICT | rule.violated | - |
| class-a-boundary-types-mapping-allowed | validate/report run | - | - | - |
| class-a-boundary-types-opaque-map-values | validate/report run | - | - | - |
| class-a-boundary-types-opaque-map-values-missing | validate/report run | APP-TYPES-NOT-DICT, APP-TYPES-NOT-DICT | rule.violated, rule.violated | - |
| class-a-boundary-types-opaque-map-values-unknown | validate/report run | - | - | - |
| class-a-boundary-types-native-map-list-values | validate/report run | APP-TYPES-NOT-DICT | rule.violated | - |
| class-a-boundary-types-native-map-list-values-missing | validate/report run | APP-TYPES-NOT-DICT, APP-TYPES-NOT-DICT, APP-TYPES-NOT-DICT | rule.violated, rule.violated, rule.violated | - |
| class-a-boundary-types-contained-mapping | validate/report run | - | - | - |
| class-a-boundary-types-contained-mapping-siblings | validate/report run | APP-TYPES-NOT-DICT | rule.violated | - |
| class-a-boundary-types-contained-mapping-unknown | validate/report run | - | - | - |
| class-a-boundary-types-builtin-dict-allowed | validate/report run | - | - | - |
| class-a-boundary-types-direct-default | validate/report run | - | - | - |
| class-a-boundary-types-direct-neighbors | validate/report run | APP-TYPES-NOT-DICT, APP-TYPES-NOT-DICT | rule.violated, rule.violated | - |
| class-a-boundary-types-shadowed-dict-unknown | validate/report run | - | - | - |
| class-a-boundary-types-native-payload | validate/report run | - | - | - |
| class-a-boundary-types-native-controls | validate/report run | APP-TYPES-NOT-DICT, APP-TYPES-NOT-DICT, APP-TYPES-NOT-DICT, APP-TYPES-NOT-DICT, APP-TYPES-NOT-DICT | rule.violated, rule.violated, rule.violated, rule.violated, rule.violated | - |
| class-a-boundary-types-mixed-evidence | validate/report run | APP-TYPES-NOT-DICT | rule.violated | - |
| class-a-boundary-types-declared-type | validate/report run | APP-TYPES-NOT-DICT | rule.violated | - |
| class-a-boundary-types-in-collection | validate/report run | APP-TYPES-NOT-DICT | rule.violated | - |
| class-a-boundary-types-reexport | validate/report run | RENDER-TYPES-NOT-DICT | rule.violated | - |
| class-a-boundary-types-reexport-aliases | validate/report run | RENDER-TYPES-NOT-DICT | rule.violated | - |
| class-a-boundary-types-ordinary-reexport | validate/report run | RENDER-TYPES-NOT-DICT | rule.violated | - |
| class-a-boundary-types-ordinary-reexport-chain-unknown | validate/report run | - | - | - |
| class-a-boundary-types-owned-public-type | validate/report run | - | - | - |
| class-a-boundary-types-owned-public-broad-field | validate/report run | APP-TYPES-NOT-DICT | rule.violated | - |
| class-a-boundary-types-datetime | validate/report run | - | - | - |
| class-a-boundary-types-datetime-external | validate/report run | - | - | - |
| class-a-boundary-types-object-field | validate/report run | APP-TYPES-NOT-DICT | rule.violated | - |
| class-a-boundary-types-model-field | validate/report run | APP-TYPES-NOT-DICT | rule.violated | - |
| class-a-inherited-generic-return | validate/report run | - | - | - |
| class-a-inherited-generic-undeclared-return | validate/report run | APP-TYPES-NOT-DICT | rule.violated | - |
| class-a-inherited-generic-undeclared-batch | validate/report run | APP-TYPES-NOT-DICT | rule.violated | - |
| class-a-inherited-generic-unused | validate/report run | - | interface.unused | - |
| class-a-inherited-generic-ambiguous | validate/report run | - | interface.usage_unknown | - |
| class-a-inherited-generic-reexport-unknown | validate/report run | - | interface.usage_unknown | - |
| class-a-inherited-local-declared | validate/report run | - | - | - |
| class-a-inherited-local-broad | validate/report run | APP-TYPES-NOT-DICT | rule.violated | - |
| class-a-inherited-local-unknown | validate/report run | - | - | - |
| class-a-owned-property-unknown | validate/report run | - | - | - |
| public-api-inherited-missing | validate/report run | - | api_surface.missing | - |
| public-api-inherited-declared | validate/report run | - | - | - |
| public-api-inherited-unknown | validate/report run | - | - | - |
| public-api-alias-missing | validate/report run | - | api_surface.missing | - |
| public-api-alias-declared | validate/report run | - | - | - |
| validation-requires-local-target | validate/report run | - | - | - |
| validation-requires-target-unknown | validate/report run | - | contract.invalid | - |
| validation-component-label-duplicate | validate/report run | - | contract.invalid | - |
| validation-module-placement-clean | validate/report run | - | - | - |
| validation-module-placement | validate/report run | COMP-MODEL, ROOT-LAYOUT | rule.violated, rule.violated | - |
| validation-interface-undeclared | validate/report run | - | interface.undeclared | - |
| validation-interface-unused | validate/report run | - | interface.unused | - |
| validation-interface-missing | validate/report run | - | interface.missing | - |
| validation-api-surface-missing | validate/report run | - | api_surface.missing | - |
| validation-api-surface-not-exported | validate/report run | - | api_surface.missing | - |
| validation-interface-planned-not-built | validate/report run | - | - | - |
| validation-interface-planned-built | validate/report run | - | - | - |
| validation-interface-planned-built-reached | tested only | - | interface.planned_built | tests/test_validation.py |
| validation-agent-decisions-attributed | validate/report run | - | - | - |
| validation-rationale-placeholder | validate/report run | - | rationale.placeholder | - |
| validation-rationale-repeated | validate/report run | - | rationale.repeated | - |
| validation-graph-count | validate/report run | - | graph.count | - |
| validation-graph-drift-write-graph | validate/report run | - | graph.drift, graph.drift | - |
| validation-graph-drift-subgraph | validate/report run | - | graph.drift, graph.drift | - |
| validation-target-graph-drift-write-graph | validate/report run | - | graph.drift | - |
| validation-target-graph-drift-subgraph | validate/report run | - | graph.drift | - |
| validation-reference-namespace | validate/report run | - | reference.namespace | - |
| validation-reference-public-owner | validate/report run | - | reference.public_owner | - |
| validation-reference-public-underscore | validate/report run | - | reference.public_underscore | - |
| validation-reference-provenance | validate/report run | - | reference.provenance | - |
| validation-reference-package-unscanned | validate/report run | - | reference.package_unscanned | - |
| validation-contract-schema-version | validate/report run | - | contract.schema_version | - |
| validation-contract-invalid | validate/report run | - | contract.invalid | - |
| validation-observation-incomplete | tested only | - | - | tests/test_trace.py |
| validation-measurement-budget-clean | validate/report run | - | - | - |
| validation-measurement-budget-rise | validate/report run | - | - | - |
| validation-measurement-budget-call-sites | tested only | - | - | tests/test_unresolved_call_sites.py |
| validation-facade-budget-clean | validate/report run | - | - | - |
| validation-coupling-budget-clean | validate/report run | - | - | - |
| validation-facade-budget-exceeded | validate/report run | - | budget.exceeded | - |
| validation-coupling-budget-exceeded | validate/report run | - | budget.exceeded | - |
| validation-facade-budget-unknown | validate/report run | - | budget.unknown | - |
| validation-facade-budget-target-first | validate/report run | - | - | - |
| validation-facade-budget-ratchet | validate/report run | - | - | - |
| validation-baseline-invalid | tested only | - | - | tests/test_baseline.py |
| validation-baseline-accept-new | tested only | - | - | tests/test_cli.py |
| validation-baseline-root-relative | tested only | - | - | tests/test_cli.py |
| validation-baseline-roles | tested only | - | - | tests/test_baseline.py |
| validation-baseline-role-evidence | tested only | - | - | tests/test_widening.py |
| validation-baseline-interface-narrowing | validate/report run | - | - | - |
| validation-baseline-subject-order | validate/report run | DEP-STORE-NO-MONEY | - | - |
| validation-baseline-refused | validate --write-baseline run | DEP-STORE-NO-MONEY | - | - |
| validation-against-invalid | tested only | - | - | tests/test_widening.py |
| validation-amendment-invalid | tested only | - | - | tests/test_widening.py |
| validation-inside-local-public | validate/report run | - | - | - |
| validation-inside-direct-publication | validate/report run | - | - | - |
| validation-inside-direct-publication-private-parent | validate/report run | INTERFACE-BOUNDARY | interface.unused, rule.violated | - |
| validation-inside-public-module-missing | validate/report run | - | interface.missing | - |
| validation-inside-public-mismatch-retired | tested only | - | - | tests/test_inside_rule_parity.py |
| validation-inside-forbidden-import | validate/report run | - | inside.forbidden_import | - |
| validation-inside-contract-missing | validate/report run | DEP-STORE-NO-MONEY | contract.invalid, rule.violated | - |
| validation-api-surface-unknown | validate/report run | - | - | - |
| validation-rule-without-subjects | validate/report run | - | - | - |
| validation-parse-error | validate/report run | - | - | - |
| validation-scope-empty | validate/report run | - | - | - |
| validation-runtime-mismatch | validate/report run | - | - | - |
| validation-missing-tool | tested only | - | - | tests/test_analyzer.py |
| validation-timeout | tested only | - | - | tests/test_analyzer.py |
| validation-incomparable-runtime | tested only | - | - | tests/test_runtime_delta.py |
| validation-rule-unsupported-by-profile | tested only | - | - | tests/test_dart_profile.py |
| validation-existing-files | tested only | - | - | tests/test_onboarding.py |
| validation-filter-unknown | tested only | - | - | tests/test_report_filter.py |
| against-widened-unamended | validate --against run | - | - | - |
| against-widened-amended | validate --against run | - | - | - |
| against-narrowed-only | validate --against run | - | - | - |
| against-boundary-types-added | validate --against run | - | - | - |
| against-symbol-placement-added | validate --against run | - | - | - |
| against-boundary-types-removed | validate --against run | - | - | - |
| against-symbol-placement-removed | validate --against run | - | - | - |
| against-facade-budget-raised | validate --against run | - | - | - |
| against-cycle-rule-scoped | validate --against run | - | - | - |
| against-contract-introduced | validate --against run | - | - | - |
| against-contract-introduced-amended | validate --against run | - | - | - |
| against-package-renamed | validate --against run | - | - | - |
| against-package-renamed-widened | validate --against run | - | - | - |
| against-package-renamed-relocated-root | validate --against run | - | - | - |
| dart-against-package-renamed | validate --against run | - | - | G-dart |
| protocol-ordered | check run | - | - | - |
| protocol-published-after-candidate | check run | - | - | - |
| protocol-candidate-changed-expectation | check run | - | - | - |
| protocol-empty-declaration | check run | - | - | - |
| class-b-check-scalar-violations | check run | - | - | - |
| class-b-check-guardrail-violations | check run | - | - | - |
| class-b-scalar-private-crossings | check run | - | - | - |
| class-b-guardrail-private-crossings | check run | - | - | - |
| class-b-scalar-private-attribute-access | check run | - | - | - |
| class-b-guardrail-private-attribute-access | check run | - | - | - |
| class-b-scalar-unknown-positions | check run | - | - | - |
| class-b-scalar-cycle-edges | check run | - | - | - |
| class-b-check-guardrail-cycles | check run | - | - | - |
| class-b-scalar-typing-positions | check run | - | - | - |
| class-b-guardrail-typing-signals | check run | - | - | - |
| class-b-scalar-calls-unresolved | check run | - | - | - |
| class-b-check-unresolved-ratio | check run | - | - | - |
| class-b-scalar-coverage-failures | tested only | - | - | tests/test_ratchets.py |
| class-b-guardrail-unknowns | tested only | - | - | tests/test_expectation.py |
| class-b-guardrail-dependency-edges | tested only | - | - | tests/test_expectation.py |
| class-b-coverage-must-pass | tested only | - | - | tests/test_expectation.py |
| class-c-capabilities | tested only | - | - | fixtures/F-architecture/architecture-contract.json |
| class-c-review-scopes | tested only | - | - | fixtures/F-architecture/architecture-contract.json |
| class-c-public-api | tested only | - | - | fixtures/F-architecture/architecture-contract.json |
| class-c-public-api-provenance | tested only | - | - | fixtures/F-architecture/architecture-contract.json |
| class-c-public-commands | tested only | - | - | fixtures/F-architecture/architecture-contract.json |
| class-c-context-roots | tested only | - | - | fixtures/F-architecture/architecture-contract.json |
| class-c-context-roots-provenance | tested only | - | - | fixtures/F-architecture/architecture-contract.json |
| class-c-paths | tested only | - | - | fixtures/F-architecture/architecture-contract.json |
| class-c-spot-owners | tested only | - | - | fixtures/F-architecture/architecture-contract.json |
| class-c-compat | tested only | - | - | fixtures/F-architecture/architecture-contract.json |
| class-c-modules | tested only | - | - | fixtures/F-architecture/architecture-contract.json |
| class-d-review-claims | tested only | - | - | docs/rules.md |
| class-d-enum-member-reference | tested only | - | - | tests/test_references.py |
| class-d-oversized-inside | tested only | - | - | docs/rules.md |
| class-d-type-fanin | tested only | - | - | docs/rules.md |
| uml-match | validate/report run | - | - | H-uml |
| uml-mismatch | validate/report run | UML-TARGET-a2e40c5592b1b06a | rule.violated | H-uml |
| uml-partial | validate/report run | - | - | H-uml |
| uml-complete | validate/report run | - | - | H-uml |
| uml-dart | validate/report run | - | - | H-uml-dart |
| uml-typescript | validate/report run | - | - | H-uml-typescript |
| ownership-exact-module-positive | validate/report run | - | - | - |
| ownership-exact-module-not-recursive | validate/report run | store:STORE-REQUIRES-COMPLETE | rule.violated | - |
| ownership-exact-module-ambiguous | validate/report run | ASSIGNMENT-COMPLETE, DEP-STORE-NO-APP | reference.public_owner | - |
| dart-clean | validate/report run | - | - | G-dart |
| dart-forbidden-dart-io | validate/report run | DEP-DOMAIN-NO-DART-IO | rule.violated | G-dart |
| dart-complete-requires | validate/report run | REQUIRES-COMPLETE | graph.drift, rule.violated | G-dart |
| dart-component-cycle | validate/report run | COMPONENT-NO-CYCLES, REQUIRES-COMPLETE | graph.drift, rule.violated, rule.violated | G-dart |
| dart-complete-assignment | validate/report run | ASSIGNMENT-COMPLETE, ROOT-LAYOUT | rule.violated, rule.violated | G-dart |
| dart-external-scope | validate/report run | EXTERNAL-HTTP-DATA | rule.violated | G-dart |
| dart-interface-show | validate/report run | INTERFACE-BOUNDARY | rule.violated | G-dart |
| dart-interface-unknown | validate/report run | - | - | G-dart |
| dart-nested-interface-unknown | validate/report run | - | - | G-dart |
| dart-nested-interface-show | validate/report run | - | - | G-dart |
| dart-nested-interface-mixed | validate/report run | domain:core:INTERFACE | rule.violated | G-dart |
| dart-nested-forbidden-symbol-unknown | validate/report run | - | - | G-dart |
| dart-unsupported-rule | validate/report run | - | - | G-dart |
| dart-unsupported-budget | validate/report run | - | - | G-dart |
| dart-unreadable-header | validate/report run | - | - | G-dart |
| dart-tour | validate/report run | ASSIGNMENT-COMPLETE, COMPONENT-NO-CYCLES, DEP-DOMAIN-NO-DART-IO, EXTERNAL-HTTP-DATA, INTERFACE-BOUNDARY, REQUIRES-COMPLETE, REQUIRES-COMPLETE, ROOT-LAYOUT | graph.drift, rule.violated, rule.violated, rule.violated, rule.violated, rule.violated, rule.violated, rule.violated, rule.violated | G-dart |
