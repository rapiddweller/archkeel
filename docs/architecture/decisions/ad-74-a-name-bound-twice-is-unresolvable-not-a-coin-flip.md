# AD-74 A name bound twice is unresolvable, not a coin flip

## What changes

`boundary_type_indexes` marks distinct same-name bindings ambiguous, including
collisions across import and symbol indexes. Repeated identical import targets
remain one binding. Previously content-hash ordering picked an arbitrary winner.

| Module | Live binding | Before | Now |
|---|---|---|---|
| two top-level `class Order` | the second | **`KeyError`, whole scan lost** | undecidable |
| `import Thing` from a, then from b | b's | b, or a, by hash | undecidable |
| imported `Thing`, then local `class Thing` | the class | imported type, clean pass | undecidable |
| `class Order`, then `def Order` | the function | **`KeyError`, whole scan lost** | undecidable |
| the same import repeated in another scope | the same target | undecidable | one binding |

## Why

The class-kind fixpoint populated only one same-name record; choosing another
raised `KeyError`. Choosing a declared target over an undeclared live binding
could also give false PASS. Records lack source order to select the runtime winner.
Report a distinct ambiguity limit, count the position and produce UNKNOWN
([AD-26](ad-26-a-quality-claim-is-a-signal-a-derivation-and-a-claim-and.md),
[AD-72](ad-72-a-rule-that-could-not-decide-everything-reports-unknown.md)).

## Rejected

`.get` hides only the crash. Removing the key loses ambiguity evidence.
Reconstructing order adds another derivation. Legal duplicate Python bindings
are not themselves boundary-type violations.

## Limit

Ambiguity is per module/name. Conditional definitions remain unseen. Imports have
no lexical scope, so distinct targets across scopes conservatively collide;
identical targets collapse. Analyzer version rises to 0.32.0 for the new limit kind.

## Check

`tests/test_boundary_type_ambiguous_bindings.py` covers collisions through observation,
missing class kinds, repeated imports and invariance under reversed record order.
