# AD-1041 A held rule counts module pairs and says how many it shows

**Decision.** The reason of a rule that module pairs hold names the unit: "N module pairs
with gaps that the contract does not allow". A gap record is one entry of the collection gaps.
A pair can have several records. The reason counts distinct pairs. When the records are more
than the pairs, it adds "(from N gap records)", so each number keeps its own noun. A list that the reason cuts says
"(showing 5)" and ends with "and M more pairs". The HTML report uses the same words.
The field `total` of `explain.holds.rules.<RULE>` counts pairs for a pair rule. Its schema
description says so. The core and the verdicts do not change.

**Reason.** On the self-scan one rule said "11997 gaps" while the scan has 18393 gap records.
A reader took both numbers as the same unit. On the self-scan each record has its own pair, so
the run says "18393 module pairs" and no record count. Another scan can have more records than pairs. The cut list said only "and 11992 more".

**Alternatives.** Rename the JSON field: this changes the frame protocol for a wording problem.
Count records in the reason: a record is a site, not the edge that the rule reads.

**Limit.** The frame keeps at most 20 pairs for each rule, so the text cannot list all pairs.
The frame has no typed cause of a pair (derive, written impl, destructor, receiver): the gap
record carries only its reason text. A tally by cause needs that typed field in the collector
reply. This record does not add it.

**Checks.** `causes_tests.rs` checks the words of a cut and a complete list. The report tests
check the HTML titles. `tests/test_cli_native_rust_interface.py` checks the text of a real run.
