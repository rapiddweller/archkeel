# AD-99 Facade and coupling budgets are contract ceilings

## Decision

`declarations.facade_budgets` sets a target for the names one component's facade exports;
`declarations.coupling_budgets` for the facade names one component imports from another. Each
entry states `max_names` and provenance. `validate` measures both with AD-88's
`interface_profile`, the derivation the report shows, and returns every budget as a structured
`interface_budgets` entry: subject, count, `max_names`, `over_target`, names, uncounted, and new
and removed names against the baseline.

| run | over `max_names` | name outside the accepted set | accepted name gone | undecided |
| --- | --- | --- | --- | --- |
| no `--baseline` | `budget.exceeded`, exit 2 | - | - | `budget.unknown`, exit 2 |
| `--baseline` | known gap, `over_target` | rise, exit 1, needs `--accept-new` | fall, exit 1 until written | `budget.unknown`, exit 2 |

The baseline ratchet is AD-89's: baseline schema 1.3 keeps each key's accepted names under
`facade_names` or `coupling_names` beside the scalars, and the same comparison, write and
widening paths read them. Names, not counts, so a swap is a rise. Under `--against`, raising or
removing `max_names`, growing an accepted name set, and a first accepted set above the old
contract's `max_names` for a key the old baseline did not hold widen.

A facade counts `module:name` per declared module, so a definition reachable through two modules
counts twice: each path is a name the facade promises. A module entry is enumerated only when
the analyzer's `all_literal` fact proves its `__all__` one non-empty literal assignment that no
other statement or import touches. `interface_boundary` reads `__all__ = []` as no `__all__`, so
an empty one is open too. A pair follows the re-export chain `interface_boundary` follows and
counts `TYPE_CHECKING` imports. A whole-module import of a facade, a star of a non-enumerated
one, and a name a non-enumerated one does not list are uncounted.

A key naming no component, a facade budget on a component without `public`, a pair naming one
component twice, a repeated key, and a pair budget without an `interface_boundary` rule that
includes `TYPE_CHECKING` imports are `contract.invalid`; so is a budget in an inside contract.
The Dart profile has no `__all__` and names no imported symbol it cannot see (AD-97), so either
list is `rule_unsupported_by_profile` there, exit 2.

## Why

AD-88 measured facades and coupling but the contract could not hold them, so a branch could reach
zero declared violations with an oversized surface (#130). A pair counts only names reached
through the facade; the required `interface_boundary` rule makes every import past it a finding,
so no bypass is silently uncounted. Requiring the rule was chosen over counting bypasses as
uncounted, which would turn every internal import into UNKNOWN instead of a named violation.

## Rejected

- **Only the contract value.** A fall leaves room a later name reuses unseen, and a target below
  today's count could not gate CI at all.
- **Excess names as baseline violations.** Which names are excess is not decidable from a count.
- **A rule kind in the analyzer.** It works on raw records and would need a second derivation.

## Limit

An absent list stays absent in the canonical contract bytes, so existing amendment digests do not
move. A target below today's count passes only with a baseline. The literal fact is static:
`globals()["__all__"] = ...` or `sys.modules[__name__].__all__.append(...)` changes `__all__`
unseen, as every dynamic binding escapes the scan.

## Check

`tests/test_facade_budgets.py` covers targets, the ratchet, UNKNOWN forms, contract errors and
widening; `tests/test_interfaces.py` the chain, the literal fact and facade-less targets. The
`validation-facade-budget-*`, `validation-coupling-budget-*` and `against-facade-budget-raised`
demo rows run the shop sample; `make self-validate` holds Archkeel's six narrow pairs. Its
facades have no `__all__`, so it declares no facade budget.
