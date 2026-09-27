# AD-117 Report verdicts require evaluator evidence

An empty finding list does not prove a rule ran (#159, #160).

The analyzer records each supported evaluator's actual scope and selected facts. The report
projects those receipts, violations and shared UNKNOWN counts into typed rule rows. No receipt
means UNKNOWN, not PASS. Permissions remain declarations. A failed rule retains its undecided
positions; filtering UNKNOWN includes that mixed result without hiding its failure.

An explicit, read-only baseline reuses the existing fingerprints, occurrence counts and cycle
contraction logic. It never changes the observation or overall verdict. Resolution requires
complete evaluation of the old subjects under the current rule, with no undecided positions.
Narrowing a rule or scan cannot resolve debt outside that scope. Cycle contraction also needs
coverage of the old cycle's members. A package's own receipt does not cover omitted descendants.
Repeated occurrences share a group count; no individual line is labelled as already known.

Resolved means absent under currently evaluated rules, not proof that code was repaired.
Baselines do not store historical rule definitions. Use `validate --against` to check contract
widening; the report does not introduce a second history system.

Keep the diagram primary. Reuse native tables, details and filters; no second report framework.
Focused CLI views remain focused. Without JavaScript, all static evidence stays readable.
