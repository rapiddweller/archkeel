# AD-51 A result carries its violations grouped by rule and by crossed component pair

`ir.decisions.violation_counts` derives `ViolationCounts` from one observation:
`by_rule` includes nonzero rule counts; `by_component_pair` includes ordered
component pairs crossed by import violations. Sort by descending count, then name.
`report` and `validate`, including rejected runs, carry both beside the unchanged
`violations` total.

Downstream refactoring had required decoding 25,000 internal rows for this breakdown.
Derive it once ([AD-35](ad-35-every-review-claim-is-counted-on-the-run-result-so-the.md)).
Use explicit `source_module` and `target_module`, not sorted subjects, which would
reverse `DEP-STORE-NO-MONEY` from `store -> model` to `model -> store`.

Constructs, unassigned modules, cycles and imports to unowned targets appear only
by rule. Pair counts therefore need not sum to the total. Zero rules already live
in the contract; a separate per-component total would duplicate derivable data.
Check: `tests/test_decisions.py::test_violation_counts_group_the_report_by_rule_and_by_crossing_pair`
pins tour counts against the reported records.
