# The target-first loop

Start with a decided contract from [onboarding](onboarding.md). Keep intent while
refactoring code toward it; do not allow existing imports merely to get green.

## Review one slice

```bash
archkeel report --only violations --json
archkeel report --only violations --component storage --json
```

Replace `storage` with a declared component. Filters retain global verdicts and
counts. Unknown selectors exit 2. Read confirmed violations and UNKNOWNs together.

## Baseline debt and gate changes

For a `requires` + `complete_requires` contract, list each permitted direction in `requires`.
A new crossing on an absent direction is a measured `complete_requires` violation that
`--accept-new` can record as debt. It appears in the observed graph while Target keeps the
declared permissions. A whole-pair `forbidden_dependency` instead produces
`closed_world.observed_forbidden` and cannot be baselined. Regenerate marked graphs and compare
the debt baseline in one run:

```bash
archkeel validate --baseline known-violations.json --write-graph --write-baseline
archkeel validate --baseline known-violations.json
```

Review both writes. If the measured baseline has new or increased debt that the owner accepts,
rerun with `--accept-new`; otherwise fix it first. For example:

```bash
archkeel validate --baseline known-violations.json --write-graph --write-baseline --accept-new
```

`--accept-new` accepts measured debt only.
The Shop whole-pair `render -> store` case in the
[forbidden-pair fixture](../fixtures/demo_catalog_dependencies.py) still emits
`closed_world.observed_forbidden` and exits 2, even with `--write-graph`, `--write-baseline` or
`--accept-new`; no baseline is written. A narrower case such as
`forbidden_dependency:target_symbol` remains baseline-capable because it does not forbid the
whole component pair.

Graph refresh does not amend policy. `validate --against "$BASE"` still rejects an unamended
permission widening. Exact debt counts can exit 0 while `declared_rules` remains FAIL; new or
increased and resolved debt exit 1; other diagnostics exit 2. Baselines never hide diagnostics
or complete UNKNOWN evidence.

Set `BASE` to the branch's reviewed base commit, then protect policy too:

```bash
archkeel validate --baseline known-violations.json --against "$BASE"
```

New permissions, removed restrictions and unclassified changes fail closed.
New or moved contracts are introductions requiring approval, not skipped checks.
For an approved widening, write and review an amendment with `--amendment`,
`--write-amendment`, `--decided-by` and `--rationale`; subsequent gates use that
file without the write flag. It binds the exact before/after policy, including
compared baseline contents, rather than approving future changes.

Put validation and existing project checks in one Make gate. Gate each configured
scope separately; a product scan does not cover neighboring tests. Separate report
outputs prevent scopes overwriting each other. Baseline/amendment paths resolve
under `--root` and must remain inside it.

## Land target work

Keep future interfaces in `planned`. Once an import or declared facade signature
reaches one, move the same entry to `public`. Built but unreached work remains
planned. Review remaining UNKNOWNs and unmeasured intent even with an empty baseline.

`validate --write-graph` refreshes eligible marked observed/target graphs;
unsupported Mermaid syntax requires manual edits. See [reference](reference.md)
for commands, [rules](rules.md) for layout, compatibility and budget policy, and
[limits](known-limits.md) before claiming conformance.
