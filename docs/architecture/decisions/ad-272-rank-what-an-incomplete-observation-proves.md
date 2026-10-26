# AD-272 Rank what an incomplete observation proves

**Decision.** This amends AD-258. A report ranks every finding that one piece of evidence proves,
also when the observation is incomplete. It ranks no finding that needs a complete observation.
One function decides the state, and the terminal, the HTML and the JSON all read it.

| Kind | Claim | On an incomplete observation |
|---|---|---|
| violation | one import site breaks a rule | ranked, if its trace is complete (`trace_valid_violations`) |
| module cycle, package cycle | the observed imports form a loop | ranked |
| hub (fan-in, fan-out) | a count; a missing import lowers it | not ranked |
| budget, other kinds | a count or a ratio | not ranked |

A claim of absence ("no violation", "no cycle", "no hub") is never made on an incomplete
observation.

**States.** One pure function `findings_state(result)` returns one of six values: `COMPLETE`,
`PARTIAL`, `NOT_RANKED`, `NO_OBSERVATION`, `FILTERED`, `NONE_RECORDED`. One function
`findings_note(result)` gives the sentence for each state. The terminal, the HTML and the JSON read
both, and no render tests `findings is None`. The result schema stays 11.0: an empty list is
measured empty, and absent is not ranked. The states, the sentences, the path as a diagram and the
17 equivalence classes are in [findings-path.md](../findings-path.md).

**Proof predicates, one source each.** A violation is proven by `trace_valid_violations` (the
predicate that already turns `declared_rules` to FAIL on a partial observation). A cycle is
proven when every step has an import site.

**Reason.** Tung reviewed the Compass report (forbidden-edge variant, 30 coverage failures). The
header said FAIL, the Explorer showed "Findings · 1", and the page said "No ranked findings are
recorded in this result." Two lists carry the word "findings", and only the graph list is filled on
an incomplete observation. AD-258 does not say that a partial observation ranks nothing; that
sentence is in a docstring only.

**Change field (AD-258 slice 2).** A comparison of two revisions covers only the kinds that both
revisions rank.

**Rejected.**
- Rank only violations. On the Compass project variant that hides two module cycles and one
  package cycle. The cycle `main.dart` and `main_development.dart` is real (`lib/main.dart:9`,
  `lib/main_development.dart:10`). A `source_resolution_gap` is an unresolved import; it does not
  make a resolved import wrong.
- Rank hubs with "at least": the order is the point of the list, and a lower bound can mislead it.
- A new result field: the reason is already in `observation_complete`, `coverage` and `report_filter`.
- Keep `None` and change the text only: the violation stays hidden.
- Remove the second build of `architecture_report` now: 3 % on EE, below the 10 % rule.

**Check.**
- Each class C1 to C17 has a test on the terminal, the HTML and the JSON, from one table.
- A drift test fails when `findings-path.md` and the test table differ.
- Compass forbidden-edge lists the violation and both cycles with the `PARTIAL` sentence; the
  project variant lists the two cycles.
- A complete observation gives the same list and the same bytes as before.
- `findings_state` is tested over every combination of observation, proven violation, cycle, hub
  and filter, and gives one state each.
