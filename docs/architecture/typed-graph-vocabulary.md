# Owned graph and assessment vocabulary

Graph control vocabulary belongs to architecture_graph. Entity and relationship kinds,
visibility, origin, presence, resolution, completeness, versions and assessment aspects
have distinct nominal types. AssessmentStatus is shared with model.RuleVerdict through
the existing facade. Completion PASS/FAIL, comparability SUPPORTED/UNKNOWN and the
four-state RuleAssessmentStatus retain their different meanings.

DecisionMaker names the architect/agent contract role. ArchitectureRuleKind owns the
existing contract rule tags so graph declarations and later contract parsing share
identity without a graph/model import cycle. Amendment.decided_by remains free-form.

Graph wire parsing uses enum constructors once. The two old string-choice loops are
removed. Existing graph dataclasses normalize valid legacy constructor spellings;
builders and UML consumers publish and branch on owned enum values. Module names,
paths, annotations and extension language spellings remain data. Known profile language
decisions consume the shared collector Language type.

Historical graph/comparison/report schemas preserve their values, ordering and subset
domains. Subset fields use Literal of owned enum members. Valid wire versions,
reference validation, inventory evidence and UNKNOWN semantics remain unchanged.

Whole-module native guards protect architecture_graph, graph_codec, target_graph and
check.uml_compare. Independent authored Target entities define enum ownership and
retain existing public field/return intent. Native widening mutations and parser
equality/membership/match/string-alias probes demonstrate enforcement.

Source graph and UML evidence adapters consume these graph values. Their unrelated
evidence-record grammar remains part of the open #542 migration; these guards do not
claim complete protection of those adapters or of presentation-only vocabularies.

## API scope and evidence

The model facade explicitly reexports the canonical AssessmentStatus. RunResult and the
architecture command view name that owner directly; RuleVerdict remains a compatibility
alias with identical type identity. Internal report status imports are private. A
module published as an API must not accidentally publish implementation vocabulary.

The exact Wire predecessor is ff4cae52451f43550639959b6f87a77f96375597; its only production change since 1852 is a profiles.py explanatory comment;
the validated functional sources are identical to 1f9cd588c21d2e485e8d7cf75b4c7a7e41ba793d. Hosted source
verification [38945025394](https://github.com/rapiddweller/archkeel/actions/runs/38945025394)
passed 751 focused tests (10 optional SDK cases skipped), strict Mypy, Ruff, hygiene,
and the real native validation command: zero failures and violations, 918 unresolved
calls, 58 UNKNOWN positions. The per-rule UNKNOWN counts remain CHECK 19, RENDER 29,
ANALYZER 2 and UML 8. No baseline, cap, or allowance changes belong to this increment.

Earlier source verification exposed two accidental public routes,
check.report.RuleAssessmentStatus and check.report.RuleVerdict
(UNKNOWN-BOUNDARY-TYPE-ROUTE-7a356882b5c70c49 and
UNKNOWN-BOUNDARY-TYPE-ROUTE-7fc89e6e6942a7cf). Private imports remove both routes
without changing nominal identity or hiding a declared API.

An additional leaf-by-leaf comparison in that verification run failed after the
native gate had passed: 16 existing UNKNOWN record identities advanced from the
legacy RunResult.declared_rules alias to diagnostics.kind. DiagnosticKind, Diagnostic
and the first-undecidable-field evaluator are unchanged. This is a more precise
remaining legacy finding, not a reduction in UNKNOWN or a new position. The freeze
check compares actual position identities and separately proves this exact leaf
transition against unchanged predecessor source. It still rejects new positions,
new public routes, or unresolved-call growth. Diagnostic vocabulary remains a
separate pending stage of #542.

The production source delta is approximately 495 net lines, primarily explicit
domain members and compatibility normalization in frozen graph values. Two
string-choice helpers are removed; there is no generic conversion framework and no
historical observation snapshot. Independently authored Target entries specify intent
rather than copying measured observations.
