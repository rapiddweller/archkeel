# AD-74 A name bound twice is unresolvable, not a coin flip

## What changes

`boundary_type_indexes` built its two lookups with last-write-wins over lists sorted by
content-hash id. Python binds the textually last definition or import; the index kept whichever
record the hash order left last. An ambiguous key now resolves to a sentinel, and the position
is reported `ambiguous_binding` -- a new undecidable kind.

| Module | Live binding | Before | Now |
|---|---|---|---|
| two top-level `class Order` | the second | **`KeyError`, whole scan lost** | undecidable |
| `import Thing` from a, then from b | b's | b, or a, by hash | undecidable |

## Why

Two defects, one cause. The crash: `_resolve_class_kinds` keys its fixpoint by qualified name,
so of two same-named classes only one record ever gets a `class_kind`; when the index kept the
other, `origin_symbol["class_kind"]` raised and `observe` returned exit 2 with no observation at
all. The silent one is worse: with the declared and the undeclared candidate both in scope, the
index could keep the declared one while the live binding was undeclared, and the position passed
clean -- a wrong PASS, the verdict this tool exists not to give.

Picking the right record is not available: `symbols` and `imports` carry no source order the
index can read, and reconstructing it would make two lookups depend on a third derivation. What
is available is the knowledge that the name is bound twice, and [AD-26](ad-26-a-quality-claim-is-a-signal-a-derivation-and-a-claim-and.md)
already says what to do with that. An undecidable position is reported, counted in the
denominator, and moves `declared_rules` to UNKNOWN ([AD-72](ad-72-a-rule-that-could-not-decide-everything-reports-unknown.md))
without gating.

Its own kind, not `unresolved_name`: a reader must be able to tell "I could not read this
annotation" from "this name means two things here", because the second is a defect in the code
under test and the first is a limit of the checker.

## Rejected

| Alternative | Why not |
|---|---|
| Guard the subscript with `.get` | Fixes the crash and keeps the coin flip, which is the worse half. |
| Leave the ambiguous key out of the index | Then "bound twice" reads as "never defined", and the breakdown cannot tell them apart. |
| Reconstruct source order in the index | A third derivation of what the scan already knows, to answer a question the honest answer is UNKNOWN to. |
| Report the ambiguity as a violation | Two definitions of one name is legal Python. The rule was asked about a boundary type, and about that it cannot decide. |

## Limit

Ambiguity is per module and per name. A conditional definition under `if` is not seen at all
(the collector does not descend into it), so it is not ambiguous here and never was. A name
shadowed across modules is unaffected: only same-module collisions collapse.
`ANALYZER_VERSION` rises to 0.32.0, because a `boundary_type_limit` breakdown can now carry a
kind no earlier analyzer emitted.

## Check

`tests/test_boundary_type_ambiguous_bindings.py` pins both directions through `observe`, the
missing `class_kind` that made the crash possible, and -- the guard against the cause returning
-- that reversing the record order leaves the index entry identical.
