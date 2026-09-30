# AD-126 Target ranking retains four unresolved stdlib calls

Use `graphlib.TopologicalSorter` rather than implement another dependency sorter.
The analyzer cannot prove its method receivers. Under Alex's delegated decision
authority, Astra approved retaining these four calls, not treating them as resolved.

Compared with release `2c561caaefa737be987e66ca7aad77bc57323196`, source
`03af7c6d90e69d7465950d373b19603a1285d3be` measures 573 unresolved calls instead
of 569. The complete added set belongs to `archkeel.render.html._target_dependency_ranks`:

| Expression | Line(s) in `src/archkeel/render/html.py` | Added calls |
|---|---|---|
| `sorter.prepare` | 1699 | 1 |
| `sorter.get_ready` | 1703, 1710 | 2 |
| `sorter.done` | 1709 | 1 |

Measured source SHA-256:
`74db0df0169965b3b517111409b51418f57dc0fe0b3abc516adfe87d2c18f90b`.
No other added unresolved calls remain. The UNKNOWN ceiling stays 40;
`declared_rules` remains UNKNOWN. No violation budget or analyzer behavior changes.

The baseline ceiling changes manually from 569 to 573. The accompanying amendment
binds the unchanged recursive comparison digest on both sides. D-self retains the
actual observations; neither the amendment nor successful validation proves full
call resolution or architectural PASS.

Check: target DAG/cycle/dependent tests, the self-report tests, and
`archkeel validate --root . --baseline architecture-baseline.json --against
2c561caaefa737be987e66ca7aad77bc57323196 --amendment
docs/architecture/decisions/ad-126-ranking-budget-amendment.json --json`.
