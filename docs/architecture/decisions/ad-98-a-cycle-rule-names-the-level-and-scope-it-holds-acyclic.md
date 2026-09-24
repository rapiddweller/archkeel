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

## Why

Issue #129: on a real repository the declared component graph was acyclic while the report
measured module SCCs of 23 and 28 modules. A component-only target passed and said nothing
about them. The measurement existed; the contract had no way to state that it matters.

## Baseline and `--against`

The violation's fingerprint is its rule and sorted members, so the existing baseline holds known
SCCs, fails on a new one and makes a resolved one leave the file (AD-52, AD-77). Under
`--against`, a baseline entry added is a widening and one removed passes (AD-61), so the number
of known SCCs may only fall. In the contract, a `level` change in either direction, a new
`components` scope and a dropped component are widenings: neither level implies the other
(`a1 -> b1`, `b2 -> a2` is a component cycle without a module cycle). Removing the scope or
listing another component narrows.

## Rejected

| Alternative | Why not |
|---|---|
| A new `no_module_cycles` rule kind | Two kinds would share the graph, scope and widening logic. |
| A second SCC computation in the rule | The rule would judge a graph the report does not show. |
| Scope as source prefixes | Labels are validated contract references, and a component is already a set of prefixes. |
| Scope cutting a cycle at its edge | A cycle through an unowned module would disappear from a scoped rule. |
| `level: "package"` and a hierarchy-aware package roll-up | `package_*` records collapse at the first two dotted segments. Splitting them along declared components changes every package fact, path and SCC in every observation. The `component` level already is the roll-up along declared boundaries. |
| `level` defaulting to a stored `"component"` | Every existing contract's canonical bytes and amendment digest would move. |

## Limit

`TYPE_CHECKING` imports close module cycles as they close component cycles; there is no
`include_type_checking` flag yet. A baseline matches an SCC exactly: breaking part of a known SCC
leaves a smaller one with a new fingerprint, which `--write-baseline` accepts only with
`--accept-new` and `--against` reads as an added entry. The `check` delta already treats a
strict subset as a contraction (`check/expectation.py`); the baseline does not yet.

## Check

`tests/test_cycle_levels.py` (hidden module cycle, members, edges and evidence, scopes at both
levels, the unchanged default, parser, baseline and `--against`), `tests/test_widening.py`,
`tests/test_contract_model.py` (corpus), the AD-11 rows
`class-a-no-component-cycles-module-hidden`, `class-a-no-component-cycles-module` and
`against-cycle-rule-scoped`, and Archkeel's own `MODULE-NO-CYCLES` under `make self-validate`.
