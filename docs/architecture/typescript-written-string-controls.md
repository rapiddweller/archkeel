# Native written-string controls in TypeScript and JavaScript

Part of #542. The first capability is deliberately partial and does not activate a browser-wide guard.

Existing owners:
- typescript/parse.py is the only Tree-sitter owner, with the TS558 per-parse Node view.
- typescript/syntax.py owns immutable lexical DTOs; the existing literal Span and named scope inventory are reused.
- typescript/collect.py owns source fact IDs, evidence and the canonical ForbiddenConstructKind producer.
- ir.facts owns SourceSectionName, ConstructCapability, ConstructSupport and construct identity. ir.profiles owns atomic optional-section groups; the observation codec validates each group without TypeScript-specific policy.
- config.py already selects .js/.jsx/.mjs/.cjs through allowJs or checkJs unless allowJs explicitly disables them. The pinned TypeScript compiler is a reference check, not architecture or runtime authority.

Phase 1:
- Read the actual equality operators ==, ===, != and !== and switch case values through their owned AST kinds.
- Recognize written string literals including escapes, and plain templates only when no interpolation is present; support simple parenthesized literal operands.
- Publish a small syntax.StringComparison carrying the literal Span and optional existing named scope. No extra public form enum.
- Collect canonical string_literal_compare facts, with source-bound evidence and stable identities for nested comparisons.
- Advertise only ConstructSupport.PARTIAL. Known facts may cause trace-valid FAIL; absence remains UNKNOWN.
- Existing unknown parent nodes must remain traversable. Parse repairs, unknown comparison kinds and missing selected JavaScript cannot prove absence.
- No constant/import/alias/mutation/closure value propagation, type checker semantics, compiler authority or runtime inference.
- No browser guard is enabled in this change.

Later forms, explicitly outside Phase 1:
- Fresh literal string arrays/tuples and appropriate .includes forms, with receiver and mutation/escape limits stated.
- Direct string matching through startsWith/endsWith only where the receiver and written operands can be classified without assuming imported or mutable aliases.
- JavaScript `in` tests property presence rather than array membership; do not equate every property-key check with a string-value comparison.
- Constant/import/closure propagation requires a separate conservative scope and mutation design.
- Deep JSDoc type/member Target claims remain unsupported by this lexical capability. checkJs inclusion does not establish type-checker evidence.

Verification sequence:
1. Commit real TS/JS Native-RED tests against the unchanged collector and fixed independent contract.
2. Run them in hosted Actions and confirm missing construct evidence causes expected assertion failures, not setup/import errors.
3. Wait for the final green TS558 legacy-DTO ref before product integration.
4. Add the smallest parser/DTO/collector/profile implementation and named target intent without copying parser domains.
5. Prove strict wire replay, trace-valid FAIL, typed/data negatives, dynamic-template and unknown/parse-error boundaries.
6. Run existing TypeScript suites, pinned compiler checks, repository/native gates and the project suite. Record any failures without hiding them.
7. Return a clean capability PR for independent final Astra review. Browser migration and a real browser-asset HRC CI run remain separate work.

RED evidence before product changes:
- Hosted run 38954690071: 24 expected missing-evidence/capability assertion failures; 16 conservative controls passed. Actual pinned AST fields were recorded from TS source.
- Hosted run 38955421952: the same 24 missing-feature failures plus the independent construct-receipt rejection; 44 controls passed, including legacy UML-array replay with constructs=null.
- The receipt compatibility change preserves the existing optional_sections read API as a derived property. Existing symbols/calls/references/bindings remain one atomic group; constructs is independent.
- Literal templates require known fragment/escape children. A removed/unknown interpolation kind cannot promote a dynamic template to a static literal.
