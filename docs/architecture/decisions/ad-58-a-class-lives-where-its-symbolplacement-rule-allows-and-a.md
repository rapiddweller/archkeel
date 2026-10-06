# AD-58 A class lives where its symbol_placement rule allows, and a facade's dict or object is all boundary_types decides

`symbol_placement` restricts classes under `source` to allowed module prefixes or
exact modules (AD-49). `class_kinds` selects `protocol`, `enum`, `pydantic_model`,
`dataclass` or `class` from the existing base-resolution fixpoint.
The self-contract's `TYPES-ENUM-IN-MODEL` kept five `StrEnum` classes in `ir.model`.

Originally `boundary_types` inspected non-underscore module-level functions under
`source`, reporting each parameter or return annotated as `dict`, `Dict`, `object`
or a dict generic. It did not inspect methods or duplicate `any_annotation` findings.

Issue #9 proposed provider-owned declared facade models. Of 189 self annotation
positions, strings/local names resolved 123 (65%); imported names raised this to
136 (72%). Restricting types to the consumer's own facade was wrong:
`analyzer.observe` returns `ir`'s `ObservationResult`, and shop rendering returns
`model`'s `Order`. Both are intended provider-owned contracts.

Cross-component ownership resolution and the remaining 28% uncertainty were beyond
this cut. Component-wide checks would also reject legitimate codec `object` and
`dict[str, RawJson]` boundaries, measured at 25 positions. Keep explicit rule scope.

Original limits: named/dotted types, forward references, other generics, `Any` and
missing annotations stayed silent. AD-63 later resolves bare named types and selects
functions through component public lists; its remaining limits are separate.
`symbol_placement` inherits unresolved-base alias blind spots. Analyzer version
rose to 0.25.0 for new violations (AD-3).

Checks: analyzer placement and dict/named-type probes, contract corpus/round trips,
`class-a-symbol-placement` and `class-a-boundary-types` demos, and clean self
validation with the enum-placement rule.
