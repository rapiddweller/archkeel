# AD-51 A result carries its violations grouped by rule and by crossed component pair


`ir.decisions.violation_counts` reads one observation's violation records and returns
`ViolationCounts`: `by_rule`, every rule id with at least one violation, and
`by_component_pair`, every ordered pair of components an import violation crosses, both
heaviest first and then alphabetical. `report` and `validate` carry them as
`violations_by_rule` and `violations_by_component_pair`, beside the `violations` scalar,
which keeps its meaning. Reason: measuring a refactoring needs one data point per change,
per rule and per component, and the only way to get it was to decode `architecture.json`
with the internal codec and count 25,000 rows, which is what a downstream repository did.
Deriving it from the records the result already carries makes the breakdown and the total
incapable of disagreeing. The pair comes from each record's `source_module` and
`target_module`, never from the position of a subject: `classified` sorts subjects, so
`DEP-STORE-NO-MONEY` would otherwise read as `model -> store` instead of `store -> model`.
A rejected `validate` run carries the counts too, because that is the run whose numbers a
gate reads. Rejected: listing every rule including those at zero was rejected because the
contract already lists them, while this answers what remains; counting a second time in the
renderer was rejected for the same reason `review_claims` is derived once ([AD-35](ad-35-every-review-claim-is-counted-on-the-run-result-so-the.md)); a
per-component total beside the pairs was rejected as the sum of pairs plus what crosses no
pair, both already present. Limit: a violation that names no import, such as a construct, an
unassigned module or a cycle, crosses no pair and appears only under `by_rule`, so the pair
counts sum to less than the total; an import whose target module no component owns, such as
an external dependency, is counted by rule alone as well. Check:
`tests/test_decisions.py`'s
`test_violation_counts_group_the_report_by_rule_and_by_crossing_pair`, which pins both
breakdowns for the demo tour and that they come from the same records the result reports.

