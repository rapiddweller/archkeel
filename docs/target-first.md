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

```bash
archkeel validate --baseline known-violations.json --write-baseline
archkeel validate --baseline known-violations.json
```

Review and commit the initial baseline. Exact debt counts can exit 0 while
`declared_rules` remains FAIL. New/increased and resolved debt exit 1; other
diagnostics exit 2. Fix code and rewrite resolved-only debt in the same change.
Contracted cycles can also shrink without `--accept-new`; new debt requires that
explicit approval. Baselines never hide diagnostics or complete UNKNOWN evidence.

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
