# Delta version controls — issue #542

Base af9f0f708142bf0529992f4f7147c7d37e3b1a99; Measurement PR #578 is independently Astra-approved and remains frozen. Remote GitHub/Actions only. This plan precedes all Delta production edits. The coordinating agent requested an inventory and native RED first; production is held for the bounded owner/line review.

## Inventory and split

The existing model.ComparisonStatus alias is shared by Delta and five separate claim owners: BindingReads, SymbolReferences, TypeFanin, InsideSizes and OwnedLogic. Their constructors/invariants plus decisions._named are actual consumers. A Delta-only replacement would duplicate the shared type or leave canonical producers raw. Shared ComparisonStatus therefore needs a later independent migration across those existing owners.

This first stage changes only the four supported Delta schema versions and their actual ports. Current codec accepts1.2.0,1.3.0,1.4.0,2.0.0. Nullable call/dimension counts arrived in1.4; runtime requirement-state support arrived in2.0. Supported future dimension/change text is intentionally open at the public wire.

## Owned API and cost

- Keep the existing IR model owner; add DeltaVersion(StrEnum) with V1_2,V1_3,V1_4,V2_0. Type ArchitectureDelta.schema_version and normalize valid legacy constructor strings there. No new module or per-enum component.
- Keep DELTA_SCHEMA_VERSION as the existing published wire grammar label, matching the ContractVersion precedent. Actual producers and decisions use DeltaVersion members, never this raw constant as a dispatch alias.
- Add one direct bool port supports_nullable_delta_counts(version:DeltaVersion)->bool at that owner. The {V1_4,V2_0} policy is shared by codec count/call gates and expectation validation. No Enum method, feature DSL, rank table or converter framework.
- Convert the version once at codec_delta ingress with a small private _parse_delta_version returning DeltaVersion, preserving the existing nonstring/unsupported-version error messages and order. Serializer uses the typed DTO field. Its runtime-requirement gate remains exactly V2_0.
- Actual version producer in check.delta and version gate in check.expectation use the canonical owner. Existing public model/check constants and all non-version interfaces remain compatible.
- Four existing production files, estimated45–65 net lines. Exact type/helper API ports plus approximately5–7 independent Target entries, no broad model-port grant.

## Preserve boundaries

Do not change ComparisonStatus, binary Verdict, Measurement types, expectation-schema version, Observation schema/runtime identities, check.delta engine dimension/change vocabulary, existing profile capabilities, or JSON field grammar. Public SemanticChange.dimension/change, DimensionDelta.name and DeltaUnknown.dimension remain ordinary strings and must roundtrip arbitrary future values. Any HRC assertion must name this actual version-only scope, not claim the entire Model or mixed Delta codec is free of raw control strings.

## TDD and verification

1. Commit this plan before tests/production.
2. Author real API Target entries independently, source-backed Enum/field/helper checks, type-widening/enum-kind/return mutations at fixed intent, and raw-dispatch controls at the migrated parser/version owner boundary.
3. Hosted native RED on unchanged af9 production. Verify every supported version's exact roundtrip, valid legacy dataclass replacement, invalid versions/error behavior, open future wire strings, and all version-feature combinations. Retain the existing test_delta_parity hashes unchanged.
4. After the coordinating owner/line review, implement only the approved version boundaries.
5. Focused Delta/parity/runtime/profile/expectation tests, strict Ruff/Mypy/Hygiene; actual normal amendment plus committed NoWrite against this real predecessor.
6. Compare precise UNKNOWN records/data and signed unresolved/PARTIAL call AST/targets/reasons/multiplicity. No baseline/cap/allowance rise or new resolver authority. Freeze for fresh independent Astra review; no next-stage source changes.

Read-only inventory: model.py currently has ArchitectureDelta.schema_version:str; codec_delta.py validates supported text in parse_delta and repeats nullable/version gates in payload/dimension/ratchet branches; check.delta only produces the current version; check.expectation gates nullable UNKNOWN dimensions. ComparisonStatus remains a shared two-value claim-support contract and is deliberately separate.
