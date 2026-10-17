# Typed current Delta dimensions and evidence ingress

Part of #542. Base: 5b8a603274b2330b85fc6fe62c8d7f6fb15da8f1. Approved bounded design, inline execution and final independent union Astra review.

## Ownership and compatibility

Profiles already owns dimension applicability. The existing model imports measurements, which imports profiles, so importing model from profiles would create a cycle. Define the current eight-value DeltaDimension in profiles and explicitly reexport the identical class through model. Keep public SemanticChange.dimension, DimensionDelta.name, DeltaCoverage lists and future wire dimensions open strings. Keep SUPPORTED_DIMENSIONS and GUARDRAIL_DIMENSIONS public wire views plain strings; current producers and fixed governance decisions consume the one enum. JSON keys, profile capabilities and source-section vocabularies remain distinct.

Use existing Facts.EvidenceClass for the two actual fixed evidence decisions. Preserve existing decoder messages/order, supported versions, canonical wire bytes and fingerprints. This slice does not claim model/codec-wide absence of string controls, does not close global Record.kind, and does not alter unrelated status/version/receipt work.

## TDD and verification plan

1. Commit this plan and independently authored narrow API intent/tests before production. Demonstrate genuine RED for the missing canonical domain/API and producer/consumer normalization, with legacy/future wire controls.
2. Change only profiles/model/check.delta/check.expectation/codec_delta and necessary independently authored Target/public ports. No new module, decoder framework or alias-based string dispatch. Guard complete genuinely migrated functions only; JSON-key and unrelated producer-tag decisions are not hidden by blanket claims.
3. Prove actual fixed Target rejection of enum relocation, input/return widening, source field narrowing and raw enum-owner/consumer decisions. Preserve actual future public wire input while fixed governance rejects unsupported dimensions. Pin EvidenceClass valid/invalid values and error priority.
4. Run affected Delta/expectation/profile/codec regressions, strict typing, Ruff/format and hygiene. Use same current observer for exact before/after UNRESOLVED/PARTIAL AST/status/reason/targets/candidate-count multiplicities and unchanged full selected UNKNOWN records. No aggregate netting hides new sites.
5. Generate the normal baseline/amendment against the exact base without raised budgets; verify committed canonical receipt and no-write result. Freeze clean intended files for Root's bounded union, final Astra review and combined full gates. No new PR/issue or Main writes.
