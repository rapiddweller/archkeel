# AD-99 Facade and coupling budgets are contract ceilings

## Decision

`declarations.facade_budgets` and `coupling_budgets` set `max_names` with provenance
for facade exports and directed consumer/provider pairs. Validation uses AD-88's
`interface_profile`, publishing subject, count, ceiling, `over_target`, names,
uncounted forms and baseline additions/removals in `interface_budgets`.

| run | over `max_names` | name outside accepted set | accepted name gone | undecided |
| --- | --- | --- | --- | --- |
| no baseline | `budget.exceeded`, exit 2 | - | - | `budget.unknown`, exit 2 |
| baseline | known gap, `over_target` | rise, exit 1; needs `--accept-new` | fall, exit 1 until written | `budget.unknown`, exit 2 |

Schema 1.3 stores accepted `facade_names`/`coupling_names` beside scalars, reusing
AD-89 comparison/write/widening paths. Names catch swaps that counts would miss.
Raising/removing ceilings, growing accepted sets or first accepting names above
the old ceiling widens under `--against`.

Count `module:name` per promised path, even when two paths share a definition.
Enumerate module exports only with a proven single, non-empty, untouched literal
`__all__`. Empty lists remain open under interface semantics. Pair counting follows
re-export chains and `TYPE_CHECKING` imports. Bare module imports, unenumerated stars
and names absent from unenumerated facades remain uncounted.

Unknown components, absent facade public lists, self-pairs, duplicate keys,
inside budgets and pair budgets without a type-checking-inclusive interface rule
are invalid. Dart budgets are unsupported, exit 2 (AD-97).

## Why

Issue #130 needed policy over measured surfaces. Requiring interface boundaries
makes facade bypasses violations rather than silently uncounted imports.

## Rejected

Ceilings alone permit replacement growth and cannot gate existing excess.
Counts cannot identify excess names as violations. Analyzer rules would need a
second profile derivation.

## Limit

Absent lists preserve old amendment bytes. Targets below current usage need a
baseline. Dynamic `__all__` mutation remains invisible.

## Check

Facade-budget and interface tests cover limits, ratchets, uncertainty, contract
errors, widening, chains and literal facts. Budget demos cover facade/coupling
cases; `make self-validate` holds six self pairs. Self facades lacked `__all__`,
so no facade budget was declared.
