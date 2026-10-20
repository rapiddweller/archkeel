# Canonical Protocol declarations

## Decision

A `protocol_declarations` rule selects parameter and annotated class-member declaration roles over the complete observed modules of a component. Its closed selectors name the declaration role, an exact parameter or member name, and public visibility. The union of selector matches is evaluated; duplicate matches collapse to one selected declaration position. A selector may require one canonical Protocol identity.

The required identity is a canonical dotted source symbol resolved through the existing `boundary_types` binding and signature evidence, including proven imports, reexports, quoted forward references, and statically proven single-name `TypeAlias` chains. Annotation text alone cannot establish identity. Unsupported alias shapes, such as a union-valued alias, remain UNKNOWN. A simple requirement accepts exactly that Protocol. An explicitly optional requirement also accepts exactly that Protocol together with `None`, including `Optional[Protocol]`. Other union arms, including a concrete implementation type, fail. Missing annotations, `object`, and `Any` fail. Shadowed, ambiguous, or unresolved names are UNKNOWN.

Class-local shadowing recorded for a selected annotation makes that position UNKNOWN, including method parameters whose annotations are affected by their enclosing class scope. For an annotated class-member position, any class-body control flow recorded by the collector makes the position UNKNOWN. This evidence is class-wide, so a conditional statement unrelated to the selected member can still prevent a proof. A missing annotation remains a known FAIL, and UNKNOWN positions do not erase known FAIL findings at other selected positions.

A selector with no matches, an absent governed source scope, or incomplete mounted source evidence is UNKNOWN, never PASS. This rule evaluates declarations and does not inspect function bodies or prove that an implementation structurally satisfies a Protocol. MyPy owns assignability; structural conformance remains with #356.

## Consequences

Future declarations in the governed scope are included without updating a function inventory. Closed selectors avoid an embedded pattern language. Existing binding and type-shape evidence remains the authority for import and supported alias identity.

## Rejected alternatives

- Annotation substring matching: spelling can be shadowed or refer to a different declaration.
- A frozen list of current functions: future declarations would escape the policy.
- Structural conformance in this rule: it duplicates #356 and MyPy's responsibility.
