# AD-98 A cycle rule names the level and the components it holds acyclic

## Decision

`no_component_cycles` adds optional level and component scope:

```json
{"kind": "no_component_cycles", "level": "module", "components": ["engine", "domains"]}
```

At `module` level, existing `module_scc` records become one `module_cycle` violation
per SCC, retaining members, module edges and every internal import's `path:line`
evidence. Every such import closes a cycle. Default level remains component.
Report the whole cycle when any member touches a listed component; overlap or
unowned members cannot be dropped. Unknown component labels invalidate the contract.

Omitted fields preserve records and canonical bytes; explicit component level
normalizes to absence. `package_scc.data.backed_by` identifies module SCCs spanning
at least two packages. Empty backing adds `roll-up only` to the title and increments
`rollup_only_package_cycles`. Package keys remain two dotted segments.

## Why

Issue #129 found an acyclic component graph alongside 23- and 28-module SCCs and
a package roll-up cycle. Component-only rules missed the module cycles; package
measurements did not distinguish real import cycles from aggregation artifacts.

## Baseline and `--against`

Fingerprints remain rule plus sorted members (AD-52, AD-77). A strict subset of a
resolved known SCC is `contracted`, writable without `--accept-new` and narrowing
under `--against`. Share `ir.baseline.is_contraction` with check delta. Supersets
and disjoint SCCs remain new.

Changing level either way, adding component scope or dropping a scoped component
widens; removing scope narrows. Neither cycle level implies the other:
`a1 -> b1`, `b2 -> a2` cycles components without cycling modules.

## Rejected

Reuse the rule and measured SCCs instead of another kind/computation. Validated
labels already describe prefix scope; cutting a cycle at the scope edge would
hide unowned members. Package re-keying would move all facts, paths and SCCs;
backing evidence answers the needed question without that change. Stored defaults
would break existing amendment digests. Only cycle subjects support contraction.

## Limit

`TYPE_CHECKING` imports count; no exclusion flag exists. Contraction requires a
current cycle rule. One module SCC can back a whole package SCC while another
package is present only through roll-up; backing identifies evidence, not full
package membership.

## Check

Cycle-level, widening and contract tests cover hidden cycles, evidence, scopes,
default bytes, roll-up/backing and contractions. Four cycle demos and
`against-cycle-rule-scoped` demonstrate them; self validation holds `MODULE-NO-CYCLES`.
