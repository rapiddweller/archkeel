# Shared comparison support — issue #542

Base 6452149d33186dc56d78f7072d73b5dbb988d35a; Delta version PR #579 is independently Astra-approved and remains frozen. Remote GitHub/Actions only. This plan precedes all shared-status production edits. The first checkpoint contains plan, authored API intent and native RED only; production awaits the coordinating scope/cost review.

## Existing responsibility

model.ComparisonStatus currently aliases Literal["SUPPORTED", "UNKNOWN"]. This exact support/availability concept already belongs to seven DTOs: DimensionDelta, RatchetObservations, and the five analysis claims BindingReads, SymbolReferences, TypeFanin, InsideSizes and OwnedLogic. It does not express a rule verdict or metric comparison. Keep its existing model owner and import identity; replace the alias with one two-member StrEnum, not a new Delta-only type or support framework.

Valid legacy constructors retain their wire strings and normalize once to this canonical type. Each existing UNKNOWN invariant still forbids measured counts/candidates. SUPPORTED with zero observations stays distinct from UNKNOWN. Ratchet measurements still exist exactly for SUPPORTED. Unknown/future status text is invalid closed control data; future dimension names and semantic-change tags remain valid open wire data.

## Bounded production surface and cost

Twelve existing files:
- ir/model.py: canonical enum and actual DimensionDelta/RatchetObservations ingress; no unrelated Model domains.
- ir/bindings.py, references.py, type_fanin.py, structure.py, duplication.py: the five existing DTO ingress/invariant and actual producer outputs.
- ir/decisions.py: existing _named support-to-count decision.
- ir/codec_delta.py: one small private nominal status decoder used by both existing Delta ingress paths, then nominal branches and unchanged wire output.
- check/delta.py and check/expectation.py: actual Delta constructors/support decisions.
- render/summary.py and render/html.py: consume the same canonical type; no backend status clone.

Estimated 35–50 net production lines, mostly seven explicit dataclass normalization boundaries. No new module, wrapper, mixin, registry, generic conversion framework or broadened Model port. Reuse existing model/codec Target anchors; independently author the actual enum, seven fields and existing producer/helper API ports with their necessary existing-owner anchors (approximately 28 entries). Target intent is authored responsibility, not an observed JSON snapshot.

The five claims' existing raw RecordData algorithms are not globally migrated by this step. Source guards are honest actual class/decoder projections at these migrated boundaries; claim producer behavior is checked against real observations. Neither whole Model nor mixed codec/HTML modules are claimed string-free. Strict later carry onto Root's combined source must preserve canonical facts.ParameterKind, browser routing and the separate duplication correction.

## Preserve

All four supported Delta versions and current nullable-count policy; canonical Delta bytes; exact existing valid/error/field-order behavior at status ingress; valid legacy constructors; UNKNOWN versus empty SUPPORTED claims; original claim algorithms/candidates/review text; actual nominal status until wire serialization. Keep Measurement.MetricComparisonStatus, AssessmentStatus, binary Verdict, DeltaUnknown.evidence_class and unrelated structure levels distinct. SemanticChange.dimension/change, DimensionDelta.name and DeltaUnknown.dimension stay open strings. No schema extension, baseline/cap/allowance increase or resolver authority.

## RED and verification

1. Commit this plan before tests or production.
2. Add independently authored exact API Target, actual-source projections, nominal owner/field/producer controls, fixed-intent enum/field/parameter/return widening mutations and raw equality/membership/match/alias negative controls. No copied observation oracle.
3. Run native RED on unchanged production. Exercise both status values through all seven valid legacy DTO paths, all five UNKNOWN invariants, measured/zero/missing cases, original codec invalid input errors, all supported version roundtrips and open future wire changes.
4. After the bounded owner/cost review, migrate actual producers, invariants, consumers and decoder only.
5. Focused claim/decision/Delta/parity/runtime/profile/expectation/render tests; strict Mypy/Ruff/format/hygiene.
6. Normal amendment against this actual predecessor, committed NoWrite, unchanged budgets, complete selected UNKNOWN records and signed unresolved/PARTIAL call AST/target/reason/candidate-count multiplicity evidence.
7. Freeze a clean independent PR (Part of #542), obtain fresh independent Astra review, and stop before any next Core stage.
