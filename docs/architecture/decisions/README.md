# Decision archive

Internal reasons and proof references. Later records can amend earlier ones.
For current behavior, use the [contract](../../../architecture-contract.json), source and tests.

| Decision | Title |
|---|---|
| AD-1 | [Flat analyzer modules](ad-01-analyzer-modules-are-flat-and-singlepurpose.md) |
| AD-2 | [One JSON type](ad-02-json-has-one-type.md) |
| AD-3 | [Analyzer comparability](ad-03-the-analyzer-digest-decides-comparability-the-version-names.md) |
| AD-4 | [Module split criteria](ad-04-module-length-alone-does-not-justify-a-split.md) |
| AD-5 | [Value invariants](ad-05-invariants-live-where-values-are-built.md) |
| AD-6 | [Function responsibility](ad-06-a-function-has-one-responsibility.md) |
| AD-7 | [Measured determinism](ad-07-determinism-is-measured-not-assumed.md) |
| AD-8 | [Statement construct rules](ad-08-statement-constructs-are-class-a-rules.md) |
| AD-9 | [Component interfaces](ad-09-components-declare-their-interface.md) |
| AD-10 | [Intent and observed flow](ad-10-the-report-draws-component-flow-as-intent-against.md) |
| AD-11 | [Rule demo coverage](ad-11-every-checkable-item-has-a-catalogued-demo.md) |
| AD-12 | [Diagnostic codes](ad-12-validation-diagnostics-carry-a-code.md) |
| AD-13 | [Mermaid validation](ad-13-mermaid-diagrams-are-checked-before-github-renders-them.md) |
| AD-14 | [Verdict-driven headlines](ad-14-the-report-headline-follows-its-verdicts-never-the-exit.md) |
| AD-15 | [Onboarding decisions](ad-15-onboarding-is-a-decision-interview-the-code-proposes-the.md) |
| AD-16 | [Onboarding modes and authorship](ad-16-onboarding-defines-a-target-architecture-in-two-agent-modes.md) |
| AD-17 | [Quality goals and pure IR](ad-17-archkeels-own-target-names-its-quality-goals-and-ir-holds.md) |
| AD-18 | [Dependency violations supersede interface findings](ad-18-a-forbidden-dependency-supersedes-the-interface-boundary-on.md) |
| AD-19 | [Plain copy, stable identifiers](ad-19-words-for-people-are-plain-identifiers-for-machines-stay.md) |
| AD-20 | [One contract per level](ad-20-a-level-is-its-own-contract-never-a-nesting-inside-one.md) |
| AD-21 | [Structure observations](ad-21-structure-measurements-are-derivations-never-gates.md) |
| AD-22 | [Language process port](ad-22-the-analyzer-is-a-process-port-with-a-language-profile.md) |
| AD-23 | [Headlines with open decisions](ad-23-the-report-headline-follows-open-decisions-as-well.md) |
| AD-24b | [Observed versus undecided](ad-24b-observed-is-not-undecided.md) |
| AD-24a | [Module navigation and crossing interfaces](ad-24a-a-module-opens-the-same-way-and-its-interface-is-what.md) |
| AD-24 | [Opening undeclared interiors](ad-24-the-report-opens-a-component-without-requiring-a-decision.md) |
| AD-25 | [Peer isolation](ad-25-peers-are-isolated-by-one-rule-not-by-nn1-prohibitions.md) |
| AD-26 | [Review signals and claims](ad-26-a-quality-claim-is-a-signal-a-derivation-and-a-claim-and.md) |
| AD-27 | [Type allowances](ad-27-a-type-escape-hatch-is-decided-not-merely-observed.md) |
| AD-28 | [Undeclared external dependencies](ad-28-an-undeclared-external-dependency-is-a-hole-not-a-detail.md) |
| AD-29 | [Placeholder body rules](ad-29-a-function-that-does-nothing-is-a-claim-not-a-stub.md) |
| AD-30 | [Contradictable ownership claims](ad-30-a-declared-owner-is-worth-nothing-until-something-can.md) |
| AD-31 | [Optional internal decisions](ad-31-deciding-inside-a-component-is-optin-and-only-for-pairs.md) |
| AD-32 | [Closed-world requires](ad-32-a-component-names-what-it-requires-what-it-does-not-name-is.md) |
| AD-33 | [Component interiors as levels](ad-33-a-components-inside-is-a-level-not-a-list-of-pairs.md) |
| AD-34 | [Recorded inside contracts](ad-34-a-declared-inside-is-recorded-so-the-report-draws-it.md) |
| AD-35 | [Shared review counts](ad-35-every-review-claim-is-counted-on-the-run-result-so-the.md) |
| AD-36 | [Scoped inside rule verdicts](ad-36-a-rule-the-inside-declares-is-recorded-and-carried-so-the.md) |
| AD-37 | [Typed stdlib receivers](ad-37-a-receiver-whose-type-is-statically-obvious-resolves-the.md) |
| AD-38 | [Draft component size](ad-38-a-drafted-component-carries-the-size-structuremetrics.md) |
| AD-39 | [Empty selected changes](ad-39-an-empty-selectedchanges-declares-that-nothing.md) |
| AD-40 | [Documented call-result types](ad-40-a-call-whose-callee-the-import-binding-proves-or-whose.md) |
| AD-41 | [Any placement rules](ad-41-where-any-may-appear-is-a-contract-rule-not-a-test.md) |
| AD-42 | [Requires through selectors](ad-42-a-requires-entry-may-name-the-modules-it-goes-through-and.md) |
| AD-43 | [Candidate-declared changes](ad-43-a-candidate-declares-what-it-changed-not-what-the-scanner.md) |
| AD-44 | [Undeclared added-edge guardrail](ad-44-an-undeclared-added-dependency-edge-is-a-guardrail-failure.md) |
| AD-45 | [Analyzer inside contract](ad-45-analyzer-declares-a-threepart-inside-the-way-check-already.md) |
| AD-46 | [Marked graph regeneration](ad-46-validate-writegraph-regenerates-the-marked-component-graph.md) |
| AD-47 | [Python package selection](ad-47-init-breaks-a-tie-between-toplevel-packages-with.md) |
| AD-48 | [Reflection writes and string comparisons](ad-48-reflection-that-writes-and-a-value-compared-with-a-string.md) |
| AD-49 | [Exact allowance scopes](ad-49-an-allowance-may-name-its-module-exactly-so-a-package-root.md) |
| AD-50 | [Edge and interface authorship](ad-50-an-edge-and-an-interface-record-who-decided-them-and-the.md) |
| AD-51 | [Grouped violation counts](ad-51-a-result-carries-its-violations-grouped-by-rule-and-by.md) |
| AD-52 | [Violation fingerprints and baselines](ad-52-a-violation-is-named-by-what-it-is-and-a-baseline-may-hold.md) |
| AD-53 | [Package import binding precedence](ad-53-from-pkg-import-name-follows-pkginitpys-own-binding-before.md) |
| AD-54 | [Typed violation rows](ad-54-a-typed-violation-row-is-the-one-supported-way-to-read-a.md) |
| AD-55 | [Decision-file index](ad-55-the-decision-record-splits-into-one-file-per-decision.md) |
| AD-56 | [Missing versus planned interfaces](ad-56-a-public-entry-the-scan-never-saw-is-missing-and-planned.md) |
| AD-57 | [Target graph marker](ad-57-a-target-graph-marker-draws-the-edges-the-contract-permits.md) |
| AD-58 | [Class placement and boundary types](ad-58-a-class-lives-where-its-symbolplacement-rule-allows-and-a.md) |
| AD-59 | [Cross-component type fan-in](ad-59-a-type-crossing-many-component-boundaries-is-a-review-claim.md) |
| AD-60 | [Report filters](ad-60-report-only-rule-and-component-narrow-what-a-rendered.md) |
| AD-61 | [Digest-bound widening amendments](ad-61-a-widening-fails-unless-an-amendment-binds-its-exact-before.md) |
| AD-62 | [Annotated variable ownership](ad-62-an-annotated-variables-owner-is-the-scope-it-is-written-in.md) |
| AD-63 | [Declared facade type checks](ad-63-boundarytypes-reads-a-components-declared-public-list-not-a.md) |
| AD-64 | [External API facade](ad-64-archkeelapi-is-the-declared-external-contract-and-ir.md) |
| AD-65 | [Facade-exposed public types](ad-65-a-type-a-declared-facade-signature-exposes-is-a-used.md) |
| AD-66 | [External API declarations](ad-66-declarationspublicapi-names-a-consumer-outside-the-package.md) |
| AD-67 | [Undecidable boundary positions](ad-67-an-undecidable-boundary-position-is-unknown-not-silence.md) |
| AD-68 | [Own boundary policies](ad-68-check-and-render-declare-boundarytypes-and-the-ten.md) |
| AD-69 | [One annotation reader](ad-69-one-annotation-is-read-once-for-both-readers.md) |
| AD-70 | [Public API type closure](ad-70-the-external-promise-declares-every-type-it-hands-out.md) |
| AD-71 | [Literal public exports](ad-71-a-promised-name-is-checked-against-the-modules-own-all.md) |
| AD-72 | [Incomplete rule verdicts](ad-72-a-rule-that-could-not-decide-everything-reports-unknown.md) |
| AD-73 | [Shared external type walk](ad-73-the-external-surface-is-judged-by-the-same-walk.md) |
| AD-74 | [Ambiguous bindings](ad-74-a-name-bound-twice-is-unresolvable-not-a-coin-flip.md) |
| AD-75 | [Local violation focus](ad-75-an-open-report-can-focus-on-violations-without-changing.md) |
| AD-76 | [Boundary restrictions in comparison](ad-76-boundary-rules-are-restrictions-in-against.md) |
| AD-77 | [Baseline comparison before writing](ad-77-an-existing-baseline-is-compared-before-it-is-written.md) |
| AD-78 | [Directional baseline evidence](ad-78-baseline-fingerprints-keep-identity-and-record-direction-roles.md) |
| AD-79 | [Planned interface promotion](ad-79-planned-entry-is-target-work-until-reached.md) |
| AD-80 | [Static string constants](ad-80-string-constant-comparisons-are-statically-resolved.md) |
| AD-81 | [Fail-closed Make gate](ad-81-the-project-owns-one-fail-closed-make-gate.md) |
| AD-82 | [Physical component namespace](ad-82-component-namespace-is-placement-not-ownership.md) |
| AD-83 | [Private attribute UNKNOWN](ad-83-private-attribute-access-without-owner-evidence-is-unknown.md) |
| AD-84 | [Facade re-exports and fields](ad-84-boundary-types-follow-declared-facade-reexports.md) |
| AD-85 | [Resolved-import interface narrowing](ad-85-a-resolved-importer-reports-interface-narrowing.md) |
| AD-86 | [Immediate-child layout](ad-86-root-layout-allows-only-declared-immediate-children.md) |
| AD-87 | [Time-bounded compatibility shims](ad-87-compatibility-shims-are-declared-logic-free-and-timebounded.md) |
| AD-88 | [Facade observations](ad-88-declared-facade-measurements-are-observations-not-budgets.md) |
| AD-89 | [Shared measurement baselines](ad-89-selected-measurements-share-the-validation-baseline.md) |
| AD-90 | [Decision-relevant evidence](ad-90-decision-relevant-evidence-is-never-neutral-metadata.md) |
| AD-91 | [Private owner resolution](ad-91-only-top-level-any-makes-private-owner-unknown.md) |
| AD-92 | [UNKNOWN verdicts and measurements](ad-92-undecided-declared-evidence-is-unknown-by-default.md) |
| AD-93 | [Owned DTO fields](ad-93-boundary-types-follow-owned-dto-fields.md) |
| AD-94 | [Static type aliases](ad-94-boundary-types-resolve-static-aliases.md) |
| AD-95 | [Exact nested-field allowances](ad-95-boundary-type-allowances-match-one-nested-field.md) |
| AD-96 | [Enum Literal bindings](ad-96-boundary-types-resolve-enum-literals.md) |
| AD-97 | [Dart directive profile](ad-97-a-dart-profile-observes-directives-and-what-it-cannot-see-is-unknown.md) |
| AD-98 | [Scoped cycle rules](ad-98-a-cycle-rule-names-the-level-and-scope-it-holds-acyclic.md) |
| AD-99 | [Facade and coupling ceilings](ad-99-facade-and-coupling-budgets-are-contract-ceilings.md) |
| AD-100 | [Unresolved call sites](ad-100-an-unresolved-call-change-names-its-call-sites.md) |
| AD-101 | [Separate scan scopes](ad-101-a-second-configuration-governs-a-second-scope.md) |
| AD-102 | [Non-JSON constants](ad-102-a-constant-json-cannot-hold-is-recorded-without-its-value.md) |
| AD-103 | [Root-relative policy paths](ad-103-baseline-and-amendment-paths-are-relative-to-root.md) |
| AD-104 | [Introduced contracts](ad-104-a-contract-the-compared-revision-lacks-is-introduced.md) |
| AD-105 | [Package renames](ad-105-a-package-rename-is-compared-under-its-new-names.md) |
| AD-106 | [Baseline subject ordering](ad-106-a-baseline-entry-names-its-violation-in-any-subject-order.md) |
| AD-107 | [Module file evidence](ad-107-a-modules-file-is-its-evidence-even-when-empty.md) |
| AD-108 | [Enum-member references](ad-108-statically-proven-enum-members-reference-their-class.md) |
| AD-109 | [Ordinary-module literal exports](ad-109-boundary-types-follows-literal-all-in-ordinary-modules.md) |
| AD-110 | [Shared inside evaluators](ad-110-inside-rules-use-the-shared-evaluator.md) |
| AD-111 | [Recursive revision-bound contracts](ad-111-recursive-inside-contract-tree.md) |
| AD-112 | [Local publication boundaries](ad-112-local-publication-at-each-boundary.md) |
| AD-113 | [Local requires targets](ad-113-requires-targets-belong-to-their-contract-level.md) |
| AD-114 | [Nested symbol uncertainty](ad-114-symbol-uncertainty-survives-nested-contracts.md) |
| AD-115 | [Nested API lifecycle](ad-115-nested-api-lifecycle-uses-local-evidence.md) |
| AD-116 | [Explicit diagram filtering](ad-116-diagram-filtering-is-an-explicit-choice.md) |
| AD-117 | [Evaluator-backed verdicts](ad-117-report-verdicts-require-evaluator-evidence.md) |
| AD-118 | [Structure versus conformance](ad-118-structure-review-is-not-contract-conformance.md) |
| AD-119 | [Re-export indexing](ad-119-index-reexports-once-per-boundary-pass.md) |
| AD-120 | [Publication through ancestors](ad-120-direct-publication-crosses-only-declared-ancestors.md) |
| AD-121 | [Exported inherited methods](ad-121-boundary-methods-are-scoped-to-exported-classes.md) |
| AD-122 | [Required field wrappers](ad-122-required-fields-keep-their-inner-boundary-type.md) |
| AD-123 | [Broad mapping types](ad-123-proven-mappings-are-broad-boundary-types.md) |
| AD-124 | [Complete scope receipts](ad-124-rule-pass-requires-complete-scope-receipt.md) |
| AD-125 | [Physical Target hierarchy](ad-125-target-hierarchy-is-physical-presentation.md) |
| AD-126 | [Target call budget](ad-126-target-ranking-call-budget.md) |
| AD-127 | [Unique contained-map allowances](ad-127-a-contained-map-allowance-needs-one-proven-occurrence.md) |
| AD-128 | [Exact module ownership](ad-128-exact-module-ownership-is-distinct-from-package-ownership.md) |
| AD-129 | [Native skill discovery](ad-129-agent-skills-use-native-discovery.md) |
| AD-130 | [Findings-first review](ad-130-review-starts-with-findings.md) |
| AD-131 | [Inherited public fields](ad-131-public-api-includes-inherited-fields.md) |
| AD-132 | [Datetime scalar proof](ad-132-datetime-is-a-proven-boundary-scalar-leaf.md) |
| AD-133 | [Exact type-ignore allowances](ad-133-type-ignore-allowances-bind-one-occurrence.md) |
| AD-134 | [Direct boundary position selectors](ad-134-omitted-boundary-path-selects-the-direct-position.md) |
| AD-135 | [Opaque native payloads](ad-135-exact-native-payloads-accept-opacity.md) |
| AD-136 | [Independent regression ceilings](ad-136-regression-checks-hold-independent-ceilings.md) |
| AD-137 | [Resolved inherited finding types](ad-137-inherited-boundary-findings-show-resolved-types.md) |
| AD-138 | [Command-result schema](ad-138-json-results-have-a-published-schema.md) |
| AD-139 | [Readable Target names](ad-139-target-overview-keeps-readable-names.md) |
| AD-140 | [Rule evidence measurements](ad-140-measure-rule-evidence-without-inventing-passes.md) |
| AD-141 | [Bounded GitHub observations](ad-141-github-events-are-bounded-observations.md) |
| AD-142 | [Exact opaque-map values](ad-142-opaque-map-values-need-exact-decisions.md) |
| AD-143 | [Initial PR causal receipt](ad-143-initial-pr-head-proves-scoped-order.md) |
| AD-144 | [Diff scope navigation](ad-144-diff-retains-navigation-scope.md) |
| AD-145 | [Effective inherited methods](ad-145-local-inherited-methods-use-the-existing-base-proof.md) |
| AD-146 | [Analyzer profile identity](ad-146-analyzer-identity-selects-observation-profile.md) |
| AD-147 | [Language-aware revision inputs](ad-147-revision-snapshots-preserve-language-inputs.md) |
| AD-148 | [Source and policy ownership](ad-148-source-facts-and-core-evaluation-have-separate-owners.md) |
| AD-149 | [Uncertain inherited publication](ad-149-uncertain-publication-retains-inherited-type-candidates.md) |
| AD-150 | [Pinned TypeScript collector](ad-150-typescript-imports-use-a-pinned-npm-collector.md) |
| AD-151 | [Unproven require references](ad-151-unproven-require-references-retain-unknown.md) |
| AD-152 | [Validated construct identity](ad-152-validated-construct-identity-controls-rules.md) |
| AD-153 | [Unproven signature candidates](ad-153-unproven-chains-retain-declared-signatures.md) |
| AD-154 | [Incomplete module ownership](ad-154-incomplete-ownership-names-its-module.md) |
| AD-156 | [Compact self provenance](ad-156-self-evidence-keeps-compact-provenance.md) |
| AD-155 | [Shared open-decision remedy](ad-155-open-dependency-decisions-share-one-remedy.md) |
| AD-157 | [Filtered source locations](ad-157-filtered-json-carries-source-locations.md) |
| AD-158 | [Neutral onboarding drafts](ad-158-onboarding-guidance-keeps-drafts-neutral.md) |
| AD-159 | [Report copy and colors](ad-159-reports-use-reader-facing-copy-and-native-colors.md) |
| AD-160 | [Inner UML uses the standard graph](ad-160-inner-uml-uses-the-standard-graph.md) |
| AD-161 | [Component intent retains boundary semantics](ad-161-component-intent-retains-boundary-semantics.md) |
| AD-162 | [Physical intent does not invent UML](ad-162-physical-intent-does-not-invent-uml.md) |
| AD-163 | [Nested UML retains declaration ownership](ad-163-nested-uml-retains-declaration-ownership.md) |
| AD-164 | [Dependency permissions keep one owner](ad-164-dependency-permissions-keep-one-owner.md) |
| AD-165 | [Diff retains observed relationships](ad-165-diff-retains-observed-relationships.md) |
| AD-166 | [Diff opens observed interiors](ad-166-diff-opens-observed-interiors.md) |
| AD-167 | [Legacy Target projection adds no rule](ad-167-legacy-target-projection-adds-no-rule.md) |
| AD-168 | [Global API intent keeps its declaration evidence](ad-168-global-api-intent-keeps-its-declaration-evidence.md) |
| AD-169 | [Legacy permission scenes retain graph identities](ad-169-legacy-permission-scenes-retain-graph-identities.md) |
| AD-170 | [Conditional inventory does not prove bindings](ad-170-conditional-inventory-does-not-prove-bindings.md) |
| AD-171 | [Static values retain their assignment sites](ad-171-static-values-retain-their-assignment-sites.md) |
| AD-172 | [Lexical resolution uses compiler scopes](ad-172-lexical-resolution-uses-compiler-scopes.md) |
| AD-173 | [Own graph boundary has independent UML intent](ad-173-own-graph-boundary-has-independent-uml-intent.md) |
| AD-174 | [UML focus retains complete evidence](ad-174-uml-focus-retains-complete-evidence.md) |
| AD-175 | [UML relationship filters retain Core status](ad-175-uml-relationship-filters-retain-core-status.md) |
| AD-176 | [Rendering decodes one authenticated Target graph](ad-176-rendering-decodes-one-authenticated-target-graph.md) |
| AD-177 | [UML element filters retain complete evidence](ad-177-uml-element-filters-retain-complete-evidence.md) |
| AD-178 | [Target navigation projects the standard graph](ad-178-target-navigation-projects-the-standard-graph.md) |
| AD-179 | [Reports render one graph boundary](ad-179-reports-render-one-graph-boundary.md) |
| AD-180 | [Relationship exploration retains evidence](ad-180-relationship-exploration-retains-evidence.md) |
| AD-181 | [UML bases retain binding evidence](ad-181-uml-bases-retain-binding-evidence.md) |
| AD-182 | [Shared report integration](ad-182-shared-report-integration.md) |
| AD-183 | [Target references bind declarations](ad-183-target-references-bind-declarations.md) |
| AD-184 | [Annotation declarations retain lexical binding](ad-184-annotation-declarations-retain-lexical-binding.md) |
| AD-185 | [Member inventories retain their owner](ad-185-member-inventories-retain-their-owner.md) |
| AD-186 | [Dense routes can leave card sides](ad-186-dense-routes-can-leave-card-sides.md) |
| AD-187 | [Class field assignments retain their sites](ad-187-class-field-assignments-retain-their-sites.md) |
| AD-188 | [Enum literals have their own UML kind](ad-188-enum-literals-have-their-own-uml-kind.md) |
| AD-189 | [Routing clearance uses numeric intervals](ad-189-routing-clearance-uses-numeric-intervals.md) |
| AD-190 | [Member previews remain readable](ad-190-member-previews-remain-readable.md) |
| AD-191 | [Source protocol Target includes resolver settings](ad-191-source-protocol-target-includes-resolver-settings.md) |
| AD-192 | [UML details separate label and identity](ad-192-uml-details-separate-label-and-identity.md) |
| AD-193 | [UML navigation distinguishes code and boundaries](ad-193-uml-navigation-distinguishes-code-and-boundaries.md) |
| AD-194 | [Language demos retain capability gaps](ad-194-language-demos-retain-capability-gaps.md) |
| AD-195 | [Overviews separate boundaries from file intent](ad-195-overviews-separate-boundaries-from-file-intent.md) |
| AD-196 | [Closed demo intent retains observation limits](ad-196-closed-demo-intent-retains-observation-limits.md) |
| AD-197 | [Expanded Target records eight UNKNOWN inventories](ad-197-expanded-target-records-eight-unknown-inventories.md) |
| AD-198 | [Provider use survives initializer ownership](ad-198-provider-use-survives-initializer-ownership.md) |
| AD-199 | [Nested permissions pin the complete field](ad-199-nested-permissions-pin-the-complete-field.md) |
| AD-200 | [Diff projects recorded imports](ad-200-diff-projects-recorded-imports.md) |
| AD-201 | [Layers assess declared permissions](ad-201-layers-assess-declared-permissions.md) |
| AD-203 | [Native map list values use proven coordinates](ad-203-native-map-list-values-use-proven-coordinates.md) |
| AD-205 | [Class binding proofs use their AST owner](ad-205-class-binding-proofs-use-their-ast-owner.md) |
| AD-206 | [Check families keep existing behavior](ad-206-check-families-keep-existing-behavior.md) |
| AD-202 | [Focused architecture projection](ad-202-focused-architecture-projection.md) |
| AD-204 | [Report Atlas and offline details](ad-204-report-atlas-and-offline-details.md) |
| AD-207 | [Atlas projection boundaries](ad-207-atlas-projection-boundaries.md) |
| AD-208 | [Evaluated module import cells](ad-208-module-import-cells-require-evaluated-import-rules.md) |
| AD-209 | [One offline detail snapshot](ad-209-atlas-uses-one-offline-detail-snapshot.md) |
