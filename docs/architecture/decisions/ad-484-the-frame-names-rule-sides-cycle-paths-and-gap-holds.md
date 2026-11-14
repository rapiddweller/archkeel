# AD-484 The frame names rule sides, cycle paths and gap holds

**Status.** Proposed. Part of #880. It adds a part to the frame of AD-388 and extends AD-464.

**Decision.** The engine frame has a new key `explain` (version 1). It is additive: each other key
keeps its bytes. It is always present. The shell decodes it strictly (`core_explain.py`).
1. `rules`: for each rule of the contract, its `kind`, its `direction` (`forbids`, `allows`,
   `requires`, `isolates`, `orders`, `acyclic` or `none`) and the component ids of its `source` and
   `target`. `archkeel_model::shape` reads them from the contract. A selector selects a component
   that holds a package or module below it, or below which it lies. A kind with no side has `none`.
2. `cycles`: for each rule with a cycle violation, one closed ordered path for each cycle. The model
   finds it (`cycle_path`): the shortest path through the first member, a tie to the smaller name.
   A step has `from`, `to`, the owner component ids, the number of imports and up to 5 evidence ids
   (the frame `locations` give file and line). `index` is the row of `details`.
3. `holds`: for each rule without a verdict, the reason as typed data (`kind`, `cause`), the gap ids
   and the `pairs` that hold it; for each coverage gap that holds a rule, the rule ids. The gap ids come
   from `Graph::coverage_gaps`. A rule holds the gaps that its own `Reason` names: the report copies
   them. `Held` now keeps each pair, and `holds_run` is the filter of `coverage::incomplete`.
4. Budgets, in `explain.budgets`: 50 cycles for a rule, 64 steps for a path, 5 evidence ids for a step,
   20 gaps or pairs for a rule, 200 rules for a gap, 500 gaps. A list over its budget keeps its first
   rows, sets `truncated` and keeps the exact `total`.
5. The part decides nothing. No status, exit code, gap or other key changes.

**Reason.** A page needs to draw a rule on the component map, to show the cycle as a ring and to
tell which gap blocks which rule. Before, it had to parse rule text, sort members into a guessed
order and guess the link between a gap and a rule.

**Rejected.** A path in the report crate: it would compute a fact there. A recount of the holds
from the facts: a second decision path. A new request flag: the part is small (4 to 168 KB).

**Limits.** The path is one witness, not each cycle of the set. A rule held by a cause with no gap
(`kind: other`) lists no gap. An import that no gap names counts in `unnamed_imports`. `holds.gaps`
lists the gaps that hold a rule; `gaps_total` counts all. Symbols and calls are not in this part.

**Tests.** `tests/test_cli_report_explain.py` (the core self run: 7 closed paths; the shell run: the
sides of 22 rules; an UNKNOWN fixture: gap to rule and rule to gap). `closed_path_tests.rs`.
