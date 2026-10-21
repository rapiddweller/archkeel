# AD-258 The report opens with ranked findings

**Decision.** By default the Atlas report opens with one verdict line and a ranked
list of findings. The list is computed once in the IR (`Finding`, built in
`ir/decisions.py` next to `review_claims`) and stored in the result JSON. The
terminal summary, the HTML and the JSON all read that one list, and the JavaScript
computes no findings of its own.

The verdict line shows the badge, the PASS and UNKNOWN counts, the agent-decision ratio
and the short git hash.

The list comes before the explorer. The rule cards, the reading guide and the
repeated counts are removed.

Order and sources. No new thresholds: each one already exists in the code or the
contract.

| Rank | Finding | Source | Threshold |
|---|---|---|---|
| 1 | Rule violation | violation records | the contract rule |
| 2 | Exceeded budget | `measure_python_ratchets` compared with baseline budgets | the contract's `measurement_budgets` |
| 3 | Dependency cycle (module before package) | `cycles` records | none: a cycle is a cycle |
| 4 | Hub (fan-in and fan-out) | module statistics | existing `>= 10`, top 3 per level, at most 10 in total |
| 5 | Type fan-in | `type_fanin` | existing `MINIMUM_CROSSINGS` |
| 6 | Repeated logic outside its owner | `repeated_logic` | existing `MINIMUM_SHAPE_NODES` |
| 7 | Unreferenced symbols, counted per module | `unreferenced_symbols` | none |

Within one kind, findings are sorted by size and then by name.

Oversized components are not findings: AD-235 forbids a replacement threshold. Typing
positions only become a finding through a declared budget.

**Change field.** A finding's identity is its kind together with the existing
canonical fingerprint (AD-52, AD-106). Changes use the existing baseline vocabulary
(`known`, `new`, `reduced`, `resolved`) plus a before and an after size:
- `report --baseline` fills it for violations and budgets.
- `validate --against` computes the list on both revisions and fills it for every kind.

Without a comparison the field is absent. It never reads "new" (AD-130). Nothing new is
stored.

**Reason.** ArchKeel already computes cycles, hubs, type fan-in, repeated logic and
unreferenced symbols. The default report showed none of them:
- On EE: 6 module cycles plus 1 package cycle, a fan-in of up to 205 and a fan-out of up
  to 75.
- The first screen spent about 475 px on verdict cards. One of them was static text, and
  the FAIL card showed 0.
- Findings were one click away, and the dependency balance two.

An architect should see at a glance what is going wrong and how it changed.

**Check.**
- Fixture tests with a cycle, a hub and growth compared with a baseline: the order,
  identities, sizes, locations and determinism are fixed.
- A finding is not counted twice when a cycle rule already reports the same strongly
  connected component (SCC) as a violation.
- Without a comparison, the change field is absent from the JSON.
- One run gives the same ordered identities in the terminal, the HTML and the JSON.
- A browser smoke test:
  - the number of list entries equals the JSON;
  - the first link selects the module;
  - there are no console errors.
- Result schema 11.0, with 10.0 left unchanged byte for byte.

**Slices.**
1. Violations, cycles and hubs, with the verdict line and the list (without the change
   field).
2. The change field via `--baseline` and `--against`.
3. Type fan-in, repeated logic and unreferenced symbols.
4. Inspector noise: 397 PASS rows, long module lists.
