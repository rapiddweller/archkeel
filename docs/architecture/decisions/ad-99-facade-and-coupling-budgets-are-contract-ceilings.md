# AD-99 Facade and coupling budgets are contract ceilings

## Decision

`declarations.facade_budgets` caps the names one component's declared facade exports.
`declarations.coupling_budgets` caps the facade names one component imports from another. Each
entry states `max_names` and its provenance. `validate` measures both with AD-88's
`interface_profile`, the same derivation the report shows:

| entry | counts | undecided when |
| --- | --- | --- |
| `{component, max_names}` | distinct `module:name` the component's `public` modules export | a whole-module entry has no literal `__all__`, or was not scanned |
| `{source, target, max_names}` | distinct target facade names `source` imports, through the re-export chain `interface_boundary` follows | `source` imports a target module whole, stars a module that is no enumerated facade, or names what a non-enumerated facade does not list |

A count over `max_names` is `budget.exceeded`. The diagnostic names the facade or pair, the
count, the excess and every counted name: a budget counts names, not which of them are too many.
An undecided count is `budget.unknown`, unless its lower bound already exceeds. Both exit 2, with
or without `--baseline`; a baseline cannot hold them. A key that names no component, a facade
budget on a component without `public`, a pair whose target has none or that names one
component twice, and a repeated key are `contract.invalid`. An inside contract may not declare
either list, because the level above measures only its own components.

Under `--against`, raising `max_names` or removing an entry widens; lowering or adding narrows.

## Why

AD-88 measured facade width and coupling but gave the contract no way to hold them, so a branch
could reach zero declared violations with an oversized surface (#130). Reusing the measurement
keeps the report and the verdict on one count. Following the re-export chain makes a pair count
what `interface_boundary` accepts: `from shop.store import OrderRepository` uses
`shop.store.repository:OrderRepository`, which AD-88 had dropped.

## Rejected

- **Baseline-pinned keyed values, the way AD-89 pins scalars.** The contract value already is
  the accepted value, and `--against` already treats raising it as a widening. A second number
  per key in the baseline could disagree with it, and would need a baseline schema change.
- **Excess names as baseline violations.** Which names are excess is not decidable from a
  count, so such a fingerprint has no stable subjects.
- **A rule kind in the analyzer.** The analyzer works on raw records and would need a second
  facade derivation.

## Limit

`max_names` is a ceiling. A count below it leaves headroom a later change may use without a
contract diff. A strict ratchet keeps `max_names` at the measured count and lowers it as names
go; each lowering is a narrowing. A target below today's count fails until the code reaches it.

Archkeel's own facades are whole modules without `__all__`, so it pins coupling budgets only:
the pairs its contract already keeps narrow, `api -> ir`, `host -> ir` and `cli`'s four edges.
The width from `analyzer`, `check` and `render` into `ir`'s shared vocabulary grows with each
rule kind; a ceiling there would be bookkeeping, not a decision.

## Check

`tests/test_facade_budgets.py` covers pass, exceeded names, the re-export count, UNKNOWN, the
baseline, contract errors, widening and the inside contract; `tests/test_interfaces.py` the
chain and uncounted imports. The demo rows `validation-facade-budget-*`,
`validation-coupling-budget-*` and `against-facade-budget-raised` run the shop sample, and
`make self-validate` holds Archkeel's own pair budgets.
