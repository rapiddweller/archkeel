# Symbol-specific requires ports

Part of #564. Approved scope: preserve legacy module-prefix permissions, evaluate named module:symbol ports using the actual imported symbol, and retain UNKNOWN when the collector cannot identify names. No widening to a whole model facade. Reuse canonical AssessmentStatus for evaluator outcomes instead of translating through raw status literals.

1. Add native source/contract RED controls for the approved symbol, sibling and other module, legacy module/empty through, known and unknown wildcard, aliases and nested contracts. Keep the contract fixed for source mutations.
2. Extend the existing owned requires matcher with an optional actual symbol. Keep old callers and query semantics. Thread real import facts through complete_requires and the common UNKNOWN record path; use one decision owner for violations and incompleteness.
3. Run the focused suite, existing dependency/scoped-proof/nested/profile regressions, strict typing, Ruff and hygiene. Compare exact UNKNOWN identities and unresolved/partial call ASTs, targets and multiplicities. Preserve native budget bounds; any inherited downward ratchet uses the normal writer.
4. Produce the normal receipt and a clean separate ref with no auxiliary workflow. Freeze for independent Astra review before integrating the Command successor.
