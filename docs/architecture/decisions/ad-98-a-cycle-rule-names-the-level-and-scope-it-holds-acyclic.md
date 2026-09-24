# AD-98 A cycle rule names the level and the components it holds acyclic

## Decision

`no_component_cycles` gains two optional fields:

```json
{"kind": "no_component_cycles", "level": "module", "components": ["engine", "domains"]}
```

- `level` is `component` (default) or `module`. At `module`, each `module_scc` record the report
  already measures becomes one `module_cycle` violation: `subjects` and `data.members` are the SCC,
  `data.edges` its module edges, and the facts are every import between two members, each with
  its `path:line` evidence. Inside an SCC every such import closes a cycle.
- `components` lists declared labels. A cycle is reported when one member belongs to a listed
  component, and it is reported whole. An undeclared label is `contract.invalid`.
- Without either field the rule, its records and the canonical contract bytes are unchanged, so
  AD-61 amendment digests of existing contracts still verify. An explicit `"component"` parses to
  the same absent value.
- A `package_scc` record names in `data.backed_by` the module SCCs whose members span two or more
  of its packages. Empty means no import cycle closes it: the title adds `roll-up only`, and the
  `rollup_only_package_cycles` metric counts it. Package facts stay keyed by two dotted segments.

## Why

Issue #129: on a real repository the declared component graph was acyclic while the report
measured module SCCs of 23 and 28 modules and a package SCC between two packages whose nested
components form no cycle. A component-only target passed and said nothing about the modules,
and the package SCC could not be told from a real cycle.

## Baseline and `--against`

The violation's fingerprint is its rule and sorted members, so the baseline holds known SCCs and
fails on a new one (AD-52, AD-77). A cycle whose members are a strict subset of a baselined cycle
that fell is that cycle contracting: validate reports it as `contracted`, to be written back
without `--accept-new`, and `--against` reads the replacement as a narrowing. The subset test is
the one the `check` delta already used, now `ir.baseline.is_contraction` for both. A superset or
disjoint SCC stays new. In the contract, a `level` change in either direction, a new `components`
scope and a dropped component are widenings: neither level implies the other (`a1 -> b1`,
`b2 -> a2` is a component cycle without a module cycle). Removing the scope narrows.

## Rejected

| Alternative | Why not |
|---|---|
| A new `no_module_cycles` rule kind | Two kinds would share the graph, scope and widening logic. |
| A second SCC computation in the rule | The rule would judge a graph the report does not show. |
| Scope as source prefixes | Labels are validated contract references, and a component is already a set of prefixes. |
| Scope cutting a cycle at its edge | A cycle through an unowned module would disappear from a scoped rule. |
| `level: "package"`, or package facts re-keyed along declared components | Re-keying moves every package fact, path and SCC in every observation; `backed_by` tells an artifact from a cycle without that, and the `component` level already rolls up along declared boundaries. |
| `level` defaulting to a stored `"component"` | Every existing contract's canonical bytes and amendment digest would move. |
| Contraction for any rule's subject subset | Only a cycle rule's subjects are one SCC; elsewhere a subset is a different violation. |

## Limit

`TYPE_CHECKING` imports close module cycles as they close component cycles; there is no
`include_type_checking` flag yet. A contraction is recognised only under a rule the current
contract declares as `no_component_cycles`.

## Check

`tests/test_cycle_levels.py` (hidden module cycle, members, edges and evidence, scopes, the
unchanged default, parser, roll-up-only and backed package SCCs, contraction, baseline and
`--against`), `tests/test_widening.py`, `tests/test_contract_model.py`, the AD-11 rows
`class-a-no-component-cycles-module-hidden`, `class-a-no-component-cycles-module`,
`class-a-package-cycle-rollup-only`, `class-a-package-cycle-backed` and
`against-cycle-rule-scoped`, and Archkeel's own `MODULE-NO-CYCLES` under `make self-validate`.
